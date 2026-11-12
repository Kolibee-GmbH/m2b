"""Runs end-to-end scenarios, each against its own isolated machine setup and store.

A scenario is a folder under ``tests/e2e/`` with:

- ``given/``: the store before the run (optional, invented content);
- ``transcripts/``: Claude Code's transcripts before the run (optional, invented content), copied to
  ``projects/`` in the scenario's ``CLAUDE_CONFIG_DIR`` below the model level; ``<an-hour-ago>`` in one
  stands for that moment, because a step that reads the sessions takes only recent prompts;
- ``steps.json``: ``{"steps": [{"run": [argv...], "exit": 0, "stdin": "...", "stdout": "<regex>", "env": {...}}]}``;
  ``env`` adds variables for one step, such as ``M2B_CURATION_RUN`` for a curator command the scenario calls
  in the model's place;
  ``stdout``, when given, is a regular expression searched for in the step's standard output.
  ``"save": {"task": "<regex with one group>"}`` keeps the group from the step's output, and a later
  step's ``{task}`` in its arguments is replaced by it (a generated id, for example). ``{core_plugin}``
  is always the core plugin's folder, for a step that starts a Claude Code session with it, and
  ``{store}`` the scenario's store folder, for a step that prepares it with another program
  (``git init``).
  ``"cwd": "<name>"`` runs the step in a folder of that name beside the scenario's working folder,
  made on first use, so two sessions can stand for two projects; without it a step runs in the
  working folder.
  An optional ``"model": {"actions": [...], "outcome": "success"}`` scripts the model: every model
  run of the scenario replays these actions in the stub ``tests/fakes/fake_claude.py``, which
  denies what the step's rules do not allow (the action format is in the stub);
  an add-on a scenario needs is turned on by one of its steps (``m2b addons on worklog``), as setup does,
  and ``--core-only`` leaves such a scenario out;
- ``expect.json``: ``{"store_files": {"<path in store>": "<exact text>"}}`` and, for files
  with generated names (captures, task files), ``"store_patterns": [{"path": "<glob>",
  "content": "<regular expression>"}]``, each matching exactly one file in full. Together they
  are the complete set of visible files in the store afterwards.

Steps run with ``M2B_HOME`` pointing at a fresh temporary folder that holds a
test config, with the core plugin's ``bin/`` first on ``PATH``, and with ``M2B_MODEL_RUNNER``
pointing at the stub, so no scenario starts the real model at this level. At this level
``CLAUDE_CONFIG_DIR``, ``M2B_HERDR``, ``M2B_LAUNCHCTL`` and ``M2B_SYSTEMCTL`` point into the
scenario's folder too, so an add-on never reads the user's own transcripts, asks the user's herdr
or changes the user's timers.

At ``--level model`` only scenarios with a ``model.json`` run: ``{"steps": [...], "invariants":
[...]}``, the steps in the same form but with the real fenced ``claude`` and the user's own login,
and invariants (``check_invariants``) in place of ``expect.json``, because a real model words its
notes its own way. A value a step saved can name a folder outside the store for an invariant, such
as the memory folder Claude Code reports at a session's start.

``--plugin`` names another folder that holds the plugin, in place of this checkout's: the proof
that the core stands without its add-ons runs the scenarios against a copy without them.
"""

from __future__ import annotations

import argparse
import datetime
import fnmatch
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from m2b.config.machine import StoreLocation, parse_machine_config
from m2b.paths import HOME_VARIABLE, MachinePaths, machine_paths

from repo_tools import REPO_ROOT

SCENARIO_ROOT = REPO_ROOT / "tests" / "e2e"
CORE_PLUGIN = REPO_ROOT / "plugins" / "m2b"
# Relative to the plugin's folder.
MODEL_STUB = Path("tests") / "fakes" / "fake_claude.py"
ADDON_ON = ["m2b", "addons", "on"]
MODEL_RUNNER_VARIABLE = "M2B_MODEL_RUNNER"
MODEL_STUB_STORE_VARIABLE = "M2B_STUB_STORE"
TEST_RESOURCE_PREFIX = "sb-test-"
STEP_TIMEOUT_SECONDS = 60
# A real curation run takes two model steps; each is stopped by the product after MODEL_TIMEOUT_MINUTES,
# and the run's whole bound (fetch, both steps with grace, the code steps) stays under the step timeout.
MODEL_TIMEOUT_MINUTES = 5
MODEL_STEP_TIMEOUT_SECONDS = 1800
STUB = "stub"
MODEL = "model"
APPLE = "apple"
INTEGRATION_VARIABLE = "M2B_IT"
MODEL_FILE = "model.json"
TRANSCRIPTS = "transcripts"
AN_HOUR_AGO = "<an-hour-ago>"
RUN_RECORD_PATH = "state/core/last-run.json"

EXIT_PASSED = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_REFUSED = 2


class RealStoreError(Exception):
    """The test setup would touch the user's real store."""


@dataclass
class ScenarioResult:
    name: str
    problems: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.problems


def configured_store(machine: MachinePaths) -> Path | None:
    """The store path a machine's config names, or None when there is no config."""
    if not machine.config_file.is_file():
        return None
    try:
        raw = json.loads(machine.config_file.read_text(encoding="utf-8"))
        return parse_machine_config(raw, machine.home).store.path
    except Exception as error:
        raise RealStoreError(
            f"cannot tell which store {machine.config_file} uses ({error}); refusing to run"
        ) from error


def refuse_real_store(test_store: Path, real_machine: MachinePaths) -> None:
    """Raises when the test store is, contains or lies inside the store of the real config."""
    real_store = configured_store(real_machine)
    if real_store is None:
        return
    test_resolved = test_store.resolve()
    real_resolved = real_store.resolve()
    if (
        test_resolved == real_resolved
        or _is_within(test_resolved, real_resolved)
        or _is_within(real_resolved, test_resolved)
    ):
        raise RealStoreError(
            f"the test folder {test_store} overlaps the real store of {real_machine.config_file}; refusing to run"
        )


def _is_within(path: Path, folder: Path) -> bool:
    return folder in path.parents


def isolated_machine_config(store: Path, level: str = STUB, backend: str = "folder") -> dict[str, Any]:
    """At the model level each model step gets a timeout short enough that the product's own
    supervisor, which stops the model's whole process group, ends a slow run before the harness kills
    the runner and deletes the store under a model still at work."""
    config: dict[str, Any] = {
        "version": 1,
        "machine_id": f"{TEST_RESOURCE_PREFIX}e2e",
        "store": {"backend": backend, "path": str(store)},
    }
    if level == MODEL:
        config["curation"] = {"model_timeout_minutes": MODEL_TIMEOUT_MINUTES}
    return config


def icloud_drive() -> Path:
    return Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"


def scenario_store(level: str, name: str, sandbox: Path, drive: Path) -> StoreLocation:
    """Where a scenario's store lives: in its sandbox, or at the apple level in a new ``sb-test-``
    folder in iCloud Drive, so the run meets real eviction and downloads."""
    if level != APPLE:
        return StoreLocation("folder", sandbox / "store")
    folder = Path(tempfile.mkdtemp(prefix=f"{TEST_RESOURCE_PREFIX}e2e-{name}-", dir=drive))
    folder.rmdir()
    return StoreLocation("icloud", folder)


def visible_store_files(store: Path) -> dict[str, str]:
    """Every file in the store whose path has no hidden part, with its text."""
    files = {}
    for path in sorted(store.rglob("*")):
        relative = path.relative_to(store)
        if path.is_file() and not any(part.startswith(".") for part in relative.parts):
            files[relative.as_posix()] = path.read_text(encoding="utf-8", errors="replace")
    return files


def compare_store(
    expected: Mapping[str, str], actual: Mapping[str, str], patterns: Sequence[Mapping[str, str]] = ()
) -> list[str]:
    """Exact files first; each pattern then takes the one remaining file whose path and content match."""
    problems = [f"missing in store: {name}" for name in sorted(set(expected) - set(actual))]
    problems += [
        f"content differs: {name}: expected {expected[name]!r}, got {actual[name]!r}"
        for name in sorted(set(expected) & set(actual))
        if expected[name] != actual[name]
    ]
    remaining = {name: text for name, text in actual.items() if name not in expected}
    for pattern in patterns:
        by_path = [name for name in sorted(remaining) if fnmatch.fnmatchcase(name, pattern["path"])]
        matching = [name for name in by_path if re.fullmatch(pattern["content"], remaining[name], re.DOTALL)]
        if not matching:
            found = f"; content of {', '.join(by_path)}: {[remaining[n] for n in by_path]!r}" if by_path else ""
            problems.append(f"missing in store: a file like {pattern['path']}{found}")
            continue
        del remaining[matching[0]]
    problems += [f"unexpected in store: {name}" for name in sorted(remaining)]
    return problems


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_steps(
    steps: Sequence[Mapping[str, Any]],
    environment: Mapping[str, str],
    work: Path,
    timeout_seconds: float = STEP_TIMEOUT_SECONDS,
    saved: dict[str, str] | None = None,
    plugin: Path = CORE_PLUGIN,
) -> list[str]:
    """Runs the steps in order; what they save is added to ``saved``, which also holds ``core_plugin``."""
    problems = []
    if saved is None:
        saved = {}
    saved.setdefault("core_plugin", str(plugin))
    for number, step in enumerate(steps, 1):
        argv = [_with_saved(str(argument), saved) for argument in step["run"]]
        expected_exit = step.get("exit", 0)
        folder = _step_folder(step, work)
        if folder is None:
            problems.append(f"step {number} {argv[0]}: cwd must be a plain folder name, got {step['cwd']!r}")
            break
        try:
            result = subprocess.run(
                argv,
                cwd=folder,
                env={**environment, **step.get("env", {})},
                input=step.get("stdin", ""),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            problems.append(f"step {number} {argv[0]}: could not run: {error}")
            break
        if result.returncode != expected_exit:
            problems.append(
                f"step {number} {argv[0]}: exit {result.returncode}, expected {expected_exit}; "
                f"stderr: {result.stderr.strip()[:400]}"
            )
            break
        pattern = step.get("stdout")
        if pattern is not None and re.search(pattern, result.stdout) is None:
            problems.append(
                f"step {number} {argv[0]}: standard output does not match {pattern!r}; got {result.stdout[:400]!r}"
            )
            break
        unsaved = _save(step.get("save", {}), result.stdout, saved)
        if unsaved:
            problems.append(f"step {number} {argv[0]}: cannot save {unsaved}; got {result.stdout[:400]!r}")
            break
    return problems


def _step_folder(step: Mapping[str, Any], work: Path) -> Path | None:
    """The folder a step runs in; None when its ``cwd`` would leave the scenario's sandbox."""
    name = step.get("cwd")
    if name is None:
        return work
    if not isinstance(name, str) or name in ("", ".", "..") or "/" in name or "\\" in name:
        return None
    folder = work.parent / name
    folder.mkdir(exist_ok=True)
    return folder


def _with_saved(argument: str, saved: Mapping[str, str]) -> str:
    for name, value in saved.items():
        argument = argument.replace(f"{{{name}}}", value)
    return argument


def _save(wanted: Mapping[str, str], stdout: str, saved: dict[str, str]) -> str | None:
    """Keeps each pattern's group; the name of the first one that does not match, or None."""
    for name, pattern in wanted.items():
        match = re.search(pattern, stdout)
        if match is None:
            return name
        saved[name] = match.group(1)
    return None


def _given_transcripts(scenario: Path, claude_config: Path) -> None:
    """Puts the scenario's transcripts where Claude Code keeps them, each ``<an-hour-ago>`` as that moment.

    Without transcripts the folder is not made, as on a machine where Claude Code never ran."""
    given = scenario / TRANSCRIPTS
    if not given.is_dir():
        return
    moment = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0) - datetime.timedelta(hours=1)
    written = moment.isoformat().replace("+00:00", "Z")
    for source in sorted(given.rglob("*.jsonl")):
        target = claude_config / "projects" / source.relative_to(given)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8").replace(AN_HOUR_AGO, written), encoding="utf-8")


def _model_stub(sandbox: Path, script: Mapping[str, Any], plugin: Path) -> Path:
    """A ``claude`` for this scenario: the stub with the scenario's model actions."""
    actions = sandbox / "model.json"
    actions.write_text(json.dumps(script), encoding="utf-8")
    runner = sandbox / "bin" / "claude"
    runner.parent.mkdir()
    stub = " ".join(shlex.quote(str(part)) for part in (sys.executable, plugin / MODEL_STUB, actions))
    runner.write_text(f'#!/bin/sh\nexec {stub} "$@"\n', encoding="utf-8")
    runner.chmod(0o755)
    return runner


def run_scenario(
    scenario: Path,
    environ: Mapping[str, str],
    keep: bool = False,
    level: str = STUB,
    sandbox_root: Path | None = None,
    plugin: Path = CORE_PLUGIN,
) -> ScenarioResult:
    """At ``stub`` the scripted model and ``expect.json``; at ``model`` the real fenced ``claude`` and
    the invariants of ``model.json``, because a real model words things its own way. The steps run
    the commands of the plugin in ``plugin``."""
    result = ScenarioResult(scenario.name)
    store: Path | None = None
    if sandbox_root is not None:
        sandbox_root.mkdir(parents=True, exist_ok=True)
    sandbox = Path(tempfile.mkdtemp(prefix=f"{TEST_RESOURCE_PREFIX}e2e-{scenario.name}-", dir=sandbox_root))
    try:
        home, work = sandbox / "home", sandbox / "work"
        location = scenario_store(level, scenario.name, sandbox, icloud_drive() if level == APPLE else sandbox)
        store = location.path
        refuse_real_store(store, machine_paths(environ))
        given = scenario / "given"
        if given.is_dir():
            shutil.copytree(given, store)
        else:
            store.mkdir()
        work.mkdir()

        config_path = MachinePaths(home).config_file
        config_path.parent.mkdir(parents=True)
        config_path.write_text(
            json.dumps(isolated_machine_config(store, level, location.backend), indent=2) + "\n", encoding="utf-8"
        )

        saved = {"store": str(store)}
        environment = dict(environ)
        environment[HOME_VARIABLE] = str(home)
        environment["M2B_CORE_ROOT"] = str(plugin)
        environment["PATH"] = os.pathsep.join([str(plugin / "bin"), environ.get("PATH", "")])
        if level == MODEL:
            environment.pop(MODEL_RUNNER_VARIABLE, None)
            environment.pop(MODEL_STUB_STORE_VARIABLE, None)
            script = _read_json(scenario / MODEL_FILE)
            result.problems += _run_steps(script["steps"], environment, work, MODEL_STEP_TIMEOUT_SECONDS, saved, plugin)
            if not result.problems:
                result.problems += check_invariants(script["invariants"], visible_store_files(store), saved)
        else:
            scenario_steps = _read_json(scenario / "steps.json")
            environment["CLAUDE_CONFIG_DIR"] = str(sandbox / "claude-config")
            _given_transcripts(scenario, sandbox / "claude-config")
            environment["M2B_HERDR"] = str(sandbox / "no-herdr")
            environment["M2B_LAUNCHCTL"] = str(sandbox / "no-launchctl")
            environment["M2B_SYSTEMCTL"] = str(sandbox / "no-systemctl")
            stub = _model_stub(sandbox, scenario_steps.get("model", {"actions": []}), plugin)
            environment[MODEL_RUNNER_VARIABLE] = str(stub)
            environment[MODEL_STUB_STORE_VARIABLE] = str(store)
            result.problems += _run_steps(scenario_steps["steps"], environment, work, saved=saved, plugin=plugin)
            expect = _read_json(scenario / "expect.json")
            result.problems += compare_store(
                expect["store_files"], visible_store_files(store), expect.get("store_patterns", [])
            )
    finally:
        if keep:
            print(f"e2e: kept {scenario.name} in {sandbox}")
            if level == APPLE and store is not None:
                print(f"e2e: kept the store of {scenario.name} in {store}")
        else:
            shutil.rmtree(sandbox, ignore_errors=True)
            if level == APPLE and store is not None:
                shutil.rmtree(store, ignore_errors=True)
    return result


def check_invariants(
    invariants: Sequence[Mapping[str, Any]], files: Mapping[str, str], saved: Mapping[str, str] | None = None
) -> list[str]:
    """What must hold after a model run, whatever the model wrote; one problem per invariant that fails.

    - ``{"count": n, "glob": "...", "content": "<regex>"}``: n visible files match the glob (and the
      regular expression, searched, when given);
    - ``{"once": "<regex>", "glob": "..."}``: the expression occurs exactly once across those files;
    - ``{"matches": "<regex>", "path": "..."}``: the file exists and the expression is found in it;
    - ``{"run_state": "succeeded"}``: the run record says so;
    - ``{"no_denials": true}``: no finding of the run record says a tool call was denied;
    - ``{"empty_folder": "{name}"}``: the folder a step saved as ``name`` holds no file, or does not
      exist, for a place outside the store such as Claude Code's own memory.
    """
    problems = []
    for invariant in invariants:
        problem = _invariant_problem(invariant, files, saved or {})
        if problem:
            problems.append(f"invariant {json.dumps(invariant)}: {problem}")
    return problems


def _invariant_problem(invariant: Mapping[str, Any], files: Mapping[str, str], saved: Mapping[str, str]) -> str | None:
    def matching(glob: str) -> list[str]:
        return [name for name in sorted(files) if fnmatch.fnmatchcase(name, glob)]

    if "count" in invariant:
        names = matching(invariant["glob"])
        if "content" in invariant:
            names = [name for name in names if re.search(invariant["content"], files[name])]
        return None if len(names) == invariant["count"] else f"found {len(names)}: {names}"
    if "once" in invariant:
        found = sum(len(re.findall(invariant["once"], files[name])) for name in matching(invariant["glob"]))
        return None if found == 1 else f"found {found} times"
    if "matches" in invariant:
        text = files.get(invariant["path"])
        if text is None:
            return "the file is missing"
        return None if re.search(invariant["matches"], text) else f"not found in {text[:300]!r}"
    if "run_state" in invariant or "no_denials" in invariant:
        try:
            record = json.loads(files[RUN_RECORD_PATH])
        except (KeyError, ValueError):
            return "the run record is missing or unreadable"
        if "run_state" in invariant:
            state = record.get("state")
            return None if state == invariant["run_state"] else f"the run record says {state}: {record.get('message')}"
        denied = [item.get("text") for item in record.get("findings", []) if "was denied" in str(item.get("text"))]
        return f"denied: {denied}" if denied else None
    if "empty_folder" in invariant:
        folder_text = _with_saved(str(invariant["empty_folder"]), saved)
        if "{" in folder_text:
            return f"no step saved the folder {folder_text}"
        folder = Path(folder_text)
        held = sorted(path.name for path in folder.rglob("*") if path.is_file()) if folder.is_dir() else []
        return f"{folder} holds {held}" if held else None
    return "unknown invariant"


class UnknownScenarioError(Exception):
    """A scenario was named that does not exist."""


def discover_scenarios(root: Path, names: Sequence[str]) -> list[Path]:
    scenarios = sorted(p for p in root.iterdir() if (p / "steps.json").is_file())
    if not names:
        return scenarios
    by_name = {p.name: p for p in scenarios}
    missing = [n for n in names if n not in by_name]
    if missing:
        raise UnknownScenarioError(f"no such scenario: {', '.join(missing)}")
    return [by_name[n] for n in names]


def turns_an_addon_on(scenario: Path) -> bool:
    """Whether a step of the scenario turns an add-on on, which is how a scenario says it needs one."""
    steps = _read_json(scenario / "steps.json")["steps"]
    return any(step["run"][: len(ADDON_ON)] == ADDON_ON for step in steps)


def _parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="e2e", description="Runs the end-to-end scenarios.")
    parser.add_argument(
        "--level",
        choices=[STUB, MODEL, APPLE],
        required=True,
        help="stub: no model, runs everywhere; model: the real fenced claude, for scenarios with model.json; "
        "apple: the stub scenarios on a sb-test- store in iCloud Drive (macOS, M2B_IT=1)",
    )
    parser.add_argument("--sandbox-root", type=Path, help="where the temporary scenario folders go")
    parser.add_argument("--keep", action="store_true", help="keep each scenario's temporary folder")
    parser.add_argument("--scenarios", type=Path, default=SCENARIO_ROOT, help=argparse.SUPPRESS)
    parser.add_argument(
        "--plugin", type=Path, default=CORE_PLUGIN, help="the folder that holds the plugin (default: this checkout's)"
    )
    parser.add_argument("--core-only", action="store_true", help="leave out the scenarios that turn an add-on on")
    parser.add_argument("names", nargs="*", help="scenario folder names (default: all)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_arguments(sys.argv[1:] if argv is None else argv)
    if arguments.level == APPLE and (sys.platform != "darwin" or os.environ.get(INTEGRATION_VARIABLE) != "1"):
        print(f"e2e: the apple level runs on macOS only and only with {INTEGRATION_VARIABLE}=1", file=sys.stderr)
        return EXIT_USAGE
    try:
        scenarios = discover_scenarios(arguments.scenarios, arguments.names)
        if arguments.level == MODEL:
            without = [scenario.name for scenario in scenarios if not (scenario / MODEL_FILE).is_file()]
            if arguments.names and without:
                raise UnknownScenarioError(f"no {MODEL_FILE} for the model level: {', '.join(without)}")
            scenarios = [scenario for scenario in scenarios if scenario.name not in without]
            if not scenarios:
                raise UnknownScenarioError(f"no scenario has a {MODEL_FILE}")
        if arguments.core_only:
            scenarios = [scenario for scenario in scenarios if not turns_an_addon_on(scenario)]
    except UnknownScenarioError as error:
        print(f"e2e: {error}", file=sys.stderr)
        return EXIT_USAGE
    failed = 0
    for scenario in scenarios:
        try:
            result = run_scenario(
                scenario,
                os.environ,
                keep=arguments.keep,
                level=arguments.level,
                sandbox_root=arguments.sandbox_root,
                plugin=arguments.plugin,
            )
        except RealStoreError as error:
            print(f"e2e: {error}", file=sys.stderr)
            return EXIT_REFUSED
        print(f"e2e {arguments.level} {result.name}: {'passed' if result.passed else 'FAILED'}")
        for problem in result.problems:
            print(f"  {problem}")
        failed += not result.passed
    print(f"e2e: {len(scenarios) - failed} of {len(scenarios)} scenarios passed")
    return EXIT_FAILED if failed else EXIT_PASSED


if __name__ == "__main__":
    sys.exit(main())
