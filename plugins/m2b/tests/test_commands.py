"""The stage-1 commands against configured backends: tasks, calendar, store, config, profile, doctor."""

from __future__ import annotations

import contextlib
import datetime
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from m2b import cli, paths
from m2b.calendar.base import local_midnight
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

        (candidate,) = self.run_json("tasks", "list", "--marker", "candidate")
        listed = self.run_json("tasks", "list")
        self.assertEqual(candidate["title"], "Merken? Dana prefers tea")
        self.assertEqual(candidate["marker"], "candidate")
        self.assertIn(
            {"id": task_id, "title": "Call Dana", "notes": "about the shed", "due": "2026-12-01"},
            [{key: task[key] for key in ("id", "title", "notes", "due")} for task in listed],
        )

        self.assertEqual(self.run_command("tasks", "complete", task_id)[0], cli.EXIT_OK)
        self.assertEqual([task["title"] for task in self.run_json("tasks", "list")], ["Merken? Dana prefers tea"])
        (done,) = [task for task in self.run_json("tasks", "list", "--include-completed") if task["id"] == task_id]
        self.assertTrue(done["completed"])

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
