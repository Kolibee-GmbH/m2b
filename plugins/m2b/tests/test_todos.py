"""Todos: open tasks grouped by due date and today's events, for the skill to present."""

from __future__ import annotations

import datetime
import json
import tempfile
import unittest
from pathlib import Path

import test_commands
from m2b import cli
from m2b.calendar.base import (
    Calendar,
    CalendarBackend,
    CalendarInfo,
    CalendarUnreachableError,
    Event,
    EventDraft,
    StoredEvent,
    local_midnight,
)
from m2b.calendar.none import NoCalendarBackend
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard
from m2b.tasks import markers
from m2b.tasks.base import Task, TasksUnreachableError
from m2b.tasks.markdown import MarkdownTasks
from m2b.todos import EVENTS_NOT_CONFIGURED, EVENTS_OK, EVENTS_UNREACHABLE, todos

NOW = datetime.datetime(2026, 11, 7, 12, 0).astimezone()
TODAY = NOW.date()
HOME = CalendarInfo("CAL-HOME", "Home", "iCloud", True)


def day(offset: int) -> datetime.date:
    return TODAY + datetime.timedelta(days=offset)


def at(offset: int, hour: int) -> datetime.datetime:
    return datetime.datetime.combine(day(offset), datetime.time(hour)).astimezone()


class FakeCalendar(CalendarBackend):
    def __init__(self, events: list[Event], unreachable: bool = False) -> None:
        self._events = events
        self._unreachable = unreachable
        self.windows: list[tuple[datetime.datetime, datetime.datetime]] = []

    def check_access(self) -> None:
        pass

    def calendars(self) -> list[CalendarInfo]:
        if self._unreachable:
            raise CalendarUnreachableError("no access to the calendars; allow it in Privacy & Security")
        return [HOME]

    def events(self, start: datetime.datetime, end: datetime.datetime) -> list[Event]:
        self.windows.append((start, end))
        return list(self._events)

    def create_event(self, calendar_id: str, draft: EventDraft) -> StoredEvent:
        raise AssertionError("todos never writes")


class UnreachableTasks(MarkdownTasks):
    def check_reachable(self) -> None:
        raise TasksUnreachableError("Reminders answered with no lists at all")


class TodosTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        root = Path(self._temp.name)
        (root / "sb-test-store").mkdir()
        self.store = FolderStore(root / "sb-test-store", root / "machine-tmp", DatalessGuard(False))
        self.tasks = MarkdownTasks(self.store, now=lambda: NOW)
        self.no_calendar = Calendar(NoCalendarBackend())

    def titles(self, found: list[Task]) -> list[str]:
        return [task.title for task in found]

    def test_open_tasks_are_grouped_overdue_within_seven_days_later_and_without_date(self) -> None:
        self.tasks.add("Return the drill to Alex", due=day(-2))
        self.tasks.add("Pay the shed invoice", due=day(7))
        self.tasks.add("Book the dentist", due=day(0))
        self.tasks.add("Renew the passport", due=day(8))
        self.tasks.add("Sort the photos")
        self.tasks.add("Call Dana about the maps", due=day(-1))

        report = todos(self.tasks, self.no_calendar, NOW)

        self.assertEqual(report.today, TODAY)
        self.assertEqual(self.titles(report.overdue), ["Return the drill to Alex", "Call Dana about the maps"])
        self.assertEqual(self.titles(report.due_soon), ["Book the dentist", "Pay the shed invoice"])
        self.assertEqual(self.titles(report.later), ["Renew the passport"])
        self.assertEqual(self.titles(report.without_date), ["Sort the photos"])

    def test_a_task_due_earlier_today_at_a_time_is_overdue_and_one_due_later_today_is_not(self) -> None:
        self.tasks.add("Morning call with Acme", due=at(0, 9))
        self.tasks.add("Evening run", due=at(0, 18))
        self.tasks.add("Lunch with Dana", due=day(0))

        report = todos(self.tasks, self.no_calendar, NOW)

        self.assertEqual(self.titles(report.overdue), ["Morning call with Acme"])
        self.assertEqual(self.titles(report.due_soon), ["Lunch with Dana", "Evening run"])

    def test_a_task_timed_for_midnight_today_is_overdue_at_noon(self) -> None:
        self.tasks.add("Night shift handover", due=at(0, 0))

        report = todos(self.tasks, self.no_calendar, NOW)

        self.assertEqual(self.titles(report.overdue), ["Night shift handover"])

    def test_a_due_time_reported_in_utc_comes_out_in_local_time(self) -> None:
        self.tasks.add("Call with Acme", due=at(2, 15).astimezone(datetime.timezone.utc))

        (task,) = todos(self.tasks, self.no_calendar, NOW).due_soon

        self.assertEqual(task.due.isoformat() if task.due else None, at(2, 15).isoformat())

    def test_curator_tasks_are_left_out_and_a_follow_up_from_a_capture_stays(self) -> None:
        self.tasks.add("Review the last run", notes=markers.with_marker(markers.REVIEW, "3 notes filed"))
        self.tasks.add("Keep: Dana likes maps?", notes=markers.with_marker(markers.CANDIDATE, "", "c1"))
        question = markers.with_marker(markers.CURRENT, "", "1a2b3c4d5e6f")
        self.tasks.add("Still current? Planning the trip", notes=question)
        self.tasks.add(
            "Call Dana about the shed",
            notes=markers.marker_line(markers.CAPTURE, "20261107T101500Z-cli-a1b2.md", "follow-up"),
            due=day(3),
        )

        report = todos(self.tasks, self.no_calendar, NOW)

        self.assertEqual(self.titles(report.due_soon), ["Call Dana about the shed"])
        self.assertEqual((report.overdue, report.later, report.without_date), ([], [], []))

    def test_completed_and_dropped_tasks_are_not_listed(self) -> None:
        self.tasks.complete(self.tasks.add("Done already", due=day(-1)))
        self.tasks.drop(self.tasks.add("Not doing this"))

        report = todos(self.tasks, self.no_calendar, NOW)

        self.assertEqual((report.overdue, report.due_soon, report.later, report.without_date), ([], [], [], []))

    def test_without_a_calendar_backend_events_are_not_configured_never_none(self) -> None:
        report = todos(self.tasks, self.no_calendar, NOW)

        self.assertEqual(report.events.state, EVENTS_NOT_CONFIGURED)
        self.assertIn("not configured", report.events.message)

    def test_today_s_events_are_read_for_the_whole_local_day(self) -> None:
        dentist = Event("Dentist", at(0, 10), at(0, 11), False, ("iCloud/Home",))
        backend = FakeCalendar([dentist])

        report = todos(self.tasks, Calendar(backend), NOW)

        self.assertEqual(report.events.state, EVENTS_OK)
        self.assertEqual(report.events.events, [dentist])
        self.assertEqual(backend.windows, [(local_midnight(TODAY), local_midnight(day(1)))])

    def test_a_calendar_that_cannot_be_read_keeps_the_tasks_and_says_so(self) -> None:
        self.tasks.add("Book the dentist", due=day(0))

        report = todos(self.tasks, Calendar(FakeCalendar([], unreachable=True)), NOW)

        self.assertEqual(self.titles(report.due_soon), ["Book the dentist"])
        self.assertEqual(report.events.state, EVENTS_UNREACHABLE)
        self.assertIn("Privacy & Security", report.events.message)

    def test_tasks_that_cannot_be_reached_raise_instead_of_an_empty_list(self) -> None:
        with self.assertRaises(TasksUnreachableError):
            todos(UnreachableTasks(self.store), self.no_calendar, NOW)


class TodosCommandTest(test_commands.CommandTest):
    def add_event_today(self, title: str, hour: int) -> None:
        start = datetime.datetime.combine(datetime.date.today(), datetime.time(hour)).astimezone()
        state = json.loads(self.calendar_state.read_text(encoding="utf-8"))
        state["events"].append(
            {
                "title": title,
                "start": test_commands.ms(start),
                "end": test_commands.ms(start) + 3_600_000,
                "allDay": False,
                "calendarId": "CAL-HOME",
            }
        )
        self.calendar_state.write_text(json.dumps(state), encoding="utf-8")

    def test_json_groups_the_tasks_and_carries_today_s_events(self) -> None:
        self.set_up()
        self.run_command("tasks", "add", "Return the drill to Alex", "--due", "2026-11-05")
        self.run_command("tasks", "add", "Pay the shed invoice", "--due", "2026-11-10")
        self.run_command("tasks", "add", "Renew the passport", "--due", "2026-12-01")
        self.run_command("tasks", "add", "Sort the photos")
        self.add_event_today("Dentist", 10)

        answer = self.run_json("todos", "--today", "2026-11-07")

        self.assertEqual(answer["today"], "2026-11-07")
        self.assertEqual([task["title"] for task in answer["overdue"]], ["Return the drill to Alex"])
        self.assertEqual([task["due"] for task in answer["due_within_7_days"]], ["2026-11-10"])
        self.assertEqual([task["title"] for task in answer["later"]], ["Renew the passport"])
        self.assertEqual([task["title"] for task in answer["without_date"]], ["Sort the photos"])
        self.assertEqual(set(answer["overdue"][0]), {"id", "title", "notes", "due"})
        events = answer["events"]
        self.assertEqual((events["configured"], events["reachable"]), (True, True))

    def test_today_s_events_are_those_of_the_real_day_without_today(self) -> None:
        self.set_up()
        self.add_event_today("Dentist", 10)

        events = self.run_json("todos")["events"]

        self.assertEqual([event["title"] for event in events["events"]], ["Dentist"])

    def test_text_lists_each_group_and_the_events(self) -> None:
        self.set_up()
        self.run_command("tasks", "add", "Return the drill to Alex", "--due", "2026-11-05")
        self.run_command("tasks", "add", "Sort the photos")

        code, out, err = self.run_command("todos", "--today", "2026-11-07")

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertIn("Overdue:\n  2026-11-05  Return the drill to Alex\n", out)
        self.assertIn("Without date:\n  Sort the photos\n", out)
        self.assertIn("No events today.", out)

    def test_nothing_open_is_said_in_words(self) -> None:
        self.set_up(calendar="none")

        code, out, _ = self.run_command("todos")

        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("No open tasks.", out)
        self.assertIn("not configured", out)

    def test_without_a_calendar_backend_json_says_not_configured(self) -> None:
        self.set_up(calendar="none")

        events = self.run_json("todos")["events"]

        self.assertFalse(events["configured"])
        self.assertNotIn("events", events)

    def test_a_calendar_without_access_keeps_the_tasks_and_reports_it(self) -> None:
        self.set_up()
        self.run_command("tasks", "add", "Sort the photos")
        state = json.loads(self.calendar_state.read_text(encoding="utf-8"))
        self.calendar_state.write_text(json.dumps({**state, "mode": "no-access"}), encoding="utf-8")

        answer = self.run_json("todos")

        self.assertEqual([task["title"] for task in answer["without_date"]], ["Sort the photos"])
        self.assertEqual((answer["events"]["configured"], answer["events"]["reachable"]), (True, False))
        self.assertIn("Privacy & Security", answer["events"]["message"])
        self.assertNotIn("events", answer["events"])

    def test_a_reminder_due_today_without_a_time_is_due_not_overdue(self) -> None:
        self.set_up(tasks={"backend": "apple-reminders", "list": "sb-test-inbox"})
        today = datetime.date.today().isoformat()
        self.run_command("tasks", "add", "Book the dentist", "--due", today)

        answer = self.run_json("todos")

        self.assertEqual(answer["overdue"], [])
        self.assertEqual([task["due"] for task in answer["due_within_7_days"]], [today])

    def test_unreachable_reminders_exit_3_with_no_list(self) -> None:
        self.set_up(tasks={"backend": "apple-reminders", "list": "sb-test-missing"})

        code, out, err = self.run_command("todos", "--json")

        self.assertEqual((code, out), (cli.EXIT_UNREACHABLE, ""), err)

    def test_without_a_setup_it_exits_2(self) -> None:
        code, out, _ = self.run_command("todos")

        self.assertEqual((code, out), (cli.EXIT_USAGE, ""))

    def test_a_loose_today_is_a_usage_error(self) -> None:
        self.set_up()

        code, _, err = self.run_command("todos", "--today", "2026-11-7")

        self.assertEqual(code, cli.EXIT_USAGE, err)


class TodosSkillTest(unittest.TestCase):
    """Structure only: the policy prose lives once, in the skill (X15)."""

    skill = Path(__file__).resolve().parents[1] / "skills" / "todos" / "SKILL.md"

    def frontmatter(self) -> dict[str, str]:
        text = self.skill.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        block = text.split("\n---\n", 1)[0].split("\n")[1:]
        return dict(line.split(": ", 1) for line in block if ": " in line)

    def test_the_skill_may_only_run_the_todos_command(self) -> None:
        """Checks the skill's structure, not its prose."""
        fields = self.frontmatter()

        self.assertEqual(fields["name"], "todos")
        self.assertEqual(fields["allowed-tools"], "Bash(m2b todos *)")
        self.assertTrue(fields["description"])

    def test_the_skill_reads_the_json(self) -> None:
        self.assertIn("m2b todos --json", self.skill.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
