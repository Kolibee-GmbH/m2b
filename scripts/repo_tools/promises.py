"""Runs the regression of what m2b promises and says per promise whether it holds.

``docs/promises.md`` holds the catalog: one table row per promise, whether it is compared against
Claude Code alone, and its cases. A case is a model-level scenario (``tests/e2e/<name>/model.json``)
or an eval case (``plugins/m2b/evals/<name>``); three eval cases joined by `` / `` are one case in
three wordings, since an eval case has one prompt. The second and third wording of a suite case
live in ``plugins/m2b/evals-wordings/``, apart from the suite, which ``docs/evals.md`` reports
whole from one run of it. Every case runs three times with m2b, each from a
fresh start, and three times without m2b where the promise is compared. A case holds when all three
runs with m2b pass and, where compared, at most one without; a case that starts Claude Code needs
three wordings of what the owner says, one in German, so that no promise rests on one sentence.

Scenarios run through ``e2e.run_scenario`` at the model level, so every session has the scenario's
own Claude Code folder and the subscription's token; eval cases run through ``claude plugin eval``
with a Claude Code folder of their own too. Without an account the command stops before the first
run, and a session that says it is not logged in ends it; neither is reported as a broken promise.
What the report shows passes through ``e2e.redacted``, so the token never stands in it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from repo_tools import REPO_ROOT, e2e
from repo_tools.evals_page import REPORT_NAME, model_of_run

CATALOG = REPO_ROOT / "docs" / "promises.md"
EVALS = e2e.CORE_PLUGIN / "evals"
WORDING_EVALS = e2e.CORE_PLUGIN / "evals-wordings"
SCENARIO = "scenario"
EVAL = "eval"
RUNS = 3
COMPARED = "compared"
NOT_COMPARED = "not compared"
OPEN_CELL = "open"
WORDING_SEPARATOR = " / "
# The tools the eval cases call; a run asks nobody, so each is granted (CONTRIBUTING, "Evals").
EVAL_TOOLS = ("mcp__m2b__search", "mcp__m2b__note", "mcp__m2b__propose", "Write", "Read", "Edit", "Bash")
EVAL_TIMEOUT_SECONDS = 1800
DEFAULT_MAX_MINUTES = 180

HELD = "held"
UNSTEADY = "unsteady"
BROKEN = "broken"
NO_DIFFERENCE = "no difference"
WORDINGS = "too few wordings"
OPEN = "open"
INCOMPLETE = "incomplete"
# The order a promise takes the worst verdict of its cases in.
WORST_FIRST = (BROKEN, UNSTEADY, NO_DIFFERENCE, WORDINGS, INCOMPLETE)
PASSED_MARK = "✓"
FAILED_MARK = "✗"
SHOWS_NOTHING_MARK = "\u25cb"

EXIT_HELD = 0
EXIT_NOT_HELD = 1
EXIT_USAGE = 2

_ROW = re.compile(r"^\|\s*(\d+)\s*\|([^|]*)\|([^|]*)\|([^|]*)\|")
_NAME = re.compile(r"`([^`]+)`")


class CatalogError(Exception):
    """The catalog cannot be read as promises with their cases; the message says where."""


@dataclass(frozen=True)
class Case:
    """One scenario, one eval case, or three eval cases that are one case in three wordings."""

    names: tuple[str, ...]
    kind: str

    @property
    def label(self) -> str:
        return WORDING_SEPARATOR.join(self.names)


@dataclass(frozen=True)
class Promise:
    number: int
    text: str
    compared: bool
    cases: tuple[Case, ...]


@dataclass(frozen=True)
class Run:
    passed: bool
    evidence: str = ""
    models: tuple[str, ...] = ()
    # False for a run that shows nothing, in either arm: the command's time ran out before it, or a
    # step marked as its control failed, so Claude Code alone never did what the comparison needs.
    shows: bool = True


@dataclass
class CaseResult:
    case: Case
    with_m2b: list[Run]
    without_m2b: list[Run]
    # Why the case's wordings cannot hold a promise, or None.
    wording_problem: str | None

    def verdict(self, compared: bool) -> str:
        # A run without m2b that shows nothing would read as Claude Code alone failing.
        if not all(run.shows for run in [*self.with_m2b, *self.without_m2b]):
            return INCOMPLETE
        passed = sum(run.passed for run in self.with_m2b)
        if passed == 0:
            return BROKEN
        if passed < len(self.with_m2b) or len(self.with_m2b) < RUNS:
            return UNSTEADY
        if compared and sum(run.passed for run in self.without_m2b) > 1:
            return NO_DIFFERENCE
        if self.wording_problem:
            return WORDINGS
        return HELD


ScenarioRunner = Callable[[Path, int, str], Run]
EvalRunner = Callable[[str, int, bool], "tuple[list[Run], list[Run]]"]


@dataclass(frozen=True)
class Runners:
    scenario: ScenarioRunner
    evals: EvalRunner


@dataclass(frozen=True)
class Versions:
    claude_code: str
    models: tuple[str, ...]
    m2b_commit: str


def read_catalog(catalog: Path, scenarios: Path, evals: Sequence[Path]) -> list[Promise]:
    """The promises of the catalog's table, each case checked to exist as a scenario with a
    ``model.json`` or an eval case."""
    try:
        lines = catalog.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise CatalogError(f"cannot read {catalog}: {error}") from error
    read = []
    for line in lines:
        row = _ROW.match(line)
        if row is None:
            continue
        number, text, comparison, cases = (part.strip() for part in row.groups())
        if comparison not in (COMPARED, NOT_COMPARED):
            raise CatalogError(f"promise {number}: say {COMPARED!r} or {NOT_COMPARED!r}, not {comparison!r}")
        read.append(Promise(int(number), text, comparison == COMPARED, _cases(number, cases, scenarios, evals)))
    if not read:
        raise CatalogError(f"{catalog} holds no table of promises")
    return read


def _cases(number: str, cell: str, scenarios: Path, evals: Sequence[Path]) -> tuple[Case, ...]:
    if cell == OPEN_CELL:
        return ()
    cases = []
    for part in cell.split(","):
        names = tuple(_NAME.findall(part))
        if not names:
            raise CatalogError(f"promise {number}: a case is a name in backticks, got {part.strip()!r}")
        kinds = {_kind(number, name, scenarios, evals) for name in names}
        if len(names) > 1 and (len(names) != RUNS or kinds != {EVAL}):
            raise CatalogError(f"promise {number}: a case in wordings is three eval cases, got {part.strip()!r}")
        cases.append(Case(names, kinds.pop()))
    return tuple(cases)


def _kind(number: str, name: str, scenarios: Path, evals: Sequence[Path]) -> str:
    if (scenarios / name / e2e.MODEL_FILE).is_file():
        return SCENARIO
    if eval_folder(name, evals) is not None:
        return EVAL
    raise CatalogError(f"promise {number}: {name} is neither a scenario with a {e2e.MODEL_FILE} nor an eval case")


def eval_folder(name: str, evals: Sequence[Path]) -> Path | None:
    """The folder of eval cases that holds the case ``name``, or None."""
    return next((folder for folder in evals if (folder / name).is_dir()), None)


def run_case(
    case: Case, compared: bool, scenarios: Path, runners: Runners, deadline: float | None = None
) -> CaseResult:
    """Every run of one case: three with m2b and, where compared, three without."""
    arms = (e2e.WITH, e2e.WITHOUT) if compared else (e2e.WITH,)
    if case.kind == SCENARIO:
        folder = scenarios / case.names[0]
        problem = e2e.wording_problem(json.loads((folder / e2e.MODEL_FILE).read_text(encoding="utf-8")))
        runs: dict[str, list[Run]] = {}
        for arm in arms:
            runs[arm] = [_scenario_run(runners, folder, wording, arm, deadline) for wording in range(RUNS)]
        return CaseResult(case, runs[e2e.WITH], runs.get(e2e.WITHOUT, []), problem)
    with_m2b: list[Run] = []
    without: list[Run] = []
    per_name = RUNS // len(case.names)
    for name in case.names:
        if deadline is not None and time.monotonic() > deadline:
            with_m2b += [_out_of_time()] * per_name
            without += [_out_of_time()] * (per_name if compared else 0)
            continue
        ran_with, ran_without = runners.evals(name, per_name, compared)
        with_m2b += ran_with
        without += ran_without
    problem = None if len(case.names) == RUNS else "an eval case alone is one wording"
    return CaseResult(case, with_m2b, without, problem)


def _scenario_run(runners: Runners, folder: Path, wording: int, arm: str, deadline: float | None) -> Run:
    if deadline is not None and time.monotonic() > deadline:
        return _out_of_time()
    return runners.scenario(folder, wording, arm)


def _out_of_time() -> Run:
    return Run(False, "not run: the command's time ran out", shows=False)


def promise_verdict(promise: Promise, results: Sequence[CaseResult]) -> str:
    if not promise.cases:
        return OPEN
    verdicts = {result.verdict(promise.compared) for result in results}
    return next((verdict for verdict in WORST_FIRST if verdict in verdicts), HELD)


def report(results: Sequence[tuple[Promise, Sequence[CaseResult]]], versions: Versions) -> str:
    lines = []
    broke = []
    held = 0
    for promise, case_results in results:
        verdict = promise_verdict(promise, case_results)
        held += verdict == HELD
        lines.append(f"{promise.number} {verdict:<17} {promise.text}")
        for result in case_results:
            arms = f"with {_marks(result.with_m2b)}"
            if promise.compared:
                arms += f"  without {_marks(result.without_m2b)}"
            note = f"  ({result.wording_problem})" if result.wording_problem else ""
            lines.append(f"    {result.case.label}  {arms}{note}")
            broke += _what_broke(result)
    lines.insert(0, f"promises: {held} of {len(results)} promises held")
    if broke:
        lines += ["", "What broke:", *(f"  {item}" for item in broke)]
    models = ", ".join(versions.models) or "none"
    lines += ["", f"Claude Code {versions.claude_code} · models {models} · m2b {versions.m2b_commit}"]
    return "\n".join(lines) + "\n"


def _marks(runs: Sequence[Run]) -> str:
    return "".join(_mark(run) for run in runs) or "-"


def _mark(run: Run) -> str:
    if not run.shows:
        return SHOWS_NOTHING_MARK
    return PASSED_MARK if run.passed else FAILED_MARK


def _what_broke(result: CaseResult) -> list[str]:
    worded = result.case.kind == SCENARIO or len(result.case.names) == RUNS
    found = []
    for arm, runs in (("with m2b", result.with_m2b), ("without m2b", result.without_m2b)):
        for number, run in enumerate(runs, 1):
            if run.passed if arm == "with m2b" else run.shows:
                continue
            wording = f" (wording {number})" if worded else ""
            found.append(f"{result.case.label} {arm}, run {number}{wording}: {run.evidence or 'no detail'}")
    return found


def scenario_runner(
    environ: Mapping[str, str], account: Mapping[str, str], sandbox_root: Path | None
) -> ScenarioRunner:
    def run(folder: Path, wording: int, arm: str) -> Run:
        result = e2e.run_scenario(
            folder, environ, level=e2e.MODEL, sandbox_root=sandbox_root, account=account, wording=wording, arm=arm
        )
        evidence = "; ".join(result.problems)
        if not result.shows:
            evidence = f"its control did not pass, so the run shows nothing: {evidence}"
        return Run(result.passed, evidence, tuple(result.models), shows=result.shows)

    return run


def eval_command(name: str, runs: int, compared: bool, output: Path, eval_dir: str = EVALS.name) -> list[str]:
    return [
        "claude",
        "plugin",
        "eval",
        ".",
        "--eval-dir",
        eval_dir,
        "--case",
        name,
        "--runs",
        str(runs),
        "--ablation",
        "with-without" if compared else "none",
        "--scaffold",
        "--trust-plugin",
        "--no-publish",
        "--keep-temp",
        "--threshold",
        "0",
        "--output-dir",
        str(output),
        "--allow-tools",
        *EVAL_TOOLS,
    ]


def runs_in_eval_report(output: Path, name: str) -> tuple[list[Run], list[Run]]:
    """The runs of the case with m2b and without, from the report ``claude plugin eval`` wrote."""
    raw = json.loads((output / REPORT_NAME).read_text(encoding="utf-8"))
    for case in raw.get("cases", []):
        if case.get("name") == name:
            arms = case.get("arms", {})
            return [_eval_run(run) for run in arms.get("with", [])], [_eval_run(run) for run in arms.get("without", [])]
    raise ValueError(f"the eval report has no case {name}")


def _eval_run(run: Mapping[str, object]) -> Run:
    model = model_of_run(run)
    evidence = "" if run.get("passed") is True else str(run.get("error") or "a grader did not pass")
    return Run(run.get("passed") is True, evidence, (model,) if model else ())


def claude_eval_runner(
    environ: Mapping[str, str], account: Mapping[str, str], plugin: Path = e2e.CORE_PLUGIN
) -> EvalRunner:
    def run(name: str, runs: int, compared: bool) -> tuple[list[Run], list[Run]]:
        folder_of_case = eval_folder(name, (EVALS, WORDING_EVALS)) or EVALS
        with tempfile.TemporaryDirectory(prefix=f"{e2e.TEST_RESOURCE_PREFIX}promises-") as folder:
            claude_config = Path(folder) / e2e.SANDBOX_CLAUDE
            e2e.prepare_claude_config(claude_config, account)
            environment = e2e.model_environment(environ, account, claude_config)
            output = Path(folder) / "report"
            try:
                done = subprocess.run(
                    eval_command(name, runs, compared, output, folder_of_case.name),
                    cwd=plugin,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=EVAL_TIMEOUT_SECONDS,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                failed = Run(False, f"claude plugin eval could not run: {error}")
                return [failed] * runs, [failed] * runs if compared else []
            said = e2e.redacted(done.stdout + done.stderr, account)
            if any(sign in said for sign in e2e.NOT_LOGGED_IN):
                raise e2e.NotLoggedInError(said[-400:])
            try:
                return runs_in_eval_report(output, name)
            except (OSError, ValueError) as error:
                failed = Run(False, f"no eval report ({error}); it said: {said.strip()[-400:]}")
                return [failed] * runs, [failed] * runs if compared else []

    return run


def versions(models: Sequence[str]) -> Versions:
    """The Claude Code version, the models the runs answered with and the commit m2b ran on."""
    return Versions(_output(["claude", "--version"]).split(" ")[0], tuple(sorted(set(models))), _commit())


def _commit() -> str:
    commit = _output(["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"])
    changed = _output(["git", "-C", str(REPO_ROOT), "status", "--porcelain"])
    return f"{commit} with changes not committed" if changed else commit


def _output(command: Sequence[str]) -> str:
    try:
        return subprocess.run(list(command), capture_output=True, text=True, timeout=60).stdout.strip() or "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def _parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="promises", description=__doc__.split("\n", 1)[0])
    parser.add_argument("numbers", nargs="*", type=int, help="the promises to run (default: all)")
    parser.add_argument(
        "--use-api-key", action="store_true", help=f"run with {e2e.API_KEY_VARIABLE}, billed per run, not the token"
    )
    parser.add_argument(
        "--max-minutes",
        type=float,
        default=DEFAULT_MAX_MINUTES,
        help="start no run after this many minutes; a run not started does not pass",
    )
    parser.add_argument("--sandbox-root", type=Path, help="where the temporary scenario folders go")
    parser.add_argument("--catalog", type=Path, default=CATALOG, help=argparse.SUPPRESS)
    parser.add_argument("--scenarios", type=Path, default=e2e.SCENARIO_ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--evals", type=Path, nargs="+", default=[EVALS, WORDING_EVALS], help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None, eval_runner: EvalRunner | None = None) -> int:
    """``eval_runner`` stands in for ``claude plugin eval`` in a test."""
    arguments = _parse_arguments(sys.argv[1:] if argv is None else argv)
    try:
        catalog = read_catalog(arguments.catalog, arguments.scenarios, arguments.evals)
        known = {promise.number for promise in catalog}
        unknown = sorted(set(arguments.numbers) - known)
        if unknown:
            raise CatalogError(f"the catalog has no promise {', '.join(map(str, unknown))}")
        account = e2e.model_account(os.environ, arguments.use_api_key)
    except (CatalogError, e2e.NoAccountError) as error:
        print(f"promises: {error}", file=sys.stderr)
        return EXIT_USAGE
    runners = Runners(
        scenario_runner(os.environ, account, arguments.sandbox_root),
        eval_runner or claude_eval_runner(os.environ, account),
    )
    deadline = time.monotonic() + arguments.max_minutes * 60
    chosen = [promise for promise in catalog if not arguments.numbers or promise.number in arguments.numbers]
    results: list[tuple[Promise, list[CaseResult]]] = []
    try:
        for promise in chosen:
            case_results = [
                run_case(case, promise.compared, arguments.scenarios, runners, deadline) for case in promise.cases
            ]
            results.append((promise, case_results))
    except e2e.NotLoggedInError as error:
        said = e2e.redacted(str(error), account)
        print(f"promises: Claude Code is not logged in ({said}); {e2e.HOW_TO_ADD_A_TOKEN}", file=sys.stderr)
        return EXIT_USAGE
    except e2e.RealStoreError as error:
        print(f"promises: {error}", file=sys.stderr)
        return EXIT_USAGE
    models = [
        model
        for _, case_results in results
        for result in case_results
        for run in [*result.with_m2b, *result.without_m2b]
        for model in run.models
    ]
    print(e2e.redacted(report(results, versions(models)), account), end="")
    every_held = all(promise_verdict(promise, case_results) == HELD for promise, case_results in results)
    return EXIT_HELD if every_held else EXIT_NOT_HELD


if __name__ == "__main__":
    sys.exit(main())
