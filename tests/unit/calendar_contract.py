"""The contract every calendar backend passes through ``Calendar``; each backend's test module runs it.

A subclass gives ``make_calendar`` a calendar store that holds one empty, writable calendar
named ``self.calendar_name`` and may hold others. Assertions look only at events in that
calendar, so a real store with the owner's own events stays out of the comparison.
"""

from __future__ import annotations

import datetime
import tempfile
import unittest
from pathlib import Path

from m2b.calendar.base import Calendar, CalendarChoiceError, Event, EventDraft, local_midnight

CHRISTMAS_EVE = datetime.date(2026, 12, 24)


class Contracts:
    """Holds the contract so that test discovery does not run it without a backend."""

    class CalendarContract(unittest.TestCase):
        calendar_name = "sb-test-calendar"

        def make_calendar(self, folder: Path) -> Calendar:
            raise NotImplementedError

        def setUp(self) -> None:
            self._temp = tempfile.TemporaryDirectory()
            self.addCleanup(self._temp.cleanup)
            self.calendar = self.make_calendar(Path(self._temp.name))

        def _in_test_calendar(self, events: list[Event]) -> list[Event]:
            return [
                event for event in events if any(source.endswith(f"/{self.calendar_name}") for source in event.sources)
            ]

        def _test_calendar_events(self, first: datetime.date, last: datetime.date) -> list[Event]:
            return self._in_test_calendar(self.calendar.events_on_days(first, last))

        def test_access_is_granted(self) -> None:
            self.calendar.check_access()

        def test_the_test_calendar_is_offered_for_writing(self) -> None:
            names = [info.name for info in self.calendar.writable_calendars()]

            self.assertIn(self.calendar_name, names)

        def test_an_all_day_event_is_created_and_read_back_with_an_exclusive_end(self) -> None:
            """Covers: B26"""
            draft = EventDraft.for_days("Bake cookies with Alex", CHRISTMAS_EVE)

            created = self.calendar.create_event(self.calendar_name, draft)

            self.assertEqual((created.title, created.all_day), ("Bake cookies with Alex", True))
            self.assertEqual(created.start, local_midnight(CHRISTMAS_EVE))
            self.assertEqual(created.end, local_midnight(datetime.date(2026, 12, 25)))
            self.assertEqual(created.calendar.name, self.calendar_name)
            (found,) = self._test_calendar_events(CHRISTMAS_EVE, CHRISTMAS_EVE)
            self.assertEqual(
                (found.title, found.start, found.end, found.all_day), (draft.title, draft.start, draft.end, True)
            )
            self.assertEqual(self._test_calendar_events(datetime.date(2026, 12, 25), datetime.date(2026, 12, 25)), [])

        def test_an_all_day_event_over_two_days_covers_both(self) -> None:
            draft = EventDraft.for_days("Visit Dana", CHRISTMAS_EVE, datetime.date(2026, 12, 26))

            created = self.calendar.create_event(self.calendar_name, draft)

            self.assertEqual(created.end, local_midnight(datetime.date(2026, 12, 26)))
            (found,) = self._test_calendar_events(datetime.date(2026, 12, 25), datetime.date(2026, 12, 25))
            self.assertEqual(found.end, local_midnight(datetime.date(2026, 12, 26)))

        def test_a_timed_event_is_created_and_read_back(self) -> None:
            start = datetime.datetime(2026, 12, 23, 10, 30).astimezone()
            draft = EventDraft.timed("Dentist", start, start + datetime.timedelta(minutes=45))

            created = self.calendar.create_event(self.calendar_name, draft)

            self.assertEqual(
                (created.title, created.start, created.end, created.all_day), ("Dentist", draft.start, draft.end, False)
            )
            (found,) = self._test_calendar_events(datetime.date(2026, 12, 23), datetime.date(2026, 12, 23))
            self.assertEqual(
                (found.title, found.start, found.end, found.all_day), ("Dentist", draft.start, draft.end, False)
            )

        def test_an_event_without_a_calendar_is_refused_with_the_writable_ones(self) -> None:
            """Covers: X21, B26"""
            draft = EventDraft.for_days("Birthday party", CHRISTMAS_EVE)

            for missing in (None, "", "   "):
                with self.subTest(calendar=missing), self.assertRaises(CalendarChoiceError) as caught:
                    self.calendar.create_event(missing, draft)
                self.assertIn(self.calendar_name, [info.name for info in caught.exception.candidates])
                self.assertIn(self.calendar_name, str(caught.exception))

            self.assertEqual(self._test_calendar_events(CHRISTMAS_EVE, CHRISTMAS_EVE), [])

        def test_an_unknown_calendar_is_refused_not_corrected(self) -> None:
            draft = EventDraft.for_days("Birthday party", CHRISTMAS_EVE)

            with self.assertRaises(CalendarChoiceError) as caught:
                self.calendar.create_event(f"{self.calendar_name}x", draft)

            self.assertIn(self.calendar_name, str(caught.exception))
            self.assertEqual(self._test_calendar_events(CHRISTMAS_EVE, CHRISTMAS_EVE), [])
