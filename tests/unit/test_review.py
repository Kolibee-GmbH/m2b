"""The review task: the one place where a run leaves what the owner must do (B14, B15)."""

from __future__ import annotations

import datetime
import tempfile
import unittest
from pathlib import Path
from typing import Any

import test_tasks_backends
from m2b import review
from m2b.curate.report import Finding
from m2b.locale import load_locale
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard
from m2b.tasks import markers
from m2b.tasks.apple_reminders import AppleRemindersTasks
from m2b.tasks.base import Tasks
from m2b.tasks.markdown import MarkdownTasks

RUN_AT = datetime.datetime(2026, 11, 7, 3, 0).astimezone()
LATER = datetime.datetime(2026, 11, 8, 3, 0).astimezone()
ACTION = Finding("lint", "action", "memory/dana.md links [[nothing.md]], which is no corpus file")
INFO = Finding("lint", "info", "3 binary files, 2.0 KB in corpus/")


class ReviewFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        base = Path(self._temp.name)
        (base / "store").mkdir()
        self.tasks: Tasks = self.make_tasks(base)
        self.english = load_locale("en")

    def make_tasks(self, base: Path) -> Tasks:
        return MarkdownTasks(FolderStore(base / "store", base / "tmp", DatalessGuard(False)))

    def update(
        self, findings: Any = (), failures: Any = (), at: datetime.datetime = RUN_AT, locale: Any = None
    ) -> review.ReviewOutcome:
        return review.update_review(self.tasks, list(findings), list(failures), at, locale or self.english)

    def review_tasks(self) -> list[Any]:
        return self.tasks.items(marker=markers.REVIEW, include_completed=True)


class ReviewTest(ReviewFixture):
    def test_action_findings_and_failures_make_one_open_review_task(self) -> None:
        """Covers: B14"""
        outcome = self.update([ACTION, INFO], [review.StepFailure("ingest", "timed out after 15 minutes")])

        (task,) = self.review_tasks()
        self.assertEqual((outcome.task_id, outcome.change), (task.id, "created"))
        self.assertFalse(task.completed)
        self.assertEqual(task.title, "m2b: review")
        self.assertEqual(
            task.notes,
            "m2b:review\n"
            f"Curation run of {RUN_AT:%Y-%m-%d %H:%M}\n"
            "\n"
            "lint: memory/dana.md links [[nothing.md]], which is no corpus file\n"
            "\n"
            "The step ingest failed: timed out after 15 minutes",
        )

    def test_a_later_run_rewrites_the_same_task(self) -> None:
        self.update([ACTION])

        outcome = self.update([Finding("ingest", "action", "x.md stays in the inbox")], at=LATER)

        (task,) = self.review_tasks()
        self.assertEqual(outcome.change, "updated")
        self.assertIn(f"Curation run of {LATER:%Y-%m-%d %H:%M}", task.notes)
        self.assertNotIn("nothing.md", task.notes)

    def test_a_completed_review_task_is_reopened_not_duplicated(self) -> None:
        """Covers: B15"""
        first = self.update([ACTION]).task_id
        assert first is not None
        self.tasks.complete(first)

        outcome = self.update([ACTION], at=LATER)

        (task,) = self.review_tasks()
        self.assertEqual((task.id, task.completed, outcome.change), (first, False, "reopened"))

    def test_a_dropped_review_task_is_reopened_too(self) -> None:
        first = self.update([ACTION]).task_id
        assert first is not None
        self.tasks.drop(first)

        self.update([ACTION], at=LATER)

        (task,) = self.review_tasks()
        self.assertEqual((task.id, task.completed, task.dropped), (first, False, False))
        self.assertTrue(task.notes.startswith("m2b:review\n"))

    def test_a_renamed_review_task_is_still_found_by_its_marker(self) -> None:
        """Covers: B15"""
        first = self.update([ACTION]).task_id
        assert first is not None
        task_file = next(Path(self._temp.name, "store", "tasks").glob("*.md"))
        task_file.write_text(task_file.read_text(encoding="utf-8").replace("m2b: review", "Look at this"))

        self.update([ACTION], at=LATER)

        (task,) = self.review_tasks()
        self.assertEqual((task.id, task.title), (first, "Look at this"))

    def test_only_info_findings_complete_an_open_review_task_and_create_none(self) -> None:
        """Covers: B14"""
        self.assertEqual(self.update([INFO]).change, "none")
        self.assertEqual(self.review_tasks(), [])

        first = self.update([ACTION]).task_id
        outcome = self.update([INFO], at=LATER)

        (task,) = self.review_tasks()
        self.assertEqual((task.id, task.completed, outcome.change), (first, True, "completed"))

    def test_a_clean_run_leaves_a_completed_review_task_alone(self) -> None:
        first = self.update([ACTION]).task_id
        assert first is not None
        self.tasks.complete(first)

        self.assertEqual(self.update([]).change, "none")
        (task,) = self.review_tasks()
        self.assertEqual((task.id, task.completed), (first, True))

    def test_a_failure_is_one_paragraph_of_bounded_length(self) -> None:
        traceback = "Traceback (most recent call last):\n\n  File x\n\nValueError: " + "y" * 2000

        self.update(failures=[review.StepFailure("ingest", traceback)])

        (task,) = self.review_tasks()
        paragraphs = task.notes.split("\n\n")
        self.assertEqual(len(paragraphs), 2)
        self.assertLessEqual(len(paragraphs[1]), 600)
        self.assertTrue(paragraphs[1].startswith("The step ingest failed: Traceback (most recent call last): File x"))

    def test_a_finding_of_an_unknown_kind_reaches_the_owner(self) -> None:
        """Only info stays out: a kind nobody knows is never dropped silently."""
        self.update([Finding("worklog", "warning", "the note\n\ncould not be written")])

        (task,) = self.review_tasks()
        self.assertIn("worklog: the note could not be written", task.notes)
        self.assertEqual(len(task.notes.split("\n\n")), 2)

    def test_the_text_around_the_findings_is_in_the_profiles_language(self) -> None:
        self.update([ACTION], [review.StepFailure("ingest", "timed out")], locale=load_locale("de"))

        (task,) = self.review_tasks()
        self.assertEqual(task.title, "m2b: Durchsicht")
        self.assertIn(f"Kurationslauf vom {RUN_AT:%Y-%m-%d %H:%M}", task.notes)
        self.assertIn("Der Schritt ingest ist fehlgeschlagen: timed out", task.notes)


class ReviewOnRemindersTest(ReviewFixture):
    """Apple Reminders refuses new notes on a completed reminder, so it is reopened first."""

    def make_tasks(self, base: Path) -> Tasks:
        command, _ = test_tasks_backends.fake_reminders(base)
        return AppleRemindersTasks(test_tasks_backends.TEST_LIST, command=command, timeout_seconds=10)

    def test_a_completed_review_reminder_is_reopened_with_the_new_notes(self) -> None:
        first = self.update([ACTION]).task_id
        assert first is not None
        self.tasks.complete(first)

        self.update([Finding("ingest", "action", "x.md stays in the inbox")], at=LATER)

        (task,) = self.review_tasks()
        self.assertEqual((task.id, task.completed), (first, False))
        self.assertIn("x.md stays in the inbox", task.notes)


if __name__ == "__main__":
    unittest.main()
