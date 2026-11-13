"""A current item no capture touched for a month goes to the owner as a question: still current?"""

from __future__ import annotations

import datetime
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from m2b.current_check import ask, settle
from m2b.expiry import QuietCurrent
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard
from m2b.tasks import markers
from m2b.tasks.base import Task, TasksError
from m2b.tasks.markdown import MarkdownTasks

PREFIX = "Still current?"
TODAY = datetime.date(2026, 11, 20)
INDEX = """# Memory

## Facts

- Dana's birthday is on 3 March (dana.md)

## Current

- Rebuilding the garden shed roof (since 2026-11-03)
- Planning the trip to Porto (since 2026-10-02)
"""
PORTO = QuietCurrent("Planning the trip to Porto", "2026-10-02")
ACME_EXPORT = QuietCurrent("Building the Acme export", "2026-10-01")
ACME_UNDER_CURRENT = "\n### Acme Ltd (Acme, Kim Lee)\n- Building the Acme export (since 2026-10-01)\n"
LIST = "markdown:"


class CurrentCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.root = base / "sb-test-store"
        self.store = FolderStore(self.root, base / "machine-tmp", DatalessGuard(False))
        (self.root / "memory").mkdir(parents=True)
        self.index().write_text(INDEX, encoding="utf-8")
        self.tasks = MarkdownTasks(self.store)

    def index(self) -> Path:
        return self.root / "memory" / "MEMORY.md"

    def questions(self) -> list[Task]:
        return self.tasks.items(marker=markers.CURRENT, include_completed=True)

    def drop(self, item: QuietCurrent) -> None:
        """Asks about ``item``, answers with a drop and lets the next run apply it."""
        ask(self.store, self.tasks, [item], PREFIX, task_list=LIST)
        [question] = [task for task in self.questions() if not task.dropped]
        self.tasks.drop(question.id)
        settle(self.store, self.tasks, TODAY, task_list=LIST)

    def test_a_quiet_item_becomes_one_question_however_often_it_is_asked(self) -> None:
        """Covers: B42"""
        ask(self.store, self.tasks, [PORTO], PREFIX, task_list=LIST)
        ask(self.store, self.tasks, [PORTO], PREFIX, task_list=LIST)

        [question] = self.questions()
        self.assertEqual(question.title, "Still current? Planning the trip to Porto")
        self.assertFalse(question.completed)

    def test_a_ticked_question_keeps_the_item_from_today_and_goes(self) -> None:
        """Covers: B42"""
        ask(self.store, self.tasks, [PORTO], PREFIX, task_list=LIST)
        [question] = self.questions()
        self.tasks.complete(question.id)

        settle(self.store, self.tasks, TODAY, task_list=LIST)

        self.assertIn("- Planning the trip to Porto (since 2026-11-20)\n", self.index().read_text(encoding="utf-8"))
        self.assertEqual(self.questions(), [])

    def test_a_dropped_question_takes_the_item_out_of_current_and_goes(self) -> None:
        """Covers: B42"""
        ask(self.store, self.tasks, [PORTO], PREFIX, task_list=LIST)
        [question] = self.questions()
        self.tasks.drop(question.id)

        settle(self.store, self.tasks, TODAY, task_list=LIST)

        text = self.index().read_text(encoding="utf-8")
        self.assertNotIn("Porto", text)
        self.assertIn("- Rebuilding the garden shed roof (since 2026-11-03)\n", text)
        self.assertEqual(self.questions(), [])

    def test_an_open_question_stays_and_the_item_with_it(self) -> None:
        ask(self.store, self.tasks, [PORTO], PREFIX, task_list=LIST)

        settle(self.store, self.tasks, TODAY, task_list=LIST)

        self.assertEqual(len(self.questions()), 1)
        self.assertEqual(self.index().read_text(encoding="utf-8"), INDEX)

    def test_a_question_whose_item_ingest_changed_meanwhile_goes_without_touching_memory(self) -> None:
        ask(self.store, self.tasks, [PORTO], PREFIX, task_list=LIST)
        changed = INDEX.replace("Planning the trip to Porto", "Booked the trip to Porto")
        self.index().write_text(changed, encoding="utf-8")
        before = self.index().read_text(encoding="utf-8")
        [question] = self.questions()
        self.tasks.drop(question.id)

        settle(self.store, self.tasks, TODAY, task_list=LIST)

        self.assertEqual(self.index().read_text(encoding="utf-8"), before)
        self.assertEqual(self.questions(), [])

    def test_a_crash_after_memory_was_written_leaves_a_question_whose_rerun_changes_nothing(self) -> None:
        for answer, expected in (("complete", "- Planning the trip to Porto (since 2026-11-20)\n"), ("drop", None)):
            with self.subTest(answer=answer):
                self.index().write_text(INDEX, encoding="utf-8")
                ask(self.store, self.tasks, [PORTO], PREFIX, task_list=LIST)
                [question] = self.questions()
                getattr(self.tasks, answer)(question.id)
                crash = mock.patch.object(self.tasks, "delete", side_effect=TasksError("crash"))
                with crash, self.assertRaises(TasksError):
                    settle(self.store, self.tasks, TODAY, task_list=LIST)
                after_crash = self.index().read_text(encoding="utf-8")

                settle(self.store, self.tasks, TODAY, task_list=LIST)

                self.assertEqual(self.index().read_text(encoding="utf-8"), after_crash)
                if expected is None:
                    self.assertNotIn("Porto", after_crash)
                else:
                    self.assertIn(expected, after_crash)
                self.assertEqual(self.questions(), [])

    def test_an_item_under_a_subheading_of_current_is_answered_too(self) -> None:
        self.index().write_text(INDEX.replace("## Current\n\n", "## Current\n\n### Trips\n\n"), encoding="utf-8")
        ask(self.store, self.tasks, [PORTO], PREFIX, task_list=LIST)
        [question] = self.questions()
        self.tasks.drop(question.id)

        settle(self.store, self.tasks, TODAY, task_list=LIST)

        self.assertNotIn("Porto", self.index().read_text(encoding="utf-8"))

    def test_a_topics_last_item_dropped_takes_its_heading_under_current_with_it(self) -> None:
        """Covers: B137"""
        lumen = "\n### Lumen (Lumen, Ben Ortiz)\n- Auditing Lumen's backups (since 2026-11-10)\n"
        for after_acme in (lumen, ""):
            with self.subTest(after_acme=after_acme):
                self.index().write_text(INDEX + ACME_UNDER_CURRENT + after_acme, encoding="utf-8")
                self.drop(ACME_EXPORT)

                self.assertEqual(self.index().read_text(encoding="utf-8"), INDEX + after_acme)

    def test_a_topic_that_keeps_an_item_keeps_its_heading_and_the_one_under_facts_stays(self) -> None:
        """Covers: B137"""
        facts = "### Acme Ltd (Acme, Kim Lee)\n- Kim Lee leads Acme's IT (kim-lee.md)\n\n"
        index = INDEX.replace("## Current", f"{facts}## Current")
        other = "- Writing the Acme offer (since 2026-11-12)\n"
        self.index().write_text(index + ACME_UNDER_CURRENT + other, encoding="utf-8")
        self.drop(ACME_EXPORT)

        self.assertEqual(self.index().read_text(encoding="utf-8"), f"{index}\n### Acme Ltd (Acme, Kim Lee)\n{other}")

    def test_a_ticked_question_about_an_item_under_a_topic_dates_it_where_it_stands(self) -> None:
        """Covers: B137"""
        self.index().write_text(INDEX + ACME_UNDER_CURRENT, encoding="utf-8")
        ask(self.store, self.tasks, [ACME_EXPORT], PREFIX, task_list=LIST)
        [question] = self.questions()
        self.tasks.complete(question.id)

        settle(self.store, self.tasks, TODAY, task_list=LIST)

        self.assertEqual(
            self.index().read_text(encoding="utf-8"),
            INDEX + ACME_UNDER_CURRENT.replace("2026-10-01", "2026-11-20"),
        )

    def test_a_heading_that_is_no_topic_stays_when_its_last_item_goes(self) -> None:
        self.index().write_text(INDEX.replace("- Planning", "### Trips\n- Planning"), encoding="utf-8")
        self.drop(PORTO)

        self.assertTrue(self.index().read_text(encoding="utf-8").endswith("### Trips\n"))

    def test_an_answer_applies_to_every_line_with_the_item(self) -> None:
        twice = INDEX + "- Planning the trip to Porto (since 2026-09-01)\n"
        self.index().write_text(twice, encoding="utf-8")
        ask(self.store, self.tasks, [PORTO], PREFIX, task_list=LIST)
        [question] = self.questions()
        self.tasks.drop(question.id)

        settle(self.store, self.tasks, TODAY, task_list=LIST)

        self.assertNotIn("Porto", self.index().read_text(encoding="utf-8"))

    def test_a_question_the_owner_deleted_counts_as_dropped_and_is_not_asked_again(self) -> None:
        """Covers: B42"""
        ask(self.store, self.tasks, [PORTO], PREFIX, task_list=LIST)
        [question] = self.questions()
        self.tasks.delete(question.id)

        settle(self.store, self.tasks, TODAY, task_list=LIST)
        ask(self.store, self.tasks, [], PREFIX, task_list=LIST)

        self.assertNotIn("Porto", self.index().read_text(encoding="utf-8"))
        self.assertEqual(self.questions(), [])

    def test_after_a_switch_to_another_task_list_an_unanswered_question_is_asked_again_not_dropped(self) -> None:
        """Covers: B58"""
        ask(self.store, self.tasks, [PORTO], PREFIX, task_list=LIST)
        other_root = self.root.parent / "sb-test-other-list"
        other = MarkdownTasks(FolderStore(other_root, self.root.parent / "machine-tmp", DatalessGuard(False)))

        settle(self.store, other, TODAY, task_list="apple-reminders:Inbox")
        ask(self.store, other, [PORTO], PREFIX, task_list="apple-reminders:Inbox")

        self.assertIn("Planning the trip to Porto", self.index().read_text(encoding="utf-8"))
        [question] = other.items(marker=markers.CURRENT, include_completed=True)
        self.assertEqual(question.title, "Still current? Planning the trip to Porto")

    def test_a_question_whose_task_file_cannot_be_read_is_not_taken_for_deleted(self) -> None:
        """Covers: B59"""
        ask(self.store, self.tasks, [PORTO], PREFIX, task_list=LIST)
        [question] = self.questions()
        task_file = self.root / "tasks" / f"{question.id}.md"
        task_file.write_text(task_file.read_text(encoding="utf-8").replace("status: open", "status: maybe"))

        settle(self.store, self.tasks, TODAY, task_list=LIST)

        self.assertIn("Planning the trip to Porto", self.index().read_text(encoding="utf-8"))

    def test_an_open_question_whose_item_ingest_changed_is_closed_at_the_next_ask(self) -> None:
        ask(self.store, self.tasks, [PORTO], PREFIX, task_list=LIST)
        booked = "Booked the trip to Porto (since 2026-11-19)"
        changed = INDEX.replace("Planning the trip to Porto (since 2026-10-02)", booked)
        self.index().write_text(changed, encoding="utf-8")

        ask(self.store, self.tasks, [], PREFIX, task_list=LIST)
        settle(self.store, self.tasks, TODAY, task_list=LIST)

        self.assertEqual(self.questions(), [])
        self.assertEqual(self.index().read_text(encoding="utf-8"), changed)


if __name__ == "__main__":
    unittest.main()
