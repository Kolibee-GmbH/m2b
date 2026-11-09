"""The calendar: every read and every new event goes through ``Calendar``.

``Calendar`` keeps the rules every backend shares, so a backend only reaches its store and
translates. Drafts are checked before a backend sees them. Every event needs a named, writable
calendar and is never filled into the system default, where a private event could land in a
work calendar. The same meeting seen in several accounts is one event.
An all-day event ends at midnight of the day after its last day. A new event is read back and
compared with its draft before success is reported. A store without any calendar could not be
looked at; it is never an empty calendar.
"""

from __future__ import annotations

import datetime
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

MAX_TITLE_LENGTH = 200
DEFAULT_DURATION = datetime.timedelta(hours=1)
# EventKit cuts a longer query short without saying so, which reads like a quiet calendar.
MAX_WINDOW = datetime.timedelta(days=4 * 365)


class CalendarError(Exception):
    """A calendar call failed."""


class CalendarUnreachableError(CalendarError):
    """The calendar could not be asked: no access, no calendars, no answer in time."""


class CalendarChoiceError(CalendarError):
    """The calendar for a new event is missing, unknown, read-only or ambiguous.

    ``candidates`` are the calendars to choose from: every writable one, or the ones an
    ambiguous name matches.
    """

    def __init__(self, message: str, candidates: Sequence[CalendarInfo]) -> None:
        super().__init__(message)
        self.candidates = tuple(candidates)


class EventMismatchError(CalendarError):
    """The new event was saved but not confirmed as asked; it exists, so trying again would add a second one."""


class CalendarNotConfigured(Exception):
    """This machine has no calendar backend; an answer of its own, neither a failure nor "no events"."""


@dataclass(frozen=True)
class CalendarInfo:
    id: str
    name: str
    account: str
    writable: bool

    @property
    def label(self) -> str:
        return f"{self.account}/{self.name}"


@dataclass(frozen=True)
class Event:
    """An event in local time; ``sources`` names every ``account/calendar`` it was seen in."""

    title: str
    start: datetime.datetime
    end: datetime.datetime
    all_day: bool
    sources: tuple[str, ...]


@dataclass(frozen=True)
class EventDraft:
    """A checked new event; build it with ``timed`` or ``for_days``."""

    title: str
    start: datetime.datetime
    end: datetime.datetime
    all_day: bool

    @classmethod
    def timed(cls, title: str, start: datetime.datetime, end: datetime.datetime | None = None) -> EventDraft:
        """Naive times are local; without an end the event lasts an hour, and an end equal to the start is kept."""
        begins = _local(start)
        ends = begins + DEFAULT_DURATION if end is None else _local(end)
        if ends < begins:
            raise ValueError(f"the event ends ({ends.isoformat()}) before it starts ({begins.isoformat()})")
        return cls(_title(title), begins, ends, all_day=False)

    @classmethod
    def for_days(cls, title: str, first_day: datetime.date, end_day: datetime.date | None = None) -> EventDraft:
        """An all-day event from ``first_day`` up to, not including, ``end_day``; one day without it."""
        for day in (first_day, end_day):
            if isinstance(day, datetime.datetime):
                raise TypeError(f"an all-day event takes dates, not times: {day.isoformat()}")
        ends = first_day + datetime.timedelta(days=1) if end_day is None else end_day
        if ends <= first_day:
            raise ValueError(f"an all-day event from {first_day} must end after it, not on {ends}")
        return cls(_title(title), local_midnight(first_day), local_midnight(ends), all_day=True)


@dataclass(frozen=True)
class StoredEvent:
    """A new event as its store holds it after saving."""

    id: str
    title: str
    start: datetime.datetime
    end: datetime.datetime
    all_day: bool
    calendar_id: str


@dataclass(frozen=True)
class CreatedEvent:
    """A new event that was read back and matches its draft."""

    id: str
    title: str
    start: datetime.datetime
    end: datetime.datetime
    all_day: bool
    calendar: CalendarInfo


class CalendarBackend(ABC):
    """Reaches one calendar store; ``Calendar`` adds the shared rules on top.

    ``access_hint`` tells the user how to give this backend access; it is added to the error
    when the store shows no calendar at all.
    """

    access_hint = ""

    @abstractmethod
    def check_access(self) -> None:
        """Raises ``CalendarUnreachableError`` unless the store may be read and written."""

    @abstractmethod
    def calendars(self) -> list[CalendarInfo]:
        """Every calendar of the store, read-only ones included."""

    @abstractmethod
    def events(self, start: datetime.datetime, end: datetime.datetime) -> list[Event]:
        """Events of every calendar that overlap the window, recurrences expanded, one source each."""

    @abstractmethod
    def create_event(self, calendar_id: str, draft: EventDraft) -> StoredEvent:
        """Saves the draft into that calendar and reads it back from the store."""


class Calendar:
    def __init__(self, backend: CalendarBackend) -> None:
        self._backend = backend

    def check_access(self) -> None:
        self._backend.check_access()

    def calendars(self) -> list[CalendarInfo]:
        found = self._backend.calendars()
        if not found:
            hint = f"; {self._backend.access_hint}" if self._backend.access_hint else ""
            raise CalendarUnreachableError(f"the calendar store answered with no calendars at all{hint}")
        return found

    def writable_calendars(self) -> list[CalendarInfo]:
        return [info for info in self.calendars() if info.writable]

    def events(self, start: datetime.datetime, end: datetime.datetime) -> list[Event]:
        """Events overlapping ``[start, end)``, a meeting seen in several accounts once, by start and title."""
        begins, ends = _local(start), _local(end)
        if ends <= begins:
            raise ValueError(f"the window must end after it starts: {begins.isoformat()} to {ends.isoformat()}")
        if ends - begins > MAX_WINDOW:
            raise ValueError(f"a window spans at most {MAX_WINDOW.days} days")
        self.calendars()
        return _merged(self._backend.events(begins, ends))

    def events_on_days(self, first_day: datetime.date, last_day: datetime.date) -> list[Event]:
        """Events on the days from ``first_day`` through ``last_day``, both included."""
        return self.events(*day_window(first_day, last_day))

    def create_event(self, calendar: str | None, draft: EventDraft) -> CreatedEvent:
        """Creates the event in the named calendar and reports it as the store holds it.

        ``calendar`` is a writable calendar's id, its name, ``account/name`` or ``name (account)``,
        compared without case and surrounding spaces. Missing, unknown, read-only and ambiguous
        names are refused before anything is written, with the calendars to choose from.
        """
        target = self._resolve(calendar)
        stored = self._backend.create_event(target.id, draft)
        asked = (draft.title, draft.start, draft.end, draft.all_day, target.id)
        if (stored.title, stored.start, stored.end, stored.all_day, stored.calendar_id) != asked:
            raise EventMismatchError(
                f"the event {stored.id} was saved, but the store holds {stored.title!r} from "
                f"{stored.start.isoformat()} to {stored.end.isoformat()} (all day: {stored.all_day}) in "
                f"{stored.calendar_id} instead of {draft.title!r} from {draft.start.isoformat()} to "
                f"{draft.end.isoformat()} (all day: {draft.all_day}) in {target.id}; check it in the calendar"
            )
        return CreatedEvent(stored.id, stored.title, stored.start, stored.end, stored.all_day, target)

    def _resolve(self, reference: str | None) -> CalendarInfo:
        calendars = self.calendars()
        writable = [info for info in calendars if info.writable]
        if not writable:
            raise CalendarChoiceError("there is no writable calendar to put the event in", ())
        wanted = (reference or "").strip()
        listed = ", ".join(info.label for info in writable)
        if not wanted:
            raise CalendarChoiceError(f"no calendar named for the event; writable calendars: {listed}", writable)
        matches = [info for info in calendars if _names(info, wanted)]
        hits = [info for info in matches if info.writable]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            choices = ", ".join(info.label for info in hits)
            raise CalendarChoiceError(f"the calendar {wanted!r} is ambiguous; it names {choices}", hits)
        problem = "is read-only" if matches else "is not a writable calendar"
        raise CalendarChoiceError(f"the calendar {wanted!r} {problem}; writable calendars: {listed}", writable)


def local_midnight(day: datetime.date) -> datetime.datetime:
    """The start of ``day`` in local time."""
    return datetime.datetime.combine(day, datetime.time()).astimezone()


def day_window(first_day: datetime.date, last_day: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    """From local midnight of ``first_day`` to local midnight after ``last_day``."""
    if last_day < first_day:
        raise ValueError(f"the last day {last_day} comes before the first day {first_day}")
    return local_midnight(first_day), local_midnight(last_day + datetime.timedelta(days=1))


def _local(moment: datetime.datetime) -> datetime.datetime:
    """Whole seconds in local time; a naive time is taken as local."""
    return moment.replace(microsecond=0).astimezone()


def _title(title: str) -> str:
    trimmed = title.strip()
    if not trimmed or "\n" in trimmed or "\r" in trimmed:
        raise ValueError("an event title is one non-empty line")
    if len(trimmed) > MAX_TITLE_LENGTH:
        raise ValueError(f"an event title has at most {MAX_TITLE_LENGTH} characters, this one {len(trimmed)}")
    return trimmed


def _names(info: CalendarInfo, wanted: str) -> bool:
    if info.id == wanted:
        return True
    folded = wanted.casefold()
    spellings = (info.name, info.label, f"{info.name} ({info.account})")
    return any(spelling.strip().casefold() == folded for spelling in spellings)


def _merged(events: list[Event]) -> list[Event]:
    """One event per title and start: sources joined, the latest end kept, all-day as first seen."""
    by_key: dict[tuple[str, datetime.datetime], Event] = {}
    for event in events:
        key = (event.title, event.start)
        seen = by_key.get(key)
        if seen is None:
            by_key[key] = event
            continue
        by_key[key] = Event(
            title=seen.title,
            start=seen.start,
            end=max(seen.end, event.end),
            all_day=seen.all_day,
            sources=tuple(sorted({*seen.sources, *event.sources})),
        )
    return sorted(by_key.values(), key=lambda event: (event.start, event.title))
