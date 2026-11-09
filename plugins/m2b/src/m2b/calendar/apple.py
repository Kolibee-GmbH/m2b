"""The ``apple-calendar`` backend: EventKit through JavaScript for Automation, no compiled helper, so
nothing needs Xcode or a build step.

Every call runs ``osascript -l JavaScript eventkit.js <request>`` through ``_call``: one
timeout, which also covers an access prompt nobody answers, one check of the exit code, and
one JSON check that keeps the raw reply in the error. The script answers ``{"ok": ...}`` or
``{"error": {"kind", "message"}}`` with times in milliseconds since the epoch. The core ends an
all-day event at midnight after its last day. EventKit reads an end at midnight as exclusive,
widens only an all-day event whose end equals its start to that day, and reports all-day events
back ending at 23:59:59 of their last day (measured on macOS 26 on 2026-11-07),
so this module writes that last second and reads it back.
"""

from __future__ import annotations

import datetime
import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from m2b.calendar.base import (
    CalendarBackend,
    CalendarError,
    CalendarInfo,
    CalendarUnreachableError,
    Event,
    EventDraft,
    EventMismatchError,
    StoredEvent,
    local_midnight,
)

SCRIPT = Path(__file__).with_name("eventkit.js")
OSASCRIPT = "/usr/bin/osascript"
UNTITLED = "(untitled)"
_ONE_DAY = datetime.timedelta(days=1)
_ONE_SECOND = datetime.timedelta(seconds=1)
_ACCESS_HINT = "give the terminal or Claude full access to Calendars in System Settings, Privacy & Security, Calendars"


class AppleCalendarBackend(CalendarBackend):
    access_hint = _ACCESS_HINT

    def __init__(self, command: Sequence[str] = (OSASCRIPT,), timeout_seconds: float = 20) -> None:
        self._command = list(command)
        self._timeout = timeout_seconds

    def check_access(self) -> None:
        self._call({"op": "access"})

    def calendars(self) -> list[CalendarInfo]:
        return [_calendar_info(entry) for entry in _as_list(self._call({"op": "calendars"}))]

    def events(self, start: datetime.datetime, end: datetime.datetime) -> list[Event]:
        reply = self._call({"op": "events", "start": _milliseconds(start), "end": _milliseconds(end)})
        return [_event(entry) for entry in _as_list(reply)]

    def create_event(self, calendar_id: str, draft: EventDraft) -> StoredEvent:
        end = draft.end - _ONE_SECOND if draft.all_day else draft.end
        request = {
            "op": "create",
            "calendarId": calendar_id,
            "title": draft.title,
            "start": _milliseconds(draft.start),
            "end": _milliseconds(end),
            "allDay": draft.all_day,
        }
        reply = self._call(request)
        # The script answers ok only after saving, so from here on the event exists.
        try:
            if not isinstance(reply, dict):
                raise CalendarError(f"the calendar script answered a create with {reply!r:.300}")
            start, stored_end, all_day = _span(reply)
            return StoredEvent(
                id=_text(reply, "id"),
                title=_text(reply, "title"),
                start=start,
                end=stored_end,
                all_day=all_day,
                calendar_id=_text(reply, "calendarId"),
            )
        except CalendarError as error:
            raise EventMismatchError(f"the event was saved, but its answer cannot be read: {error}") from error

    def _call(self, request: dict[str, Any]) -> Any:
        command = [*self._command, "-l", "JavaScript", str(SCRIPT), json.dumps(request)]
        operation = request["op"]
        try:
            result = subprocess.run(command, capture_output=True, timeout=self._timeout)
        except subprocess.TimeoutExpired as error:
            raise CalendarUnreachableError(
                f"the calendar did not answer within {self._timeout:g} seconds; an access prompt may be waiting"
            ) from error
        except OSError as error:
            raise CalendarUnreachableError(f"osascript could not be started: {error}") from error
        stdout = result.stdout.decode("utf-8", errors="replace").strip()
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            raise CalendarError(f"the calendar script failed on {operation}: {stderr or stdout}")
        try:
            reply = json.loads(stdout)
        except ValueError as error:
            raise CalendarError(
                f"the calendar script did not answer {operation} with JSON: {stdout[:300]!r}"
            ) from error
        if not isinstance(reply, dict) or ("ok" in reply) == ("error" in reply):
            raise CalendarError(f"the calendar script answered {operation} with {stdout[:300]!r}")
        if "ok" in reply:
            return reply["ok"]
        failure = reply["error"] if isinstance(reply["error"], dict) else {}
        message = str(failure.get("message", reply["error"]))
        if failure.get("kind") == "access":
            raise CalendarUnreachableError(f"{message}; {self.access_hint}")
        if failure.get("kind") == "read-back":
            raise EventMismatchError(f"{message}; check it in the calendar before adding it again")
        raise CalendarError(f"the calendar refused {operation}: {message}")


def _as_list(reply: Any) -> list[Any]:
    if not isinstance(reply, list):
        raise CalendarError(
            f"the calendar script answered {type(reply).__name__} where a list was expected: {reply!r:.300}"
        )
    return reply


def _calendar_info(entry: Any) -> CalendarInfo:
    if not isinstance(entry, dict) or not isinstance(entry.get("writable"), bool):
        raise CalendarError(f"a calendar the script describes as {entry!r:.300}")
    return CalendarInfo(
        id=_text(entry, "id"), name=_text(entry, "name"), account=_text(entry, "account"), writable=entry["writable"]
    )


def _event(entry: Any) -> Event:
    if not isinstance(entry, dict):
        raise CalendarError(f"an event the script describes as {entry!r:.300}")
    title = entry.get("title")
    start, end, all_day = _span(entry)
    source = f"{entry.get('account') or '?'}/{entry.get('calendar') or '?'}"
    return Event(title if isinstance(title, str) and title else UNTITLED, start, end, all_day, (source,))


def _span(entry: dict[str, Any]) -> tuple[datetime.datetime, datetime.datetime, bool]:
    """Start, end and all-day of a reply; an all-day event ends at midnight after its last day.

    The last day is the day of the last second before the store's end, which reads both
    23:59:59 of the last day and midnight after it correctly; a store that ends a one-day
    event at its own midnight still gets its one day.
    """
    all_day = entry.get("allDay")
    if not isinstance(all_day, bool):
        raise CalendarError(f"an event without a clear all-day flag: {entry!r:.300}")
    start, end = _instant(entry.get("start"), entry), _instant(entry.get("end"), entry)
    if not all_day:
        return start, end, False
    first_day = start.date()
    last_day = max(first_day, (end - _ONE_SECOND).date())
    return local_midnight(first_day), local_midnight(last_day + _ONE_DAY), True


def _instant(value: object, entry: dict[str, Any]) -> datetime.datetime:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CalendarError(f"an event time that is not milliseconds since the epoch: {entry!r:.300}")
    return datetime.datetime.fromtimestamp(value / 1000, datetime.timezone.utc).astimezone()


def _text(entry: dict[str, Any], key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str):
        raise CalendarError(f"the calendar script left out {key}: {entry!r:.300}")
    return value


def _milliseconds(moment: datetime.datetime) -> int:
    return round(moment.timestamp() * 1000)
