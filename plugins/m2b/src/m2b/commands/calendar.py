"""``calendar list / events / add`` through ``Calendar``.

Without a calendar backend the reads answer "not configured" with exit 0, in JSON as
``{"configured": false}``, never as an empty list; ``add`` then has nothing to write into and
exits 1. With ``--all-day``, ``--end`` is the last day of the event, included.
"""

from __future__ import annotations

import argparse
import datetime
from typing import Any

from m2b.calendar.base import (
    Calendar,
    CalendarInfo,
    CalendarNotConfigured,
    CreatedEvent,
    Event,
    EventDraft,
)
from m2b.commands import Context, ProblemError, UsageError
from m2b.commands.backends import configured_calendar
from m2b.commands.output import iso, print_json
from m2b.commands.times import parse_day, parse_moment
from m2b.config.machine import load_machine_config

_ONE_DAY = datetime.timedelta(days=1)


def _calendar(context: Context) -> Calendar:
    return configured_calendar(load_machine_config(context.machine))


def calendar_list(arguments: argparse.Namespace, context: Context) -> int:
    calendar = _calendar(context)
    try:
        found = calendar.writable_calendars() if arguments.writable else calendar.calendars()
    except CalendarNotConfigured as answer:
        return _not_configured(answer, arguments.json)
    if arguments.json:
        print_json({"configured": True, "calendars": [_calendar_json(info) for info in found]})
        return 0
    for info in found:
        print(info.label if info.writable else f"{info.label} (read-only)")
    return 0


def calendar_events(arguments: argparse.Namespace, context: Context) -> int:
    first = parse_day(arguments.first, "--from") if arguments.first else datetime.date.today()
    last = parse_day(arguments.last, "--to") if arguments.last else first
    if last < first:
        raise UsageError(f"--to {last} comes before --from {first}")
    try:
        found = _calendar(context).events_on_days(first, last)
    except CalendarNotConfigured as answer:
        return _not_configured(answer, arguments.json)
    except ValueError as error:
        raise UsageError(str(error)) from error
    if arguments.json:
        print_json({"configured": True, "events": [event_json(event) for event in found]})
        return 0
    for event in found:
        print(f"{when(event)}  {event.title}")
    return 0


def calendar_add(arguments: argparse.Namespace, context: Context) -> int:
    draft = _draft(arguments)
    try:
        created = _calendar(context).create_event(arguments.calendar, draft)
    except CalendarNotConfigured as error:
        raise ProblemError(str(error)) from error
    if arguments.json:
        print_json(_created_json(created))
    else:
        print(f"created in {created.calendar.label}: {when(created)}  {created.title}")
    return 0


def _draft(arguments: argparse.Namespace) -> EventDraft:
    try:
        if arguments.all_day:
            first = parse_day(arguments.start, "--start")
            last = parse_day(arguments.end, "--end") if arguments.end else first
            if last < first:
                raise UsageError(f"--end {last} comes before --start {first}")
            return EventDraft.for_days(arguments.title, first, last + _ONE_DAY)
        start = parse_moment(arguments.start, "--start")
        end = parse_moment(arguments.end, "--end") if arguments.end else None
        return EventDraft.timed(arguments.title, start, end)
    except ValueError as error:
        raise UsageError(str(error)) from error


def _not_configured(answer: CalendarNotConfigured, as_json: bool) -> int:
    if as_json:
        print_json({"configured": False, "message": str(answer)})
    else:
        print(str(answer))
    return 0


def _calendar_json(info: CalendarInfo) -> dict[str, Any]:
    return {"id": info.id, "name": info.name, "account": info.account, "writable": info.writable}


def _span_json(start: datetime.datetime, end: datetime.datetime, all_day: bool) -> dict[str, Any]:
    span: dict[str, Any] = {"start": iso(start), "end": iso(end), "all_day": all_day}
    if all_day:
        span.update(first_day=start.date().isoformat(), last_day=(end.date() - _ONE_DAY).isoformat())
    return span


def event_json(event: Event) -> dict[str, Any]:
    return {"title": event.title, **_span_json(event.start, event.end, event.all_day), "sources": list(event.sources)}


def _created_json(created: CreatedEvent) -> dict[str, Any]:
    return {
        "id": created.id,
        "title": created.title,
        **_span_json(created.start, created.end, created.all_day),
        "calendar": created.calendar.name,
        "account": created.calendar.account,
    }


def when(event: Event | CreatedEvent) -> str:
    if event.all_day:
        last = event.end.date() - _ONE_DAY
        first = event.start.date()
        return f"{first} all day" if last == first else f"{first} to {last} all day"
    return f"{event.start:%Y-%m-%d %H:%M}-{event.end:%H:%M}"
