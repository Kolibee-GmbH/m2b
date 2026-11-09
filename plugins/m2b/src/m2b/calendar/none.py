"""The ``none`` backend, the off switch: every call answers "not configured", never "no events"."""

from __future__ import annotations

import datetime
from typing import NoReturn

from m2b.calendar.base import (
    CalendarBackend,
    CalendarInfo,
    CalendarNotConfigured,
    Event,
    EventDraft,
    StoredEvent,
)

NOT_CONFIGURED = "the calendar is not configured on this machine; calendar.backend in config.json is none"


class NoCalendarBackend(CalendarBackend):
    def check_access(self) -> None:
        _not_configured()

    def calendars(self) -> list[CalendarInfo]:
        _not_configured()

    def events(self, start: datetime.datetime, end: datetime.datetime) -> list[Event]:
        _not_configured()

    def create_event(self, calendar_id: str, draft: EventDraft) -> StoredEvent:
        _not_configured()


def _not_configured() -> NoReturn:
    raise CalendarNotConfigured(NOT_CONFIGURED)
