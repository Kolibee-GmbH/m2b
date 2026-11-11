"""``tasks list / add / complete / drop / delete / notes`` over the configured tasks backend."""

from __future__ import annotations

import argparse
import datetime
import sys
from typing import Any

from m2b import candidates
from m2b.commands import Context, UsageError
from m2b.commands.backends import configured_store, configured_tasks
from m2b.commands.candidates import candidate_prefix
from m2b.commands.output import iso, print_json
from m2b.commands.times import parse_day_or_moment
from m2b.config.machine import load_machine_config
from m2b.config.store_settings import require_store_writable
from m2b.tasks.base import Task, Tasks


def _tasks(context: Context) -> Tasks:
    return configured_tasks(load_machine_config(context.machine), context.machine)


def tasks_list(arguments: argparse.Namespace, context: Context) -> int:
    """Checks the list can be reached first: without the privacy grant macOS answers empty, with exit 0."""
    configured = _tasks(context)
    configured.check_reachable()
    found = configured.items(marker=arguments.marker, include_completed=arguments.include_completed)
    for _, problem in configured.unreadable():
        print(f"m2b: {problem}; this task is left out until the file is fixed", file=sys.stderr)
    if arguments.json:
        print_json([task_json(task) for task in found])
        return 0
    for task in found:
        due = f"  (due {iso(task.due)})" if task.due is not None else ""
        state = "  [dropped]" if task.dropped else "  [done]" if task.completed else ""
        print(f"{task.id}  {task.title}{due}{state}")
    return 0


REFUSALS = {
    candidates.OPEN: "an open candidate has the same text",
    candidates.DROPPED: "a candidate with the same text was dropped within 90 days",
}


def tasks_add(arguments: argparse.Namespace, context: Context) -> int:
    if arguments.candidate:
        return _add_candidate(arguments, context)
    due = parse_day_or_moment(arguments.due, "--due") if arguments.due else None
    try:
        task_id = _tasks(context).add(arguments.title, notes=arguments.notes, due=due)
    except ValueError as error:
        raise UsageError(str(error)) from error
    if arguments.json:
        print_json({"id": task_id})
    else:
        print(task_id)
    return 0


def _add_candidate(arguments: argparse.Namespace, context: Context) -> int:
    """A memory candidate; the same text as an open one or one dropped lately is refused, with exit 0 (B35)."""
    if arguments.notes or arguments.due:
        raise UsageError("a candidate takes no --notes or --due: its notes are its marker")
    config = load_machine_config(context.machine)
    store = configured_store(config, context.machine)
    require_store_writable(store)
    tasks = configured_tasks(config, context.machine)
    try:
        proposal = candidates.propose(store, tasks, arguments.title, candidate_prefix(store), _now())
    except ValueError as error:
        raise UsageError(str(error)) from error
    if arguments.json:
        print_json(
            {"id": proposal.task_id, "refused": proposal.refused} if proposal.refused else {"id": proposal.task_id}
        )
    elif proposal.refused:
        print(f"refused: {REFUSALS[proposal.refused]}")
    else:
        print(proposal.task_id)
    return 0


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def tasks_complete(arguments: argparse.Namespace, context: Context) -> int:
    _tasks(context).complete(arguments.id)
    return 0


def tasks_drop(arguments: argparse.Namespace, context: Context) -> int:
    _tasks(context).drop(arguments.id)
    return 0


def tasks_delete(arguments: argparse.Namespace, context: Context) -> int:
    _tasks(context).delete(arguments.id)
    return 0


def tasks_notes(arguments: argparse.Namespace, context: Context) -> int:
    _tasks(context).set_notes(arguments.id, arguments.notes)
    return 0


def task_json(task: Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "notes": task.notes,
        "due": iso(task.due),
        "completed": task.completed,
        "completed_at": iso(task.completed_at),
        "dropped": task.dropped,
        "marker": task.marker,
    }
