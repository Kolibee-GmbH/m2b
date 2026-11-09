"""Opening the calendar backend this machine's config names."""

from __future__ import annotations

from collections.abc import Mapping

from m2b.calendar.apple import OSASCRIPT, AppleCalendarBackend
from m2b.calendar.base import Calendar
from m2b.calendar.none import NoCalendarBackend
from m2b.config.machine import CalendarSettings


def open_calendar(settings: CalendarSettings, executables: Mapping[str, str]) -> Calendar:
    """The backend for these settings; Apple Calendar runs the ``osascript`` setup recorded, if any."""
    if settings.backend == "apple-calendar":
        command = [executables.get("osascript", OSASCRIPT)]
        return Calendar(AppleCalendarBackend(command=command, timeout_seconds=settings.timeout_seconds))
    return Calendar(NoCalendarBackend())
