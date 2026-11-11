"""The ``m2b`` command: argument parsing and exit codes, nothing else.

Exit codes: 0 success, including "nothing to do"; 1 the command ran and found a problem the
user must act on; 2 usage or configuration error; 3 a backend could not be reached; 4 a capture
could not be written, so nothing was saved. Hook commands always exit 0. The handlers live in
``m2b.commands``.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any, TextIO

from m2b import hooks
from m2b.calendar.base import (
    CalendarChoiceError,
    CalendarError,
    CalendarUnreachableError,
    EventMismatchError,
)
from m2b.capture import NotSavedError
from m2b.commands import Context, ProblemError, UsageError, settings, store, tasks
from m2b.commands import addons as addons_commands
from m2b.commands import band as band_commands
from m2b.commands import calendar as calendar_commands
from m2b.commands import candidates as candidate_commands
from m2b.commands import capture as capture_commands
from m2b.commands import curate as curate_commands
from m2b.commands import distillate as distillate_commands
from m2b.commands import doctor as doctor_command
from m2b.commands import ingest as ingest_commands
from m2b.commands import launcher as launcher_commands
from m2b.commands import lint as lint_commands
from m2b.commands import proposals as proposals_commands
from m2b.commands import rediscover as rediscover_commands
from m2b.commands import refresh as refresh_commands
from m2b.commands import search as search_commands
from m2b.commands import setup as setup_commands
from m2b.commands import status as status_commands
from m2b.commands import todos as todos_commands
from m2b.config.errors import ConfigError, NotSetUpError, StoreUnreachableError
from m2b.config.machine import MachineConfig, load_machine_config
from m2b.curate import model, report
from m2b.curate.take_over import RunInProgressError
from m2b.hook_input import HookInput, read_hook_input
from m2b.notes.frontmatter import NoteFormatError
from m2b.paths import MachinePaths, machine_paths
from m2b.store.base import StoreError, UnsupportedStoreError
from m2b.tasks import markers
from m2b.tasks.base import (
    TasksError,
    TaskStateError,
    TasksUnreachableError,
    UnconfirmedTaskError,
    UnknownTaskError,
)

EXIT_OK = 0
EXIT_PROBLEM = 1
EXIT_USAGE = 2
EXIT_UNREACHABLE = 3
EXIT_NOT_SAVED = 4

Hook = Callable[[MachineConfig, MachinePaths, Mapping[str, str], HookInput], None]
Handler = Callable[[argparse.Namespace, Context], int]

# Session-start hooks by name.
HOOKS: Mapping[str, Hook] = {"distillate": hooks.distillate, "nudge": hooks.nudge, "launcher": hooks.launcher_hook}
# Set on the curation run's model runs: hooks run in ``claude -p`` too, and without it a model step
# would load the distillate again or start a second run.
CURATION_RUN_VARIABLE = model.CURATION_RUN_VARIABLE

# Most specific first: the first matching class decides the exit code.
_EXIT_CODES: tuple[tuple[type[BaseException], int], ...] = (
    (NotSavedError, EXIT_NOT_SAVED),
    (UsageError, EXIT_USAGE),
    (ConfigError, EXIT_USAGE),
    (UnsupportedStoreError, EXIT_USAGE),
    (model.FenceError, EXIT_USAGE),
    (report.NoRunError, EXIT_USAGE),
    (report.FindingError, EXIT_USAGE),
    (ProblemError, EXIT_PROBLEM),
    (RunInProgressError, EXIT_PROBLEM),
    (UnknownTaskError, EXIT_PROBLEM),
    (TaskStateError, EXIT_PROBLEM),
    (UnconfirmedTaskError, EXIT_PROBLEM),
    (NoteFormatError, EXIT_PROBLEM),
    (CalendarChoiceError, EXIT_PROBLEM),
    (EventMismatchError, EXIT_PROBLEM),
    (StoreUnreachableError, EXIT_UNREACHABLE),
    (StoreError, EXIT_UNREACHABLE),
    (TasksUnreachableError, EXIT_UNREACHABLE),
    (TasksError, EXIT_UNREACHABLE),
    (CalendarUnreachableError, EXIT_UNREACHABLE),
    (CalendarError, EXIT_UNREACHABLE),
    (model.ModelUnreachableError, EXIT_UNREACHABLE),
)
_HANDLED = tuple(error_type for error_type, _ in _EXIT_CODES)


def main(
    argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None, stdin: TextIO | None = None
) -> int:
    """``stdin`` carries a hook's input; run from the command line (no ``argv``), it is the process's own."""
    environ = os.environ if environ is None else environ
    if stdin is None and argv is None:
        stdin = sys.stdin
    try:
        arguments = _parser().parse_args(argv)
    except SystemExit as exit_request:
        return exit_request.code if isinstance(exit_request.code, int) else EXIT_USAGE

    if getattr(arguments, "curator", False) and environ.get(CURATION_RUN_VARIABLE) != "1":
        command = " ".join(part for part in (arguments.command, getattr(arguments, "action", None)) if part)
        print(f"m2b: {command} runs only inside a curation run; start one with m2b curate --force", file=sys.stderr)
        return EXIT_USAGE
    machine = machine_paths(environ)
    if arguments.command == "hook":
        if environ.get(CURATION_RUN_VARIABLE) == "1":
            return EXIT_OK
        return _run_hook(arguments.name, machine, environ, stdin)
    try:
        handler: Handler = arguments.handler
        return handler(arguments, Context(machine, environ))
    except _HANDLED as error:
        print(f"m2b: {error}", file=sys.stderr)
        return next(code for error_type, code in _EXIT_CODES if isinstance(error, error_type))


def _run_hook(name: str, machine: MachinePaths, environ: Mapping[str, str], stdin: TextIO | None) -> int:
    """Runs a hook; it never fails a session, and it prints nothing when nothing is set up.

    Anything else that keeps it from looking is one line for the session to show.
    """
    try:
        config = load_machine_config(machine)
        hook = HOOKS.get(name)
        if hook is not None:
            hook(config, machine, environ, read_hook_input(stdin))
    except NotSetUpError:
        pass
    # A hook must never block a session start, whatever went wrong.
    except Exception as error:
        print(f"m2b: {error}")
    return EXIT_OK


class _Once(argparse.Action):
    """An option that may be given once; a second value is refused instead of silently winning."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        if getattr(namespace, self.dest) is not None:
            parser.error(f"{option_string} given twice")
        setattr(namespace, self.dest, values)


def _command(
    group: Any,
    name: str,
    handler: Handler,
    help_text: str,
    json_flag: bool = False,
    curator: bool = False,
    listed: bool = True,
) -> argparse.ArgumentParser:
    """``curator``: the command moves, renames or edits store files, which only the curation run may
    do (clients only add); ``listed``: it appears in ``--help``."""
    command: argparse.ArgumentParser = group.add_parser(name, **_help(help_text, listed))
    command.set_defaults(handler=handler, curator=curator)
    if json_flag:
        command.add_argument("--json", action="store_true")
    return command


def _group(commands: Any, name: str, help_text: str, listed: bool = True) -> Any:
    return commands.add_parser(name, **_help(help_text, listed)).add_subparsers(dest="action", required=True)


def _help(help_text: str, listed: bool) -> dict[str, str]:
    """argparse lists a subcommand in ``--help`` only when it is given ``help``."""
    return {"help": help_text} if listed else {"description": help_text}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="m2b")
    commands = parser.add_subparsers(dest="command", required=True)

    config = _group(commands, "config", "the machine config")
    _command(config, "get", settings.config_get, "print the config or one key of it", json_flag=True).add_argument(
        "key", nargs="?", help="a dotted key such as store.path"
    )
    config_set = _command(config, "set", settings.config_set, "set one key; the config is validated first")
    config_set.add_argument("key")
    config_set.add_argument("value", help="JSON, or plain text for a string")

    distillate_group = _group(commands, "distillate", "the distillate at session start, per project")
    for name, handler, help_text in (
        ("off", distillate_commands.distillate_off, "no distillate in sessions in this folder and below"),
        ("on", distillate_commands.distillate_on, "the distillate again in this folder"),
    ):
        _command(distillate_group, name, handler, help_text).add_argument(
            "folder", nargs="?", help="the project folder; the current folder without it"
        )

    addons_group = _group(commands, "addons", "the add-ons of m2b on this machine")
    _command(addons_group, "list", addons_commands.addons_list, "each add-on and whether it is on", json_flag=True)
    for name, handler, help_text in (
        ("on", addons_commands.addons_on, "turn an add-on on; its setup skill does this once the add-on is set up"),
        ("off", addons_commands.addons_off, "turn an add-on off; its settings stay"),
    ):
        _command(addons_group, name, handler, help_text).add_argument("addon")

    profile = _group(commands, "profile", "the owner's profile")
    _command(profile, "get", settings.profile_get, "print the profile or one key of it", json_flag=True).add_argument(
        "key", nargs="?"
    )
    profile_set = _command(profile, "set", settings.profile_set, "set one key; other keys stay")
    profile_set.add_argument("key")
    profile_set.add_argument("value", help="JSON, or plain text for a string")
    _command(profile, "merge", settings.profile_merge, "merge a JSON object; spheres by id").add_argument(
        "patch", help="a JSON object, or - to read it from standard input"
    )

    capture = _command(commands, "capture", capture_commands.capture_command, "write a new note into the inbox", True)
    capture.add_argument("text", nargs="?", help="the text; - or nothing reads it from standard input")
    capture.add_argument(
        "--source", default=capture_commands.DEFAULT_SOURCE, help="claude from the skill, cli otherwise"
    )
    capture.add_argument("--quiet", action="store_true", help="keep it out of everything proactive")
    capture.add_argument("--follow-up", help="YYYY-MM-DD: also create a task due that day")

    search = _command(commands, "search", search_commands.search_command, "full text over archive, memory, inbox", True)
    search.add_argument("terms", nargs="+", help="one phrase; with --any, one phrase per term")
    search.add_argument("--any", action="store_true", help="each term on its own; a line holding one of them is a hit")
    search.add_argument("--word", action="store_true", help="whole words only, not parts of words")

    again = _command(commands, "rediscover", rediscover_commands.rediscover_command, "old notes back into view", True)
    again.add_argument("--count", type=int, default=3, help="at most this many notes; 3 without it")
    again.add_argument("--today", help="YYYY-MM-DD: the day that counts as today")
    again.add_argument("--month", help="YYYY-MM or YYYY-MM..YYYY-MM: notes from these months only")

    proposed = _command(
        commands, "proposals", proposals_commands.proposals_command, "what the sessions proposed, to keep or drop", True
    )
    # No answer named: the listing. The answers set no handler of their own, the command reads ``action``.
    answers = proposed.add_subparsers(dest="action")
    for answer, help_text in (
        ("keep", "file these proposals with the next curation run"),
        ("drop", "forget these proposals"),
    ):
        given = answers.add_parser(answer, help=help_text)
        given.add_argument("ids", nargs="*", metavar="id")
        given.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        given.set_defaults(all=False)
        if answer == "keep":
            given.add_argument("--all", action="store_true", help="every proposal that waits for an answer")

    refresh_group = _group(commands, "refresh", "memory lines past their day or gone quiet")
    refresh_due = _command(refresh_group, "due", refresh_commands.refresh_due, "what is due, for the refresh", True)
    refresh_due.add_argument("--today", help="YYYY-MM-DD: the day that counts as today")

    todos = _command(commands, "todos", todos_commands.todos_command, "open tasks by due date, today's events", True)
    todos.add_argument("--today", help="YYYY-MM-DD: the day to count from; today without it")

    task_group = _group(commands, "tasks", "the owner's task list")
    tasks_list = _command(task_group, "list", tasks.tasks_list, "open tasks", json_flag=True)
    tasks_list.add_argument("--marker", choices=markers.KINDS, help="only curator tasks with this marker")
    tasks_list.add_argument("--include-completed", action="store_true")
    tasks_add = _command(task_group, "add", tasks.tasks_add, "add a task and print its id", json_flag=True)
    tasks_add.add_argument("title")
    tasks_add.add_argument("--notes", default="")
    tasks_add.add_argument("--due", help="YYYY-MM-DD or YYYY-MM-DD HH:MM, local time")
    tasks_add.add_argument("--candidate", action="store_true", help="a memory candidate; the title is its text")
    for name, handler, help_text in (
        ("complete", tasks.tasks_complete, "complete a task"),
        ("drop", tasks.tasks_drop, "mark a task dropped and complete it"),
        ("delete", tasks.tasks_delete, "delete a task"),
    ):
        _command(task_group, name, handler, help_text).add_argument("id")
    tasks_notes = _command(task_group, "notes", tasks.tasks_notes, "replace a task's notes")
    tasks_notes.add_argument("id")
    tasks_notes.add_argument("notes")

    calendar = _group(commands, "calendar", "calendar access")
    _command(calendar, "list", calendar_commands.calendar_list, "the calendars", json_flag=True).add_argument(
        "--writable", action="store_true", help="only the calendars an event can be added to"
    )
    events = _command(calendar, "events", calendar_commands.calendar_events, "events of some days", json_flag=True)
    events.add_argument("--from", dest="first", help="first day, YYYY-MM-DD; today without it")
    events.add_argument("--to", dest="last", help="last day, included; the first day without it")
    add = _command(
        calendar, "add", calendar_commands.calendar_add, "create an event in a named calendar", json_flag=True
    )
    add.add_argument("--calendar", required=True, action=_Once, help="name, account/name or name (account)")
    add.add_argument("--title", required=True, action=_Once)
    add.add_argument("--start", required=True, action=_Once, help="YYYY-MM-DD HH:MM, or YYYY-MM-DD with --all-day")
    add.add_argument("--end", action=_Once, help="an hour after the start without it; with --all-day the last day")
    add.add_argument("--all-day", action="store_true")

    store_group = _group(commands, "store", "the store's files")
    _command(store_group, "check-local", store.store_check_local, "list evicted files", json_flag=True).add_argument(
        "paths", nargs="+"
    )
    fetch = _command(store_group, "fetch", store.store_fetch, "download evicted files")
    fetch.add_argument("paths", nargs="+")
    fetch.add_argument("--timeout", type=float, default=store.DEFAULT_FETCH_TIMEOUT_SECONDS)

    ingest_group = _group(commands, "ingest", "the curator's steps on inbox captures", listed=False)
    _command(
        ingest_group, "normalize", ingest_commands.ingest_normalize, "schema names, bundles, copies", True, curator=True
    )
    _command(ingest_group, "list", ingest_commands.ingest_list, "the captures waiting, for the model", True)
    ingest_task = _command(
        ingest_group, "task", ingest_commands.ingest_task, "a task for a capture", True, curator=True
    )
    ingest_task.add_argument("file", help="the capture's file name in the inbox")
    ingest_task.add_argument("--key", help="one word that keeps this task apart from the capture's others")
    ingest_task.add_argument("--title", help="the task's title")
    ingest_task.add_argument("--due", help="YYYY-MM-DD or YYYY-MM-DD HH:MM, local time")
    ingest_task.add_argument("--follow-up", action="store_true", help="the task the capture's follow_up asks for")
    ingest_ref = _command(ingest_group, "ref", ingest_commands.ingest_ref, "add a ref to a capture", curator=True)
    ingest_ref.add_argument("file")
    ingest_ref.add_argument("ref", help="an archive file name or a URL")
    ingest_note = _command(
        ingest_group, "note", ingest_commands.ingest_note, "add a line to the curation trailer", curator=True
    )
    ingest_note.add_argument("file")
    ingest_note.add_argument("text", help="the note, or - to read it from standard input")
    _command(
        ingest_group,
        "facts-filed",
        ingest_commands.ingest_facts_filed,
        "mark the capture's facts as filed",
        curator=True,
    ).add_argument("file")
    _command(
        ingest_group, "finish", ingest_commands.ingest_finish, "move a capture into the archive", True, curator=True
    ).add_argument("file")

    curate_parser = commands.add_parser("curate", help="the curation run")
    curate_parser.set_defaults(handler=curate_commands.curate_run)
    curate_parser.add_argument("--force", action="store_true", help="run even when no run is due")
    curate_parser.add_argument("--detach", action="store_true", help="start the run in the background")
    curate_parser.add_argument(
        "--refresh-all",
        action="store_true",
        help="run now and also date the memory lines written without until or since, once",
    )
    curate_parser.add_argument(
        "--sort-facts",
        action="store_true",
        help="run now and also sort the facts of a distillate written before topics into topics, once",
    )
    curate = curate_parser.add_subparsers(dest="action")
    _command(curate, "take-over", curate_commands.curate_take_over, "make this machine the curating machine")
    curate_model = _command(curate, "model", curate_commands.curate_model, "run one model step, fenced")
    curate_model.add_argument("--skill", required=True, action=_Once, help="plugin:skill, such as m2b:ingest")
    curate_model.add_argument(
        "--allow", required=True, action="append", help="a tool rule; <store> starts a path in the store; repeatable"
    )
    curate_report = _command(curate, "report", curate_commands.curate_report, "hand a finding to the run")
    curate_report.add_argument("--step", required=True, action=_Once, help="the step's name, such as lint")
    curate_report.add_argument("--kind", required=True, action=_Once, help="action: the owner must act; info")
    curate_report.add_argument(
        "--text", required=True, action=_Once, help="the finding, or - to read it from standard input"
    )

    _command(
        commands,
        "harvest",
        candidate_commands.harvest_command,
        "ticked candidates and kept proposals into the inbox",
        True,
        curator=True,
        listed=False,
    )
    _command(
        commands,
        "journal",
        candidate_commands.journal_command,
        "completed tasks into the month's journal",
        True,
        curator=True,
        listed=False,
    )

    lint_group = _group(commands, "lint", "findings about the store, and the safe fixes")
    lint_scan = _command(lint_group, "scan", lint_commands.lint_scan, "findings: action or info", json_flag=True)
    lint_scan.add_argument("--report", action="store_true", help="hand every finding to the curation run")
    _command(
        lint_group,
        "fix",
        lint_commands.lint_fix,
        "remove identical conflict copies, old temp files",
        True,
        curator=True,
    )

    setup_group = _group(commands, "setup", "set this machine up, for a new store or one that exists")
    inspect = _command(setup_group, "inspect", setup_commands.setup_inspect, "what the store holds", json_flag=True)
    inspect.add_argument("--store-backend", choices=setup_commands.STORE_BACKENDS)
    inspect.add_argument("--store-path", help="the store folder; the configured store without it")
    _command(setup_group, "apply", setup_commands.setup_apply, "write the answers", json_flag=True).add_argument(
        "--answers", required=True, action=_Once, help="a JSON object, or - to read it from standard input"
    )
    _command(commands, "doctor", doctor_command.doctor, "check every backend", json_flag=True)
    _command(commands, "status", status_commands.status_command, "inbox, curation run, backends", json_flag=True)
    band_command = _command(
        commands, "band", band_commands.band_command, "what the band above the prompt shows, as JSON", json_flag=True
    )
    band_command.add_argument("--tasks-only", action="store_true", help="only the curator tasks, nothing else")

    launcher = _group(commands, "launcher", "the launcher in ~/.local/bin")
    _command(launcher, "install", launcher_commands.launcher_install, "write or refresh the launcher")
    _command(launcher, "resolve", launcher_commands.launcher_resolve, "print a plugin's install path").add_argument(
        "plugin"
    )

    hook = commands.add_parser("hook", description="run a session hook; always exits 0")
    hook.add_argument("name")
    commands.metavar = "{" + ",".join(action.dest for action in commands._choices_actions) + "}"
    return parser


if __name__ == "__main__":
    sys.exit(main())
