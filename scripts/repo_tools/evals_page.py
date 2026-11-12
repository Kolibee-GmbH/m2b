"""Writes the results of an eval run into ``docs/evals.md``.

``claude plugin eval`` leaves its report, ``aggregate-result.json``, in a folder git ignores, so
without this the scores a release was checked with would stand nowhere. ``scripts/evals-page``
reads the newest report, or the one named, and replaces the part of the page between two marker
comments: the facts of the run and one row per case with its score with and without m2b. The
prose around the markers is written by hand and stays as it is.

The report does not say which model answered. Each run's trace does, in the line that starts the
session, so the suite has to run with ``--keep-temp`` and the page be written while the kept
folders are still there.

A report whose numbers would mislead is refused and the page left alone: a run that stopped
early, one without the arm without m2b, one that covers other cases than the suite has (a run
with ``--case``), one with fewer runs of a case than the case asks for (a run with ``--runs``),
and one in another schema than this was written for.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from repo_tools import REPO_ROOT

EVALS = REPO_ROOT / "plugins" / "m2b" / "evals"
PAGE = REPO_ROOT / "docs" / "evals.md"
REPORT_NAME = "aggregate-result.json"
BLOCK_START = "<!-- results: written by scripts/evals-page from an eval report, not by hand -->"
BLOCK_END = "<!-- /results -->"

PLUGIN_NAME = "m2b"
KNOWN_SCHEMA = 1
BOTH_ARMS = "with-without"
# What `claude plugin eval` runs a case, per arm, whose prompt.md names no number.
DEFAULT_RUNS = 3
RUNS_LINE = re.compile(r"^runs:\s*(\d+)\s*$", re.MULTILINE)

EXIT_WRITTEN = 0
EXIT_REFUSED = 2


class EvalsPageError(Exception):
    """The report cannot go on the page; the message says why."""


@dataclass(frozen=True)
class Arm:
    """One case's runs with m2b, or its runs without."""

    score: float
    passed: int
    runs: int
    errors: int


@dataclass(frozen=True)
class Case:
    name: str
    with_m2b: Arm
    without_m2b: Arm


@dataclass(frozen=True)
class EvalRun:
    day: date
    m2b_version: str
    claude_code_version: str
    models: tuple[str, ...]
    cases: tuple[Case, ...]


def suite_cases(evals: Path) -> dict[str, int]:
    """Each case of the suite, with the runs per arm its ``prompt.md`` asks for."""
    return {
        case_file.parent.name: _runs_asked_for(case_file.parent / "prompt.md")
        for case_file in sorted(evals.glob("*/case.yaml"))
    }


def newest_report(results: Path) -> Path:
    """The report in the latest of the folders ``claude plugin eval`` names by their start time."""
    reports = sorted(results.glob(f"*/{REPORT_NAME}"))
    if not reports:
        raise EvalsPageError(f"no report under {results}: run the evals first")
    return reports[-1]


def read_run(report: Path, suite: Mapping[str, int]) -> EvalRun:
    try:
        raw = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise EvalsPageError(f"cannot read {report}: {error}") from error
    if not isinstance(raw, dict) or raw.get("schemaVersion") != KNOWN_SCHEMA:
        raise EvalsPageError(f"{report} is not an eval report of schema version {KNOWN_SCHEMA}")
    if raw.get("partial") is not False:
        raise EvalsPageError("the run stopped early, so its scores cover only a part of the runs")
    suite_record = _record(raw, "suite")
    if suite_record.get("ablation") != BOTH_ARMS:
        raise EvalsPageError(f"the run has no arm without {PLUGIN_NAME}: run the evals with --ablation {BOTH_ARMS}")

    case_records = _records(raw, "cases")
    _refuse_other_cases([_text(record, "name") for record in case_records], suite)
    models: set[str] = set()
    cases = [_case(record, suite, models) for record in case_records]
    try:
        day = date.fromisoformat(_text(raw, "startedAt")[:10])
    except ValueError as error:
        raise EvalsPageError(f"the report's startedAt is not a time: {error}") from error
    return EvalRun(
        day=day,
        m2b_version=_plugin_version(suite_record),
        claude_code_version=_text(raw, "claudeVersion"),
        models=tuple(sorted(models)),
        cases=tuple(sorted(cases, key=lambda case: case.name)),
    )


def results_block(run: EvalRun) -> str:
    arms = [arm for case in run.cases for arm in (case.with_m2b, case.without_m2b)]
    runs = str(sum(arm.runs for arm in arms))
    errors = sum(arm.errors for arm in arms)
    if errors:
        runs += f", of which {errors} ended in an error and count as failed"
    facts = [
        ("Day", run.day.isoformat()),
        (PLUGIN_NAME, run.m2b_version),
        ("Claude Code", run.claude_code_version),
        ("Model", ", ".join(f"`{model}`" for model in run.models)),
        ("Runs", runs),
    ]
    lines = [
        BLOCK_START,
        "",
        "| | |",
        "|---|---|",
        *(f"| {name} | {value} |" for name, value in facts),
        "",
        f"| Case | With {PLUGIN_NAME} | Without {PLUGIN_NAME} |",
        "|---|---|---|",
        *(f"| `{case.name}` | {_cell(case.with_m2b)} | {_cell(case.without_m2b)} |" for case in run.cases),
        "",
        BLOCK_END,
    ]
    return "\n".join(lines)


def replace_results(page: str, block: str) -> str:
    before, start, rest = page.partition(BLOCK_START)
    _, end, after = rest.partition(BLOCK_END)
    if not start or not end or BLOCK_START in before + after or BLOCK_END in before + after:
        raise EvalsPageError(f"the page needs one {BLOCK_START} and one {BLOCK_END} after it")
    return before + block + after


def _refuse_other_cases(reported: Sequence[str], suite: Mapping[str, int]) -> None:
    missing = sorted(set(suite) - set(reported))
    unknown = sorted(set(reported) - set(suite))
    if missing:
        raise EvalsPageError(f"the run leaves out cases of the suite: {', '.join(missing)}")
    if unknown or len(set(reported)) != len(reported):
        raise EvalsPageError(f"the run's cases are not the suite's: {', '.join(unknown or reported)}")


def _case(record: Mapping[str, Any], suite: Mapping[str, int], models: set[str]) -> Case:
    name = _text(record, "name")
    arms = _record(record, "arms")
    scores = _record(record, "aggregates")
    return Case(
        name=name,
        with_m2b=_arm(name, _number(scores, "score"), _asked_runs(name, arms, "with", suite), models),
        without_m2b=_arm(name, _number(scores, "scoreWithout"), _asked_runs(name, arms, "without", suite), models),
    )


def _asked_runs(case: str, arms: Mapping[str, Any], arm: str, suite: Mapping[str, int]) -> list[Mapping[str, Any]]:
    runs = _records(arms, arm)
    asked = max(suite[case], 1)
    if len(runs) < asked:
        raise EvalsPageError(
            f"the case {case} has {len(runs)} runs {arm} {PLUGIN_NAME} and asks for {asked}: "
            "run the evals without --runs"
        )
    return runs


def _arm(case: str, score: float, runs: Sequence[Mapping[str, Any]], models: set[str]) -> Arm:
    errors = 0
    for run in runs:
        model = _model(run)
        if model is not None:
            models.add(model)
        elif run.get("error") is None:
            raise EvalsPageError(
                f"a run of {case} has no trace that names its model ({run.get('tracePath')}): "
                "run the evals with --keep-temp and write the page before the kept folders are cleared"
            )
        errors += run.get("error") is not None
    return Arm(score=score, passed=sum(run.get("passed") is True for run in runs), runs=len(runs), errors=errors)


def _model(run: Mapping[str, Any]) -> str | None:
    """The model of the session a run started, from the trace Claude Code wrote for it."""
    trace = run.get("tracePath")
    if not isinstance(trace, str):
        return None
    try:
        lines = Path(trace).read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return None
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "system" and event.get("subtype") == "init":
            model = event.get("model")
            return model if isinstance(model, str) and model else None
    return None


def _runs_asked_for(prompt: Path) -> int:
    try:
        front_matter = prompt.read_text(encoding="utf-8").partition("\n---")[0]
    except OSError:
        return DEFAULT_RUNS
    asked = RUNS_LINE.search(front_matter)
    return int(asked.group(1)) if asked else DEFAULT_RUNS


def _plugin_version(suite_record: Mapping[str, Any]) -> str:
    for plugin in _records(suite_record, "plugins"):
        if plugin.get("name") == PLUGIN_NAME:
            return _text(plugin, "version")
    raise EvalsPageError(f"the run did not load {PLUGIN_NAME}")


def _cell(arm: Arm) -> str:
    return f"{arm.score:.2f} ({arm.passed} of {arm.runs} runs)"


def _record(parent: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise EvalsPageError(f"the report's {key} is missing or not an object")
    return value


def _records(parent: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = parent.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise EvalsPageError(f"the report's {key} is missing or not a list of objects")
    return value


def _text(parent: Mapping[str, Any], key: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value:
        raise EvalsPageError(f"the report's {key} is missing or not a text")
    return value


def _number(parent: Mapping[str, Any], key: str) -> float:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvalsPageError(f"the report's {key} is missing or not a number")
    return float(value)


def _report_file(named: Path | None, evals: Path) -> Path:
    if named is None:
        return newest_report(evals / "results")
    return named / REPORT_NAME if named.is_dir() else named


def _parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="evals-page", description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "report",
        type=Path,
        nargs="?",
        help=f"a report's folder or its {REPORT_NAME}; without it, the newest under the evals' results/",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None, *, evals: Path = EVALS, page: Path = PAGE) -> int:
    arguments = _parse_arguments(sys.argv[1:] if argv is None else argv)
    try:
        report = _report_file(arguments.report, evals)
        run = read_run(report, suite_cases(evals))
        page.write_text(replace_results(page.read_text(encoding="utf-8"), results_block(run)), encoding="utf-8")
    except (OSError, EvalsPageError) as error:
        print(f"evals-page: {error}", file=sys.stderr)
        return EXIT_REFUSED

    print(f"evals-page: {len(run.cases)} cases of the run {report.parent.name} written to {page}")
    for case in run.cases:
        if case.with_m2b.score < 1:
            print(f"evals-page: {case.name} scores {case.with_m2b.score:.2f} with {PLUGIN_NAME}; a release needs 1.00")
    return EXIT_WRITTEN


if __name__ == "__main__":
    sys.exit(main())
