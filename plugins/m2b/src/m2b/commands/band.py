"""``band``: everything the band above the prompt shows, in one call.

The band refreshes about once a minute in every open session, so this answer reaches and reads the
task list once and sorts it by marker, instead of one list per marker, and hands the same probe of
the task list to the status part, which would otherwise probe it again. The status part is the
answer of ``status --json``; its backend probes stay cached for five minutes, so at most every
five minutes the calendar is probed too, here within ``CALENDAR_BUDGET_SECONDS`` whatever the
configured timeout, so a hanging calendar costs the band a few seconds and is cached as not
reachable instead of making the band's answer run past the band's own time limit.

A task list that cannot be read is named in ``tasks.error``; the status part still answers.
``tasks.due`` holds the owner's own tasks due today or overdue, from the same look at the list,
unless ``band.due_tasks`` in the machine config is off.
``tasks.review`` holds, while a review task is open, the changes of the facts it names as data:
each with its fact file, a short topic, the whole lines before and after and the words that
differ, the copy of ``memory/`` from before the run, and the review's paragraphs these stand for,
so the band can draw them readably and leave the rest of the review as written.
``version`` is this core's: the launcher always runs the installed one, while a session keeps the
band it loaded, so the band compares the two and asks for a reload when they differ.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import difflib
import re
from typing import Any

from m2b.commands import Context
from m2b.commands.backends import configured_tasks
from m2b.commands.doctor import NOT_REACHABLE, PROBE_FAILURES, REACHABLE, Check
from m2b.commands.output import print_json
from m2b.commands.status import status_answer
from m2b.commands.tasks import task_json
from m2b.config.machine import MachineConfig, load_machine_config
from m2b.curate import machine_state, memory_guard
from m2b.curate.report import one_line
from m2b.launcher import core_version
from m2b.notes.memory_index import parse_fact_line
from m2b.tasks import markers
from m2b.tasks.base import Task
from m2b.todos import due_by_today

# The configured calendar timeout (20 seconds by default) may be longer; the band's answer is waited for.
CALENDAR_BUDGET_SECONDS = 10


def band_command(arguments: argparse.Namespace, context: Context) -> int:
    """Always JSON: the band is its only reader; ``--json`` is accepted like elsewhere. ``--tasks-only``
    leaves the status out, for the band's second look before a keep or drop."""
    config = load_machine_config(context.machine)
    tasks, tasks_check = _tasks_part(config, context, datetime.datetime.now().astimezone())
    if arguments.tasks_only:
        print_json({"tasks": tasks})
        return 0
    status = status_answer(_short_calendar(config), context, tasks_check)
    print_json({"version": core_version(), "tasks": tasks, "status": status})
    return 0


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
        "questions": marked(markers.CURRENT),
        "reviews": marked(markers.REVIEW),
    }
    if config.band.due_tasks:
        part["due"] = _due(open_tasks, moment)
    if part["reviews"]:
        part["review"] = _review_changes(context)
    return part, Check("tasks", REACHABLE)


# A word, a run of spaces or one other character: brackets and commas are parts of their own, so
# a name followed by a comma before and a bracket after still counts as kept. The parts join to the
# statement again.
_PARTS = re.compile(r"\w+|\s+|[^\w\s]")
# The statement up to its first comma, bracket or dash: what it is about.
_TOPIC = re.compile(r"^(?P<topic>[^,(\u2014]+?)\s*(?:[,(\u2014]|\Z)")


def _review_changes(context: Context) -> dict[str, Any]:
    """The changes of the facts the open review names, as the last run kept them for it."""
    changes: list[dict[str, Any]] = []
    copy: dict[str, Any] | None = None
    paragraphs: list[str] = []
    for finding in machine_state.load_memory_changes(context.machine):
        change = finding.change
        if change is None:
            continue
        paragraphs.append(f"{finding.step}: {one_line(finding.text)}")
        if change.get("kind") == memory_guard.COPY:
            captures = change.get("captures")
            copy = {
                "path": str(change.get("path", "")),
                "captures": [str(name) for name in captures] if isinstance(captures, list) else [],
            }
            continue
        changes.append(_change_json(change))
    return {"changes": changes, "copy": copy, "paragraphs": paragraphs}


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
