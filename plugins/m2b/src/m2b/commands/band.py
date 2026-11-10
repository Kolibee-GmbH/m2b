"""``band``: everything the band above the prompt shows, in one call.

The band refreshes about once a minute in every open session, so this answer reaches and reads the
task list once and sorts it by marker, instead of one list per marker, and hands the same probe of
the task list to the status part, which would otherwise probe it again. The status part is the
answer of ``status --json``; its backend probes stay cached for five minutes, so at most every
five minutes the calendar is probed too, here within ``CALENDAR_BUDGET_SECONDS`` whatever the
configured timeout, so a hanging calendar costs the band a few seconds and is cached as not
reachable instead of making the band's answer run past the band's own time limit.

A task list that cannot be read is named in ``tasks.error``; the status part still answers.
"""

from __future__ import annotations

import argparse
import dataclasses
from typing import Any

from m2b.commands import Context
from m2b.commands.backends import configured_tasks
from m2b.commands.doctor import NOT_REACHABLE, PROBE_FAILURES, REACHABLE, Check
from m2b.commands.output import print_json
from m2b.commands.status import status_answer
from m2b.commands.tasks import task_json
from m2b.config.machine import MachineConfig, load_machine_config
from m2b.tasks import markers

# The configured calendar timeout (20 seconds by default) may be longer; the band's answer is waited for.
CALENDAR_BUDGET_SECONDS = 10


def band_command(arguments: argparse.Namespace, context: Context) -> int:
    """Always JSON: the band is its only reader; ``--json`` is accepted like elsewhere. ``--tasks-only``
    leaves the status out, for the band's second look before a keep or drop."""
    config = load_machine_config(context.machine)
    tasks, tasks_check = _tasks_part(config, context)
    if arguments.tasks_only:
        print_json({"tasks": tasks})
        return 0
    print_json({"tasks": tasks, "status": status_answer(_short_calendar(config), context, tasks_check)})
    return 0


def _short_calendar(config: MachineConfig) -> MachineConfig:
    """The band waits for this answer, so its calendar probe keeps to a budget of its own."""
    seconds = min(config.calendar.timeout_seconds, CALENDAR_BUDGET_SECONDS)
    return dataclasses.replace(config, calendar=dataclasses.replace(config.calendar, timeout_seconds=seconds))


def _tasks_part(config: MachineConfig, context: Context) -> tuple[dict[str, Any], Check]:
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

    part = {
        "candidates": marked(markers.CANDIDATE),
        "questions": marked(markers.CURRENT),
        "reviews": marked(markers.REVIEW),
    }
    return part, Check("tasks", REACHABLE)
