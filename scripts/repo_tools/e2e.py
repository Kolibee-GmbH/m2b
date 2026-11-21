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
  run of the scenario replays these actions in the stub ``tests/unit/fakes/fake_claude.py``, which
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
[...]}``, the steps in the same form but with the real fenced ``claude``, and invariants
(``check_invariants``) in place of ``expect.json``, because a real model words its notes its own way.
A value a step saved can name a folder outside the store for an invariant, such as the memory folder
Claude Code reports at a session's start. A scenario that is only a ``model.json`` runs at this level
alone.

Every session at the model level runs in a Claude Code folder of the scenario's own
(``CLAUDE_CONFIG_DIR``), so its transcript never reaches the user's folder, where their own curation
reads, and Claude Code's own memory starts empty. The account is the subscription's token
(``CLAUDE_CODE_OAUTH_TOKEN``, from the environment or, on macOS, the keychain); ``ANTHROPIC_API_KEY``,
which Claude Code would put before it and bill per run, is taken only with ``--use-api-key``. The
variables of a Claude Code session that runs this script stay out too: inherited, they make the
started one a child session that writes no transcript.

A step ``{"session": [claude arguments...], "turns": ["...", ...], "cwd": "<name>"}`` runs Claude Code
interactively in a hidden terminal and types each turn once the one before has ended, because the
reading of sessions passes over every transcript of a headless run. ``turn_seconds`` bounds a turn.

A ``model.json`` can hold ``"wordings": [{"<name>": "<text>", ...}, ...]``: three ways to say what
the owner says, one marked ``"language": "de"``. A run plays one of them, ``{name}`` put in for its
text in every argument, turn, pattern and invariant (a pattern's part is a regular expression, so
one wording can expect an answer in German). Without ``--wording`` the first is played. A step or an
invariant marked ``"arm": "with"`` is left out of a run against Claude Code alone, which
``scripts/promises`` makes: the same scenario without any ``--plugin-dir``. A step marked
``"control": true`` shows that a run is fair, for instance that Claude Code alone did keep what it
was told; when it or a step before it fails, the run shows nothing (``ScenarioResult.shows``) and
does not count as Claude Code alone failing.

``--plugin`` names another folder that holds the plugin, in place of this checkout's: the proof
that the core stands without its add-ons runs the scenarios against a copy without them. The stub
is a tool of the repository and always this checkout's.
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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from m2b.config.machine import StoreLocation, parse_machine_config
from m2b.paths import HOME_VARIABLE, MachinePaths, machine_paths
from m2b.sessions import Prompt, read_sessions

from repo_tools import REPO_ROOT
from repo_tools.terminal import TerminalError, Wait, record_timed

SCENARIO_ROOT = REPO_ROOT / "tests" / "e2e"
CORE_PLUGIN = REPO_ROOT / "plugins" / "m2b"
MODEL_STUB = REPO_ROOT / "tests" / "unit" / "fakes" / "fake_claude.py"
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
TOKEN_VARIABLE = "CLAUDE_CODE_OAUTH_TOKEN"
API_KEY_VARIABLE = "ANTHROPIC_API_KEY"
# A bearer credential Claude Code puts before the subscription's token, as a gateway setup sets it.
AUTH_TOKEN_VARIABLE = "ANTHROPIC_AUTH_TOKEN"
API_KEY_END_CHARACTERS = 20
KEYCHAIN_SERVICE = "m2b-journey-token"
CLAUDE_CONFIG_VARIABLE = "CLAUDE_CONFIG_DIR"
# The variables of a running Claude Code session, and of the user's own Claude Code setup.
CLAUDE_PREFIX = "CLAUDE"
SANDBOX_CLAUDE = "claude-config"
CLAUDE_SETTINGS = ".claude.json"
ENTER = "\r"
EXIT_COMMAND = "/exit"
# What Claude Code says, headless or on its screen, when it has no account to work with.
NOT_LOGGED_IN = ("Not logged in", "Please run /login")
HOW_TO_ADD_A_TOKEN = (
    "make a token for your subscription with `claude setup-token` and set it as "
    f"{TOKEN_VARIABLE}, or on macOS keep it in the keychain: "
    f'security add-generic-password -s {KEYCHAIN_SERVICE} -a "$USER" -w; '
    f"to bill an API key per run instead, set {API_KEY_VARIABLE} and pass --use-api-key"
)
SESSION_COLUMNS = 120
SESSION_ROWS = 40
SESSION_READY_SECONDS = 60
SESSION_TURN_SECONDS = 600
SESSION_EXIT_SECONDS = 15
# Text typed and its Enter go apart, or Claude Code takes the two as one paste and sends nothing.
TYPING_PAUSE_SECONDS = 1
# Claude Code draws its prompt with this sign once the session takes input.
PROMPT_SIGN = "\u276f".encode()
TURN_END_SUBTYPE = "turn_duration"
HEADLESS_ENTRYPOINT = "sdk-cli"
# How far back the sessions_read invariant reads: longer than any scenario runs.
READ_BACK = datetime.timedelta(days=1)
# The two arms of a promise case: with m2b, and against Claude Code alone.
WITH = "with"
WITHOUT = "without"
GERMAN = "de"
WORDINGS = 3  # at least one of them German
PLUGIN_DIR_FLAG = "--plugin-dir"
# What a transcript names as the model of a message Claude Code wrote itself, such as an error.
SYNTHETIC_MODEL = "<synthetic>"

EXIT_PASSED = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_REFUSED = 2


class RealStoreError(Exception):
    """The test setup would touch the user's real store."""


class NoAccountError(Exception):
    """The model level has no account to run Claude Code with; the message says how to add one."""


class NotLoggedInError(Exception):
    """Claude Code said it is not logged in: the account was refused, which is no failed scenario."""


@dataclass
class ScenarioResult:
    name: str
    problems: list[str] = field(default_factory=list)
    # At the model level, the models the scenario's sessions answered with.
    models: list[str] = field(default_factory=list)
    # False when a step marked as a control failed, or a step before it: the run shows nothing.
    shows: bool = True

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
        # Paused, so a run comes only from a step: a run the session start began would race the
        # scenario's own and spend the model on what the scenario does not check.
        config["curation"] = {"model_timeout_minutes": MODEL_TIMEOUT_MINUTES, "paused": True}
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


def for_run(script: Mapping[str, Any], wording: int = 0, arm: str = WITH) -> dict[str, Any]:
    """A ``model.json`` as one run of it plays: its wording number ``wording`` put in for each
    ``{name}`` the wording has, in every text of the steps and invariants, and for the arm against
    Claude Code alone every ``--plugin-dir`` taken out of a Claude Code command or session and what is
    marked ``"arm": "with"`` left out. A script without wordings keeps its texts as written."""
    wordings = script.get("wordings") or [{}]
    chosen = {name: value for name, value in wordings[wording % len(wordings)].items() if name != "language"}
    played = {key: value for key, value in script.items() if key != "wordings"}
    played["steps"] = [_filled(step, chosen) for step in script["steps"] if _in_arm(step, arm)]
    played["invariants"] = [_filled(item, chosen) for item in script.get("invariants", []) if _in_arm(item, arm)]
    if arm == WITHOUT:
        played["steps"] = [_without_plugin(step) for step in played["steps"]]
    return played


def _split_at_control(steps: Sequence[Mapping[str, Any]]) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    """The steps up to the last one marked ``"control": true``, and the rest; no control, no first part."""
    marked = [number for number, step in enumerate(steps) if step.get("control")]
    end = marked[-1] + 1 if marked else 0
    return list(steps[:end]), list(steps[end:])


def wording_problem(script: Mapping[str, Any]) -> str | None:
    """Why the script's wordings do not hold a promise, or None. A script that starts Claude Code types
    what the owner says, which a promise must not rest on in one wording."""
    starts_claude = any("session" in step or step.get("run", [""])[0] == "claude" for step in script["steps"])
    if not starts_claude:
        return None
    wordings = script.get("wordings") or []
    if len(wordings) != WORDINGS:
        return f"a case that starts Claude Code needs three wordings, it has {len(wordings)}"
    if not any(wording.get("language") == GERMAN for wording in wordings):
        return "one of its three wordings must be German"
    return None


def _in_arm(item: Mapping[str, Any], arm: str) -> bool:
    return bool(item.get("arm", arm) == arm)


def _filled(item: Any, wording: Mapping[str, str]) -> Any:
    if isinstance(item, str):
        for name, value in wording.items():
            item = item.replace(f"{{{name}}}", value)
        return item
    if isinstance(item, list):
        return [_filled(part, wording) for part in item]
    if isinstance(item, dict):
        return {key: _filled(value, wording) for key, value in item.items() if key != "arm"}
    return item


def _without_plugin(step: Mapping[str, Any]) -> dict[str, Any]:
    changed = dict(step)
    if "session" in step:
        changed["session"] = _without_plugin_dir(step["session"])
    elif step.get("run", [""])[0] == "claude":
        changed["run"] = _without_plugin_dir(step["run"])
    return changed


def _without_plugin_dir(argv: Sequence[str]) -> list[str]:
    kept: list[str] = []
    skip = False
    for argument in argv:
        if skip:
            skip = False
        elif argument == PLUGIN_DIR_FLAG:
            skip = True
        else:
            kept.append(argument)
    return kept


def models_in(projects: Path) -> list[str]:
    """The models Claude answered with in the transcripts under ``projects``, each once, in order."""
    found: list[str] = []
    for path in sorted(projects.glob("*/*.jsonl")) if projects.is_dir() else []:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if '"model"' not in line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                message = record.get("message") if isinstance(record, dict) else None
                model = message.get("model") if isinstance(message, dict) else None
                if not isinstance(model, str) or record.get("type") != "assistant" or model == SYNTHETIC_MODEL:
                    continue
                if model not in found:
                    found.append(model)
    return found


def keychain_token() -> str | None:
    """The token kept in the macOS keychain under ``KEYCHAIN_SERVICE``; None elsewhere or without one."""
    if sys.platform != "darwin":
        return None
    try:
        found = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True,
            text=True,
            timeout=STEP_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    token = found.stdout.strip()
    return token if found.returncode == 0 and token else None


def model_account(environ: Mapping[str, str], use_api_key: bool = False) -> dict[str, str]:
    """The one variable that gives the model level's sessions an account."""
    if use_api_key:
        key = environ.get(API_KEY_VARIABLE)
        if not key:
            raise NoAccountError(f"--use-api-key needs {API_KEY_VARIABLE} set")
        return {API_KEY_VARIABLE: key}
    token = environ.get(TOKEN_VARIABLE) or keychain_token()
    if not token:
        raise NoAccountError(f"the model level needs an account and found none: {HOW_TO_ADD_A_TOKEN}")
    return {TOKEN_VARIABLE: token}


def model_environment(environ: Mapping[str, str], account: Mapping[str, str], claude_config: Path) -> dict[str, str]:
    """The environment without a running session's variables and any account, with the scenario's
    Claude Code folder and the one account given."""
    kept = {
        name: value
        for name, value in environ.items()
        if not name.startswith(CLAUDE_PREFIX) and name not in (API_KEY_VARIABLE, AUTH_TOKEN_VARIABLE)
    }
    return {**kept, **account, CLAUDE_CONFIG_VARIABLE: str(claude_config)}


def prepare_claude_config(folder: Path, account: Mapping[str, str]) -> None:
    """A Claude Code folder past its first start: without it an interactive session opens on the
    theme picker instead of the prompt. An API key is marked as accepted, by its end as Claude Code
    keeps it there, or an interactive session asks whether to use it and declines by default."""
    folder.mkdir(parents=True, exist_ok=True)
    settings: dict[str, Any] = {"hasCompletedOnboarding": True, "theme": "dark", "projects": {}}
    key = account.get(API_KEY_VARIABLE)
    if key:
        settings["customApiKeyResponses"] = {"approved": [key[-API_KEY_END_CHARACTERS:]], "rejected": []}
    _write_claude_settings(folder, settings)


def trust_folder(claude_config: Path, folder: Path) -> None:
    """Marks the folder as trusted, by the path given and the one it resolves to, so an interactive
    session there opens without the trust dialog."""
    settings = json.loads((claude_config / CLAUDE_SETTINGS).read_text(encoding="utf-8"))
    for path in {str(folder), str(folder.resolve())}:
        settings["projects"].setdefault(path, {})["hasTrustDialogAccepted"] = True
    _write_claude_settings(claude_config, settings)


def _write_claude_settings(folder: Path, settings: Mapping[str, Any]) -> None:
    (folder / CLAUDE_SETTINGS).write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def turn_ends(projects: Path, folder: Path) -> int:
    """How many turns interactive sessions started in ``folder`` have ended, by the record Claude
    Code writes into the transcript at the end of each. A transcript belongs to the folder its first
    record names, as the reading of sessions takes it: later records follow the Bash tool's ``cd``.
    A headless run's transcript does not count."""
    if not projects.is_dir():
        return 0
    wanted = folder.resolve()
    return sum(_turn_ends_in(path, wanted) for path in projects.glob("*/*.jsonl"))


def _turn_ends_in(path: Path, folder: Path) -> int:
    started_in: Path | None = None
    ended = 0
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            # Asked between reads of the terminal: a line that can change nothing is not parsed.
            if started_in is not None and TURN_END_SUBTYPE not in line and HEADLESS_ENTRYPOINT not in line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            if record.get("entrypoint") == HEADLESS_ENTRYPOINT:
                return 0
            if started_in is None and isinstance(record.get("cwd"), str):
                started_in = Path(record["cwd"]).resolve()
            ended += record.get("subtype") == TURN_END_SUBTYPE
    return ended if started_in == folder else 0


def claude_folder_name(path: Path) -> str:
    """The name Claude Code gives the folder of a project's transcripts: every character that is no
    letter or digit becomes a dash."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def leaked_transcripts(user_claude: Path, sandbox: Path) -> list[str]:
    """The folders of the user's Claude Code transcripts that belong to a project in the sandbox."""
    projects = user_claude / "projects"
    if not projects.is_dir():
        return []
    marker = claude_folder_name(Path(sandbox.name))
    return sorted(folder.name for folder in projects.iterdir() if marker in folder.name)


def user_claude_folder(environ: Mapping[str, str]) -> Path:
    configured = environ.get(CLAUDE_CONFIG_VARIABLE)
    return Path(configured) if configured else Path(environ.get("HOME") or Path.home()) / ".claude"


def _not_logged_in(text: str) -> bool:
    return any(sign in text for sign in NOT_LOGGED_IN)


def _run_session(
    step: Mapping[str, Any], environment: Mapping[str, str], folder: Path, saved: Mapping[str, str]
) -> str | None:
    """Runs Claude Code interactively in ``folder`` and types the step's turns, each once the turn
    before has ended in the transcript; a problem, or None. A session that says it is not logged in
    raises ``NotLoggedInError``."""
    claude_config = Path(environment[CLAUDE_CONFIG_VARIABLE])
    trust_folder(claude_config, folder)
    projects = claude_config / "projects"
    ended_before = turn_ends(projects, folder)
    turns = [str(turn) for turn in step.get("turns", [])]
    if not turns:
        return "a session step needs at least one turn"
    turn_seconds = float(step.get("turn_seconds", SESSION_TURN_SECONDS))

    def ended(count: int) -> Callable[[], bool]:
        return lambda: turn_ends(projects, folder) >= ended_before + count

    # Each wait reads, then types: the first turn once the prompt is drawn, each later one, and at
    # last the command that ends the session, once the turn before has ended.
    waits = [Wait(SESSION_READY_SECONDS, turns[0], until=PROMPT_SIGN)]
    for number, following in enumerate([*turns[1:], EXIT_COMMAND], 1):
        waits.append(Wait(TYPING_PAUSE_SECONDS, ENTER))
        waits.append(Wait(turn_seconds, following, done=ended(number), waits_for=f"end of turn {number}"))
    waits += [Wait(TYPING_PAUSE_SECONDS, ENTER), Wait(SESSION_EXIT_SECONDS)]
    command = ["claude", *(_with_saved(str(argument), saved) for argument in step["session"])]
    account = account_in(environment)
    try:
        recording = record_timed(command, folder, environment, SESSION_ROWS, SESSION_COLUMNS, waits)
    except TerminalError as error:
        drawn = redacted(error.drawn, account)
        if _not_logged_in(drawn):
            raise NotLoggedInError(_last_lines(drawn)) from None
        return f"{error}; it drew last: {_last_lines(drawn)}"
    drawn = redacted(recording.text(), account)
    if _not_logged_in(drawn):
        raise NotLoggedInError(_last_lines(drawn))
    # Only the last wait may end early: the session ends there, after the command that ends it.
    if len(recording.typed_at) < len(waits) - 1:
        return f"Claude Code ended before its last turn; it drew last: {_last_lines(drawn)}"
    return None


def _last_lines(drawn: str) -> str:
    return " | ".join(line.strip() for line in drawn.splitlines() if line.strip())[-400:] or "nothing"


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
    account = account_in(environment)
    if saved is None:
        saved = {}
    saved.setdefault("core_plugin", str(plugin))
    for number, step in enumerate(steps, 1):
        folder = _step_folder(step, work)
        if folder is None:
            problems.append(f"step {number}: cwd must be a plain folder name, got {step['cwd']!r}")
            break
        if "session" in step:
            problem = _run_session(step, {**environment, **step.get("env", {})}, folder, saved)
            if problem:
                problems.append(f"step {number} session: {problem}")
                break
            continue
        argv = [_with_saved(str(argument), saved) for argument in step["run"]]
        expected_exit = step.get("exit", 0)
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
        # Shown only redacted, and redacted whole before it is cut, or a cut leaves part of a secret.
        shown_out, shown_err = (redacted(text, account) for text in (result.stdout, result.stderr))
        if result.returncode != expected_exit and _not_logged_in(shown_out + shown_err):
            raise NotLoggedInError(_last_lines(shown_out + shown_err))
        if result.returncode != expected_exit:
            problems.append(
                f"step {number} {argv[0]}: exit {result.returncode}, expected {expected_exit}; "
                f"stderr: {shown_err.strip()[:400]}"
            )
            break
        pattern = step.get("stdout")
        if pattern is not None and re.search(pattern, result.stdout) is None:
            problems.append(
                f"step {number} {argv[0]}: standard output does not match {pattern!r}; got {shown_out[:400]!r}"
            )
            break
        unsaved = _save(step.get("save", {}), result.stdout, saved)
        if unsaved:
            problems.append(f"step {number} {argv[0]}: cannot save {unsaved}; got {shown_out[:400]!r}")
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


def model_stub(sandbox: Path, script: Mapping[str, Any]) -> Path:
    """A ``claude`` for this scenario: the stub with the scenario's model actions."""
    actions = sandbox / "model.json"
    actions.write_text(json.dumps(script), encoding="utf-8")
    runner = sandbox / "bin" / "claude"
    runner.parent.mkdir()
    stub = " ".join(shlex.quote(str(part)) for part in (sys.executable, MODEL_STUB, actions))
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
    account: Mapping[str, str] | None = None,
    wording: int = 0,
    arm: str = WITH,
) -> ScenarioResult:
    """At ``stub`` the scripted model and ``expect.json``; at ``model`` the real fenced ``claude`` and
    the invariants of ``model.json``, because a real model words things its own way, every session in
    the scenario's own Claude Code folder with ``account``, in the wording and arm ``for_run`` plays.
    The steps run the commands of the plugin in ``plugin``."""
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
            claude_config = sandbox / SANDBOX_CLAUDE
            prepare_claude_config(claude_config, account or {})
            environment = model_environment(environment, account or {}, claude_config)
            saved["claude_config"] = str(claude_config)
            script = for_run(_read_json(scenario / MODEL_FILE), wording, arm)
            controlled, rest = _split_at_control(script["steps"])
            result.problems += _run_steps(controlled, environment, work, MODEL_STEP_TIMEOUT_SECONDS, saved, plugin)
            result.shows = not (controlled and result.problems)
            if not result.problems:
                result.problems += _run_steps(rest, environment, work, MODEL_STEP_TIMEOUT_SECONDS, saved, plugin)
            if not result.problems:
                result.problems += check_invariants(script["invariants"], visible_store_files(store), saved)
            result.models = models_in(claude_config / "projects")
            leaked = leaked_transcripts(user_claude_folder(environ), sandbox)
            if leaked:
                result.problems.append(f"transcripts of this run lie in the user's Claude Code folder: {leaked}")
        else:
            scenario_steps = _read_json(scenario / "steps.json")
            environment["CLAUDE_CONFIG_DIR"] = str(sandbox / "claude-config")
            _given_transcripts(scenario, sandbox / "claude-config")
            environment["M2B_HERDR"] = str(sandbox / "no-herdr")
            environment["M2B_LAUNCHCTL"] = str(sandbox / "no-launchctl")
            environment["M2B_SYSTEMCTL"] = str(sandbox / "no-systemctl")
            stub = model_stub(sandbox, scenario_steps.get("model", {"actions": []}))
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
    - ``{"at_least": n, "glob": "...", "content": "<regex>"}``: as ``count``, n or more, where a model
      may write one thing as one file or as two;
    - ``{"once": "<regex>", "glob": "..."}``: the expression occurs exactly once across those files;
    - ``{"matches": "<regex>", "path": "..."}``: the file exists and the expression is found in it;
    - ``{"run_state": "succeeded"}``: the run record says so;
    - ``{"no_denials": true}``: no finding of the run record says a tool call was denied;
    - ``{"empty_folder": "{name}"}``: the folder a step saved as ``name`` holds no file, or does not
      exist, for a place outside the store such as Claude Code's own memory;
    - ``{"sessions_read": [{"prompt": "<regex>", "commands": "<regex>"}, ...]}``: the reading of
      sessions (``m2b.sessions``) finds, in the scenario's Claude Code folder and in this order,
      prompts whose typed text matches each ``prompt``, each with a Bash command of the turn before
      it that matches ``commands`` when one is given.
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

    if "count" in invariant or "at_least" in invariant:
        names = matching(invariant["glob"])
        if "content" in invariant:
            names = [name for name in names if re.search(invariant["content"], files[name])]
        if "at_least" in invariant:
            return None if len(names) >= invariant["at_least"] else f"found {len(names)}: {names}"
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
    if "sessions_read" in invariant:
        return _sessions_read_problem(invariant["sessions_read"], saved)
    if "empty_folder" in invariant:
        folder_text = _with_saved(str(invariant["empty_folder"]), saved)
        if "{" in folder_text:
            return f"no step saved the folder {folder_text}"
        folder = Path(folder_text)
        held = sorted(path.name for path in folder.rglob("*") if path.is_file()) if folder.is_dir() else []
        return f"{folder} holds {held}" if held else None
    return "unknown invariant"


def _sessions_read_problem(expected: Sequence[Mapping[str, str]], saved: Mapping[str, str]) -> str | None:
    claude_config = saved.get("claude_config")
    if claude_config is None:
        return "no Claude Code folder of the scenario's own at this level"
    now = datetime.datetime.now(datetime.timezone.utc)
    reading = read_sessions(Path(claude_config) / "projects", now - READ_BACK, now + datetime.timedelta(minutes=1))
    prompts = [prompt for session in reading.sessions for prompt in session.prompts]
    position = 0
    for wanted in expected:
        while position < len(prompts) and not _prompt_matches(prompts[position], wanted):
            position += 1
        if position == len(prompts):
            read = [(prompt.text, list(prompt.commands)) for prompt in prompts]
            return f"no prompt like {wanted} after the ones before; read: {read}"
        position += 1
    return None


def _prompt_matches(prompt: Prompt, wanted: Mapping[str, str]) -> bool:
    if re.search(wanted["prompt"], prompt.text) is None:
        return False
    commands = wanted.get("commands")
    return commands is None or any(re.search(commands, command) for command in prompt.commands)


def account_in(environment: Mapping[str, str]) -> dict[str, str]:
    """The account variables an environment holds, to redact their values from what is shown."""
    return {name: environment[name] for name in (TOKEN_VARIABLE, API_KEY_VARIABLE) if environment.get(name)}


def redacted(text: str, account: Mapping[str, str]) -> str:
    """The text with the account's value replaced, so a report never shows the token or the key."""
    for name, value in account.items():
        text = text.replace(value, "<token>" if name == TOKEN_VARIABLE else "<api key>")
    return text


class UnknownScenarioError(Exception):
    """A scenario was named that does not exist."""


def discover_scenarios(root: Path, names: Sequence[str]) -> list[Path]:
    """The scenarios with a ``steps.json`` or a ``model.json``; the levels leave out what they cannot run."""
    scenarios = sorted(p for p in root.iterdir() if (p / "steps.json").is_file() or (p / MODEL_FILE).is_file())
    if not names:
        return scenarios
    by_name = {p.name: p for p in scenarios}
    missing = [n for n in names if n not in by_name]
    if missing:
        raise UnknownScenarioError(f"no such scenario: {', '.join(missing)}")
    return [by_name[n] for n in names]


def turns_an_addon_on(scenario: Path) -> bool:
    """Whether a step of the scenario turns an add-on on, which is how a scenario says it needs one."""
    script = scenario / "steps.json" if (scenario / "steps.json").is_file() else scenario / MODEL_FILE
    steps = _read_json(script)["steps"]
    return any(step.get("run", [])[: len(ADDON_ON)] == ADDON_ON for step in steps)


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
    parser.add_argument(
        "--wording",
        type=int,
        choices=range(1, WORDINGS + 1),
        default=1,
        help="model level: which of a scenario's wordings to play (default: the first)",
    )
    parser.add_argument(
        "--use-api-key",
        action="store_true",
        help=f"model level: run with {API_KEY_VARIABLE}, billed per run, in place of the subscription's token",
    )
    parser.add_argument("names", nargs="*", help="scenario folder names (default: all)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_arguments(sys.argv[1:] if argv is None else argv)
    if arguments.level == APPLE and (sys.platform != "darwin" or os.environ.get(INTEGRATION_VARIABLE) != "1"):
        print(f"e2e: the apple level runs on macOS only and only with {INTEGRATION_VARIABLE}=1", file=sys.stderr)
        return EXIT_USAGE
    account: dict[str, str] = {}
    try:
        scenarios = discover_scenarios(arguments.scenarios, arguments.names)
        if arguments.level != MODEL:
            without = [scenario.name for scenario in scenarios if not (scenario / "steps.json").is_file()]
            if arguments.names and without:
                raise UnknownScenarioError(f"only a {MODEL_FILE}, for the model level: {', '.join(without)}")
            scenarios = [scenario for scenario in scenarios if scenario.name not in without]
        if arguments.level == MODEL:
            without = [scenario.name for scenario in scenarios if not (scenario / MODEL_FILE).is_file()]
            if arguments.names and without:
                raise UnknownScenarioError(f"no {MODEL_FILE} for the model level: {', '.join(without)}")
            scenarios = [scenario for scenario in scenarios if scenario.name not in without]
            if not scenarios:
                raise UnknownScenarioError(f"no scenario has a {MODEL_FILE}")
        if arguments.core_only:
            scenarios = [scenario for scenario in scenarios if not turns_an_addon_on(scenario)]
        if arguments.level == MODEL:
            account = model_account(os.environ, arguments.use_api_key)
    except (UnknownScenarioError, NoAccountError) as error:
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
                account=account,
                wording=arguments.wording - 1,
            )
        except RealStoreError as error:
            print(f"e2e: {error}", file=sys.stderr)
            return EXIT_REFUSED
        except NotLoggedInError as error:
            said = redacted(str(error), account)
            print(f"e2e {scenario.name}: Claude Code is not logged in ({said}); {HOW_TO_ADD_A_TOKEN}", file=sys.stderr)
            return EXIT_REFUSED
        print(f"e2e {arguments.level} {result.name}: {'passed' if result.passed else 'FAILED'}")
        for problem in result.problems:
            print(f"  {redacted(problem, account)}")
        failed += not result.passed
    print(f"e2e: {len(scenarios) - failed} of {len(scenarios)} scenarios passed")
    return EXIT_FAILED if failed else EXIT_PASSED


if __name__ == "__main__":
    sys.exit(main())
