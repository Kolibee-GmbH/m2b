"""``band``: everything the band shows, in one call.

The band refreshes about once a minute in every open session, so this answer reaches and reads the
task list once and sorts it by marker, instead of one list per marker, and hands the same probe of
the task list to the status part, which would otherwise probe it again. The status part is the
answer of ``status --json``; its backend probes stay cached for five minutes, so at most every
five minutes the calendar is probed too, here within ``CALENDAR_BUDGET_SECONDS`` whatever the
configured timeout, so a hanging calendar costs the band a few seconds and is cached as not
reachable instead of making the band's answer run past the band's own time limit.

A task list that cannot be read is named in ``tasks.error``; the status part still answers.
``tasks.due_by_today`` holds the owner's own tasks due today or overdue, from the same look at the
list, whatever the band shows of them. ``tasks.due`` holds the same tasks only while
``band.due_tasks`` is ``list``: a band from before the three values draws every task this key
names, so it stays what such a band may list.
``band`` is the machine config's section of that name as it reads, so the band need not ask for
the config: ``place``, where the band stands (``above`` the prompt, ``below`` it or above it only
while something is ``waiting``; ``null`` without an entry, where the band picks by its surface),
``due_tasks``, how the band shows the tasks due (``off``, ``count`` or ``list``), and ``topics``,
whether it names how many topics the session was given. A band from before ``place`` reads the
other two and stands where it always stood.
``tasks.review`` holds, while a review task is open, the changes of the facts it names as data:
each with its fact file, a short topic, the whole lines before and after and the words that
differ, each copy of ``memory/`` from before a run, and the review's paragraphs these stand for,
so the band can draw them readably and leave the rest of the review as written. Only changes whose
paragraph the open review still holds are named: the changes are this machine's, the review is
shared, and another machine's run may have rewritten it.
``proposals`` is the answer of ``proposals --json``: what a reading of the sessions proposed and
still waits for keep or drop, with the fields the band draws, how many answers wait for the
next run, and how many proposals sessions handed in wait for a run to take them in (null where
their folder could not be listed). A store where that cannot be looked at is named in ``proposals.error``, like the task
list in its part, and the other parts still answer: could not look is never an empty list.
``version`` is this core's: the launcher always runs the installed one, while a session keeps the
band it loaded, so the band compares the two and asks for a reload when they differ.
``session``, only with ``--session <id>``, is what m2b gave that session, as this machine noted it
when it gave it: the topics by name, each with the facts lines and current items its block held
then, and how the session's start printed the distillate. Whether the distillate is off for the
folder is said as it is now, for the folder Claude Code names as the project or else the one the
command runs in; ``distillate.folder`` names that folder as it resolves, so ``distillate off`` can
be handed the very folder the answer is about. A value that is no session id is answered in
``session.error`` and never looked
up, and so is a folder that cannot be looked at: the other parts still answer.
With ``--session-only`` the answer is that part and the version alone: every session asks it for
itself, where the rest is one answer the open sessions share, so it reaches no task list, no
calendar and no store. It needs ``--session`` and does not go with ``--tasks-only``.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import difflib
import re
from typing import Any

from m2b import topic_state
from m2b.commands import Context, UsageError
from m2b.commands.backends import configured_store, configured_tasks
from m2b.commands.doctor import NOT_REACHABLE, PROBE_FAILURES, REACHABLE, Check
from m2b.commands.output import print_json
from m2b.commands.proposals import waiting_answer
from m2b.commands.status import status_answer
from m2b.commands.tasks import task_json
from m2b.config.machine import DUE_TASKS_LIST, MachineConfig, load_machine_config
from m2b.curate import machine_state, memory_guard
from m2b.curate.report import one_line
from m2b.hook_input import project_folder
from m2b.launcher import core_version
from m2b.notes.memory_index import parse_fact_line
from m2b.proposals import ProposalsError
from m2b.tasks import markers
from m2b.tasks.base import Task
from m2b.todos import due_by_today

# The configured calendar timeout (20 seconds by default) may be longer; the band's answer is waited for.
CALENDAR_BUDGET_SECONDS = 10


def band_command(arguments: argparse.Namespace, context: Context) -> int:
    """Always JSON: the band is its only reader; ``--json`` is accepted like elsewhere. ``--tasks-only``
    leaves the status and the proposals out, for the band's second look before a keep or drop;
    ``--session-only`` leaves out everything but what the named session was given."""
    config = load_machine_config(context.machine)
    if arguments.session_only:
        if arguments.session is None:
            raise UsageError("--session-only needs --session <id>")
        if arguments.tasks_only:
            raise UsageError("--session-only does not go with --tasks-only")
        print_json({"version": core_version(), "session": _session_part(config, context, arguments.session)})
        return 0
    tasks, tasks_check = _tasks_part(config, context, datetime.datetime.now().astimezone())
    if arguments.tasks_only:
        print_json({"tasks": tasks})
        return 0
    status = status_answer(_short_calendar(config), context, tasks_check)
    waiting = _proposals_part(config, context)
    answer = {
        "version": core_version(),
        "band": dataclasses.asdict(config.band),
        "tasks": tasks,
        "proposals": waiting,
        "status": status,
    }
    if arguments.session is not None:
        answer["session"] = _session_part(config, context, arguments.session)
    print_json(answer)
    return 0


def _session_part(config: MachineConfig, context: Context, session_id: str) -> dict[str, Any]:
    """What this machine noted of the session, and whether the distillate is off where it runs.

    A session nothing was noted of (started under an m2b before the notes, its note removed after
    seven days, or without m2b's hooks) is not known and has no topics; that is not "was given
    nothing".
    """
    if not topic_state.is_session_id(session_id):
        return {"error": "not a session id"}
    noted = topic_state.session(context.machine, session_id)
    try:
        folder = project_folder(context.environ).resolve()
        off_under = config.distillate.covering(folder)
    # A working directory that was removed, or a folder whose path does not resolve.
    except (OSError, RuntimeError) as error:
        return {"error": f"the session's folder cannot be looked at: {one_line(str(error))}"}
    return {
        "id": session_id,
        "known": noted is not None,
        "topics": [
            {"name": topic.name, "facts": topic.facts, "current": topic.current}
            for topic in (noted.topics if noted is not None else ())
        ],
        "distillate": {
            "at_start": noted.distillate if noted is not None else None,
            "off_under": str(off_under) if off_under is not None else None,
            "folder": str(folder),
        },
    }


def _proposals_part(config: MachineConfig, context: Context) -> dict[str, Any]:
    try:
        return waiting_answer(configured_store(config, context.machine))
    except (*PROBE_FAILURES, ProposalsError) as error:
        return {"error": str(error)}


def _short_calendar(config: MachineConfig) -> MachineConfig:
    """The band waits for this answer, so its calendar probe keeps to a budget of its own."""
    seconds = min(config.calendar.timeout_seconds, CALENDAR_BUDGET_SECONDS)
    return dataclasses.replace(config, calendar=dataclasses.replace(config.calendar, timeout_seconds=seconds))


def _tasks_part(config: MachineConfig, context: Context, moment: datetime.datetime) -> tuple[dict[str, Any], Check]:
    """The open curator tasks by marker, and the check of the task list the status part reuses.

    The check means what ``status`` probes: whether the list can be reached. A list that is reached
    but cannot be read is named in the answer and leaves the check ``reachable``.
    """
    try:
        configured = configured_tasks(config, context.machine)
        # Without the privacy grant macOS answers an empty list with exit 0, so reach it first.
        configured.check_reachable()
    except PROBE_FAILURES as error:
        return {"error": str(error)}, Check("tasks", NOT_REACHABLE, str(error))
    try:
        open_tasks = configured.items()
    except PROBE_FAILURES as error:
        return {"error": str(error)}, Check("tasks", REACHABLE)

    def marked(kind: str) -> list[dict[str, Any]]:
        return [task_json(task) for task in open_tasks if task.marker == kind]

    part: dict[str, Any] = {
        "candidates": marked(markers.CANDIDATE),
        # Still current? and still needed? are answered alike, with keep or drop.
        "questions": marked(markers.CURRENT) + marked(markers.LESSON),
        "reviews": marked(markers.REVIEW),
    }
    due = _due(open_tasks, moment)
    part["due_by_today"] = due
    if config.band.due_tasks == DUE_TASKS_LIST:
        part["due"] = due
    if part["reviews"]:
        part["review"] = _review_changes(context, _paragraphs(part["reviews"][0].get("notes")))
    return part, Check("tasks", REACHABLE)


# A word, a run of spaces or one other character: brackets and commas are parts of their own, so
# a name followed by a comma before and a bracket after still counts as kept. The parts join to the
# statement again.
_PARTS = re.compile(r"\w+|\s+|[^\w\s]")
# The statement up to its first comma, bracket or dash: what it is about.
_TOPIC = re.compile(r"^(?P<topic>[^,(\u2014]+?)\s*(?:[,(\u2014]|\Z)")


def _paragraphs(notes: object) -> set[str]:
    """The paragraphs of a review task's notes, as the review writes them and the band splits them."""
    if not isinstance(notes, str):
        return set()
    return {paragraph.strip() for paragraph in re.split(r"\n\s*\n", notes) if paragraph.strip()}


def _review_changes(context: Context, in_review: set[str]) -> dict[str, Any]:
    """The changes of the facts the open review names, as the last runs kept them for it.

    A review open over several runs names a copy of ``memory/`` for each; the copies are listed in
    order, the captures of the steps that share one copy together.
    """
    changes: list[dict[str, Any]] = []
    copies: dict[str, list[str]] = {}
    paragraphs: list[str] = []
    for finding in machine_state.load_memory_changes(context.machine):
        change = finding.change
        paragraph = f"{finding.step}: {one_line(finding.text)}"
        if change is None or paragraph not in in_review:
            continue
        paragraphs.append(paragraph)
        if change.get("kind") == memory_guard.COPY:
            captures = change.get("captures")
            filed = copies.setdefault(str(change.get("path", "")), [])
            filed += [str(name) for name in captures if str(name) not in filed] if isinstance(captures, list) else []
            continue
        changes.append(_change_json(change))
    return {
        "changes": changes,
        "copies": [{"path": path, "captures": captures} for path, captures in copies.items()],
        "paragraphs": paragraphs,
    }


def _change_json(change: Any) -> dict[str, Any]:
    before = _statement(change.get("before"))
    after = _statement(change.get("after"))
    kind = str(change.get("kind", ""))
    file = str(change.get("file", ""))
    shown = before or after or file
    found = _TOPIC.match(shown)
    return {
        "kind": kind,
        "file": file,
        "topic": found.group("topic").strip() if found else shown,
        "before": before,
        "after": after,
        "parts": _parts(before, after),
    }


def _statement(line: object) -> str | None:
    """What a facts line states, without its dash and its fact file; the line as it is otherwise."""
    if not isinstance(line, str):
        return None
    parsed = parse_fact_line(line)
    return parsed.statement if parsed is not None else line


def _parts(before: str | None, after: str | None) -> list[dict[str, str]]:
    """The line as parts that stayed, were added or were removed, word by word."""
    if before is None or after is None:
        line = before if before is not None else after
        return [] if line is None else [{"text": line, "change": "same"}]
    old, new = _PARTS.findall(before), _PARTS.findall(after)
    parts: list[dict[str, str]] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes():
        if tag == "equal":
            parts.append({"text": "".join(new[j1:j2]), "change": "same"})
            continue
        if tag in ("delete", "replace"):
            parts.append({"text": "".join(old[i1:i2]), "change": "removed"})
        if tag in ("insert", "replace"):
            parts.append({"text": "".join(new[j1:j2]), "change": "added"})
    return parts


def _due(open_tasks: list[Task], moment: datetime.datetime) -> list[dict[str, Any]]:
    """The owner's own tasks due today or overdue, the earliest first, as ``todos`` reads due dates."""
    return [{**task_json(task), "overdue": overdue} for task, overdue in due_by_today(open_tasks, moment)]
