"""The ``none`` and ``apple-calendar`` backends; Apple Calendar runs against a fake ``osascript``."""

from __future__ import annotations

import datetime
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Callable
from unittest import mock

from calendar_contract import Contracts
from m2b.calendar.apple import SCRIPT, AppleCalendarBackend
from m2b.calendar.base import (
    Calendar,
    CalendarError,
    CalendarNotConfigured,
    CalendarUnreachableError,
    EventDraft,
    EventMismatchError,
    local_midnight,
)
from m2b.calendar.factory import open_calendar
from m2b.calendar.none import NoCalendarBackend
from m2b.config.machine import CalendarSettings

FAKE_OSASCRIPT = Path(__file__).resolve().parent / "fakes" / "fake_osascript.py"
TEST_CALENDAR = {"id": "CAL-TEST", "name": "sb-test-calendar", "account": "iCloud", "writable": True}
WORK = {"id": "CAL-WORK", "name": "Calendar", "account": "Acme Exchange", "writable": True}
PRIVATE = {"id": "CAL-PRIVATE", "name": "Calendar", "account": "iCloud", "writable": True}
HOLIDAYS = {"id": "CAL-HOLIDAYS", "name": "Holidays", "account": "Subscribed", "writable": False}


def ms(moment: datetime.datetime) -> int:
    return round(moment.timestamp() * 1000)


def fake_osascript(folder: Path, **state: Any) -> tuple[list[str], Path]:
    """The command of a fake ``osascript`` and its state file."""
    state_file = folder / "fake-calendar.json"
    initial = {"calendars": [TEST_CALENDAR, WORK, PRIVATE, HOLIDAYS], "events": [], **state}
    state_file.write_text(json.dumps(initial), encoding="utf-8")
    return [sys.executable, str(FAKE_OSASCRIPT), str(state_file)], state_file


class AppleCalendarContractTest(Contracts.CalendarContract):
    def make_calendar(self, folder: Path) -> Calendar:
        command, self.state_file = fake_osascript(folder)
        return Calendar(AppleCalendarBackend(command=command, timeout_seconds=10))


class AppleCalendarTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.folder = Path(self._temp.name)

    def calendar(self, timeout_seconds: float = 10, **state: Any) -> Calendar:
        command, self.state_file = fake_osascript(self.folder, **state)
        return Calendar(AppleCalendarBackend(command=command, timeout_seconds=timeout_seconds))

    def state(self) -> dict[str, Any]:
        return json.loads(self.state_file.read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    def test_the_script_ships_with_the_plugin(self) -> None:
        self.assertTrue(SCRIPT.is_file())
        self.assertEqual(SCRIPT.suffix, ".js")

    def test_calendars_carry_id_name_account_and_writable(self) -> None:
        infos = self.calendar().calendars()

        self.assertEqual(
            [(info.id, info.name, info.account, info.writable) for info in infos],
            [
                ("CAL-TEST", "sb-test-calendar", "iCloud", True),
                ("CAL-WORK", "Calendar", "Acme Exchange", True),
                ("CAL-PRIVATE", "Calendar", "iCloud", True),
                ("CAL-HOLIDAYS", "Holidays", "Subscribed", False),
            ],
        )

    def test_an_all_day_event_is_written_ending_at_the_last_second_of_its_last_day(self) -> None:
        """EventKit reads an end at midnight as exclusive; 23:59:59 is what it reports back itself."""
        calendar = self.calendar()

        calendar.create_event(
            "sb-test-calendar",
            EventDraft.for_days("Visit Dana", datetime.date(2026, 12, 24), datetime.date(2026, 12, 26)),
        )

        (request,) = [entry for entry in self.state()["requests"] if entry["op"] == "create"]
        self.assertEqual(request["start"], ms(local_midnight(datetime.date(2026, 12, 24))))
        self.assertEqual(request["end"], ms(local_midnight(datetime.date(2026, 12, 26))) - 1000)
        self.assertEqual((request["allDay"], request["calendarId"], request["title"]), (True, "CAL-TEST", "Visit Dana"))

    def test_an_all_day_event_read_with_midnight_ends_keeps_its_days(self) -> None:
        """Some stores end an all-day event at midnight of the day after, some at midnight of its own day."""
        christmas = local_midnight(datetime.date(2026, 12, 24))
        boxing_day = local_midnight(datetime.date(2026, 12, 25))
        events = [
            {
                "title": "Next-day end",
                "start": ms(christmas),
                "end": ms(boxing_day),
                "allDay": True,
                "calendarId": "CAL-HOLIDAYS",
            },
            {
                "title": "Same-day end",
                "start": ms(christmas),
                "end": ms(christmas),
                "allDay": True,
                "calendarId": "CAL-HOLIDAYS",
            },
        ]

        found = self.calendar(events=events).events_on_days(datetime.date(2026, 12, 24), datetime.date(2026, 12, 24))

        self.assertEqual(
            [(event.title, event.start, event.end) for event in found],
            [("Next-day end", christmas, boxing_day), ("Same-day end", christmas, boxing_day)],
        )

    def test_the_same_meeting_in_two_accounts_is_read_once(self) -> None:
        """Covers: B25"""
        start = datetime.datetime(2026, 12, 23, 9, 0).astimezone()
        meeting = {"title": "Planning with Acme", "start": ms(start), "end": ms(start) + 3_600_000, "allDay": False}
        events = [{**meeting, "calendarId": "CAL-WORK"}, {**meeting, "calendarId": "CAL-PRIVATE"}]

        (event,) = self.calendar(events=events).events_on_days(datetime.date(2026, 12, 23), datetime.date(2026, 12, 23))

        self.assertEqual(event.sources, ("Acme Exchange/Calendar", "iCloud/Calendar"))
        self.assertEqual(event.start, start)

    def test_an_event_without_a_title_is_untitled(self) -> None:
        start = datetime.datetime(2026, 12, 23, 9, 0).astimezone()
        events = [{"title": None, "start": ms(start), "end": ms(start), "allDay": False, "calendarId": "CAL-WORK"}]

        (event,) = self.calendar(events=events).events(start, start + datetime.timedelta(hours=1))

        self.assertEqual(event.title, "(untitled)")

    def test_a_read_only_calendar_never_reaches_the_script(self) -> None:
        """Covers: B26, X21"""
        calendar = self.calendar()

        with self.assertRaises(CalendarError):
            calendar.create_event("Holidays", EventDraft.for_days("Birthday of Alex", datetime.date(2026, 12, 24)))

        self.assertNotIn("create", [entry["op"] for entry in self.state()["requests"]])

    def test_a_store_that_moves_the_event_is_reported_with_the_stored_times(self) -> None:
        """Covers: B26"""
        calendar = self.calendar(mode="shift-read-back")

        with self.assertRaises(CalendarError) as caught:
            calendar.create_event(
                "sb-test-calendar", EventDraft.timed("Dentist", datetime.datetime(2026, 12, 23, 10, 0))
            )

        self.assertIn("EV0001", str(caught.exception))
        self.assertIn("11:00", str(caught.exception))

    def test_an_event_saved_but_not_confirmed_is_a_mismatch_never_a_reason_to_retry(self) -> None:
        for mode in ("lost-after-save", "bad-create-reply"):
            with self.subTest(mode=mode), self.assertRaises(EventMismatchError) as caught:
                self.calendar(mode=mode).create_event(
                    "sb-test-calendar", EventDraft.for_days("Party", datetime.date(2026, 12, 24))
                )
            self.assertIn("saved", str(caught.exception))

    def test_a_refused_save_is_an_error_with_the_stores_reason(self) -> None:
        with self.assertRaises(CalendarError) as caught:
            self.calendar(mode="refuse-save").create_event(
                "sb-test-calendar", EventDraft.for_days("Party", datetime.date(2026, 12, 24))
            )

        self.assertIn("refused the event", str(caught.exception))

    def test_missing_access_could_not_look(self) -> None:
        calendar = self.calendar(mode="no-access")

        for call in self._every_call(calendar):
            with self.subTest(call=call), self.assertRaises(CalendarUnreachableError) as caught:
                call()
            self.assertIn("Privacy & Security", str(caught.exception))

    def test_a_store_without_calendars_names_the_privacy_setting_once(self) -> None:
        """Covers: B24"""
        with self.assertRaises(CalendarUnreachableError) as caught:
            self.calendar(calendars=[]).calendars()

        self.assertEqual(str(caught.exception).count("Privacy & Security"), 1)

    def test_a_hanging_access_prompt_hits_the_timeout(self) -> None:
        """Covers: X4"""
        calendar = self.calendar(timeout_seconds=0.5, mode="hang")

        began = time.monotonic()
        with self.assertRaises(CalendarUnreachableError) as caught:
            calendar.check_access()

        self.assertLess(time.monotonic() - began, 10)
        self.assertIn("0.5 seconds", str(caught.exception))

    def test_a_reply_that_is_not_json_keeps_the_raw_reply(self) -> None:
        with self.assertRaises(CalendarError) as caught:
            self.calendar(mode="garbage").calendars()

        self.assertIn("this is no JSON", str(caught.exception))

    def test_a_failing_script_keeps_its_message(self) -> None:
        with self.assertRaises(CalendarError) as caught:
            self.calendar(mode="crash").calendars()

        self.assertIn("something broke", str(caught.exception))

    def test_a_reply_of_the_wrong_shape_is_an_error(self) -> None:
        start = datetime.datetime(2026, 12, 23, 9, 0).astimezone()
        end = ms(start) + 1_800_000
        for broken in (
            {"title": "x", "start": "9:00", "end": end, "allDay": False, "calendarId": "CAL-WORK"},
            {"title": "x", "start": True, "end": end, "allDay": False, "calendarId": "CAL-WORK"},
            {"title": "x", "start": ms(start), "end": end, "allDay": "no", "calendarId": "CAL-WORK"},
        ):
            with self.subTest(broken=broken), self.assertRaises(CalendarError):
                self.calendar(events=[broken]).events(start, start + datetime.timedelta(hours=1))

    def test_an_osascript_that_cannot_start_could_not_look(self) -> None:
        calendar = Calendar(AppleCalendarBackend(command=[str(self.folder / "missing-osascript")], timeout_seconds=5))

        with self.assertRaises(CalendarUnreachableError):
            calendar.check_access()

    def test_an_all_day_event_keeps_its_days_across_a_daylight_saving_change(self) -> None:
        self.addCleanup(time.tzset)
        with mock.patch.dict(os.environ, {"TZ": "Europe/Zurich"}):
            time.tzset()
            draft = EventDraft.for_days("Spring trip", datetime.date(2026, 3, 28), datetime.date(2026, 3, 30))
            created = self.calendar().create_event("sb-test-calendar", draft)

        self.assertEqual((created.start, created.end), (draft.start, draft.end))
        self.assertEqual(draft.end - draft.start, datetime.timedelta(hours=47))

    @staticmethod
    def _every_call(calendar: Calendar) -> list[Callable[[], object]]:
        start = datetime.datetime(2026, 12, 23, 9, 0).astimezone()
        return [
            calendar.check_access,
            calendar.calendars,
            lambda: calendar.events(start, start + datetime.timedelta(hours=1)),
            lambda: calendar.create_event("sb-test-calendar", EventDraft.timed("Dentist", start)),
        ]


class NoCalendarTest(unittest.TestCase):
    def test_every_call_answers_not_configured_which_is_no_error_and_no_empty_list(self) -> None:
        calendar = Calendar(NoCalendarBackend())
        start = datetime.datetime(2026, 12, 23, 9, 0).astimezone()

        for call in (
            calendar.check_access,
            calendar.calendars,
            calendar.writable_calendars,
            lambda: calendar.events(start, start + datetime.timedelta(hours=1)),
            lambda: calendar.events_on_days(datetime.date(2026, 12, 23), datetime.date(2026, 12, 23)),
            lambda: calendar.create_event("Home", EventDraft.timed("Dentist", start)),
        ):
            with self.subTest(call=call), self.assertRaises(CalendarNotConfigured) as caught:
                call()
            self.assertNotIsInstance(caught.exception, CalendarError)
            self.assertIn("not configured", str(caught.exception))


class OpenCalendarTest(unittest.TestCase):
    def test_none_opens_the_off_switch(self) -> None:
        calendar = open_calendar(CalendarSettings(backend="none"), {})

        with self.assertRaises(CalendarNotConfigured):
            calendar.check_access()

    def test_apple_calendar_runs_osascript_with_the_configured_timeout(self) -> None:
        with mock.patch("m2b.calendar.apple.subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout=b'{"ok": true}', stderr=b"")

            open_calendar(CalendarSettings(backend="apple-calendar", timeout_seconds=7), {}).check_access()

        (command,), options = run.call_args
        self.assertEqual(command[:4], ["/usr/bin/osascript", "-l", "JavaScript", str(SCRIPT)])
        self.assertEqual(json.loads(command[4])["op"], "access")
        self.assertEqual(options["timeout"], 7)


if __name__ == "__main__":
    unittest.main()
