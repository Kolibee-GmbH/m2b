"""The contract every tasks backend passes; each backend's test module runs it with its own list."""

from __future__ import annotations

import datetime
import tempfile
import unittest
from pathlib import Path

from m2b.tasks import markers
from m2b.tasks.base import Due, Tasks, UnknownTaskError


def local_date(due: Due | None) -> datetime.date | None:
    if isinstance(due, datetime.datetime):
        return due.astimezone().date()
    return due


class Contracts:
    """Holds the contract so that test discovery does not run it without a backend."""

    class TasksContract(unittest.TestCase):
        """Subclass it and implement ``make_tasks`` for a fresh, empty list in ``folder``."""

        def make_tasks(self, folder: Path) -> Tasks:
            raise NotImplementedError

        def setUp(self) -> None:
            self._temp = tempfile.TemporaryDirectory()
            self.folder = Path(self._temp.name)
            self.tasks = self.make_tasks(self.folder)

        def tearDown(self) -> None:
            self._temp.cleanup()

        def _since(self) -> datetime.datetime:
            return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)

        def test_a_healthy_list_is_reachable(self) -> None:
            self.tasks.check_reachable()

        def test_an_added_task_is_listed_with_its_title_notes_and_due_date(self) -> None:
            task_id = self.tasks.add(
                "Call Dana about the shed", notes="ask about the roof", due=datetime.date(2026, 12, 1)
            )

            (task,) = self.tasks.items()

            self.assertEqual(
                (task.id, task.title, task.notes), (task_id, "Call Dana about the shed", "ask about the roof")
            )
            self.assertEqual(local_date(task.due), datetime.date(2026, 12, 1))
            self.assertFalse(task.completed)

        def test_the_id_survives_completing_and_reopening(self) -> None:
            task_id = self.tasks.add("Water the plants")

            self.tasks.complete(task_id)
            self.tasks.uncomplete(task_id)
            self.assertEqual([t.id for t in self.tasks.items()], [task_id])
            self.tasks.complete(task_id)

            self.assertEqual(self.tasks.items(), [])
            (done,) = self.tasks.completed_items(self._since())
            self.assertEqual(done.id, task_id)
            assert done.completed_at is not None
            self.assertGreaterEqual(done.completed_at, self._since())

        def test_completed_items_leave_out_older_completions(self) -> None:
            self.tasks.complete(self.tasks.add("Done long ago"))

            future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)

            self.assertEqual(self.tasks.completed_items(future), [])

        def test_delete_removes_the_task(self) -> None:
            task_id = self.tasks.add("Temporary")

            self.tasks.delete(task_id)

            self.assertEqual(self.tasks.items(include_completed=True), [])

        def test_a_completed_task_can_be_deleted(self) -> None:
            task_id = self.tasks.add("Harvested candidate")
            self.tasks.complete(task_id)

            self.tasks.delete(task_id)

            self.assertEqual(self.tasks.items(include_completed=True), [])

        def test_a_completed_review_task_is_found_by_its_marker(self) -> None:
            review_id = self.tasks.add("m2b: review", notes=markers.with_marker(markers.REVIEW, "two findings"))
            self.tasks.add("Buy milk")
            self.tasks.complete(review_id)

            found = self.tasks.items(marker=markers.REVIEW, include_completed=True)

            self.assertEqual([task.id for task in found], [review_id])
            self.assertEqual(self.tasks.items(marker=markers.REVIEW), [])

        def test_a_curator_task_is_found_by_marker_whatever_its_title(self) -> None:
            """Covers: X2"""
            candidate_id = self.tasks.add("Merken? Dana prefers tea", notes=markers.with_marker(markers.CANDIDATE, ""))
            self.tasks.add("m2b: candidate", notes="a title that only looks like one")

            (found,) = self.tasks.items(marker=markers.CANDIDATE)

            self.assertEqual(found.id, candidate_id)
            self.assertTrue(found.notes.startswith("m2b:candidate"))

        def test_set_notes_replaces_the_notes(self) -> None:
            task_id = self.tasks.add("Plan the garden", notes="first draft")

            self.tasks.set_notes(task_id, "m2b:capture 20260329T003000Z-claude-3f9a.md t1\nsee the capture")

            (task,) = self.tasks.items(marker=markers.CAPTURE)
            self.assertEqual(task.id, task_id)
            self.assertEqual(task.notes, "m2b:capture 20260329T003000Z-claude-3f9a.md t1\nsee the capture")

        def test_export_holds_open_and_completed_tasks(self) -> None:
            self.tasks.add("Open one")
            self.tasks.complete(self.tasks.add("Closed one"))

            self.assertEqual(len(self.tasks.export()), 2)

        def test_a_dropped_task_is_done_but_no_completion(self) -> None:
            task_id = self.tasks.add("Merken? Dana prefers tea", notes=markers.with_marker(markers.CANDIDATE, ""))
            self.tasks.add("Buy milk")

            self.tasks.drop(task_id)

            self.assertEqual([task.title for task in self.tasks.items()], ["Buy milk"])
            (dropped,) = self.tasks.items(marker=markers.CANDIDATE, include_completed=True)
            self.assertEqual(dropped.id, task_id)
            self.assertTrue(dropped.completed and dropped.dropped)
            self.assertEqual(self.tasks.completed_items(self._since()), [])

        def test_a_completed_task_can_be_dropped_afterwards(self) -> None:
            task_id = self.tasks.add("Merken? Alex likes chess", notes=markers.with_marker(markers.CANDIDATE, ""))
            self.tasks.complete(task_id)

            self.tasks.drop(task_id)

            (dropped,) = self.tasks.items(include_completed=True)
            self.assertTrue(dropped.dropped)
            self.assertEqual(self.tasks.completed_items(self._since()), [])

        def test_a_dropped_task_reopened_is_an_open_task_again(self) -> None:
            task_id = self.tasks.add("Merken? Alex likes chess", notes=markers.with_marker(markers.CANDIDATE, "kept"))
            self.tasks.drop(task_id)

            self.tasks.uncomplete(task_id)
            (reopened,) = self.tasks.items()
            self.tasks.complete(task_id)

            self.assertFalse(reopened.dropped or reopened.completed)
            self.assertEqual(reopened.notes, "m2b:candidate\nkept")
            self.assertEqual([task.id for task in self.tasks.completed_items(self._since())], [task_id])

        def test_a_list_whose_tasks_have_no_copies_names_none(self) -> None:
            self.tasks.add("Call Dana")

            self.assertEqual(self.tasks.conflict_copies(), [])

        def test_an_unknown_id_is_an_error(self) -> None:
            for call in (self.tasks.complete, self.tasks.uncomplete, self.tasks.delete, self.tasks.drop):
                with self.subTest(call=call.__name__), self.assertRaises(UnknownTaskError):
                    call("0123456789ab")
