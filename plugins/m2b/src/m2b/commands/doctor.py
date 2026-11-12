"""``doctor``: one line per backend, the reminders-cli version, the recorded executables,
whether the launcher finds m2b in Claude Code's plugin list, whether the prompt hook answers, and
whether a session ran the band. Where the store folder is a git repository, one line says whether a
curation run on this machine commits into it.

The reminders-cli line appears only when the store's tasks live in Apple Reminders. A ``claude``
that setup could not find is named with the command that records it; it is needed only on the
machine that curates, so it is not counted as a problem.

Every check runs even when an earlier one failed, so one answer shows everything that needs
fixing. "Not configured" (no calendar backend) and a band no session has run yet are states, not
problems. Exit 1 when anything cannot be reached or is missing.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from m2b import claude_code, launcher, prompt_hook
from m2b.calendar.base import CalendarError, CalendarNotConfigured
from m2b.commands import Context
from m2b.commands.backends import configured_calendar, configured_store, configured_tasks
from m2b.commands.output import print_json
from m2b.config import store_path
from m2b.config.errors import ConfigError, StoreUnreachableError
from m2b.config.machine import MachineConfig, load_machine_config
from m2b.config.store_settings import NEWER, describe_format, format_state, load_store_settings
from m2b.curate import run_commit
from m2b.notes.characters import with_hidden_written_out
from m2b.paths import MachinePaths
from m2b.store.base import StoreError
from m2b.tasks.base import TasksError

REACHABLE, NOT_CONFIGURED, NOT_REACHABLE = "reachable", "not configured", "not reachable"
FOUND, MISSING, UNKNOWN, NOT_INSTALLED = "found", "missing", "version unknown", "not installed"
NOT_RECORDED = "not recorded"
UNUSABLE = "not usable for curation"
APPLE_REMINDERS = "apple-reminders"
ANSWERS, SILENT = "answers", "does not answer"
NO_REPOSITORY, CANNOT_COMMIT = "no repository", "cannot commit"
PROBLEMS = (NOT_REACHABLE, MISSING, NEWER, UNUSABLE, SILENT, CANNOT_COMMIT)
GIT_FOLDER_SEEN = f"{run_commit.GIT_FOLDER} in the store folder"
NO_GIT = f"the store folder holds a {run_commit.GIT_FOLDER}, but this machine has no git to start"
COMMITS_EACH_RUN = "a curation run on this machine ends with one commit of what it changed"
LEFT_UNCOMMITTED = "a curation run on this machine leaves what it changed uncommitted"
PROMPT_HOOK_COMMAND = "bin/m2b-prompt-hook"
NO_TOPIC_FACTS = "so no topic's facts come in before a prompt"
_HOMEBREW_VERSION = re.compile(r"/reminders-cli/([^/]+)/")
PROBE_FAILURES = (ConfigError, StoreUnreachableError, StoreError, TasksError, CalendarError, OSError)
SEEN, NOT_SEEN = "seen", "not seen"
# The band and the launcher hook start within moments of each other in one session.
SAME_SESSION = datetime.timedelta(minutes=5)
BAND_PAGE = "https://github.com/Kolibee-GmbH/m2b/blob/main/docs/band.md"
MODS_OFF = (
    "ran m2b's hooks but not the band: Claude Code loaded no mods there, most often because an earlier "
    "session saved its rollout switch off without network access; start claude once with network access, "
    "then a new session. Everything else in m2b works without the band"
)
NO_HOOKS = (
    "no Claude Code session has run m2b's hooks on this machine since setup: Claude Code runs no plugin "
    "hooks under --bare, or with allowManagedHooksOnly or disableAllHooks in managed settings, and then "
    "neither the band nor the distillate at session start; right after setup, start a new session first"
)


@dataclass(frozen=True)
class Check:
    name: str
    state: str
    detail: str = ""


def doctor(arguments: argparse.Namespace, context: Context) -> int:
    config = load_machine_config(context.machine)
    checks = [
        probe("store", lambda: _check_store(config, context)),
        *_store_path_check(config, context),
        *_store_format_check(config, context),
        *_store_git_check(config, context),
        probe("tasks", lambda: configured_tasks(config, context.machine).check_reachable()),
        calendar_check(config),
        *([_reminders_version(config)] if _uses_reminders(config, context) else []),
        *[_executable(name, path) for name, path in sorted(config.executables.items())],
        *([] if "claude" in config.executables else [_claude_not_recorded()]),
        claude_code_check(context.environ),
        prompt_hook_check(context.environ),
        band_check(context.machine),
    ]
    if arguments.json:
        print_json({"checks": [check.__dict__ for check in checks]})
    else:
        for check in checks:
            print(f"{check.name}: {check.state}" + (f" ({check.detail})" if check.detail else ""))
    return 1 if any(check.state in PROBLEMS for check in checks) else 0


def claude_code_check(environ: Mapping[str, str]) -> Check:
    """Whether the launcher finds m2b in Claude Code's ``installed_plugins.json``, an internal file."""
    name = "claude-code"
    checkout = environ.get(launcher.CORE_ROOT_VARIABLE)
    if checkout:
        return Check(name, FOUND, f"the launcher runs m2b from {checkout} ({launcher.CORE_ROOT_VARIABLE})")
    found = claude_code.resolve_install_path(claude_code.CORE_PLUGIN, environ)
    if found is not None:
        return Check(name, FOUND, f"the launcher runs m2b from {found}")
    listing = claude_code.installed_plugins_file(environ)
    return Check(
        name,
        MISSING,
        f"{listing} lists no user-scope m2b@m2b, so ~/.local/bin/m2b and everything outside Claude Code that "
        "calls it cannot find m2b; install it for your user with /plugin, from the marketplace named m2b",
    )


def prompt_hook_check(environ: Mapping[str, str], plugin_root: Path = launcher.PLUGIN_ROOT) -> Check:
    """Whether the plugin has Claude Code run the prompt hook, and whether the hook gets to the topics.

    The hook says nothing when it fails, so that no prompt waits or breaks for it. Here it is
    started as Claude Code starts it and within the time ``hooks.json`` gives it, asked to check
    itself: then it says what it would swallow. Whether Claude Code runs it cannot be asked.
    """
    name = "prompt-hook"
    hooks_file = plugin_root / "hooks" / "hooks.json"
    timeout = _prompt_hook_timeout(hooks_file)
    if timeout is None:
        return Check(name, MISSING, f"{hooks_file} names no hook that runs {PROMPT_HOOK_COMMAND}, {NO_TOPIC_FACTS}")
    command = plugin_root / PROMPT_HOOK_COMMAND
    try:
        result = subprocess.run(
            [str(command), prompt_hook.CHECK_ARGUMENT],
            env=dict(environ),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Check(
            name, SILENT, f"{command} took longer than the {timeout:g} s Claude Code gives it, {NO_TOPIC_FACTS}"
        )
    except OSError as error:
        return Check(name, MISSING, f"{command} could not be started: {error}, {NO_TOPIC_FACTS}")
    said = (result.stdout.strip() or result.stderr.strip() or f"exit code {result.returncode}").splitlines()[-1]
    if result.returncode != 0:
        return Check(name, SILENT, f"{said}; {NO_TOPIC_FACTS}")
    return Check(name, ANSWERS, said)


def _prompt_hook_timeout(hooks_file: Path) -> float | None:
    """The seconds Claude Code gives the prompt hook, or None when the plugin's hooks do not name it."""
    try:
        groups = json.loads(hooks_file.read_text(encoding="utf-8"))["hooks"]["UserPromptSubmit"]
        hooks = [hook for group in groups for hook in group["hooks"]]
        timeouts = [hook["timeout"] for hook in hooks if PROMPT_HOOK_COMMAND in hook["command"]]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return float(timeouts[0]) if timeouts and isinstance(timeouts[0], (int, float)) else None


def band_check(machine: MachinePaths) -> Check:
    """Whether the latest session that ran m2b's own hooks also started the band, the one mod of m2b.

    Python cannot ask Claude Code whether it loaded the mod, so the launcher hook and the band each
    note when a session started them, and the two times are compared.
    """
    session, band = _seen_at(machine.session_seen_file), _seen_at(machine.band_seen_file)
    last_ran = f" (the band last ran {_local(band)})" if band is not None else ""
    if band is not None and (session is None or band >= session - SAME_SESSION):
        return Check("band", SEEN, f"it ran in the latest session, started {_local(band)}")
    if session is not None:
        return Check(
            "band", NOT_SEEN, f"the latest session, started {_local(session)}, {MODS_OFF}{last_ran}; {BAND_PAGE}"
        )
    return Check("band", NOT_SEEN, f"{NO_HOOKS}{last_ran}; {BAND_PAGE}")


def _seen_at(path: Path) -> datetime.datetime | None:
    try:
        text = json.loads(path.read_text(encoding="utf-8"))["seenAt"]
        # The band writes JavaScript's UTC form with a "Z", which Python 3.9 does not read.
        moment = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    return moment if moment.tzinfo is not None else None


def _local(moment: datetime.datetime) -> str:
    return f"{moment.astimezone():%Y-%m-%d %H:%M}"


def _store_format_check(config: MachineConfig, context: Context) -> list[Check]:
    """The store's format against this m2b; nothing when the store cannot be read, which ``store`` reports."""
    try:
        settings = load_store_settings(configured_store(config, context.machine))
    except PROBE_FAILURES:
        return []
    return [Check("store-format", format_state(settings), describe_format(settings))]


def _store_path_check(config: MachineConfig, context: Context) -> list[Check]:
    """A line only on the curating machine, for a store path no curation run can work in; a machine
    that only captures never fences with its path."""
    unusable = store_path.problem(config.store.path)
    if unusable is None:
        return []
    try:
        curates = load_store_settings(configured_store(config, context.machine)).curating_machine == config.machine_id
    except PROBE_FAILURES:
        return []
    return [Check("store-path", UNUSABLE, unusable)] if curates else []


def _store_git_check(config: MachineConfig, context: Context) -> list[Check]:
    """Whether a curation run on this machine ends with a git commit, and into which git directory.

    git is started only where a run would start it: on the curating machine, with the commit on.
    A run on a machine without git commits nothing and says nothing, so this line is where the
    owner learns that the repository they made gets no commits. Nothing when the store cannot be
    read, which ``store`` reports.

    Where the git directory lies, and what git says when it cannot use it, is text of the ``.git``
    in the store folder, which whoever writes the store can write; a session's model reads this
    line, so a character that draws nothing is written out in both.
    """
    name = "store-git"
    try:
        store = configured_store(config, context.machine)
        curates = load_store_settings(store).curating_machine == config.machine_id
    except PROBE_FAILURES:
        return []
    if not run_commit.holds_git_folder(store):
        return [Check(name, NO_REPOSITORY)]
    if not curates:
        return [Check(name, FOUND, f"{GIT_FOLDER_SEEN}; this machine does not curate, so it commits nothing")]
    if not config.curation.git_commit:
        switched_off = "curation.git_commit is false on this machine, so its runs commit nothing"
        return [Check(name, FOUND, f"{GIT_FOLDER_SEEN}; {switched_off}")]
    try:
        repository = run_commit.find_repository(store, context.environ)
        if repository is None:
            return [Check(name, CANNOT_COMMIT, f"{NO_GIT}; {LEFT_UNCOMMITTED}")]
        directory = run_commit.git_directory(repository)
    except (run_commit.CommitError, OSError) as error:
        return [Check(name, CANNOT_COMMIT, f"{with_hidden_written_out(str(error))}; {LEFT_UNCOMMITTED}")]
    where = with_hidden_written_out(str(directory))
    return [Check(name, FOUND, f"{where}, read with {repository.git}; {COMMITS_EACH_RUN}")]


def _check_store(config: MachineConfig, context: Context) -> None:
    load_store_settings(configured_store(config, context.machine))


def probe(name: str, call: Callable[[], None]) -> Check:
    try:
        call()
    except PROBE_FAILURES as error:
        return Check(name, NOT_REACHABLE, str(error))
    return Check(name, REACHABLE)


def calendar_check(config: MachineConfig) -> Check:
    try:
        configured_calendar(config).check_access()
    except CalendarNotConfigured:
        return Check("calendar", NOT_CONFIGURED)
    except PROBE_FAILURES as error:
        return Check("calendar", NOT_REACHABLE, str(error))
    return Check("calendar", REACHABLE, config.calendar.backend)


def _uses_reminders(config: MachineConfig, context: Context) -> bool:
    """True unless the store says otherwise: a store that cannot be read keeps the line."""
    try:
        return load_store_settings(configured_store(config, context.machine)).tasks.backend == APPLE_REMINDERS
    except PROBE_FAILURES:
        return True


def _claude_not_recorded() -> Check:
    return Check("executable claude", NOT_RECORDED, "curation needs it: m2b config set executables.claude <path>")


def _reminders_version(config: MachineConfig) -> Check:
    """reminders-cli has no version option; Homebrew keeps the version in the installed path."""
    command = config.executables.get("reminders") or shutil.which("reminders")
    if not command:
        return Check("reminders-cli", NOT_INSTALLED)
    found = _HOMEBREW_VERSION.search(os.path.realpath(command))
    return Check("reminders-cli", found.group(1) if found else UNKNOWN, command)


def _executable(name: str, path: str) -> Check:
    if os.path.isfile(path) and os.access(path, os.X_OK):
        return Check(f"executable {name}", FOUND, path)
    return Check(f"executable {name}", MISSING, path)
