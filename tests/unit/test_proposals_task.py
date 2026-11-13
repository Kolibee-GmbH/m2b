"""The one task that says proposals from the sessions wait for an answer."""

from __future__ import annotations

import datetime
from typing import Any
from unittest import mock

import test_tasks_backends
from m2b import proposal_answers, proposals, proposals_task
from m2b.locale import load_locale
from m2b.store.base import EvictedFileError
from m2b.tasks import markers
from m2b.tasks.apple_reminders import AppleRemindersTasks
from m2b.tasks.base import Tasks, TasksError
from m2b.tasks.markdown import MarkdownTasks
from test_proposal_answers import AnswerFixture
from test_proposals import DANA, LADDER, NOW

DANA_ID = proposals.proposal_id(DANA)
LADDER_ID = proposals.proposal_id(LADDER)
LATER = NOW + datetime.timedelta(days=1)
ONE_WAITS = (
    "m2b:proposals\n"
    "One proposal from your sessions waits for your answer: m2b proposals shows it, and there you keep "
    "or drop it. Completing this task answers nothing."
)
TWO_WAIT = (
    "m2b:proposals\n"
    "2 proposals from your sessions wait for your answer: m2b proposals lists them, and there you keep "
    "or drop each. Completing this task answers none of them."
)


class ProposalsTaskFixture(AnswerFixture):
    def setUp(self) -> None:
        super().setUp()
        self.tasks = self.make_tasks()
        self.english = load_locale("en")

    def make_tasks(self) -> Tasks:
        return MarkdownTasks(self.store)

    def update(self, locale: Any = None) -> proposals_task.TaskOutcome:
        return proposals_task.update(self.store, self.tasks, locale or self.english)

    def proposal_tasks(self) -> list[Any]:
        return self.tasks.items(marker=markers.PROPOSALS, include_completed=True)

    def the_task(self) -> Any:
        (task,) = self.proposal_tasks()
        return task

    def start_over(self) -> None:
        """An empty store again, for the next case of a test that goes through several."""
        for task in self.proposal_tasks():
            self.tasks.delete(task.id)
        for name in self.answer_files():
            (self.root / proposal_answers.FOLDER / name).unlink()
        (self.root / proposals.PROPOSALS_FILE).unlink()


class WaitingProposalsTest(ProposalsTaskFixture):
    def test_proposals_that_wait_make_one_open_task_that_says_how_many(self) -> None:
        """Covers: B124"""
        self.kept(DANA, LADDER)

        outcome = self.update()

        task = self.the_task()
        self.assertEqual(outcome, proposals_task.TaskOutcome("created", 2))
        self.assertFalse(task.completed)
        self.assertEqual(task.title, "m2b: proposals from your sessions")
        self.assertEqual(task.notes, TWO_WAIT)
        self.assertIsNone(task.due)

    def test_a_single_proposal_is_said_as_one(self) -> None:
        self.kept(DANA)

        self.update()

        self.assertEqual(self.the_task().notes, ONE_WAITS)

    def test_the_task_is_in_the_language_of_the_profile(self) -> None:
        """Covers: B124"""
        self.kept(DANA, LADDER)

        self.update(load_locale("de"))

        task = self.the_task()
        self.assertEqual(task.title, "m2b: Vorschläge aus deinen Sessions")
        self.assertIn("\n2 Vorschläge aus deinen Sessions warten auf deine Antwort: m2b proposals ", task.notes)

    def test_a_second_run_adds_no_second_task_and_rewrites_nothing(self) -> None:
        """Covers: B124"""
        self.kept(DANA, LADDER)
        self.update()

        with mock.patch.object(MarkdownTasks, "set_notes") as rewritten:
            outcome = self.update()

        self.assertEqual(outcome, proposals_task.TaskOutcome("none", 2))
        self.assertEqual(len(self.proposal_tasks()), 1)
        rewritten.assert_not_called()

    def test_the_task_is_found_by_its_marker_whatever_its_title(self) -> None:
        """Covers: B124"""
        self.kept(DANA)
        renamed = self.tasks.add("Look at what m2b found", notes="m2b:proposals")

        outcome = self.update()

        task = self.the_task()
        self.assertEqual((task.id, task.title, task.notes), (renamed, "Look at what m2b found", ONE_WAITS))
        self.assertEqual(outcome.change, "updated")

    def test_beside_a_completed_copy_the_open_task_is_the_one_kept_up_to_date(self) -> None:
        self.kept(DANA)
        first, second = sorted(self.tasks.add("m2b: proposals from your sessions", "m2b:proposals") for _ in "ab")
        self.tasks.complete(first)

        self.update()

        by_id = {task.id: task for task in self.proposal_tasks()}
        self.assertEqual((by_id[first].completed, by_id[first].notes), (True, "m2b:proposals"))
        self.assertEqual((by_id[second].completed, by_id[second].notes), (False, ONE_WAITS))

    def test_the_number_follows_what_still_waits(self) -> None:
        """Covers: B124"""
        self.kept(DANA, LADDER)
        self.update()
        proposal_answers.give(self.store, [LADDER_ID], proposal_answers.DROP)

        outcome = self.update()

        self.assertEqual(outcome, proposals_task.TaskOutcome("updated", 1))
        self.assertEqual(self.the_task().notes, ONE_WAITS)

    def test_once_nothing_waits_the_task_is_completed(self) -> None:
        """Covers: B124"""
        answered = {
            "settled by a run": lambda: self.settle(DANA_ID, proposals.DROPPED),
            "answered, not settled yet": lambda: proposal_answers.give(self.store, [DANA_ID], proposal_answers.KEEP),
        }
        for case, answer in answered.items():
            with self.subTest(case):
                self.kept(DANA)
                self.update()

                answer()
                outcome = self.update()

                self.assertEqual(outcome, proposals_task.TaskOutcome("completed", 0))
                self.assertTrue(self.the_task().completed)
                self.assertEqual(self.update().change, "none")
                self.start_over()

    def test_without_a_proposal_no_task_is_made_and_no_file_written(self) -> None:
        outcome = self.update()

        self.assertEqual(outcome, proposals_task.TaskOutcome("none", 0))
        self.assertEqual(self.tasks.items(include_completed=True), [])
        self.assertFalse((self.root / proposals.PROPOSALS_FILE).exists())


class DismissedTaskTest(ProposalsTaskFixture):
    def dismissals(self) -> dict[str, Any]:
        return {"completed": self.tasks.complete, "dropped": self.tasks.drop, "deleted": self.tasks.delete}

    def test_a_task_the_person_completed_dropped_or_deleted_answers_nothing_and_stays_away(self) -> None:
        """Covers: B125"""
        for case, dismiss in self.dismissals().items():
            with self.subTest(case):
                self.kept(DANA, LADDER)
                self.update()
                before = self.written()

                dismiss(self.the_task().id)
                outcome = self.update()

                self.assertEqual(outcome, proposals_task.TaskOutcome("none", 2))
                self.assertEqual(self.tasks.items(), [])
                self.assertEqual(self.written(), before)
                self.assertEqual(self.answer_files(), [])
                self.assertEqual(len(proposal_answers.waiting(self.store).proposals), 2)
                self.start_over()

    def test_a_proposal_added_since_brings_the_task_back_with_all_that_wait(self) -> None:
        """Covers: B125"""
        expected = {"completed": "reopened", "dropped": "reopened", "deleted": "created"}
        for case, dismiss in self.dismissals().items():
            with self.subTest(case):
                self.kept(DANA)
                self.update()
                dismiss(self.the_task().id)

                self.kept(LADDER, now=LATER)
                outcome = self.update()

                task = self.the_task()
                self.assertEqual(outcome, proposals_task.TaskOutcome(expected[case], 2))
                self.assertFalse(task.completed)
                self.assertFalse(task.dropped)
                self.assertEqual(task.notes, TWO_WAIT)
                self.start_over()

    def test_a_proposal_the_open_task_told_of_does_not_bring_it_back_once_completed(self) -> None:
        """Covers: B125"""
        self.kept(DANA)
        self.update()
        self.kept(LADDER, now=LATER)
        self.update()

        self.tasks.complete(self.the_task().id)
        outcome = self.update()

        self.assertEqual(outcome.change, "none")
        self.assertTrue(self.the_task().completed)

    def test_an_answer_does_not_bring_a_completed_task_back(self) -> None:
        self.kept(DANA, LADDER)
        self.update()
        self.tasks.complete(self.the_task().id)
        proposal_answers.give(self.store, [LADDER_ID], proposal_answers.DROP)

        outcome = self.update()

        self.assertEqual(outcome, proposals_task.TaskOutcome("none", 1))
        self.assertTrue(self.the_task().completed)

    def test_what_the_task_told_of_is_kept_when_a_reading_adds_a_proposal(self) -> None:
        self.kept(DANA)
        self.update()
        told = self.written()["announced_until"]

        self.kept(LADDER, now=LATER)

        self.assertEqual(told, NOW.isoformat())
        self.assertEqual(self.written()["announced_until"], told)


class OnRemindersTest(ProposalsTaskFixture):
    """Apple Reminders refuses new notes on a completed reminder and marks a dropped one in its notes."""

    def make_tasks(self) -> Tasks:
        command, _ = test_tasks_backends.fake_reminders(self.root.parent)
        return AppleRemindersTasks(test_tasks_backends.TEST_LIST, command=command, timeout_seconds=10)

    def test_a_reminder_the_person_completed_or_dropped_comes_back_open_with_the_new_number(self) -> None:
        for case, dismiss in {"completed": self.tasks.complete, "dropped": self.tasks.drop}.items():
            with self.subTest(case):
                self.kept(DANA)
                self.update()
                dismiss(self.the_task().id)

                self.kept(LADDER, now=LATER)
                outcome = self.update()

                task = self.the_task()
                self.assertEqual(outcome, proposals_task.TaskOutcome("reopened", 2))
                self.assertEqual((task.completed, task.dropped, task.notes), (False, False, TWO_WAIT))
                self.start_over()

    def test_once_nothing_waits_the_reminder_is_completed(self) -> None:
        self.kept(DANA)
        self.update()
        self.settle(DANA_ID, proposals.DROPPED)

        self.update()

        self.assertTrue(self.the_task().completed)


class CouldNotLookTest(ProposalsTaskFixture):
    def test_an_answers_folder_that_is_not_downloaded_does_not_pass_for_nothing_waiting(self) -> None:
        """Covers: B124"""
        self.kept(DANA)
        self.update()
        proposal_answers.give(self.store, [DANA_ID], proposal_answers.DROP)

        with self.not_downloaded("proposal-answers"), self.assertRaises(EvictedFileError):
            self.update()

        self.assertFalse(self.the_task().completed)

    def test_a_proposals_file_this_m2b_cannot_use_leaves_the_task_as_it_is(self) -> None:
        self.kept(DANA)
        self.update()
        self.write({**self.written(), "format": proposals.FORMAT + 1})

        with self.assertRaises(proposals.ProposalsError):
            self.update()

        self.assertEqual(self.the_task().notes, ONE_WAITS)
        self.assertFalse(self.the_task().completed)

    def test_a_task_that_could_not_be_written_is_made_by_the_next_run(self) -> None:
        """Covers: B125"""
        self.kept(DANA)
        unreachable = mock.patch.object(MarkdownTasks, "add", side_effect=TasksError("the task list does not answer"))
        with unreachable, self.assertRaises(TasksError):
            self.update()

        outcome = self.update()

        self.assertEqual(outcome, proposals_task.TaskOutcome("created", 1))
        self.assertEqual(self.the_task().notes, ONE_WAITS)
