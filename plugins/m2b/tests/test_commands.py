"""The stage-1 commands against configured backends: tasks, calendar, store, config, profile, doctor."""

from __future__ import annotations

import contextlib
import datetime
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from m2b import cli, paths
from m2b.calendar.base import local_midnight
from m2b.commands import doctor
from m2b.config import machine, profile
from m2b.config.store_settings import KNOWN_STORE_FORMAT, save_store_settings
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard

FAKES = Path(__file__).resolve().parent / "fakes"
TEST_CALENDARS = [
    {"id": "CAL-HOME", "name": "Home", "account": "iCloud", "writable": True},
    {"id": "CAL-WORK", "name": "Calendar", "account": "Acme Exchange", "writable": True},
    {"id": "CAL-HOLIDAYS", "name": "Holidays", "account": "Subscribed", "writable": False},
]


def ms(moment: datetime.datetime) -> int:
    return round(moment.timestamp() * 1000)


class CommandTest(unittest.TestCase):
    """Runs ``cli.main`` in process with a machine home, a folder store and fake Apple programs."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        root = Path(self._temp.name)
        self.home = root / "home"
        self.machine = paths.MachinePaths(self.home)
        self.store_root = root / "store"
        self.store_root.mkdir()
        self.store = FolderStore(self.store_root, self.machine.temp_dir, DatalessGuard(False))
        self.bin = root / "bin"
        self.bin.mkdir()
        self.calendar_state = root / "calendar.json"
        self.calendar_state.write_text(json.dumps({"calendars": TEST_CALENDARS, "events": []}), encoding="utf-8")
        self.reminders_state = root / "reminders.json"
        self.reminders_state.write_text(json.dumps({"lists": ["sb-test-inbox"], "items": {}}), encoding="utf-8")
        self.environ = {"HOME": str(root / "user-home"), "M2B_HOME": str(self.home)}

    def fake_program(self, name: str, fake: str, state: Path) -> str:
        """A wrapper script that runs a fake from ``tests/fakes`` with its state file."""
        script = self.bin / name
        script.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKES / fake}" "{state}" "$@"\n', encoding="utf-8")
        script.chmod(0o755)
        return str(script)

    def set_up(self, tasks: dict[str, Any] | None = None, calendar: str = "apple-calendar", **extra: Any) -> None:
        config: dict[str, Any] = {
            "version": 1,
            "machine_id": "sb-test-m1",
            "store": {"backend": "folder", "path": str(self.store_root)},
            "calendar": {"backend": calendar, "timeout_seconds": 10},
            "executables": {
                "python3": sys.executable,
                "osascript": self.fake_program("osascript", "fake_osascript.py", self.calendar_state),
                "reminders": self.fake_program("reminders", "fake_reminders.py", self.reminders_state),
            },
            **extra,
        }
        machine.save_machine_config(self.machine, config)
        save_store_settings(
            self.store,
            {
                "format": KNOWN_STORE_FORMAT,
                "tasks": tasks or {"backend": "markdown"},
                "curating_machine": "sb-test-m1",
                "journal_since": "2026-11-01",
            },
        )

    def run_command(self, *arguments: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(arguments), self.environ)
        return code, out.getvalue(), err.getvalue()

    def run_json(self, *arguments: str) -> Any:
        code, out, err = self.run_command(*arguments, "--json")
        self.assertEqual(code, cli.EXIT_OK, err)
        return json.loads(out)


class TasksCommandTest(CommandTest):
    def test_add_list_complete_and_the_marker_filter_on_markdown(self) -> None:
        self.set_up()
        code, out, _ = self.run_command("tasks", "add", "Call Dana", "--notes", "about the shed", "--due", "2026-12-01")
        self.assertEqual(code, cli.EXIT_OK)
        task_id = out.strip()
        self.run_command("tasks", "add", "Merken? Dana prefers tea", "--notes", "m2b:candidate")

        self.run_command("tasks", "add", "m2b: proposals from your sessions", "--notes", "m2b:proposals\n2 wait")

        (candidate,) = self.run_json("tasks", "list", "--marker", "candidate")
        (waiting,) = self.run_json("tasks", "list", "--marker", "proposals")
        self.assertEqual((waiting["title"], waiting["marker"]), ("m2b: proposals from your sessions", "proposals"))
        listed = self.run_json("tasks", "list")
        self.assertEqual(candidate["title"], "Merken? Dana prefers tea")
        self.assertEqual(candidate["marker"], "candidate")
        self.assertIn(
            {"id": task_id, "title": "Call Dana", "notes": "about the shed", "due": "2026-12-01"},
            [{key: task[key] for key in ("id", "title", "notes", "due")} for task in listed],
        )

        self.assertEqual(self.run_command("tasks", "complete", task_id)[0], cli.EXIT_OK)
        self.assertEqual(
            sorted(task["title"] for task in self.run_json("tasks", "list")),
            ["Merken? Dana prefers tea", "m2b: proposals from your sessions"],
        )
        (done,) = [task for task in self.run_json("tasks", "list", "--include-completed") if task["id"] == task_id]
        self.assertTrue(done["completed"])

    def test_a_task_id_after_double_dash_is_never_read_as_an_option(self) -> None:
        """Covers: B94"""
        self.set_up()
        task_id = self.run_json("tasks", "add", "Merken? Dana prefers tea", "--notes", "m2b:candidate")["id"]

        self.assertEqual(self.run_command("tasks", "drop", "--", task_id)[0], cli.EXIT_OK)
        code, out, _ = self.run_command("tasks", "complete", "--", "-h")

        self.assertEqual(code, cli.EXIT_PROBLEM)
        self.assertNotIn("usage:", out)
        (dropped,) = self.run_json("tasks", "list", "--include-completed")
        self.assertTrue(dropped["dropped"])

    def test_drop_notes_and_delete_against_apple_reminders(self) -> None:
        self.set_up(tasks={"backend": "apple-reminders", "list": "sb-test-inbox"})
        task_id = self.run_json("tasks", "add", "Merken? Alex likes chess", "--notes", "m2b:candidate")["id"]
        other_id = self.run_json("tasks", "add", "Water the plants")["id"]

        self.assertEqual(self.run_command("tasks", "notes", other_id, "on the balcony")[0], cli.EXIT_OK)
        self.assertEqual(self.run_command("tasks", "drop", task_id)[0], cli.EXIT_OK)
        listed = self.run_json("tasks", "list", "--include-completed")

        self.assertEqual({task["id"]: task["dropped"] for task in listed}, {task_id: True, other_id: False})
        self.assertEqual([task["notes"] for task in listed if task["id"] == other_id], ["on the balcony"])
        self.assertEqual(self.run_command("tasks", "delete", other_id)[0], cli.EXIT_OK)
        self.assertEqual([task["id"] for task in self.run_json("tasks", "list", "--include-completed")], [task_id])

    def test_a_timed_due_date_is_read_in_local_time(self) -> None:
        self.set_up()
        self.run_command("tasks", "add", "Dentist", "--due", "2026-12-01 09:30")

        (task,) = self.run_json("tasks", "list")

        self.assertEqual(
            datetime.datetime.fromisoformat(task["due"]), datetime.datetime(2026, 12, 1, 9, 30).astimezone()
        )

    def test_an_unknown_task_is_a_problem_exit_1(self) -> None:
        self.set_up()
        for action in ("complete", "drop", "delete"):
            with self.subTest(action=action):
                code, out, err = self.run_command("tasks", action, "0123456789ab")
                self.assertEqual((code, out), (cli.EXIT_PROBLEM, ""))
                self.assertIn("0123456789ab", err)

    def test_unreachable_reminders_exit_3_and_are_never_an_empty_list(self) -> None:
        """Covers: B24"""
        self.set_up(tasks={"backend": "apple-reminders", "list": "sb-test-inbox"})
        self.reminders_state.write_text(json.dumps({"lists": [], "items": {}, "mode": "no-lists"}), encoding="utf-8")

        code, out, err = self.run_command("tasks", "list", "--json")

        self.assertEqual((code, out), (cli.EXIT_UNREACHABLE, ""))
        self.assertIn("Reminders", err)

    def test_an_unknown_marker_is_a_usage_error_not_an_empty_list(self) -> None:
        self.set_up()

        code, out, _ = self.run_command("tasks", "list", "--marker", "candidates", "--json")

        self.assertEqual((code, out), (cli.EXIT_USAGE, ""))

    def test_a_task_file_that_cannot_be_read_is_a_problem_in_one_line(self) -> None:
        self.set_up()
        (self.store_root / "tasks").mkdir()
        (self.store_root / "tasks" / "call-dana.md").write_text(
            "---\nstatus: maybe\n---\nCall Dana\n", encoding="utf-8"
        )

        code, out, err = self.run_command("tasks", "list")

        # The other tasks are listed; the file that cannot be read is named and left out.
        self.assertEqual((code, out), (0, ""))
        self.assertEqual(len(err.splitlines()), 1, err)
        self.assertIn("call-dana.md", err)

    def test_a_task_file_in_another_encoding_is_a_problem_in_one_line(self) -> None:
        self.set_up()
        (self.store_root / "tasks").mkdir()
        (self.store_root / "tasks" / "cafe.md").write_bytes("Caf\xe9 with Dana\n".encode("latin-1"))

        for arguments, exit_code in ((("tasks", "list"), 0), (("tasks", "complete", "cafe"), cli.EXIT_PROBLEM)):
            with self.subTest(arguments=arguments):
                code, _, err = self.run_command(*arguments)
                self.assertEqual(code, exit_code, err)
                self.assertIn("cafe.md", err)
                self.assertEqual(len(err.splitlines()), 1, err)

    def test_a_reminder_that_cannot_be_found_after_adding_is_a_problem(self) -> None:
        self.set_up(tasks={"backend": "apple-reminders", "list": "sb-test-inbox"})
        state = json.loads(self.reminders_state.read_text(encoding="utf-8"))
        self.reminders_state.write_text(json.dumps({**state, "mode": "lose-notes-on-add"}), encoding="utf-8")

        code, _, err = self.run_command("tasks", "add", "Call Dana")

        self.assertEqual(code, cli.EXIT_PROBLEM, err)

    def test_notes_of_a_completed_reminder_are_a_problem_not_unreachable(self) -> None:
        self.set_up(tasks={"backend": "apple-reminders", "list": "sb-test-inbox"})
        task_id = self.run_json("tasks", "add", "Water the plants")["id"]
        self.run_command("tasks", "complete", task_id)

        code, _, err = self.run_command("tasks", "notes", task_id, "on the balcony")

        self.assertEqual(code, cli.EXIT_PROBLEM, err)
        self.assertIn("reopen", err)

    def test_bad_titles_and_dates_are_usage_errors(self) -> None:
        self.set_up()
        for arguments in (
            ("tasks", "add", "  "),
            ("tasks", "add", "Call Dana", "--due", "1.12.2026"),
            ("tasks", "add", "Call Dana", "--due", "2026-12-1"),
        ):
            with self.subTest(arguments=arguments):
                code, _, err = self.run_command(*arguments)
                self.assertEqual(code, cli.EXIT_USAGE, err)
                self.assertNotIn("Traceback", err)


class CalendarCommandTest(CommandTest):
    def test_list_shows_every_calendar_and_marks_read_only_ones(self) -> None:
        self.set_up()

        answer = self.run_json("calendar", "list")
        code, out, _ = self.run_command("calendar", "list", "--writable")

        self.assertTrue(answer["configured"])
        self.assertEqual([entry["writable"] for entry in answer["calendars"]], [True, True, False])
        self.assertEqual((code, out.splitlines()), (cli.EXIT_OK, ["iCloud/Home", "Acme Exchange/Calendar"]))

    def test_add_without_a_calendar_is_refused_before_anything_is_written(self) -> None:
        """Covers: X21"""
        self.set_up()

        code, _, err = self.run_command(
            "calendar", "add", "--title", "Birthday party", "--start", "2026-12-24", "--all-day"
        )

        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertIn("--calendar", err)
        self.assertEqual(json.loads(self.calendar_state.read_text(encoding="utf-8"))["events"], [])

    def test_add_into_a_read_only_calendar_names_the_writable_ones(self) -> None:
        """Covers: B26"""
        self.set_up()

        code, out, err = self.run_command(
            "calendar",
            "add",
            "--calendar",
            "Holidays",
            "--title",
            "Birthday party",
            "--start",
            "2026-12-24",
            "--all-day",
        )

        self.assertEqual((code, out), (cli.EXIT_PROBLEM, ""))
        self.assertIn("iCloud/Home, Acme Exchange/Calendar", err)

    def test_an_all_day_event_takes_its_last_day_inclusively_and_reads_back(self) -> None:
        self.set_up()

        created = self.run_json(
            "calendar",
            "add",
            "--calendar",
            "Home",
            "--title",
            "Visit Dana",
            "--start",
            "2026-12-24",
            "--end",
            "2026-12-25",
            "--all-day",
        )
        (event,) = self.run_json("calendar", "events", "--from", "2026-12-25")["events"]

        self.assertEqual((created["first_day"], created["last_day"]), ("2026-12-24", "2026-12-25"))
        self.assertEqual((created["calendar"], created["account"]), ("Home", "iCloud"))
        self.assertEqual((event["title"], event["all_day"], event["last_day"]), ("Visit Dana", True, "2026-12-25"))
        self.assertEqual(event["sources"], ["iCloud/Home"])

    def test_a_timed_event_without_an_end_lasts_an_hour(self) -> None:
        self.set_up()

        created = self.run_json(
            "calendar", "add", "--calendar", "iCloud/Home", "--title", "Dentist", "--start", "2026-12-23 10:30"
        )

        start = datetime.datetime(2026, 12, 23, 10, 30).astimezone()
        self.assertEqual(datetime.datetime.fromisoformat(created["start"]), start)
        self.assertEqual(datetime.datetime.fromisoformat(created["end"]), start + datetime.timedelta(hours=1))

    def test_loose_or_repeated_arguments_are_refused(self) -> None:
        self.set_up()
        base = ("calendar", "add", "--calendar", "Home", "--title", "Dentist")
        for extra in (
            ("--start", "2026-12-23T10:30"),
            ("--start", "2026-12-23 9:30"),
            ("--start", "2026-02-30 10:00"),
            ("--start", "2026-12-23 10:30", "--start", "2026-12-23 11:30"),
            ("--start", "2026-12-23 10:30", "--all-day"),
            ("--start", "2026-12-24", "--end", "2026-12-23", "--all-day"),
        ):
            with self.subTest(extra=extra):
                code, _, err = self.run_command(*base, *extra)
                self.assertEqual(code, cli.EXIT_USAGE, err)
        self.assertEqual(json.loads(self.calendar_state.read_text(encoding="utf-8"))["events"], [])

    def test_events_from_two_accounts_are_merged_and_today_is_the_default(self) -> None:
        """Covers: B25"""
        self.set_up()
        start = datetime.datetime.combine(datetime.date.today(), datetime.time(9)).astimezone()
        meeting = {"title": "Planning with Acme", "start": ms(start), "end": ms(start) + 3_600_000, "allDay": False}
        state = json.loads(self.calendar_state.read_text(encoding="utf-8"))
        state["events"] = [{**meeting, "calendarId": "CAL-HOME"}, {**meeting, "calendarId": "CAL-WORK"}]
        self.calendar_state.write_text(json.dumps(state), encoding="utf-8")

        (event,) = self.run_json("calendar", "events")["events"]

        self.assertEqual(event["sources"], ["Acme Exchange/Calendar", "iCloud/Home"])

    def test_a_window_over_four_years_is_a_usage_error(self) -> None:
        self.set_up()

        code, _, err = self.run_command("calendar", "events", "--from", "2026-01-01", "--to", "2031-01-01")

        self.assertEqual(code, cli.EXIT_USAGE, err)
        self.assertNotIn("Traceback", err)

    def test_an_event_stored_differently_is_a_problem_never_a_reason_to_retry(self) -> None:
        """Exit 3 would invite a retry, and a retry would create a second event."""
        self.set_up()
        state = json.loads(self.calendar_state.read_text(encoding="utf-8"))
        self.calendar_state.write_text(json.dumps({**state, "mode": "shift-read-back"}), encoding="utf-8")

        code, _, err = self.run_command(
            "calendar", "add", "--calendar", "Home", "--title", "Dentist", "--start", "2026-12-23 10:30"
        )

        self.assertEqual(code, cli.EXIT_PROBLEM, err)
        self.assertIn("was saved", err)

    def test_without_a_calendar_backend_reads_answer_not_configured_with_exit_0(self) -> None:
        self.set_up(calendar="none")

        for command in (("calendar", "list"), ("calendar", "events")):
            with self.subTest(command=command):
                answer = self.run_json(*command)
                code, out, _ = self.run_command(*command)
                self.assertFalse(answer["configured"])
                self.assertNotIn("events", answer)
                self.assertEqual(code, cli.EXIT_OK)
                self.assertIn("not configured", out)

    def test_without_a_calendar_backend_add_is_a_problem(self) -> None:
        self.set_up(calendar="none")

        code, _, err = self.run_command(
            "calendar", "add", "--calendar", "Home", "--title", "Dentist", "--start", "2026-12-23 10:30"
        )

        self.assertEqual(code, cli.EXIT_PROBLEM)
        self.assertIn("not configured", err)

    def test_an_unreachable_calendar_exits_3(self) -> None:
        self.set_up()
        state = json.loads(self.calendar_state.read_text(encoding="utf-8"))
        self.calendar_state.write_text(json.dumps({**state, "mode": "no-access"}), encoding="utf-8")

        code, out, err = self.run_command("calendar", "events", "--json")

        self.assertEqual((code, out), (cli.EXIT_UNREACHABLE, ""))
        self.assertIn("Privacy & Security", err)

    def test_events_on_an_all_day_holiday_are_read_from_read_only_calendars(self) -> None:
        self.set_up()
        state = json.loads(self.calendar_state.read_text(encoding="utf-8"))
        christmas = local_midnight(datetime.date(2026, 12, 25))
        state["events"] = [
            {
                "title": "Christmas Day",
                "start": ms(christmas),
                "end": ms(christmas) + 86_399_000,
                "allDay": True,
                "calendarId": "CAL-HOLIDAYS",
            }
        ]
        self.calendar_state.write_text(json.dumps(state), encoding="utf-8")

        code, out, _ = self.run_command("calendar", "events", "--from", "2026-12-24", "--to", "2026-12-26")

        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("Christmas Day", out)


class StoreCommandTest(CommandTest):
    def test_check_local_lists_nothing_for_a_plain_folder_and_fetch_succeeds(self) -> None:
        self.set_up()
        (self.store_root / "inbox").mkdir()
        (self.store_root / "inbox" / "note.md").write_text("hello\n", encoding="utf-8")

        self.assertEqual(self.run_json("store", "check-local", "inbox/note.md"), [])
        self.assertEqual(self.run_command("store", "fetch", "inbox/note.md")[0], cli.EXIT_OK)

    def test_a_path_outside_the_store_is_a_usage_error(self) -> None:
        self.set_up()

        code, _, err = self.run_command("store", "check-local", "../secrets.txt")

        self.assertEqual(code, cli.EXIT_USAGE, err)


class SettingsCommandTest(CommandTest):
    def test_config_set_writes_one_key_and_keeps_the_rest(self) -> None:
        self.set_up()

        self.assertEqual(self.run_command("config", "set", "calendar.timeout_seconds", "45")[0], cli.EXIT_OK)

        self.assertEqual(
            self.run_json("config", "get", "calendar"), {"backend": "apple-calendar", "timeout_seconds": 45}
        )
        self.assertEqual(self.run_command("config", "get", "machine_id")[1].strip(), "sb-test-m1")

    def test_config_set_refuses_a_store_path_curation_cannot_use_on_the_curating_machine(self) -> None:
        """Covers: B81"""
        self.set_up(calendar="none")
        before = self.machine.config_file.read_text(encoding="utf-8")

        code, _, err = self.run_command("config", "set", "store.path", str(self.store_root.parent / "Notes (2026)"))

        self.assertEqual(code, cli.EXIT_USAGE, err)
        self.assertIn("(", err)
        self.assertEqual(self.machine.config_file.read_text(encoding="utf-8"), before)

    def test_config_set_refuses_such_a_path_after_the_store_was_moved_there(self) -> None:
        """Covers: B81"""
        self.set_up(calendar="none")
        moved = self.store_root.parent / "Notes (2026)"
        self.store_root.rename(moved)
        before = self.machine.config_file.read_text(encoding="utf-8")

        code, _, err = self.run_command("config", "set", "store.path", str(moved))

        self.assertEqual(code, cli.EXIT_USAGE, err)
        self.assertEqual(self.machine.config_file.read_text(encoding="utf-8"), before)

    def test_config_set_lets_such_a_path_through_when_the_store_there_is_curated_elsewhere(self) -> None:
        """Covers: B81"""
        self.set_up(calendar="none")
        other = self.store_root.parent / "Dropbox (Personal)"
        other.mkdir()
        settings = json.loads((self.store_root / "store.json").read_text(encoding="utf-8"))
        (other / "store.json").write_text(json.dumps({**settings, "curating_machine": "sb-test-m2"}), encoding="utf-8")

        code, _, err = self.run_command("config", "set", "store.path", str(other))

        self.assertEqual(code, cli.EXIT_OK, err)

    def test_config_set_checks_a_whole_store_section_too(self) -> None:
        """Covers: B81"""
        self.set_up(calendar="none")
        section = json.dumps({"backend": "folder", "path": str(self.store_root.parent / "Notes (2026)")})

        code, _, err = self.run_command("config", "set", "store", section)

        self.assertEqual(code, cli.EXIT_USAGE, err)

    def test_config_set_keeps_such_a_store_path_on_a_machine_that_only_captures(self) -> None:
        """Covers: B81"""
        self.set_up(calendar="none")
        settings = json.loads((self.store_root / "store.json").read_text(encoding="utf-8"))
        settings["curating_machine"] = "sb-test-m2"
        (self.store_root / "store.json").write_text(json.dumps(settings), encoding="utf-8")
        linked = self.store_root.parent / "Dropbox (Personal)"
        linked.symlink_to(self.store_root)

        code, _, err = self.run_command("config", "set", "store.path", str(linked))

        self.assertEqual(code, cli.EXIT_OK, err)

    def test_config_set_refuses_a_value_the_config_does_not_allow(self) -> None:
        self.set_up()

        code, _, err = self.run_command("config", "set", "calendar.backend", "outlook")

        self.assertEqual(code, cli.EXIT_USAGE, err)
        self.assertEqual(self.run_command("config", "get", "calendar.backend")[1].strip(), "apple-calendar")

    def test_profile_merge_adds_to_the_profile_and_set_changes_one_key(self) -> None:
        self.set_up()
        profile.save_profile(self.store, {"version": 1, "owner": "Alex", "language": "en"})

        self.assertEqual(self.run_command("profile", "merge", '{"language": "de"}')[0], cli.EXIT_OK)
        self.assertEqual(self.run_command("profile", "set", "owner", "Alex Example")[0], cli.EXIT_OK)

        self.assertEqual(self.run_command("profile", "get", "language")[1].strip(), "de")
        self.assertEqual(self.run_command("profile", "get", "owner")[1].strip(), "Alex Example")

    def test_profile_merge_takes_a_json_object_only(self) -> None:
        self.set_up()
        for patch in ('["de"]', "language=de"):
            with self.subTest(patch=patch):
                self.assertEqual(self.run_command("profile", "merge", patch)[0], cli.EXIT_USAGE)


class DoctorTest(CommandTest):
    def setUp(self) -> None:
        super().setUp()
        self.installed = self.bin.parent / "installed_plugins.json"
        self.install({"m2b@m2b": [{"scope": "user", "installPath": "/sb-test-plugins/m2b/0.1.0"}]})
        self.environ["M2B_INSTALLED_PLUGINS"] = str(self.installed)

    def install(self, plugins: dict[str, Any]) -> None:
        self.installed.write_text(json.dumps({"version": 2, "plugins": plugins}), encoding="utf-8")

    def test_the_launcher_finding_m2b_in_claude_codes_plugin_list_is_checked(self) -> None:
        self.set_up(calendar="none", tasks={"backend": "markdown"})
        self.assertIn(
            "claude-code: found (the launcher runs m2b from /sb-test-plugins/m2b/0.1.0)", self.run_command("doctor")[1]
        )

        self.install({"m2b@m2b": [{"scope": "project", "installPath": "/sb-test-plugins/m2b/0.1.0"}]})
        code, out, _ = self.run_command("doctor")
        self.assertEqual(code, cli.EXIT_PROBLEM)
        self.assertIn("claude-code: missing (", out)
        self.assertIn("install it for your user with /plugin", out)

        self.environ["M2B_CORE_ROOT"] = "/sb-test-checkout/plugins/m2b"
        self.assertIn("claude-code: found (the launcher runs m2b from /sb-test-checkout", self.run_command("doctor")[1])

    def seen(self, name: str, moment: str) -> None:
        path = self.machine.state_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"seenAt": moment}), encoding="utf-8")

    def band_line(self) -> str:
        code, out, _ = self.run_command("doctor")
        self.assertEqual(code, cli.EXIT_OK, out)
        return next(line for line in out.splitlines() if line.startswith("band: "))

    def test_doctor_says_the_band_ran_in_the_latest_session_in_local_time(self) -> None:
        """Covers: B92"""
        self.set_up(calendar="none", tasks={"backend": "markdown"})
        self.seen("session-seen.json", "2026-03-14T18:30:00+01:00")
        self.seen("band-seen.json", "2026-03-14T17:30:01.000Z")
        local = datetime.datetime(2026, 3, 14, 17, 30, 1, tzinfo=datetime.timezone.utc).astimezone()

        self.assertEqual(self.band_line(), f"band: seen (it ran in the latest session, started {local:%Y-%m-%d %H:%M})")

    def test_a_latest_session_without_the_band_means_mods_are_off(self) -> None:
        """Covers: B92"""
        self.set_up(calendar="none", tasks={"backend": "markdown"})
        self.seen("band-seen.json", "2026-03-10T08:00:00.000Z")
        self.seen("session-seen.json", "2026-03-14T18:30:00+01:00")

        line = self.band_line()

        self.assertTrue(line.startswith("band: not seen (the latest session"), line)
        self.assertIn("ran m2b's hooks but not the band", line)
        self.assertIn("rollout switch", line)
        self.assertIn("the band last ran 2026-03-10", line)

    def test_no_session_with_m2bs_hooks_names_the_cases_that_turn_all_hooks_off(self) -> None:
        """Covers: B92"""
        self.set_up(calendar="none", tasks={"backend": "markdown"})
        self.seen("band-seen.json", "not a time")

        line = self.band_line()

        self.assertTrue(line.startswith("band: not seen (no Claude Code session has run m2b's hooks"), line)
        self.assertIn("--bare", line)
        self.assertIn("allowManagedHooksOnly", line)
        self.assertIn("distillate", line)

    def test_the_launcher_hook_notes_the_session_and_removes_the_old_band_caches(self) -> None:
        """Covers: B92"""
        self.set_up(calendar="none", tasks={"backend": "markdown"})
        leftovers = [
            self.machine.state_dir / name for name in ("band-addons.json", "band-snapshot.json", "band-status.json")
        ]
        kept = self.machine.state_dir / "band-view.json"
        kept.parent.mkdir(parents=True, exist_ok=True)
        for path in [*leftovers, kept]:
            path.write_text("{}", encoding="utf-8")

        self.run_command("hook", "launcher")

        noted = json.loads((self.machine.state_dir / "session-seen.json").read_text(encoding="utf-8"))
        self.assertIsNotNone(datetime.datetime.fromisoformat(noted["seenAt"]).tzinfo)
        self.assertEqual([path.exists() for path in leftovers], [False, False, False])
        self.assertTrue(kept.exists())

    def test_the_launcher_hook_keeps_the_machine_state_readable_by_the_owner_only(self) -> None:
        """Covers: B95"""
        self.set_up(calendar="none", tasks={"backend": "markdown"})
        self.machine.state_dir.mkdir(parents=True, exist_ok=True)
        self.machine.state_dir.chmod(0o755)

        self.run_command("hook", "launcher")

        self.assertEqual(stat.S_IMODE(self.machine.state_dir.stat().st_mode), 0o700)

    def test_a_store_path_the_curation_run_cannot_fence_is_a_problem(self) -> None:
        """Covers: B81"""
        self.set_up(calendar="none", tasks={"backend": "markdown"})
        linked = self.store_root.parent / "Notes (2026)"
        linked.symlink_to(self.store_root)
        config = json.loads(self.machine.config_file.read_text(encoding="utf-8"))
        config["store"]["path"] = str(linked)
        self.machine.config_file.write_text(json.dumps(config), encoding="utf-8")

        code, out, _ = self.run_command("doctor")

        self.assertEqual(code, cli.EXIT_PROBLEM, out)
        (line,) = [line for line in out.splitlines() if line.startswith("store-path: ")]
        self.assertIn("(", line)
        self.assertIn("store: reachable", out)

    def test_a_store_path_with_such_a_character_is_fine_on_a_machine_that_does_not_curate(self) -> None:
        """Covers: B81"""
        self.set_up(calendar="none", tasks={"backend": "markdown"})
        settings = json.loads((self.store_root / "store.json").read_text(encoding="utf-8"))
        settings["curating_machine"] = "sb-test-m2"
        (self.store_root / "store.json").write_text(json.dumps(settings), encoding="utf-8")
        linked = self.store_root.parent / "Dropbox (Personal)"
        linked.symlink_to(self.store_root)
        config = json.loads(self.machine.config_file.read_text(encoding="utf-8"))
        config["store"]["path"] = str(linked)
        self.machine.config_file.write_text(json.dumps(config), encoding="utf-8")

        code, out, _ = self.run_command("doctor")

        self.assertEqual(code, cli.EXIT_OK, out)
        self.assertNotIn("store-path: ", out)

    def test_a_healthy_machine_gets_one_line_per_backend_and_exit_0(self) -> None:
        self.set_up(tasks={"backend": "apple-reminders", "list": "sb-test-inbox"})

        code, out, err = self.run_command("doctor")

        self.assertEqual(code, cli.EXIT_OK, out + err)
        lines = out.splitlines()
        for start in ("store: reachable", "tasks: reachable", "calendar: reachable"):
            self.assertEqual(sum(line.startswith(start) for line in lines), 1, out)
        self.assertTrue(any(line.startswith("reminders-cli: ") for line in lines), out)
        self.assertTrue(any(line.startswith("executable osascript: ") for line in lines), out)

    def test_markdown_tasks_get_no_reminders_cli_line(self) -> None:
        self.set_up(tasks={"backend": "markdown"})

        code, out, _ = self.run_command("doctor")

        self.assertEqual(code, cli.EXIT_OK, out)
        self.assertNotIn("reminders-cli", out)

    def test_a_claude_that_was_never_recorded_is_named_with_the_fix(self) -> None:
        # The test setup records python3, osascript and reminders, never claude.
        self.set_up(tasks={"backend": "markdown"})

        code, out, _ = self.run_command("doctor")

        self.assertEqual(code, cli.EXIT_OK, out)
        self.assertIn("executable claude: not recorded (curation needs it: m2b config set executables.claude", out)

    def test_a_calendar_that_is_not_configured_is_no_problem(self) -> None:
        self.set_up(calendar="none")

        code, out, _ = self.run_command("doctor")

        self.assertEqual(code, cli.EXIT_OK, out)
        self.assertIn("calendar: not configured", out)

    def test_an_unreachable_backend_and_a_missing_executable_are_problems_with_reasons(self) -> None:
        self.set_up(tasks={"backend": "apple-reminders", "list": "sb-test-inbox"})
        self.reminders_state.write_text(json.dumps({"lists": [], "items": {}, "mode": "no-lists"}), encoding="utf-8")
        machine.set_machine_config_value(self.machine, "executables.claude", str(self.bin / "missing-claude"))

        answer = self.run_json_any("doctor")

        self.assertEqual(answer["code"], cli.EXIT_PROBLEM)
        checks = {check["name"]: check for check in answer["json"]["checks"]}
        self.assertEqual(checks["tasks"]["state"], "not reachable")
        self.assertIn("Reminders", checks["tasks"]["detail"])
        self.assertEqual(checks["executable claude"]["state"], "missing")
        self.assertEqual(sum(c["name"] == "executable claude" for c in answer["json"]["checks"]), 1)
        self.assertEqual(checks["store"]["state"], "reachable")

    def prompt_hook_line(self) -> tuple[int, str]:
        code, out, _ = self.run_command("doctor")
        return code, next(line for line in out.splitlines() if line.startswith("prompt-hook: "))

    def test_doctor_starts_the_prompt_hook_and_says_that_it_answers(self) -> None:
        """Covers: B146"""
        self.set_up(calendar="none", tasks={"backend": "markdown"})
        index = self.store_root / "memory" / "MEMORY.md"
        index.parent.mkdir(exist_ok=True)
        index.write_text("# Memory\n\n## Facts\n\n### Acme (Acme)\n- Kim leads IT (kim.md)\n", encoding="utf-8")

        self.assertEqual(self.prompt_hook_line(), (cli.EXIT_OK, "prompt-hook: answers (topics in the distillate: 1)"))

    def test_a_prompt_hook_that_cannot_read_the_distillate_is_a_problem_with_its_reason(self) -> None:
        """Covers: B146"""
        self.set_up(calendar="none", tasks={"backend": "markdown"})
        index = self.store_root / "memory" / "MEMORY.md"
        if index.exists():
            index.unlink()
        index.mkdir(parents=True)

        code, line = self.prompt_hook_line()

        self.assertEqual(code, cli.EXIT_PROBLEM)
        self.assertTrue(line.startswith("prompt-hook: does not answer ("), line)
        self.assertIn("MEMORY.md", line)
        self.assertTrue(line.endswith("; so no topic's facts come in before a prompt)"), line)

    def plugin_with(self, hooks: dict[str, Any] | None, script: str | None) -> Path:
        """A plugin folder with these hooks and this prompt hook, either left out when None."""
        root = Path(tempfile.mkdtemp(prefix="sb-test-plugin-", dir=self.bin.parent))
        (root / "hooks").mkdir()
        (root / "bin").mkdir()
        if hooks is not None:
            (root / "hooks" / "hooks.json").write_text(json.dumps({"hooks": hooks}), encoding="utf-8")
        if script is not None:
            command = root / "bin" / "m2b-prompt-hook"
            command.write_text(script, encoding="utf-8")
            command.chmod(0o755)
        return root

    @staticmethod
    def registered(timeout: int = 5) -> dict[str, Any]:
        command = '"${CLAUDE_PLUGIN_ROOT}"/bin/m2b-prompt-hook'
        return {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": command, "timeout": timeout}]}]}

    def test_a_plugin_whose_hooks_do_not_name_the_prompt_hook_is_a_problem(self) -> None:
        """Covers: B146"""
        other = {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "bin/other", "timeout": 5}]}]}
        for hooks in (None, {}, other, {"UserPromptSubmit": "broken"}):
            with self.subTest(hooks=hooks):
                check = doctor.prompt_hook_check(self.environ, self.plugin_with(hooks, "#!/bin/sh\necho ready\n"))

                self.assertEqual(check.state, "missing")
                self.assertIn("hooks.json names no hook that runs bin/m2b-prompt-hook", check.detail)

    def test_a_prompt_hook_that_cannot_be_started_is_a_problem(self) -> None:
        """Covers: B146"""
        check = doctor.prompt_hook_check(self.environ, self.plugin_with(self.registered(), None))

        self.assertEqual(check.state, "missing")
        self.assertIn("bin/m2b-prompt-hook could not be started: ", check.detail)

    def test_it_is_started_with_check_and_its_last_line_is_the_reason(self) -> None:
        """Covers: B146"""
        script = "#!/bin/sh\necho starting\necho \"asked with: $*\"\necho 'the store is gone' >&2\nexit 3\n"
        said = doctor.prompt_hook_check(self.environ, self.plugin_with(self.registered(), script))
        self.assertEqual(said.state, "does not answer")
        self.assertEqual(said.detail, "asked with: --check; so no topic's facts come in before a prompt")

    def test_a_prompt_hook_that_says_nothing_is_named_by_its_standard_error_or_its_exit_code(self) -> None:
        for script, reason in (
            ("#!/bin/sh\necho 'python3: not found' >&2\nexit 127\n", "python3: not found"),
            ("#!/bin/sh\nexit 4\n", "exit code 4"),
        ):
            with self.subTest(reason=reason):
                check = doctor.prompt_hook_check(self.environ, self.plugin_with(self.registered(), script))

                self.assertEqual(check.state, "does not answer")
                self.assertEqual(check.detail, f"{reason}; so no topic's facts come in before a prompt")

    def test_a_prompt_hook_slower_than_claude_code_allows_is_a_problem(self) -> None:
        """Covers: B146"""
        root = self.plugin_with(self.registered(timeout=7), "#!/bin/sh\necho ready\n")

        allowed: list[float] = []

        def too_slow(command: list[str], **options: Any) -> None:
            allowed.append(options["timeout"])
            raise subprocess.TimeoutExpired(command, options["timeout"])

        with mock.patch("m2b.commands.doctor.subprocess.run", side_effect=too_slow):
            check = doctor.prompt_hook_check(self.environ, root)

        self.assertEqual(allowed, [7])
        self.assertEqual(check.state, "does not answer")
        self.assertIn("bin/m2b-prompt-hook took longer than the 7 s Claude Code gives it", check.detail)

    def store_git_line(self) -> tuple[int, str]:
        code, out, _ = self.run_command("doctor")
        return code, next(line for line in out.splitlines() if line.startswith("store-git: "))

    def git_init(self, *arguments: str) -> None:
        """Makes the store folder a git repository, without the developer's git configuration."""
        environ = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
        subprocess.run(
            ["git", "init", "-q", "-b", "main", *arguments],
            cwd=self.store_root,
            env=environ,
            capture_output=True,
            check=True,
        )
        self.environ.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)

    def no_git_on_this_machine(self) -> None:
        """A PATH with the two programs the prompt hook's line needs, and no git."""
        programs = self.bin.parent / "no-git"
        programs.mkdir()
        os.symlink(sys.executable, programs / "python3")
        os.symlink(str(shutil.which("dirname")), programs / "dirname")
        self.environ["PATH"] = str(programs)

    def test_a_store_folder_without_a_git_folder_is_no_repository(self) -> None:
        """Covers: B149"""
        self.set_up(calendar="none", tasks={"backend": "markdown"})

        self.assertEqual(self.store_git_line(), (cli.EXIT_OK, "store-git: no repository"))

    def test_a_store_that_is_a_repository_names_the_git_directory_a_run_commits_into(self) -> None:
        """Covers: B149"""
        self.set_up(calendar="none", tasks={"backend": "markdown"})
        self.git_init()
        commits = "a curation run on this machine ends with one commit of what it changed"

        where = f"{self.store_root.resolve() / '.git'}, read with {shutil.which('git')}"

        self.assertEqual(self.store_git_line(), (cli.EXIT_OK, f"store-git: found ({where}; {commits})"))

    def test_a_git_directory_outside_the_store_folder_is_named_where_it_lies(self) -> None:
        """Covers: B149"""
        self.set_up(calendar="none", tasks={"backend": "markdown"})
        outside = self.bin.parent.resolve() / "sb-test-store.git"
        self.git_init("--separate-git-dir", str(outside))

        code, line = self.store_git_line()

        self.assertEqual(code, cli.EXIT_OK)
        self.assertTrue(line.startswith(f"store-git: found ({outside}, read with "), line)

    def test_a_machine_that_does_not_curate_commits_nothing_and_starts_no_git(self) -> None:
        """Covers: B149"""
        self.set_up(calendar="none", tasks={"backend": "markdown"})
        self.git_init()
        settings = json.loads((self.store_root / "store.json").read_text(encoding="utf-8"))
        save_store_settings(self.store, {**settings, "curating_machine": "sb-test-m2"})
        self.no_git_on_this_machine()

        self.assertEqual(
            self.store_git_line(),
            (
                cli.EXIT_OK,
                "store-git: found (.git in the store folder; this machine does not curate, so it commits nothing)",
            ),
        )

    def test_with_the_commit_turned_off_nothing_is_committed_and_no_git_starts(self) -> None:
        """Covers: B149"""
        self.set_up(calendar="none", tasks={"backend": "markdown"}, curation={"git_commit": False})
        self.git_init()
        self.no_git_on_this_machine()

        self.assertEqual(
            self.store_git_line(),
            (
                cli.EXIT_OK,
                "store-git: found (.git in the store folder; curation.git_commit is false on this machine, "
                "so its runs commit nothing)",
            ),
        )

    def test_a_repository_on_a_curating_machine_without_git_is_a_problem(self) -> None:
        """Covers: B149"""
        self.set_up(calendar="none", tasks={"backend": "markdown"})
        self.git_init()
        self.no_git_on_this_machine()

        self.assertEqual(
            self.store_git_line(),
            (
                cli.EXIT_PROBLEM,
                "store-git: cannot commit (the store folder holds a .git, but this machine has no git to start; "
                "a curation run on this machine leaves what it changed uncommitted)",
            ),
        )

    def test_a_git_folder_git_cannot_use_is_a_problem_with_gits_reason(self) -> None:
        """Covers: B149"""
        self.set_up(calendar="none", tasks={"backend": "markdown"})
        (self.store_root / ".git").write_text("gitdir: /sb-test-nowhere\n", encoding="utf-8")

        code, line = self.store_git_line()

        self.assertEqual(code, cli.EXIT_PROBLEM)
        self.assertTrue(line.startswith("store-git: cannot commit (git rev-parse failed: "), line)
        self.assertTrue(line.endswith("; a curation run on this machine leaves what it changed uncommitted)"), line)

    def test_gits_reason_is_printed_with_the_characters_that_draw_nothing_written_out(self) -> None:
        """Covers: B149"""
        self.set_up(calendar="none", tasks={"backend": "markdown"})
        (self.store_root / ".git").write_text("gitdir: /sb-test-no\u200bwhere\U000e0041\n", encoding="utf-8")

        code, line = self.store_git_line()

        self.assertEqual(code, cli.EXIT_PROBLEM)
        self.assertIn("/sb-test-no<U+200B>where<U+E0041>", line)

    def test_the_git_directory_is_printed_with_the_characters_that_draw_nothing_written_out(self) -> None:
        """Covers: B149"""
        self.set_up(calendar="none", tasks={"backend": "markdown"})
        outside = self.bin.parent.resolve() / "sb-test\u200b-store.git"
        self.git_init("--separate-git-dir", str(outside))

        code, line = self.store_git_line()

        self.assertEqual(code, cli.EXIT_OK)
        shown = self.bin.parent.resolve() / "sb-test<U+200B>-store.git"
        self.assertTrue(line.startswith(f"store-git: found ({shown}, read with "), line)

    def test_a_repository_whose_work_tree_is_another_folder_is_a_problem(self) -> None:
        """Covers: B149"""
        self.set_up(calendar="none", tasks={"backend": "markdown"})
        self.git_init()
        elsewhere = self.bin.parent / "another-work-tree"
        elsewhere.mkdir()
        subprocess.run(["git", "config", "core.worktree", str(elsewhere)], cwd=self.store_root, check=True)

        code, line = self.store_git_line()

        self.assertEqual(code, cli.EXIT_PROBLEM)
        self.assertIn("cannot commit (the store folder is not the top of the repository's work tree; ", line)

    def test_a_store_that_cannot_be_reached_has_no_line_for_its_repository(self) -> None:
        """Covers: B149"""
        self.set_up(calendar="none", tasks={"backend": "markdown"})
        os.rename(self.store_root, self.store_root.with_name("moved"))

        self.assertNotIn("store-git", self.run_command("doctor")[1])

    def test_the_skills_that_run_doctor_name_every_state_that_is_a_problem(self) -> None:
        skills = Path(__file__).resolve().parents[1] / "skills"
        for skill in ("m2b", "setup"):
            body = (skills / skill / "SKILL.md").read_text(encoding="utf-8")
            for state in doctor.PROBLEMS:
                with self.subTest(skill=skill, state=state):
                    self.assertIn(f"`{state}`", body)

    def test_a_missing_store_is_reported_and_the_other_checks_still_run(self) -> None:
        self.set_up()
        os.rename(self.store_root, self.store_root.with_name("moved"))

        code, out, _ = self.run_command("doctor")

        self.assertEqual(code, cli.EXIT_PROBLEM)
        self.assertIn("store: not reachable", out)
        # Without the store, which task backend it uses is unknown, so the reminders-cli line stays.
        self.assertIn("reminders-cli: ", out)
        self.assertIn("calendar: reachable", out)

    def run_json_any(self, *arguments: str) -> dict[str, Any]:
        code, out, _ = self.run_command(*arguments, "--json")
        return {"code": code, "json": json.loads(out)}


if __name__ == "__main__":
    unittest.main()
