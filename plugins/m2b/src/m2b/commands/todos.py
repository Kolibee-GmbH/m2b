"""``todos``: open tasks by due date and today's events; ``--json`` for the skill.

Nothing open and no events are said in words. The calendar part reports "not configured" and
"could not be read" as answers of their own, never as an empty list. A task file that holds no task
is named with its path and ends the command with exit 1, so a list without it never reads as all
that is open.
"""

from __future__ import annotations

import argparse
import datetime
from typing import Any

from m2b.calendar.base import local_midnight
from m2b.commands import Context
from m2b.commands.backends import configured_calendar, configured_tasks
from m2b.commands.calendar import event_json, when
from m2b.commands.output import iso, print_json
from m2b.commands.times import parse_day
from m2b.config.machine import load_machine_config
from m2b.tasks.base import Task
from m2b.todos import EVENTS_NOT_CONFIGURED, EVENTS_OK, TodayEvents, TodoReport, todos

GROUPS = (
    ("overdue", "Overdue"),
    ("due_within_7_days", "Due within 7 days"),
    ("later", "Later"),
    ("without_date", "Without date"),
)


def todos_command(arguments: argparse.Namespace, context: Context) -> int:
    now = (
        local_midnight(parse_day(arguments.today, "--today"))
        if arguments.today
        else datetime.datetime.now().astimezone()
    )
    config = load_machine_config(context.machine)
    report = todos(configured_tasks(config, context.machine), configured_calendar(config), now)
    if arguments.json:
        print_json(_as_json(report))
    else:
        _print_text(report)
    return 1 if report.unreadable else 0


def _groups(report: TodoReport) -> dict[str, list[Task]]:
    return {
        "overdue": report.overdue,
        "due_within_7_days": report.due_soon,
        "later": report.later,
        "without_date": report.without_date,
    }


def _as_json(report: TodoReport) -> dict[str, Any]:
    groups = {key: [_task_json(task) for task in found] for key, found in _groups(report).items()}
    unreadable = [{"path": path, "reason": problem} for path, problem in report.unreadable]
    return {
        "today": report.today.isoformat(),
        **groups,
        "unreadable": unreadable,
        "events": _events_json(report.events),
    }


def _task_json(task: Task) -> dict[str, Any]:
    return {"id": task.id, "title": task.title, "notes": task.notes, "due": iso(task.due)}


def _events_json(answer: TodayEvents) -> dict[str, Any]:
    if answer.state == EVENTS_NOT_CONFIGURED:
        return {"configured": False, "message": answer.message}
    if answer.state != EVENTS_OK:
        return {"configured": True, "reachable": False, "message": answer.message}
    return {"configured": True, "reachable": True, "events": [event_json(event) for event in answer.events]}


def _print_text(report: TodoReport) -> None:
    groups = _groups(report)
    # The problem starts with the file's path already.
    for _, problem in report.unreadable:
        print(f"Could not read {problem}; this task is not listed until the file is fixed.")
    if not any(groups.values()) and not report.unreadable:
        print("No open tasks.")
    for key, heading in GROUPS:
        if groups[key]:
            print(f"{heading}:")
            for task in groups[key]:
                print(f"  {iso(task.due)}  {task.title}" if task.due is not None else f"  {task.title}")
    answer = report.events
    if answer.state != EVENTS_OK:
        print(f"Calendar: {answer.message}")
    elif not answer.events:
        print("No events today.")
    else:
        print("Today:")
        for event in answer.events:
            print(f"  {when(event)}  {event.title}")
