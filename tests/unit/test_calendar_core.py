"""The rules ``Calendar`` keeps for every backend, tested over an in-memory backend."""

from __future__ import annotations

import dataclasses
import datetime
import unittest
from pathlib import Path

from calendar_contract import Contracts
from m2b.calendar.base import (
    Calendar,
    CalendarBackend,
    CalendarChoiceError,
    CalendarError,
    CalendarInfo,
    CalendarUnreachableError,
    Event,
    EventDraft,
    StoredEvent,
    day_window,
    local_midnight,
)

HOME = CalendarInfo(id="cal-home", name="Home", account="iCloud", writable=True)
WORK = CalendarInfo(id="cal-work", name="Calendar", account="Acme Exchange", writable=True)
PRIVATE = CalendarInfo(id="cal-private", name="Calendar", account="iCloud", writable=True)
HOLIDAYS = CalendarInfo(id="cal-holidays", name="Holidays", account="Subscribed", writable=False)


def at(hour: int, minute: int = 0, day: int = 23) -> datetime.datetime:
    return datetime.datetime(2026, 12, day, hour, minute).astimezone()


class MemoryBackend(CalendarBackend):
    """Keeps calendars and events in lists; ``shift_read_back`` simulates a store that changes an event."""

    def __init__(self, calendars: list[CalendarInfo]) -> None:
        self.infos = list(calendars)
        self.stored: list[tuple[str, Event]] = []
        self.created: list[tuple[str, EventDraft]] = []
        self.shift_read_back = datetime.timedelta(0)

    def check_access(self) -> None:
        pass

    def calendars(self) -> list[CalendarInfo]:
        return list(self.infos)

    def events(self, start: datetime.datetime, end: datetime.datetime) -> list[Event]:
        return [event for _, event in self.stored if event.start < end and event.end > start]

    def add(
        self, info: CalendarInfo, title: str, start: datetime.datetime, end: datetime.datetime, all_day: bool = False
    ) -> None:
        self.stored.append((info.id, Event(title, start, end, all_day, (info.label,))))

    def create_event(self, calendar_id: str, draft: EventDraft) -> StoredEvent:
        self.created.append((calendar_id, draft))
        (info,) = [info for info in self.infos if info.id == calendar_id]
        self.add(info, draft.title, draft.start, draft.end, draft.all_day)
        return StoredEvent(
            id=f"event-{len(self.created)}",
            title=draft.title,
            start=draft.start + self.shift_read_back,
            end=draft.end,
            all_day=draft.all_day,
            calendar_id=calendar_id,
        )


class MemoryCalendarContractTest(Contracts.CalendarContract):
    def make_calendar(self, folder: Path) -> Calendar:
        return Calendar(MemoryBackend([HOME, HOLIDAYS, CalendarInfo("cal-test", self.calendar_name, "iCloud", True)]))


class EventDraftTest(unittest.TestCase):
    def test_a_timed_draft_without_an_end_lasts_one_hour(self) -> None:
        draft = EventDraft.timed("Call Dana", at(9))

        self.assertEqual((draft.start, draft.end, draft.all_day), (at(9), at(10), False))

    def test_a_naive_time_is_read_as_local_time(self) -> None:
        draft = EventDraft.timed("Call Dana", datetime.datetime(2026, 12, 23, 9, 0))

        self.assertEqual(draft.start, at(9))
        self.assertIsNotNone(draft.start.utcoffset())

    def test_a_zero_length_event_is_what_was_said(self) -> None:
        self.assertEqual(EventDraft.timed("Reminder call", at(9), at(9)).end, at(9))

    def test_an_end_before_the_start_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            EventDraft.timed("Call Dana", at(10), at(9))

    def test_seconds_are_kept_and_microseconds_dropped(self) -> None:
        draft = EventDraft.timed("Call Dana", at(9).replace(second=30, microsecond=123456))

        self.assertEqual((draft.start.second, draft.start.microsecond), (30, 0))

    def test_an_all_day_draft_ends_at_midnight_of_the_day_after(self) -> None:
        draft = EventDraft.for_days("Holiday", datetime.date(2026, 12, 24))

        self.assertEqual(draft.start, local_midnight(datetime.date(2026, 12, 24)))
        self.assertEqual(draft.end, local_midnight(datetime.date(2026, 12, 25)))
        self.assertTrue(draft.all_day)

    def test_an_all_day_end_on_or_before_the_first_day_is_refused(self) -> None:
        for end in (datetime.date(2026, 12, 24), datetime.date(2026, 12, 23)):
            with self.subTest(end=end), self.assertRaises(ValueError):
                EventDraft.for_days("Holiday", datetime.date(2026, 12, 24), end)

    def test_a_date_with_a_time_is_no_all_day_start(self) -> None:
        with self.assertRaises(TypeError):
            EventDraft.for_days("Holiday", at(9))  # type: ignore[arg-type]

    def test_the_title_is_trimmed_and_must_be_one_line_of_at_most_200_characters(self) -> None:
        self.assertEqual(EventDraft.timed("  Call Dana  ", at(9)).title, "Call Dana")
        self.assertEqual(len(EventDraft.timed("ä" * 200, at(9)).title), 200)
        for title in ("", "   ", "ä" * 201, "Call Dana\nabout the shed"):
            with self.subTest(title=title[:20]), self.assertRaises(ValueError):
                EventDraft.timed(title, at(9))


class WindowTest(unittest.TestCase):
    def test_a_day_window_runs_from_midnight_to_midnight_after_the_last_day(self) -> None:
        start, end = day_window(datetime.date(2026, 12, 24), datetime.date(2026, 12, 26))

        self.assertEqual(start, local_midnight(datetime.date(2026, 12, 24)))
        self.assertEqual(end, local_midnight(datetime.date(2026, 12, 27)))

    def test_a_last_day_before_the_first_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            day_window(datetime.date(2026, 12, 24), datetime.date(2026, 12, 23))

    def test_an_empty_or_backwards_window_is_refused(self) -> None:
        calendar = Calendar(MemoryBackend([HOME]))
        for start, end in ((at(10), at(10)), (at(10), at(9))):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                calendar.events(start, end)

    def test_a_window_longer_than_four_years_is_refused(self) -> None:
        """EventKit silently cuts such a query short, which would read like a quiet calendar."""
        calendar = Calendar(MemoryBackend([HOME]))

        with self.assertRaises(ValueError):
            calendar.events(at(0), at(0) + datetime.timedelta(days=4 * 366))


class EventsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = MemoryBackend([WORK, PRIVATE, HOME, HOLIDAYS])
        self.calendar = Calendar(self.backend)

    def test_the_same_meeting_in_two_accounts_is_one_event_with_both_sources(self) -> None:
        """Covers: B25"""
        self.backend.add(WORK, "Planning with Acme", at(9), at(10))
        self.backend.add(PRIVATE, "Planning with Acme", at(9), at(10, 30))

        (event,) = self.calendar.events(at(0), at(23))

        self.assertEqual(event.sources, ("Acme Exchange/Calendar", "iCloud/Calendar"))
        self.assertEqual(event.end, at(10, 30), "the longer end wins: cutting a meeting short is the worse mistake")

    def test_the_same_title_at_another_time_stays_a_separate_event(self) -> None:
        self.backend.add(WORK, "Standup", at(9), at(9, 15))
        self.backend.add(WORK, "Standup", at(9, day=24), at(9, 15, day=24))

        self.assertEqual(len(self.calendar.events(at(0), at(23, day=24))), 2)

    def test_events_come_sorted_by_start_and_title(self) -> None:
        self.backend.add(HOME, "Lunch", at(12), at(13))
        self.backend.add(HOME, "Breakfast", at(8), at(9))
        self.backend.add(HOME, "Apples", at(12), at(12, 15))

        self.assertEqual(
            [event.title for event in self.calendar.events(at(0), at(23))], ["Breakfast", "Apples", "Lunch"]
        )

    def test_read_only_calendars_are_read(self) -> None:
        """Covers: B25"""
        self.backend.add(
            HOLIDAYS,
            "Christmas Eve",
            local_midnight(datetime.date(2026, 12, 24)),
            local_midnight(datetime.date(2026, 12, 25)),
            True,
        )

        (event,) = self.calendar.events_on_days(datetime.date(2026, 12, 24), datetime.date(2026, 12, 24))

        self.assertEqual((event.title, event.sources, event.all_day), ("Christmas Eve", ("Subscribed/Holidays",), True))

    def test_an_empty_window_is_an_empty_list(self) -> None:
        self.assertEqual(self.calendar.events(at(0), at(23)), [])

    def test_a_store_without_any_calendar_could_not_be_looked_at(self) -> None:
        """Covers: B24"""
        calendar = Calendar(MemoryBackend([]))

        for call in (calendar.calendars, calendar.writable_calendars, lambda: calendar.events(at(0), at(23))):
            with self.subTest(call=call), self.assertRaises(CalendarUnreachableError) as caught:
                call()
            self.assertIn("no calendars at all", str(caught.exception))
            self.assertNotIn("System Settings", str(caught.exception), "the remedy belongs to the backend")

    def test_a_backend_adds_its_own_remedy_when_no_calendar_is_seen(self) -> None:
        backend = MemoryBackend([])
        backend.access_hint = "open the calendar app once"

        with self.assertRaises(CalendarUnreachableError) as caught:
            Calendar(backend).calendars()

        self.assertTrue(str(caught.exception).endswith("; open the calendar app once"))


class CreateEventTest(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = MemoryBackend([WORK, PRIVATE, HOME, HOLIDAYS])
        self.calendar = Calendar(self.backend)
        self.draft = EventDraft.for_days("Birthday of Alex", datetime.date(2026, 12, 24))

    def test_read_only_calendars_are_not_offered_for_writing(self) -> None:
        """Covers: B25"""
        self.assertEqual(self.calendar.writable_calendars(), [WORK, PRIVATE, HOME])

    def test_a_read_only_calendar_is_refused_with_the_writable_ones(self) -> None:
        """Covers: B26"""
        with self.assertRaises(CalendarChoiceError) as caught:
            self.calendar.create_event("Holidays", self.draft)

        self.assertIn("read-only", str(caught.exception))
        self.assertEqual(caught.exception.candidates, (WORK, PRIVATE, HOME))
        self.assertEqual(self.backend.created, [])

    def test_without_a_calendar_nothing_reaches_the_backend(self) -> None:
        """Covers: X21"""
        with self.assertRaises(CalendarChoiceError) as caught:
            self.calendar.create_event(None, self.draft)

        self.assertIn("Acme Exchange/Calendar, iCloud/Calendar, iCloud/Home", str(caught.exception))
        self.assertEqual(self.backend.created, [])

    def test_a_name_two_accounts_share_is_ambiguous(self) -> None:
        with self.assertRaises(CalendarChoiceError) as caught:
            self.calendar.create_event("calendar", self.draft)

        self.assertEqual(caught.exception.candidates, (WORK, PRIVATE))
        self.assertIn("ambiguous", str(caught.exception))
        self.assertEqual(self.backend.created, [])

    def test_a_calendar_is_found_by_name_account_and_name_or_id(self) -> None:
        for reference, expected in (
            ("Home", HOME),
            (" home ", HOME),
            ("iCloud/Calendar", PRIVATE),
            ("ICLOUD/calendar", PRIVATE),
            ("Calendar (Acme Exchange)", WORK),
            ("cal-work", WORK),
        ):
            with self.subTest(reference=reference):
                created = self.calendar.create_event(reference, self.draft)
                self.assertEqual(created.calendar, expected)
                self.assertEqual(self.backend.created[-1][0], expected.id)

    def test_a_near_miss_is_refused_not_corrected(self) -> None:
        for reference in ("Hom", "Home (Acme Exchange)", "Acme/Calendar"):
            with self.subTest(reference=reference), self.assertRaises(CalendarChoiceError):
                self.calendar.create_event(reference, self.draft)

    def test_no_writable_calendar_at_all_is_said_so(self) -> None:
        calendar = Calendar(MemoryBackend([HOLIDAYS]))

        with self.assertRaises(CalendarChoiceError) as caught:
            calendar.create_event("Holidays", self.draft)

        self.assertIn("no writable calendar", str(caught.exception))
        self.assertEqual(caught.exception.candidates, ())

    def test_success_needs_the_stored_event_to_match_the_draft(self) -> None:
        """Covers: B26"""
        self.backend.shift_read_back = datetime.timedelta(hours=1)

        with self.assertRaises(CalendarError) as caught:
            self.calendar.create_event("Home", self.draft)

        self.assertIn("event-1", str(caught.exception))
        self.assertNotIsInstance(caught.exception, CalendarChoiceError)

    def test_the_created_event_carries_its_calendar(self) -> None:
        created = self.calendar.create_event("Home", self.draft)

        self.assertEqual(dataclasses.astuple(created.calendar), dataclasses.astuple(HOME))
        self.assertEqual(created.id, "event-1")


if __name__ == "__main__":
    unittest.main()
