"""Todos: the owner's open tasks grouped by due date, and today's events, for the skill to present.

Curator tasks (the review task and memory candidates) are left out; a follow-up task from a
capture is the owner's and stays. Tasks that cannot be reached raise, so "could not look" never
reads as "nothing open"; a task file that can be read but holds no task is named in ``unreadable``
for the same reason. The calendar is optional: without a backend its events are "not
configured", and a calendar that cannot be read leaves the tasks standing and says so.
"""

from __future__ import annotations

import dataclasses
import datetime
from dataclasses import dataclass

from m2b.calendar.base import Calendar, CalendarError, CalendarNotConfigured, Event
from m2b.tasks import markers
from m2b.tasks.base import Due, Task, Tasks

DUE_SOON_DAYS = 7
CURATOR_MARKERS = markers.CURATOR

EVENTS_OK = "ok"
EVENTS_NOT_CONFIGURED = "not configured"
EVENTS_UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class TodayEvents:
    state: str
    events: list[Event]
    message: str = ""


@dataclass(frozen=True)
class TodoReport:
    today: datetime.date
    overdue: list[Task]
    due_soon: list[Task]
    later: list[Task]
    without_date: list[Task]
    events: TodayEvents
    # Task files left out because they hold no task: path and reason.
    unreadable: list[tuple[str, str]] = dataclasses.field(default_factory=list)


def todos(tasks: Tasks, calendar: Calendar, now: datetime.datetime) -> TodoReport:
    """``now`` is timezone-aware; a task due at a time is overdue once that time has passed.

    A task due on a day is overdue from the next day on. "Due within 7 days" runs from today
    through the same weekday next week; anything after that is ``later``. The reported tasks
    carry a due time in local time.
    """
    tasks.check_reachable()
    today = now.date()
    last_soon_day = today + datetime.timedelta(days=DUE_SOON_DAYS)
    overdue: list[Task] = []
    due_soon: list[Task] = []
    later: list[Task] = []
    without_date: list[Task] = []
    for found in tasks.items():
        if found.marker in CURATOR_MARKERS:
            continue
        task = dataclasses.replace(found, due=_local(found.due))
        if task.due is None:
            without_date.append(task)
        elif _is_overdue(task.due, now):
            overdue.append(task)
        elif _day_of(task.due) <= last_soon_day:
            due_soon.append(task)
        else:
            later.append(task)
    return TodoReport(
        today=today,
        overdue=_by_due(overdue),
        due_soon=_by_due(due_soon),
        later=_by_due(later),
        without_date=sorted(without_date, key=lambda task: task.title.casefold()),
        events=_events_on(calendar, today),
        unreadable=tasks.unreadable(),
    )


def _events_on(calendar: Calendar, today: datetime.date) -> TodayEvents:
    try:
        return TodayEvents(EVENTS_OK, calendar.events_on_days(today, today))
    except CalendarNotConfigured as answer:
        return TodayEvents(EVENTS_NOT_CONFIGURED, [], str(answer))
    except CalendarError as error:
        return TodayEvents(EVENTS_UNREACHABLE, [], str(error))


def _local(due: Due | None) -> Due | None:
    return due.astimezone() if isinstance(due, datetime.datetime) else due


def due_by_today(found: list[Task], now: datetime.datetime) -> list[tuple[Task, bool]]:
    """The owner's own tasks due today, at any time of it, or overdue, the earliest first, each
    with whether it is overdue; due times in local time, as the report gives them."""
    due = []
    for task in found:
        if task.marker in CURATOR_MARKERS or task.due is None:
            continue
        task = dataclasses.replace(task, due=_local(task.due))
        assert task.due is not None
        if _is_overdue(task.due, now) or _day_of(task.due) <= now.date():
            due.append(task)
    return [(task, _is_overdue(task.due, now)) for task in _by_due(due) if task.due is not None]


def _is_overdue(due: Due, now: datetime.datetime) -> bool:
    if isinstance(due, datetime.datetime):
        return due < now
    return due < now.date()


def _day_of(due: Due) -> datetime.date:
    return due.date() if isinstance(due, datetime.datetime) else due


def _sort_key(task: Task) -> tuple[datetime.date, datetime.time, str]:
    assert task.due is not None
    time_of_day = task.due.time() if isinstance(task.due, datetime.datetime) else datetime.time.min
    return _day_of(task.due), time_of_day, task.title.casefold()


def _by_due(found: list[Task]) -> list[Task]:
    return sorted(found, key=_sort_key)
