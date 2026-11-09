"""The journal of completed tasks: one file per month in the corpus, appended in place (B23)."""

from __future__ import annotations

import datetime
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import test_commands
from m2b import cli, journal
from m2b.store.folder import FolderStore
from m2b.store.guard import SF_DATALESS, DatalessGuard
from m2b.tasks import markers
from m2b.tasks.base import Task, TasksUnreachableError

SINCE = datetime.date(2026, 11, 1)
NOW = datetime.datetime(2026, 12, 2, 9, 0).astimezone()


def local(year: int, month: int, day: int, hour: int = 12) -> datetime.datetime:
    return datetime.datetime(year, month, day, hour).astimezone()


def done(task_id: str, title: str, at: datetime.datetime, notes: str = "") -> Task:
    return Task(task_id, title, notes=notes, completed=True, completed_at=at)


class FakeTasks:
    def __init__(self, items: list[Task]) -> None:
        self.items_done = items
        self.since: datetime.datetime | None = None

    def check_reachable(self) -> None:
        pass

    def completed_items(self, since: datetime.datetime) -> list[Task]:
        self.since = since
        return [task for task in self.items_done if task.completed_at and task.completed_at >= since]


class JournalTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        base = Path(self._temp.name)
        self.root = base / "sb-test-store"
        self.root.mkdir()
        self.evicted: set[str] = set()
        self.store = FolderStore(self.root, base / "machine-tmp", DatalessGuard(True, lstat=self._lstat))

    def _lstat(self, path: str | os.PathLike[str]) -> Any:
        result = os.lstat(path)
        relative = Path(path).relative_to(self.root).as_posix() if Path(path).is_relative_to(self.root) else ""
        return mock.Mock(st_flags=SF_DATALESS if relative in self.evicted else 0, st_mode=result.st_mode)

    def run_journal(self, items: list[Task]) -> journal.JournalReport:
        return journal.write_journal(self.store, FakeTasks(items), SINCE, NOW)

    def read(self, relative: str) -> str:
        return (self.root / relative).read_text(encoding="utf-8")

    def test_completed_tasks_go_into_the_file_of_their_month_one_line_each(self) -> None:
        report = self.run_journal(
            [
                done("aaaa00000001", "Call the plumber", local(2026, 11, 13, 10)),
                done("bbbb00000002", "Renew passport", local(2026, 12, 1, 8)),
            ]
        )

        november = self.read("corpus/2026/11/202611-done.md")
        self.assertTrue(november.startswith("---\ncreated: "))
        self.assertIn("\nsource: journal\nkind: journal\n---\n", november)
        self.assertTrue(november.endswith("- 2026-11-13 Call the plumber <!-- m2b:done aaaa00000001 2026-11-13 -->\n"))
        self.assertIn(
            "- 2026-12-01 Renew passport <!-- m2b:done bbbb00000002 2026-12-01 -->\n",
            self.read("corpus/2026/12/202612-done.md"),
        )
        self.assertEqual(report.appended, {"corpus/2026/11/202611-done.md": 1, "corpus/2026/12/202612-done.md": 1})

    def test_only_new_pairs_are_appended_and_the_existing_bytes_stay(self) -> None:
        """Covers: B23"""
        existing = (
            "---\ncreated: 2026-11-05T03:00:00+01:00\nsource: journal\nkind: journal\n---\n"
            "- 2026-11-04 Water the plants <!-- m2b:done aaaa00000001 2026-11-04 -->\n"
            "a line the owner added by hand\n"
        )
        (self.root / "corpus" / "2026" / "11").mkdir(parents=True)
        (self.root / "corpus" / "2026" / "11" / "202611-done.md").write_text(existing, encoding="utf-8")

        self.run_journal(
            [
                done("aaaa00000001", "Water the plants", local(2026, 11, 4)),
                done("aaaa00000001", "Water the plants", local(2026, 11, 18)),
                done("cccc00000003", "Book the dentist", local(2026, 11, 20)),
            ]
        )

        self.assertEqual(
            self.read("corpus/2026/11/202611-done.md"),
            existing
            + "- 2026-11-18 Water the plants <!-- m2b:done aaaa00000001 2026-11-18 -->\n"
            + "- 2026-11-20 Book the dentist <!-- m2b:done cccc00000003 2026-11-20 -->\n",
        )

    def test_a_second_run_adds_nothing(self) -> None:
        items = [done("aaaa00000001", "Call the plumber", local(2026, 11, 13))]
        self.run_journal(items)
        before = self.read("corpus/2026/11/202611-done.md")

        report = self.run_journal(items)

        self.assertEqual(self.read("corpus/2026/11/202611-done.md"), before)
        self.assertEqual(report.appended, {})

    def test_a_hand_named_task_with_spaces_or_a_comment_end_in_its_id_is_written_once(self) -> None:
        """Covers: B23"""
        items = [
            done("Call the plumber", "Call the plumber", local(2026, 11, 13)),
            done("odd --> name", "Odd one", local(2026, 11, 13)),
        ]
        self.run_journal(items)
        before = self.read("corpus/2026/11/202611-done.md")

        report = self.run_journal(items)

        self.assertEqual(self.read("corpus/2026/11/202611-done.md"), before)
        self.assertEqual(report.appended, {})
        self.assertEqual(before.count("<!--"), 2)
        self.assertEqual(before.count("-->"), 2)

    def test_curator_tasks_are_left_out_and_capture_tasks_are_the_owners(self) -> None:
        """Covers: B23"""
        self.run_journal(
            [
                done("aaaa00000001", "m2b: review", local(2026, 11, 13), notes=markers.marker_line(markers.REVIEW)),
                done("bbbb00000002", "Remember? Dana prefers tea", local(2026, 11, 13), notes="m2b:candidate"),
                done("dddd00000004", "Still current? The trip", local(2026, 11, 13), notes="m2b:current 1a2b3c4d5e6f"),
                done("cccc00000003", "Call Dana", local(2026, 11, 13), notes="m2b:capture x.md follow-up"),
            ]
        )

        self.assertNotIn("review", self.read("corpus/2026/11/202611-done.md"))
        self.assertNotIn("Remember?", self.read("corpus/2026/11/202611-done.md"))
        self.assertNotIn("Still current?", self.read("corpus/2026/11/202611-done.md"))
        self.assertIn("Call Dana", self.read("corpus/2026/11/202611-done.md"))

    def test_nothing_before_journal_since_is_asked_for_or_written(self) -> None:
        tasks = FakeTasks([done("aaaa00000001", "Old one", local(2026, 10, 31, 23))])

        journal.write_journal(self.store, tasks, SINCE, NOW)

        assert tasks.since is not None
        self.assertEqual(tasks.since, datetime.datetime(2026, 11, 1).astimezone())
        self.assertFalse((self.root / "corpus").exists())

    def test_a_title_cannot_open_a_comment_or_break_the_line(self) -> None:
        self.run_journal([done("aaaa00000001", "Fix <!-- the\nheader", local(2026, 11, 13))])

        line = self.read("corpus/2026/11/202611-done.md").splitlines()[-1]
        self.assertEqual(line, "- 2026-11-13 Fix &lt;!-- the header <!-- m2b:done aaaa00000001 2026-11-13 -->")

    def test_an_evicted_month_file_fails_the_step_before_anything_is_written(self) -> None:
        """Covers: X3"""
        (self.root / "corpus" / "2026" / "12").mkdir(parents=True)
        (self.root / "corpus" / "2026" / "12" / "202612-done.md").write_text("old", encoding="utf-8")
        self.evicted.add("corpus/2026/12/202612-done.md")

        with self.assertRaises(journal.StoreError):
            self.run_journal(
                [
                    done("aaaa00000001", "Call the plumber", local(2026, 11, 13)),
                    done("bbbb00000002", "Renew passport", local(2026, 12, 1)),
                ]
            )

        self.assertFalse((self.root / "corpus" / "2026" / "11").exists())

    def test_unreachable_tasks_fail_the_step_and_write_nothing(self) -> None:
        """Covers: X3"""
        tasks = mock.Mock()
        tasks.completed_items.side_effect = TasksUnreachableError("Reminders did not answer")

        with self.assertRaises(TasksUnreachableError):
            journal.write_journal(self.store, tasks, SINCE, NOW)
        self.assertFalse((self.root / "corpus").exists())

    def test_an_empty_answer_without_access_is_could_not_look_not_nothing_completed(self) -> None:
        """Covers: X3 (without the privacy grant Reminders answers an empty list with exit 0)"""
        tasks = mock.Mock()
        tasks.check_reachable.side_effect = TasksUnreachableError("no access to Reminders")
        tasks.completed_items.return_value = []

        with self.assertRaises(TasksUnreachableError):
            journal.write_journal(self.store, tasks, SINCE, NOW)
        tasks.completed_items.assert_not_called()

    def test_a_month_file_that_is_not_utf8_is_a_problem_for_the_owner(self) -> None:
        (self.root / "corpus" / "2026" / "11").mkdir(parents=True)
        (self.root / "corpus" / "2026" / "11" / "202611-done.md").write_bytes(b"\xff old")

        with self.assertRaises(journal.NoteFormatError):
            self.run_journal([done("aaaa00000001", "Call the plumber", local(2026, 11, 13))])


class JournalCommandTest(test_commands.CommandTest):
    def setUp(self) -> None:
        super().setUp()
        # The curation run calls these commands; outside it they are refused.
        self.environ["M2B_CURATION_RUN"] = "1"

    def test_journal_writes_the_completed_tasks_and_prints_the_files(self) -> None:
        self.set_up(calendar="none")
        _, out, _ = self.run_command("tasks", "add", "Call the plumber")
        self.run_command("tasks", "complete", out.strip())

        answer = self.run_json("journal")

        (path,) = answer["appended"]
        self.assertTrue(path.startswith("corpus/") and path.endswith("-done.md"))
        self.assertIn("Call the plumber", (self.store_root / path).read_text(encoding="utf-8"))
        self.assertEqual(self.run_command("journal")[0], cli.EXIT_OK)


if __name__ == "__main__":
    unittest.main()
