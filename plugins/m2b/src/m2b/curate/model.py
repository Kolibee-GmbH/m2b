"""The fenced model run: the one way the core and its parts start the model.

A product cannot rely on one user's permission rules, so every model step brings its own: it never
prompts, never hangs on a prompt and never does more than its step needs.

``claude -p /<skill>`` starts from an empty folder with ``--setting-sources project`` (the user's
own settings, permission rules and plugins stay out), ``--plugin-dir`` for this plugin, whose
skills the core's and the parts' steps are, ``--permission-mode dontAsk`` (nothing runs that is not
pre-approved) and ``--allowedTools`` from the step. ``<store>`` at the start of a ``Read`` or
``Edit`` rule names the configured store, so ``Read(<store>/inbox/**)`` covers the real folder.
The run's ``result`` line lists the tool calls the fence denied.

Measured with Claude Code 2.1.319 on 2026-11-07: the store is not passed
with ``--add-dir``, because an added folder is readable as a whole and would void the step's Read
rules; and a path rule for writing is ``Edit(...)``, because ``Write(<path>)`` leaves the Write
tool denied. That a ``Read`` rule also covers Glob and Grep is Claude Code's documented behaviour,
not measured here; so ``<store>`` goes into Read rules only, never into Glob or Grep rules.

``M2B_MODEL_RUNNER`` replaces the ``claude`` executable (tests and the e2e stub).
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from m2b.config import store_path
from m2b.config.machine import MachineConfig
from m2b.curate import report
from m2b.paths import MachinePaths

CURATION_RUN_VARIABLE = "M2B_CURATION_RUN"
# Set for the refresh steps of ``m2b curate --refresh-all`` alone, to the step's batch as JSON:
# ``m2b refresh due`` then lists those undated lines too.
REFRESH_ALL_VARIABLE = "M2B_REFRESH_ALL"
MODEL_RUNNER_VARIABLE = "M2B_MODEL_RUNNER"
STORE_PLACEHOLDER = "<store>"
PATH_RULE_TOOLS = ("Read", "Edit")
RESULT_TEXT_LENGTH = 200
DEFAULT_GRACE_SECONDS = 5.0
STDERR_TAIL_CHARACTERS = 400
DENIAL_DETAIL_CHARACTERS = 200

_RULE = re.compile(r"([A-Z][A-Za-z0-9_]*)(?:\(([^()]+)\))?")
_NAME = re.compile(r"[a-z][a-z0-9-]*")


class FenceError(Exception):
    """The step cannot be fenced as asked: a rule, the store path or the skill does not fit."""


class ModelUnreachableError(Exception):
    """The ``claude`` executable cannot be started."""


@dataclass(frozen=True)
class Denial:
    tool: str
    detail: str

    def __str__(self) -> str:
        return f"{self.tool}: {self.detail}" if self.detail else self.tool


@dataclass(frozen=True)
class ModelRun:
    """How a run ended: ``error`` is None when it finished; the denials are listed either way."""

    error: str | None
    denials: tuple[Denial, ...]
    seconds: float


def store_rules(rules: Sequence[str], store: Path) -> list[str]:
    """The rules with ``<store>`` at the start of a file rule turned into the store's absolute path."""
    return [_store_rule(rule, store) for rule in rules]


def _store_rule(rule: str, store: Path) -> str:
    match = _RULE.fullmatch(rule)
    if match is None:
        raise FenceError(f"{rule!r} is not a tool rule like Read or Bash(m2b search *)")
    tool, specifier = match.group(1), match.group(2)
    if tool == "Write" and specifier is not None:
        raise FenceError(f"{rule} would leave Write denied; a path rule for writing is Edit(...)")
    if specifier is None or STORE_PLACEHOLDER not in specifier:
        return rule
    if tool not in PATH_RULE_TOOLS or not specifier.startswith(STORE_PLACEHOLDER):
        raise FenceError(f"{STORE_PLACEHOLDER} may only start the path of a Read or Edit rule: {rule}")
    if not store.is_absolute():
        raise FenceError(f"the store path {store} is not absolute")
    unusable = store_path.problem(store)
    if unusable is not None:
        raise FenceError(unusable)
    # A permission rule reads //path as an absolute path; /path would be relative to the project.
    return f"{tool}(/{store}{specifier[len(STORE_PLACEHOLDER) :]})"


def check_skill(skill: str, plugin_dirs: Mapping[str, Path]) -> str:
    """The skill's name without its plugin; the skill must exist in one of the loaded plugins."""
    plugin, _, name = skill.partition(":")
    if not _NAME.fullmatch(plugin) or not _NAME.fullmatch(name):
        raise FenceError(f"{skill!r} is not a skill like m2b:ingest")
    root = plugin_dirs.get(plugin)
    if root is None:
        raise FenceError(f"the skill {skill} belongs to {plugin}, which this run does not load")
    if not (root / "skills" / name / "SKILL.md").is_file():
        raise FenceError(f"the plugin {plugin} has no skill {name} ({root})")
    return name


def fenced_command(
    executable: str,
    skill: str,
    rules: Sequence[str],
    plugin_dirs: Sequence[Path],
    model: str,
    max_turns: int,
    max_budget_usd: float | None = None,
) -> list[str]:
    command = [executable, "-p", f"/{skill}", "--setting-sources", "project", "--model", model]
    command += ["--max-turns", str(max_turns)]
    if max_budget_usd is not None:
        command += ["--max-budget-usd", f"{max_budget_usd:g}"]
    for plugin_dir in plugin_dirs:
        command += ["--plugin-dir", str(plugin_dir)]
    # Nobody answers a prompt in this run: Claude Code's flag for a scheduled job, beside dontAsk.
    command += ["--permission-mode", "dontAsk", "--permission-prompts", "none", "--allowedTools", *rules]
    command += ["--output-format", "stream-json", "--verbose"]
    return command


def run_fenced(
    command: Sequence[str],
    temp_dir: Path,
    environ: Mapping[str, str],
    timeout_seconds: float,
    grace_seconds: float = DEFAULT_GRACE_SECONDS,
    pass_fds: Sequence[int] = (),
) -> ModelRun:
    """Runs the command from a new empty folder inside ``temp_dir``, removed afterwards."""
    with empty_folder(temp_dir) as work:
        return run_model(command, work, environ, timeout_seconds, grace_seconds, pass_fds)


@contextlib.contextmanager
def empty_folder(temp_dir: Path) -> Iterator[Path]:
    """A new empty working folder for a child, never the session's, whose project
    settings and ``CLAUDE.md`` would reach the child."""
    temp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="model-", dir=temp_dir) as work:
        yield Path(work)


def run_model(
    command: Sequence[str],
    cwd: Path,
    environ: Mapping[str, str],
    timeout_seconds: float,
    grace_seconds: float = DEFAULT_GRACE_SECONDS,
    pass_fds: Sequence[int] = (),
) -> ModelRun:
    """Runs the model under ``run_supervised`` and reads its ``result`` line."""
    result: dict[str, object] | None = None

    def read(raw: bytes) -> None:
        nonlocal result
        result = _result_in(raw) or result

    end = run_supervised(command, cwd, environ, timeout_seconds, grace_seconds, pass_fds, read)
    denials = _denials(result)
    if end.timed_out:
        return ModelRun(f"timed out after {_duration(timeout_seconds)}", denials, end.seconds)
    if result is not None:
        if result.get("subtype") == "error_max_turns":
            limit = "its turn limit (curation.max_turns in config.json)"
            return ModelRun(f"the model run stopped at {limit}", denials, end.seconds)
        if result.get("subtype") == "error_max_budget_usd":
            limit = "its spending cap (curation.max_budget_usd in config.json)"
            return ModelRun(f"the model run stopped at {limit}", denials, end.seconds)
        if result.get("is_error") or result.get("subtype") != "success":
            return ModelRun(_failure(result), denials, end.seconds)
        return ModelRun(None, denials, end.seconds)
    if end.returncode != 0:
        return ModelRun(end.failure(), denials, end.seconds)
    return ModelRun("the model run ended without a result", denials, end.seconds)


def _failure(result: Mapping[str, object]) -> str:
    """Claude Code reports some failures, a missing login among them, as subtype success with ``is_error``."""
    subtype = result.get("subtype")
    text = " ".join(str(result.get("result") or "").split())[:RESULT_TEXT_LENGTH]
    detail = f"the model run failed{f' ({subtype})' if subtype and subtype != 'success' else ''}"
    detail += f": {text}" if text else ""
    if "logged in" in text.lower() or "/login" in text:
        detail += (
            ". Claude Code has no login for this run: run claude once and sign in with /login, or set "
            "ANTHROPIC_API_KEY, which bills the API instead of a subscription"
        )
    return detail


@dataclass(frozen=True)
class ProcessEnd:
    returncode: int
    timed_out: bool
    stderr_tail: str
    seconds: float

    def failure(self) -> str:
        return f"exit {self.returncode}: {self.stderr_tail}".rstrip(": ")


def run_supervised(
    command: Sequence[str],
    cwd: Path,
    environ: Mapping[str, str],
    timeout_seconds: float,
    grace_seconds: float = DEFAULT_GRACE_SECONDS,
    pass_fds: Sequence[int] = (),
    on_line: Callable[[bytes], None] | None = None,
) -> ProcessEnd:
    """Runs a child in its own process group; past the timeout the whole group is stopped.

    SIGTERM first, SIGKILL after ``grace_seconds``. Whatever the run left behind in its group is
    stopped when it ends, so no child keeps editing the store after its step. A supervisor that is
    itself stopped with SIGTERM (a part step past its timeout that runs a model step) stops its
    child's group first, because that group is its own and the outer stop does not reach it.
    ``pass_fds`` hands the run's lock to the child, so a killed runner leaves the lock held until
    the child is gone. Without ``on_line`` the output is dropped.
    """
    started = time.monotonic()
    timed_out = threading.Event()
    with tempfile.TemporaryFile() as stderr:
        try:
            process = subprocess.Popen(
                list(command),
                cwd=cwd,
                env=dict(environ),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE if on_line else subprocess.DEVNULL,
                stderr=stderr,
                start_new_session=True,
                pass_fds=tuple(pass_fds),
            )
        except OSError as error:
            raise ModelUnreachableError(f"cannot start {command[0]}: {error.strerror or error}") from error

        def stop() -> None:
            timed_out.set()
            _signal_group(process.pid, signal.SIGTERM)

        timers = [
            threading.Timer(timeout_seconds, stop),
            threading.Timer(timeout_seconds + grace_seconds, _signal_group, (process.pid, signal.SIGKILL)),
        ]
        for timer in timers:
            timer.daemon = True
            timer.start()
        with process, _stopped_with_the_child():
            try:
                if process.stdout is not None and on_line is not None:
                    for raw in process.stdout:
                        on_line(raw)
                else:
                    process.wait()
            finally:
                for timer in timers:
                    timer.cancel()
                # Before the leader is reaped, so its process group id cannot belong to anyone else yet.
                _signal_group(process.pid, signal.SIGKILL)
                process.wait()
        stderr.seek(0)
        tail = stderr.read().decode("utf-8", errors="replace").strip()[-STDERR_TAIL_CHARACTERS:]
        return ProcessEnd(process.returncode, timed_out.is_set(), tail, time.monotonic() - started)


def model_step(
    config: MachineConfig,
    machine: MachinePaths,
    environ: Mapping[str, str],
    skill: str,
    allow: Sequence[str],
    token: str,
    plugin_dirs: Mapping[str, Path],
    pass_fds: Sequence[int] = (),
) -> ModelRun:
    """Runs one skill fenced inside the run with this token; each denial goes to the run as an action."""
    step = check_skill(skill, plugin_dirs)
    executable = environ.get(MODEL_RUNNER_VARIABLE) or config.executables.get("claude", "claude")
    rules = store_rules(allow, config.store.path)
    curation = config.curation
    command = fenced_command(
        executable,
        skill,
        rules,
        list(plugin_dirs.values()),
        curation.model,
        curation.max_turns,
        curation.max_budget_usd,
    )
    step_environ = {**environ, CURATION_RUN_VARIABLE: "1", report.RUN_TOKEN_VARIABLE: token}
    timeout = config.curation.model_timeout_minutes * 60
    run = run_fenced(command, machine.temp_dir, step_environ, timeout, pass_fds=pass_fds)
    for denial in run.denials:
        text = f"the model step {skill} was denied {denial}"
        report.add_finding(machine, token, report.Finding(step, report.ACTION, text))
    return run


@contextlib.contextmanager
def _stopped_with_the_child() -> Iterator[None]:
    """While a child runs, SIGTERM ends this process through ``SystemExit``, so its ``finally`` runs."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    def stop(signal_number: int, frame: object) -> None:
        raise SystemExit(128 + signal_number)

    previous = signal.signal(signal.SIGTERM, stop)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def _signal_group(pid: int, signal_number: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pid, signal_number)


def _result_in(raw: bytes) -> dict[str, object] | None:
    try:
        message = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError:
        return None
    if isinstance(message, dict) and message.get("type") == "result":
        return message
    return None


def _denials(result: Mapping[str, object] | None) -> tuple[Denial, ...]:
    raw = result.get("permission_denials") if result else None
    denials = []
    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, dict):
            continue
        tool_input = entry.get("tool_input")
        tool_input = tool_input if isinstance(tool_input, dict) else {}
        detail = tool_input.get("command") or tool_input.get("file_path") or tool_input.get("pattern")
        if detail is None and tool_input:
            detail = json.dumps(tool_input, ensure_ascii=False)
        text = " ".join(str(detail or "").split())
        if len(text) > DENIAL_DETAIL_CHARACTERS:
            text = text[: DENIAL_DETAIL_CHARACTERS - 3] + "..."
        denials.append(Denial(str(entry.get("tool_name") or "a tool"), text))
    return tuple(denials)


def _duration(seconds: float) -> str:
    if seconds >= 60:
        return f"{seconds / 60:g} minutes"
    return f"{seconds:g} seconds"
