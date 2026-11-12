"""The fenced model run: the one place the core and its add-ons start the model from.

A product cannot rely on one user's permission rules, so every model step brings its own: it never
prompts, never hangs on a prompt and never does more than its step needs. A step has one of two
forms: a skill with the commands and paths of its step, or a text to read with nothing to call.

``claude -p /<skill>`` starts from an empty folder with ``--setting-sources project`` (the user's
own settings, permission rules and plugins stay out), ``--plugin-dir`` for this plugin, whose
skills the core's and the add-ons' steps are, ``--permission-mode dontAsk`` (nothing runs that is not
pre-approved) and ``--allowedTools`` from the step. ``<store>`` at the start of a ``Read`` or
``Edit`` rule names the configured store, so ``Read(<store>/inbox/**)`` covers the real folder.
The run's ``result`` line lists the tool calls the fence denied.

The session has only the tools the step's rules name (``--tools``, ``step_tools``), no MCP server
(``--strict-mcp-config`` and a deny rule for every ``mcp__`` tool), keeps no transcript
(``--no-session-persistence``: what the step read from the store is not written a second time
under Claude Code's folder) and reads no ``CLAUDE.md`` and no memory of Claude Code's own
(``FENCE_ENVIRONMENT``). Measured with Claude Code 2.1.322 on 2026-11-12, because
``dontAsk`` denies only what asks: without these a step had some twenty more tools. Of those,
listing the other Claude sessions on the machine and starting a subagent ran without asking, and
a message to such a session was stopped by no permission (it was tried with a name no session
has). The connectors of the person's claude.ai account were part of the session, waiting to
connect. And every ``CLAUDE.md`` in a folder above the working folder was in the model's context,
the person's own ``~/.claude/CLAUDE.md`` among them, since the working folder lies under their
home folder. Every command outside the rules was denied either way, read-only ones too (``cat``,
``ls``, ``printenv``), so the environment is handed on as it is: the model has no way to read it,
and a proxy or a provider's credentials in it are what the run needs.

The two switches keep Claude Code's memory out of the model's context; they do not close its
folder. Claude Code allows the file tools in the memory folder it keeps for a session's project
without any rule, and measured on the same day a step with both switches set read, wrote and
edited files there (the memory folder of another project was refused). The folder belongs to the
step's working folder or to a git repository above it, which is the person's home folder where
they keep that under git, and what a step wrote there would be in the context of every later
session of that repository. So the folder Claude Code keeps its own files in is denied by path
(``off_limits``, ``claude_code.own_folders``), for Read and for Edit, the rule Claude Code reads
for Write too: a deny rule holds whatever allows a call, and with it the same calls were refused
and listed with the denials.

The fence is not taken on trust: before the model's first answer Claude Code prints a line that
names the session's tools and MCP servers (after the lines of the plugin's session-start hooks),
and a run that has more than it was to have is stopped right there; a run that ends well without
having said so fails too. A call of a tool the session does not have
is counted with the denials, because Claude Code refuses it without listing it.

Measured with Claude Code 2.1.319 on 2026-11-07: the store is not passed
with ``--add-dir``, because an added folder is readable as a whole and would void the step's Read
rules; and a path rule for writing is ``Edit(...)``, because ``Write(<path>)`` leaves the Write
tool denied. That a ``Read`` rule also covers Glob and Grep is Claude Code's documented behaviour,
not measured here; so ``<store>`` goes into Read rules only, never into Glob or Grep rules.

A step that only reads a text and answers runs without tools (``text_step``): ``claude -p`` with the
instruction as its prompt and the text on standard input, ``--tools ""``, no plugin, no MCP server,
no skill, one turn, and no session kept on disk. It is for text the model must not act on, such as
what a person typed in their sessions: with nothing to call, whatever the text says can only change
the answer, and the caller checks the answer in code. Nothing is kept on disk, so the text is not
written a second time under Claude Code's folder. Measured with Claude Code 2.1.322 on 2026-11-11:
the answer is the ``result`` of the one JSON object the run prints, the model that gave it the key
of ``modelUsage``.

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
from typing import IO

from m2b import claude_code
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
# The tools a rule gives a step: an Edit rule is the one Claude Code reads for the Write tool too.
# A Read rule gives Read alone. No step searches with Glob or Grep; they come only with a rule of
# their own, and such a rule cannot name the store, so it allows them on every path.
TOOLS_OF_A_RULE = {"Edit": ("Edit", "Write")}
NO_MCP_TOOL = "mcp__*"
# The tools of an Edit rule and of a Read rule: a deny rule for both leaves no file tool on a path.
FILE_RULES = ("Edit", "Read")
# Claude Code's switches for a child that is to read nothing but its step: no CLAUDE.md, of the
# folders above the working folder or of the person, and no memory of its own.
FENCE_ENVIRONMENT = {"CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}
NAMES_SHOWN = 5
UNPROVEN = "the model run did not say which tools and MCP servers it had, so its fence is unproven"
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


@dataclass(frozen=True)
class TextRun:
    """What a run without tools answered and which model answered, or why there is no answer.

    ``error`` never holds text of the run; ``detail`` may: what Claude Code said about a failure, or
    the end of what the command wrote as its error. ``advice`` is what to do about it where that is
    known, a sentence of m2b's own.
    """

    answer: str | None
    model: str | None
    error: str | None
    detail: str
    seconds: float
    advice: str = ""

    def failure(self) -> str:
        """Why there is no answer, in one line: the error, what was said, then the advice."""
        return (f"{self.error}: {self.detail}" if self.detail else str(self.error)) + self.advice


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


def step_tools(rules: Sequence[str]) -> list[str]:
    """The tools a step's rules can allow, each once, in the order the rules name them."""
    tools: list[str] = []
    for rule in rules:
        match = _RULE.fullmatch(rule)
        if match is None:
            raise FenceError(f"{rule!r} is not a tool rule like Read or Bash(m2b search *)")
        for tool in TOOLS_OF_A_RULE.get(match.group(1), (match.group(1),)):
            if tool not in tools:
                tools.append(tool)
    return tools


def fenced_command(
    executable: str,
    skill: str,
    rules: Sequence[str],
    off_limits: Sequence[Path],
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
    command += ["--tools", ",".join(step_tools(rules)), "--strict-mcp-config"]
    # A deny rule holds whatever allows the call: the step's rules, or Claude Code itself, which
    # allows the file tools in the memory folder it keeps for a session without any rule.
    command += ["--disallowedTools", NO_MCP_TOOL]
    for folder in off_limits:
        unnamable = store_path.unsafe_characters(folder)
        if unnamable:
            raise FenceError(
                f"Claude Code's own folder {str(folder)!r} holds {unnamable!r}, which a permission rule "
                "cannot name, so no model step can be kept out of it"
            )
        command += [f"{tool}(/{folder}/**)" for tool in FILE_RULES]
    command += ["--no-session-persistence"]
    # Nobody answers a prompt in this run: Claude Code's flag for a scheduled job, beside dontAsk.
    command += ["--permission-mode", "dontAsk", "--permission-prompts", "none", "--allowedTools", *rules]
    command += ["--output-format", "stream-json", "--verbose"]
    return command


def text_command(executable: str, instruction: str, model: str, max_budget_usd: float | None = None) -> list[str]:
    """A run that reads the instruction and its standard input and answers once, with nothing to call."""
    command = [executable, "-p", instruction, "--model", model, "--setting-sources", "project", "--tools", ""]
    command += ["--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"]
    command += ["--permission-mode", "dontAsk", "--max-turns", "1"]
    if max_budget_usd is not None:
        command += ["--max-budget-usd", f"{max_budget_usd:g}"]
    return [*command, "--output-format", "json"]


def run_fenced(
    command: Sequence[str],
    tools: Sequence[str],
    temp_dir: Path,
    environ: Mapping[str, str],
    timeout_seconds: float,
    grace_seconds: float = DEFAULT_GRACE_SECONDS,
    pass_fds: Sequence[int] = (),
) -> ModelRun:
    """Runs the command from a new empty folder inside ``temp_dir``, removed afterwards."""
    with empty_folder(temp_dir) as work:
        return run_model(command, tools, work, environ, timeout_seconds, grace_seconds, pass_fds)


@contextlib.contextmanager
def empty_folder(temp_dir: Path) -> Iterator[Path]:
    """A new empty working folder for a child, never the session's, whose project
    settings and ``CLAUDE.md`` would reach the child."""
    temp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="model-", dir=temp_dir) as work:
        yield Path(work)


class _OutsideTheFenceError(Exception):
    """Claude Code gave the session more than the step was to have."""


def run_model(
    command: Sequence[str],
    tools: Sequence[str],
    cwd: Path,
    environ: Mapping[str, str],
    timeout_seconds: float,
    grace_seconds: float = DEFAULT_GRACE_SECONDS,
    pass_fds: Sequence[int] = (),
) -> ModelRun:
    """Runs the model under ``run_supervised``, holds its session to ``tools`` and reads its ``result`` line.

    A session that starts with another tool or with an MCP server is stopped at the line of its
    output that says so, which comes before the model's first answer. A call of a tool the session does not have is a
    denial like those of the ``result`` line.
    """
    result: dict[str, object] | None = None
    said_its_tools = False
    missing_tools: list[Denial] = []

    def read(raw: bytes) -> None:
        nonlocal result, said_its_tools
        message = _message_in(raw)
        if message is None:
            return
        if message.get("type") == "system" and message.get("subtype") == "init":
            beyond = _beyond_the_fence(message, tools)
            if beyond:
                raise _OutsideTheFenceError(beyond)
            said_its_tools = True
        elif message.get("type") == "assistant":
            missing_tools.extend(_calls_of_other_tools(message, tools))
        elif message.get("type") == "result":
            result = message

    started = time.monotonic()
    try:
        end = run_supervised(command, cwd, environ, timeout_seconds, grace_seconds, pass_fds, read)
    except _OutsideTheFenceError as error:
        return ModelRun(str(error), (), time.monotonic() - started)
    denials = (*_denials(result), *missing_tools)
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
        if not said_its_tools:
            return ModelRun(UNPROVEN, denials, end.seconds)
        return ModelRun(None, denials, end.seconds)
    if end.returncode != 0:
        return ModelRun(end.failure(), denials, end.seconds)
    return ModelRun("the model run ended without a result", denials, end.seconds)


def run_text(
    command: Sequence[str],
    text: str,
    cwd: Path,
    environ: Mapping[str, str],
    timeout_seconds: float,
    grace_seconds: float = DEFAULT_GRACE_SECONDS,
    pass_fds: Sequence[int] = (),
) -> TextRun:
    """Runs the command under ``run_supervised`` with ``text`` as its standard input and reads its one result."""
    output: list[bytes] = []
    end = run_supervised(command, cwd, environ, timeout_seconds, grace_seconds, pass_fds, output.append, text)
    result = _one_result(b"".join(output))
    usage = result.get("modelUsage") if result else None
    answered_by = ", ".join(sorted(usage)) if isinstance(usage, dict) and usage else None
    if end.timed_out:
        return TextRun(None, answered_by, f"timed out after {_duration(timeout_seconds)}", "", end.seconds)
    if result is None:
        return TextRun(None, None, f"exit {end.returncode} without a result", end.stderr_tail, end.seconds)
    if result.get("subtype") == "error_max_budget_usd":
        limit = "its spending cap (curation.max_budget_usd in config.json)"
        return TextRun(None, answered_by, f"the model run stopped at {limit}", "", end.seconds)
    answer = result.get("result")
    if result.get("is_error") or result.get("subtype") not in (None, "success") or not isinstance(answer, str):
        what, said, advice = _failure_parts(result)
        return TextRun(None, answered_by, what, said, end.seconds, advice)
    return TextRun(answer, answered_by, None, "", end.seconds)


def _one_result(output: bytes) -> dict[str, object] | None:
    """The JSON object a run with ``--output-format json`` prints, whole or as its last line that is one."""
    text = output.decode("utf-8", errors="replace")
    for candidate in (text, *reversed(text.splitlines())):
        try:
            found = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(found, dict):
            return found
    return None


def _failure(result: Mapping[str, object]) -> str:
    what, said, advice = _failure_parts(result)
    return f"{what}: {said}{advice}" if said else what + advice


def _failure_parts(result: Mapping[str, object]) -> tuple[str, str, str]:
    """That the run failed, what Claude Code said about it, and what to do where that is known.

    Claude Code reports some failures, a missing login among them, as subtype success with ``is_error``.
    """
    subtype = result.get("subtype")
    said = " ".join(str(result.get("result") or "").split())[:RESULT_TEXT_LENGTH]
    what = f"the model run failed{f' ({subtype})' if subtype and subtype != 'success' else ''}"
    advice = ""
    if "logged in" in said.lower() or "/login" in said:
        advice = (
            ". Claude Code has no login for this run: run claude once and sign in with /login, or set "
            "ANTHROPIC_API_KEY, which bills the API instead of a subscription"
        )
    return what, said, advice


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
    standard_input: str | None = None,
) -> ProcessEnd:
    """Runs a child in its own process group; past the timeout the whole group is stopped.

    SIGTERM first, SIGKILL after ``grace_seconds``. Whatever the run left behind in its group is
    stopped when it ends, so no child keeps editing the store after its step. A supervisor that is
    itself stopped with SIGTERM (an add-on step past its timeout that runs a model step) stops its
    child's group first, because that group is its own and the outer stop does not reach it.
    ``pass_fds`` hands the run's lock to the child, so a killed runner leaves the lock held until
    the child is gone. Without ``on_line`` the output is dropped; without ``standard_input`` the
    child reads nothing.
    """
    started = time.monotonic()
    timed_out = threading.Event()
    with tempfile.TemporaryFile() as stderr, _as_standard_input(standard_input) as stdin:
        try:
            process = subprocess.Popen(
                list(command),
                cwd=cwd,
                env=dict(environ),
                stdin=stdin,
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
        claude_code.own_folders(environ),
        list(plugin_dirs.values()),
        curation.model,
        curation.max_turns,
        curation.max_budget_usd,
    )
    step_environ = {**environ, **FENCE_ENVIRONMENT, CURATION_RUN_VARIABLE: "1", report.RUN_TOKEN_VARIABLE: token}
    timeout = config.curation.model_timeout_minutes * 60
    run = run_fenced(command, step_tools(rules), machine.temp_dir, step_environ, timeout, pass_fds=pass_fds)
    for denial in run.denials:
        text = f"the model step {skill} was denied {denial}"
        report.add_finding(machine, token, report.Finding(step, report.ACTION, text))
    return run


def text_step(
    config: MachineConfig,
    machine: MachinePaths,
    environ: Mapping[str, str],
    instruction: str,
    text: str,
    pass_fds: Sequence[int] = (),
) -> TextRun:
    """Asks the curation model once, with nothing to call: ``instruction`` as the prompt, ``text`` to read."""
    executable = environ.get(MODEL_RUNNER_VARIABLE) or config.executables.get("claude", "claude")
    curation = config.curation
    command = text_command(executable, instruction, curation.model, curation.max_budget_usd)
    step_environ = {**environ, **FENCE_ENVIRONMENT, CURATION_RUN_VARIABLE: "1"}
    timeout = curation.model_timeout_minutes * 60
    with empty_folder(machine.temp_dir) as work:
        return run_text(command, text, work, step_environ, timeout, pass_fds=pass_fds)


@contextlib.contextmanager
def _as_standard_input(text: str | None) -> Iterator[int | IO[bytes]]:
    """What the child reads: nothing, or the text from a file without a name.

    A file and not a pipe, so a child that reads late or not at all blocks nobody, whatever the
    text's size; without a name, so the text lies on no path. Half a character, as a transcript can
    hold one, becomes a question mark.
    """
    if text is None:
        yield subprocess.DEVNULL
        return
    with tempfile.TemporaryFile() as handle:
        handle.write(text.encode("utf-8", errors="replace"))
        handle.seek(0)
        yield handle


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


def _message_in(raw: bytes) -> dict[str, object] | None:
    try:
        message = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError:
        return None
    return message if isinstance(message, dict) else None


def _beyond_the_fence(start: Mapping[str, object], tools: Sequence[str]) -> str | None:
    """What the session has beyond the step's tools, as the reason to stop it, or None."""
    started_with, servers = start.get("tools"), start.get("mcp_servers")
    # A server that is not connected yet has no tool in the list, so only its own field shows it.
    if not isinstance(started_with, list) or not isinstance(servers, list):
        return UNPROVEN
    beyond = [
        _named("the tool", "the tools", [str(tool) for tool in started_with if tool not in tools]),
        _named("the MCP server", "the MCP servers", [_server_name(server) for server in servers]),
    ]
    found = " and ".join(part for part in beyond if part)
    if not found:
        return None
    return f"Claude Code gave the model step {found}, which its fence leaves out; the step was stopped at its start"


def _named(one: str, several: str, names: Sequence[str]) -> str:
    if not names:
        return ""
    shown = ", ".join(_one_word(name) for name in sorted(names)[:NAMES_SHOWN])
    more = f" and {len(names) - NAMES_SHOWN} more" if len(names) > NAMES_SHOWN else ""
    return f"{one if len(names) == 1 else several} {shown}{more}"


def _one_word(name: str) -> str:
    return "-".join(name.split())[:60] or "without a name"


def _server_name(server: object) -> str:
    return str(server.get("name") or "") if isinstance(server, dict) else str(server)


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _calls_of_other_tools(message: Mapping[str, object], tools: Sequence[str]) -> list[Denial]:
    """The tool calls of this line of the output for a tool the session does not have."""
    body = message.get("message")
    content = body.get("content") if isinstance(body, dict) else None
    calls = []
    for block in _list(content):
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") not in tools:
            calls.append(Denial(_one_word(str(block.get("name") or "a tool")), _denial_detail(block.get("input"))))
    return calls


def _denials(result: Mapping[str, object] | None) -> tuple[Denial, ...]:
    raw = result.get("permission_denials") if result else None
    denials = []
    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, dict):
            continue
        denials.append(Denial(str(entry.get("tool_name") or "a tool"), _denial_detail(entry.get("tool_input"))))
    return tuple(denials)


def _denial_detail(tool_input: object) -> str:
    """What a refused call was for, in one line: its command, file or pattern, else its whole input."""
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    detail = tool_input.get("command") or tool_input.get("file_path") or tool_input.get("pattern")
    if detail is None and tool_input:
        detail = json.dumps(tool_input, ensure_ascii=False)
    text = " ".join(str(detail or "").split())
    if len(text) > DENIAL_DETAIL_CHARACTERS:
        text = text[: DENIAL_DETAIL_CHARACTERS - 3] + "..."
    return text


def _duration(seconds: float) -> str:
    if seconds >= 60:
        return f"{seconds / 60:g} minutes"
    return f"{seconds:g} seconds"
