from __future__ import annotations

import datetime
import errno
import json
import os
import sys
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from m2b.config.store_settings import TasksSettings
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard
from m2b.store.icloud import ICloudStore
from m2b.tasks.apple_reminders import AppleRemindersTasks
from m2b.tasks.base import Tasks, TasksError, TasksUnreachableError, UnconfirmedTaskError, UnknownTaskError
from m2b.tasks.factory import open_tasks
from m2b.tasks.markdown import MarkdownTasks
from tasks_contract import Contracts

FAKE_REMINDERS = Path(__file__).resolve().parent / "fakes" / "fake_reminders.py"
TEST_LIST = "sb-test-inbox"


def fake_reminders(folder: Path, **state: Any) -> tuple[list[str], Path]:
    """The command of a fake ``reminders`` and its state file, with one empty test list."""
    state_file = folder / "fake-reminders.json"
    state_file.write_text(json.dumps({"lists": [TEST_LIST, "sb-test-other"], "items": {}, **state}), encoding="utf-8")
    return [sys.executable, str(FAKE_REMINDERS), str(state_file)], state_file


class MarkdownTasksContractTest(Contracts.TasksContract):
    def make_tasks(self, folder: Path) -> Tasks:
        (folder / "store").mkdir()
        self.store = FolderStore(folder / "store", folder / "machine-tmp", DatalessGuard(False))
        return MarkdownTasks(self.store)


class AppleRemindersContractTest(Contracts.TasksContract):
    def make_tasks(self, folder: Path) -> Tasks:
        command, self.state_file = fake_reminders(folder)
        return AppleRemindersTasks(TEST_LIST, command=command, timeout_seconds=10)


class AppleRemindersDueTest(unittest.TestCase):
    """reminders-cli reports every due as an instant in UTC; a date-only due is local midnight."""

    def setUp(self) -> None:
        import tempfile

        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        command, _ = fake_reminders(Path(self._temp.name))
        self.tasks = AppleRemindersTasks(TEST_LIST, command=command, timeout_seconds=10)

    def test_a_due_date_reads_back_as_that_day(self) -> None:
        self.tasks.add("Book the dentist", due=datetime.date(2026, 11, 20))

        (task,) = self.tasks.items()

        self.assertEqual(task.due, datetime.date(2026, 11, 20))

    def test_a_due_time_reads_back_in_local_time(self) -> None:
        due = datetime.datetime(2026, 11, 20, 15, 30).astimezone()
        self.tasks.add("Call with Acme", due=due)

        (task,) = self.tasks.items()

        self.assertEqual(task.due.isoformat() if task.due else None, due.isoformat())


class AppleRemindersAddTest(unittest.TestCase):
    def test_a_reminder_added_but_not_found_again_is_unconfirmed_never_a_reason_to_retry(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            command, _ = fake_reminders(Path(folder), mode="lose-notes-on-add")
            tasks = AppleRemindersTasks(TEST_LIST, command=command, timeout_seconds=10)

            with self.assertRaises(UnconfirmedTaskError) as caught:
                tasks.add("Call Dana")

        self.assertIn("was added", str(caught.exception))


class MarkdownTaskFilesTest(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._temp = tempfile.TemporaryDirectory()
        root = Path(self._temp.name)
        (root / "store").mkdir()
        self.store = FolderStore(root / "store", root / "machine-tmp", DatalessGuard(False))
        self.tasks = MarkdownTasks(self.store)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_each_task_is_its_own_file_named_by_a_twelve_hex_id(self) -> None:
        task_id = self.tasks.add("Call Dana", notes="about the shed", due=datetime.date(2026, 12, 1))

        self.assertRegex(task_id, r"\A[0-9a-f]{12}\Z")
        text = self.store.read_text(f"tasks/{task_id}.md")
        self.assertTrue(text.startswith("---\nstatus: open\ndue: 2026-12-01\ncreated: "))
        self.assertTrue(text.endswith("---\nCall Dana\nabout the shed\n"))

    def test_completing_writes_status_and_done(self) -> None:
        task_id = self.tasks.add("Water the plants")

        self.tasks.complete(task_id)

        text = self.store.read_text(f"tasks/{task_id}.md")
        self.assertIn("\nstatus: done\n", text)
        self.assertRegex(text, r"\ndone: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}\n")

    def test_a_hand_added_file_without_frontmatter_is_an_open_task_named_by_its_file(self) -> None:
        self.store.create_exclusive("tasks/call-the-plumber.md", b"Call the plumber\nbefore Friday\n")

        (task,) = self.tasks.items()

        self.assertEqual((task.id, task.title, task.notes), ("call-the-plumber", "Call the plumber", "before Friday"))
        self.tasks.complete("call-the-plumber")
        self.assertEqual(self.tasks.items(), [])
        self.assertIn("Call the plumber\nbefore Friday\n", self.store.read_text("tasks/call-the-plumber.md"))

    def test_a_task_file_that_cannot_be_read_is_left_out_and_the_others_are_listed(self) -> None:
        """Covers: B59"""
        self.store.create_exclusive("tasks/milk.md", b"---\nstatus: todo\n---\nMilk\n")
        self.store.create_exclusive("tasks/latin1.md", "Caf\u00e9".encode("latin-1"))
        task_id = self.tasks.add("Call Dana")

        self.assertEqual([task.id for task in self.tasks.items()], [task_id])
        self.assertEqual(self.tasks.completed_items(datetime.datetime(2026, 1, 1).astimezone()), [])
        problems = self.tasks.unreadable()
        self.assertEqual([path for path, _ in problems], ["tasks/latin1.md", "tasks/milk.md"])
        self.assertIn("todo", problems[1][1])
        self.assertFalse(self.tasks.lists_every_task())

    def test_a_hand_named_task_file_with_a_colon_is_named_by_its_whole_path(self) -> None:
        self.store.create_exclusive("tasks/Meeting 10:30.md", b"---\nstatus: soon\n---\nMeeting\n")

        ((path, problem),) = self.tasks.unreadable()

        self.assertEqual(path, "tasks/Meeting 10:30.md")
        self.assertIn("soon", problem)

    def test_done_without_a_date_takes_the_files_modification_time(self) -> None:
        self.store.create_exclusive("tasks/aaaaaaaaaaaa.md", b"---\nstatus: done\n---\nOld task\n")
        stamp = time.time() - 3600
        os.utime(self.store.path("tasks/aaaaaaaaaaaa.md"), (stamp, stamp))

        (task,) = self.tasks.completed_items(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1))

        assert task.completed_at is not None
        self.assertAlmostEqual(task.completed_at.timestamp(), stamp, delta=1)

    def test_a_dropped_task_counts_as_completed_but_stays_out_of_completed_items(self) -> None:
        self.store.create_exclusive("tasks/bbbbbbbbbbbb.md", b"---\nstatus: dropped\n---\nm2b: review\nm2b:review\n")

        (task,) = self.tasks.items(marker="review", include_completed=True)
        self.assertTrue(task.completed and task.dropped)
        self.assertEqual(self.tasks.items(), [])
        self.assertEqual(self.tasks.completed_items(datetime.datetime(2000, 1, 1, tzinfo=datetime.timezone.utc)), [])
        self.assertEqual([entry["status"] for entry in self.tasks.export()], ["dropped"])

    def test_a_conflict_copy_of_a_task_file_is_no_second_task(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "store"
            (root / "tasks").mkdir(parents=True)
            (root / "tasks" / "a1b2c3d4e5f6.md").write_text("---\nstatus: open\n---\nCall Dana\n", encoding="utf-8")
            (root / "tasks" / "a1b2c3d4e5f6 2.md").write_text("---\nstatus: done\n---\nCall Dana\n", encoding="utf-8")
            tasks = MarkdownTasks(ICloudStore(root, Path(folder) / "tmp", DatalessGuard(False), macos_release="15.0"))

            self.assertEqual([task.id for task in tasks.items(include_completed=True)], ["a1b2c3d4e5f6"])

    def test_a_dropbox_or_syncthing_copy_of_a_task_file_is_no_second_task(self) -> None:
        """Covers: B150"""
        done = b"---\nstatus: done\n---\nCall Dana\n"
        self.store.create_exclusive("tasks/a1b2c3d4e5f6.md", b"---\nstatus: open\n---\nCall Dana\n")
        self.store.create_exclusive("tasks/a1b2c3d4e5f6 (Dana's conflicted copy 2026-11-05).md", done)
        self.store.create_exclusive("tasks/a1b2c3d4e5f6.sync-conflict-20261105-081500-ABCDEFG.md", done)

        self.assertEqual([task.id for task in self.tasks.items(include_completed=True)], ["a1b2c3d4e5f6"])

    def test_a_due_time_with_microseconds_reads_back(self) -> None:
        due = datetime.datetime.now().astimezone() + datetime.timedelta(days=1)

        self.tasks.add("Call Dana", due=due)

        (task,) = self.tasks.items()
        assert isinstance(task.due, datetime.datetime)
        self.assertEqual(task.due, due.replace(microsecond=0))

    def test_a_hand_written_done_without_offset_is_read_as_local_time(self) -> None:
        self.store.create_exclusive(
            "tasks/dddddddddddd.md", b"---\nstatus: done\ndone: 2026-11-01T10:00:00\n---\nOld\n"
        )

        (task,) = self.tasks.completed_items(datetime.datetime(2026, 10, 1, tzinfo=datetime.timezone.utc))

        assert task.completed_at is not None
        self.assertEqual(task.completed_at, datetime.datetime(2026, 11, 1, 10, 0).astimezone())

    def test_an_unreadable_tasks_folder_is_unreachable(self) -> None:
        self.store.create_exclusive("tasks/eeeeeeeeeeee.md", b"x")
        real_iterdir = Path.iterdir

        def iterdir(path: Path) -> Any:
            if path.name == "tasks":
                raise PermissionError(errno.EPERM, "Operation not permitted")
            return real_iterdir(path)

        with mock.patch.object(Path, "iterdir", iterdir):
            for call in (self.tasks.check_reachable, self.tasks.items, self.tasks.export):
                with self.subTest(call=call.__name__), self.assertRaises(TasksUnreachableError):
                    call()

    def test_changing_an_evicted_task_file_is_unreachable_not_a_store_error(self) -> None:
        from store_contract import FakeEviction

        eviction = FakeEviction()
        store = FolderStore(self.store.root, self.store.temp_dir, DatalessGuard(True, lstat=eviction.lstat))
        tasks = MarkdownTasks(store)
        task_id = tasks.add("Call Dana")
        eviction.evicted.add(store.path(f"tasks/{task_id}.md"))

        for call in (tasks.complete, tasks.uncomplete, lambda task: tasks.set_notes(task, "x")):
            with self.subTest(call=getattr(call, "__name__", "set_notes")), self.assertRaises(TasksUnreachableError):
                call(task_id)


class AppleRemindersFailuresTest(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._temp = tempfile.TemporaryDirectory()
        self.folder = Path(self._temp.name)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _tasks(self, timeout: float = 10, list_name: str = TEST_LIST, **state: Any) -> AppleRemindersTasks:
        command, _ = fake_reminders(self.folder, **state)
        return AppleRemindersTasks(list_name, command=command, timeout_seconds=timeout)

    def test_zero_lists_is_not_reachable(self) -> None:
        """Covers: B24, X3"""
        with self.assertRaises(TasksUnreachableError) as caught:
            self._tasks(mode="no-lists").check_reachable()

        self.assertIn("Privacy", str(caught.exception))

    def test_a_missing_list_is_not_reachable(self) -> None:
        """Covers: X3"""
        with self.assertRaises(TasksUnreachableError) as caught:
            self._tasks(list_name="sb-test-missing").check_reachable()

        self.assertIn("sb-test-missing", str(caught.exception))

    def test_a_hanging_reminders_fails_after_the_timeout(self) -> None:
        """Covers: X4"""
        started = time.monotonic()

        with self.assertRaises(TasksUnreachableError) as caught:
            self._tasks(timeout=1, mode="hang").items()

        self.assertLess(time.monotonic() - started, 10)
        self.assertIn("1 seconds", str(caught.exception))

    def test_a_reply_that_is_not_json_fails_with_the_raw_reply(self) -> None:
        """Covers: X2"""
        with self.assertRaises(TasksError) as caught:
            self._tasks(mode="garbage").items()

        self.assertIn("EKErrorDomain", str(caught.exception))

    def test_a_missing_reminders_program_is_not_reachable(self) -> None:
        tasks = AppleRemindersTasks(TEST_LIST, command=[str(self.folder / "no-such-program")])

        with self.assertRaises(TasksUnreachableError):
            tasks.check_reachable()

    def test_an_add_that_prints_no_id_finds_the_task_by_its_nonce(self) -> None:
        tasks = self._tasks(mode="no-id-on-add")

        task_id = tasks.add("Call Dana", notes="m2b:review")

        (task,) = tasks.items()
        self.assertEqual((task.id, task.notes), (task_id, "m2b:review"))

    def test_notes_and_titles_that_start_with_a_dash_reach_reminders_as_text(self) -> None:
        tasks = self._tasks()

        task_id = tasks.add("-1 day left", notes="- buy eggs\n- buy milk")
        tasks.set_notes(task_id, "--notes is just text here")

        (task,) = tasks.items()
        self.assertEqual((task.title, task.notes), ("-1 day left", "--notes is just text here"))

    def test_a_failing_nonce_cleanup_still_returns_the_new_id(self) -> None:
        tasks = self._tasks()
        real_run = tasks._run

        def failing_edit(arguments: list[str], expect_json: bool = True) -> Any:
            if arguments[0] == "edit":
                raise TasksUnreachableError("reminders did not answer within 1 seconds")
            return real_run(arguments, expect_json)

        with mock.patch.object(tasks, "_run", failing_edit):
            task_id = tasks.add("Call Dana")

        self.assertEqual([task.id for task in tasks.items()], [task_id])

    def test_notes_of_a_completed_reminder_need_it_reopened_first(self) -> None:
        tasks = self._tasks()
        task_id = tasks.add("m2b: review", notes="m2b:review")
        tasks.complete(task_id)

        with self.assertRaises(TasksError) as caught:
            tasks.set_notes(task_id, "m2b:review\nnew findings")

        self.assertIn("reopen", str(caught.exception))
        self.assertNotIsInstance(caught.exception, UnknownTaskError)

    def test_the_nonce_never_stays_in_the_notes(self) -> None:
        tasks = self._tasks()

        tasks.add("Buy milk")

        (task,) = tasks.items()
        self.assertEqual(task.notes, "")


class OpenTasksTest(unittest.TestCase):
    def test_the_backend_follows_the_store_settings(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            store = FolderStore(Path(folder), Path(folder) / "tmp", DatalessGuard(False))

            markdown = open_tasks(TasksSettings("markdown", None), store, {})
            apple = open_tasks(TasksSettings("apple-reminders", TEST_LIST, 7), store, {"reminders": "/opt/x/reminders"})

        self.assertIsInstance(markdown, MarkdownTasks)
        self.assertIsInstance(apple, AppleRemindersTasks)
        self.assertEqual((apple._list, apple._command, apple._timeout), (TEST_LIST, ["/opt/x/reminders"], 7))


class RemindersFileTest(unittest.TestCase):
    def test_apple_reminders_keeps_no_task_files_and_lists_every_task(self) -> None:
        """Covers: B59

        Lint and m2b tasks list ask every backend for the task files it cannot read; Reminders has
        none, so a tasks/ folder left from the Markdown backend is never read as its own.
        """
        reminders = AppleRemindersTasks("sb-test-inbox", command=("/sb-test/no-such-reminders",))

        self.assertEqual(reminders.unreadable(), [])
        self.assertTrue(reminders.lists_every_task())


if __name__ == "__main__":
    unittest.main()
