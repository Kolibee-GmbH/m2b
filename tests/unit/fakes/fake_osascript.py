"""A stand-in for ``osascript -l JavaScript eventkit.js <request>`` that keeps a calendar store in JSON.

It answers the requests of the ``apple-calendar`` backend the way the shipped script does:
``{"ok": ...}`` or ``{"error": {"kind", "message"}}``, times in milliseconds since the epoch,
and EventKit's all-day handling as measured on macOS (2026-11-07): an all-day event covers the
days from its start through the day of the last second before its end, at least its first day,
and is read back ending at 23:59:59 of its last day. So an end at midnight after the first of
two days stores one day. The state holds ``calendars``
(``id``, ``name``, ``account``, ``writable``) and ``events`` (``title``, ``start``, ``end``,
``allDay``, ``calendarId``). Every request is appended to ``requests``. The state's ``mode``
simulates failures: ``no-access``, ``hang``, ``garbage`` (a reply that is not JSON), ``crash``
(exit 1), ``refuse-save``, ``shift-read-back`` (the store moves a new event by an hour),
``lost-after-save`` (saved, then not found again) and ``bad-create-reply`` (saved, then an answer
without the event's id).

Usage: python3 fake_osascript.py <state file> -l JavaScript <script> <request>
"""

from __future__ import annotations

import datetime
import json
import sys
import time
from pathlib import Path
from typing import Any

HOUR_MS = 3_600_000


def _answer(result: Any) -> str:
    return json.dumps({"ok": result})


def _failure(kind: str, message: str) -> str:
    return json.dumps({"error": {"kind": kind, "message": message}})


def _calendar(state: dict[str, Any], calendar_id: str) -> dict[str, Any] | None:
    return next((info for info in state["calendars"] if info["id"] == calendar_id), None)


def _all_day_end(start: int, end: int) -> int:
    """23:59:59 local time of the last day covered, counted by the calendar as EventKit does."""
    last = datetime.datetime.fromtimestamp(max(start, end - 1000) / 1000)
    return round(last.replace(hour=23, minute=59, second=59).timestamp() * 1000)


def _overlaps(event: dict[str, Any], request: dict[str, Any]) -> bool:
    """An event without a length counts in a window that starts with it; a malformed one is passed on."""
    try:
        return bool(event["start"] < request["end"] and max(event["end"], event["start"] + 1) > request["start"])
    except TypeError:
        return True


def _events(state: dict[str, Any], request: dict[str, Any]) -> list[dict[str, Any]]:
    found = []
    for event in state["events"]:
        if _overlaps(event, request):
            info = _calendar(state, event["calendarId"]) or {"name": "?", "account": "?"}
            found.append({**event, "calendar": info["name"], "account": info["account"]})
    return found


def _create(state: dict[str, Any], request: dict[str, Any]) -> str:
    info = _calendar(state, request["calendarId"])
    if info is None:
        return _failure("not-found", f"no calendar with the identifier {request['calendarId']}")
    if not info["writable"]:
        return _failure("read-only", f"the calendar {info['name']} does not allow changes")
    if state.get("mode") == "refuse-save":
        return _failure("save", "The calendar store refused the event.")
    end = _all_day_end(request["start"], request["end"]) if request["allDay"] else request["end"]
    start = request["start"] + (HOUR_MS if state.get("mode") == "shift-read-back" else 0)
    event = {
        "title": request["title"],
        "start": start,
        "end": end,
        "allDay": request["allDay"],
        "calendarId": info["id"],
    }
    state["events"].append(event)
    if state.get("mode") == "lost-after-save":
        return _failure("read-back", "the event was saved but cannot be read back")
    if state.get("mode") == "bad-create-reply":
        return _answer({"title": request["title"]})
    return _answer({"id": f"EV{len(state['events']):04d}", **event})


def main(arguments: list[str]) -> int:
    state_file = Path(arguments[0])
    if arguments[1:3] != ["-l", "JavaScript"] or not Path(arguments[3]).is_file():
        print(f"fake osascript: unexpected arguments {arguments[1:4]}", file=sys.stderr)
        return 1
    state = json.loads(state_file.read_text(encoding="utf-8"))
    request = json.loads(arguments[4])
    state.setdefault("requests", []).append(request)
    mode = state.get("mode")
    if mode == "hang":
        time.sleep(60)
    if mode == "crash":
        print("execution error: Error: something broke (-2700)", file=sys.stderr)
        return 1
    if mode == "garbage":
        reply = "this is no JSON"
    elif mode == "no-access":
        reply = _failure("access", "calendar access was not granted")
    elif request["op"] == "access":
        reply = _answer(True)
    elif request["op"] == "calendars":
        reply = _answer(state["calendars"])
    elif request["op"] == "events":
        reply = _answer(_events(state, request))
    elif request["op"] == "create":
        reply = _create(state, request)
    else:
        reply = _failure("request", f"unknown op {request['op']!r}")
    state_file.write_text(json.dumps(state), encoding="utf-8")
    print(reply)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
