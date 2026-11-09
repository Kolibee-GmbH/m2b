"""The life of a memory candidate: proposed, ticked or dropped, harvested, remembered."""

from __future__ import annotations

import datetime
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import test_commands
import test_tasks_backends
from m2b import candidates, cli, harvest
from m2b.config import profile
from m2b.notes.frontmatter import Note
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard
from m2b.tasks import markers
from m2b.tasks.apple_reminders import AppleRemindersTasks
from m2b.tasks.markdown import MarkdownTasks

NOW = datetime.datetime(2026, 11, 7, 3, 0, tzinfo=datetime.timezone.utc)
PREFIX = "Remember? "


class CandidateFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        base = Path(self._temp.name)
        self.root = base / "sb-test-store"
        (self.root / "inbox").mkdir(parents=True)
        self.store = FolderStore(self.root, base / "machine-tmp", DatalessGuard(False))
        self.tasks = MarkdownTasks(self.store)

    def propose(self, text: str, now: datetime.datetime = NOW) -> candidates.Proposal:
        return candidates.propose(self.store, self.tasks, text, PREFIX, now)

    def harvest(self, now: datetime.datetime = NOW) -> harvest.HarvestReport:
        return harvest.harvest(self.store, self.tasks, PREFIX, now)

    def entries(self) -> dict[str, Any]:
        raw = json.loads((self.root / candidates.CANDIDATES_FILE).read_text(encoding="utf-8"))
        entries: dict[str, Any] = raw["candidates"]
        return entries

    def captures(self) -> list[Note]:
        return [Note.parse(path.read_text(encoding="utf-8")) for path in sorted((self.root / "inbox").glob("*.md"))]


class ProposeTest(CandidateFixture):
    def test_a_candidate_is_a_task_with_the_marker_and_the_prefix_and_is_recorded(self) -> None:
        proposal = self.propose("Dana prefers tea")

        assert proposal.task_id is not None
        (task,) = self.tasks.items()
        self.assertEqual(
            (task.id, task.title, task.marker), (proposal.task_id, "Remember? Dana prefers tea", "candidate")
        )
        self.assertEqual(self.entries()[task.id]["text"], "Dana prefers tea")
        self.assertEqual(self.entries()[task.id]["state"], "open")

    def test_the_same_text_as_an_open_candidate_is_refused(self) -> None:
        """Covers: B35"""
        self.propose("Dana prefers tea")

        refused = self.propose("  dana prefers   TEA ")

        self.assertEqual((refused.task_id, refused.refused), (None, "open"))
        self.assertEqual(len(self.tasks.items()), 1)

    def test_an_open_candidate_the_file_does_not_know_is_still_found_in_the_task_list(self) -> None:
        self.tasks.add("Remember? Dana prefers tea", notes=markers.marker_line(markers.CANDIDATE))

        self.assertEqual(self.propose("Dana prefers tea").refused, "open")

    def test_a_text_dropped_within_90_days_is_refused_and_after_that_allowed_again(self) -> None:
        """Covers: B35"""
        task_id = self.propose("Alex plays chess").task_id
        assert task_id is not None
        self.tasks.drop(task_id)
        self.harvest()

        self.assertEqual(self.propose("Alex plays chess", NOW + datetime.timedelta(days=89)).refused, "dropped")
        later = NOW + datetime.timedelta(days=91)
        self.harvest(later)
        self.assertIsNotNone(self.propose("Alex plays chess", later).task_id)

    def test_an_empty_text_is_refused_before_anything_is_written(self) -> None:
        with self.assertRaises(ValueError):
            self.propose("  \n ")
        self.assertEqual(self.tasks.items(), [])


class HarvestTest(CandidateFixture):
    def test_a_ticked_candidate_becomes_a_capture_and_its_task_and_entry_go(self) -> None:
        """Covers: X18 (recognized by marker; no list of harvested ids is kept)"""
        task_id = self.propose("Dana prefers tea").task_id
        assert task_id is not None
        self.tasks.complete(task_id)
        self.tasks.add("Remember? typed by hand", notes="no marker")
        self.tasks.complete(self.tasks.items()[-1].id)

        report = self.harvest()

        (note,) = self.captures()
        assert note.frontmatter is not None
        self.assertEqual(note.frontmatter.get("source"), "candidate")
        self.assertEqual(note.frontmatter.get("from_candidate"), task_id)
        self.assertEqual(note.body, "Dana prefers tea\n")
        self.assertEqual([task.title for task in self.tasks.items(include_completed=True)], ["Remember? typed by hand"])
        self.assertEqual(self.entries(), {})
        self.assertEqual(len(report.captured), 1)

    def test_a_title_the_owner_edited_wins_and_loses_only_the_prefix(self) -> None:
        task_id = self.propose("Dana prefers tea").task_id
        assert task_id is not None
        task_file = self.root / "tasks" / f"{task_id}.md"
        task_file.write_text(
            task_file.read_text(encoding="utf-8").replace("Dana prefers tea", "Dana prefers green tea")
        )
        self.tasks.complete(task_id)

        self.harvest()

        self.assertEqual(self.captures()[0].body, "Dana prefers green tea\n")

    def test_a_crash_between_capture_and_delete_neither_loses_nor_doubles_the_candidate(self) -> None:
        """Covers: B34"""
        task_id = self.propose("Dana prefers tea").task_id
        assert task_id is not None
        self.tasks.complete(task_id)
        with (
            mock.patch.object(self.tasks, "delete", side_effect=harvest.TasksError("crash")),
            self.assertRaises(harvest.TasksError),
        ):
            self.harvest()
        self.assertEqual(len(self.captures()), 1)

        self.harvest()

        self.assertEqual(len(self.captures()), 1)
        self.assertEqual(self.tasks.items(include_completed=True), [])
        self.assertEqual(self.entries(), {})

    def test_a_capture_already_moved_to_the_corpus_counts_as_harvested(self) -> None:
        task_id = self.propose("Dana prefers tea").task_id
        assert task_id is not None
        self.tasks.complete(task_id)
        with (
            mock.patch.object(self.tasks, "delete", side_effect=harvest.TasksError("crash")),
            self.assertRaises(harvest.TasksError),
        ):
            self.harvest()
        (capture,) = (self.root / "inbox").glob("*.md")
        (self.root / "corpus" / "2026" / "11").mkdir(parents=True)
        capture.rename(self.root / "corpus" / "2026" / "11" / capture.name)

        self.harvest()

        self.assertEqual(list((self.root / "inbox").glob("*.md")), [])
        self.assertEqual(self.tasks.items(include_completed=True), [])

    def test_a_crash_after_the_delete_does_not_turn_the_candidate_into_a_dropped_one(self) -> None:
        task_id = self.propose("Dana prefers tea").task_id
        assert task_id is not None
        self.tasks.complete(task_id)
        with mock.patch.object(candidates, "save", side_effect=OSError("crash")), self.assertRaises(OSError):
            self.harvest()
        self.assertEqual(self.entries()[task_id]["state"], "open")

        self.harvest()

        self.assertEqual(self.entries(), {})
        self.assertIsNotNone(self.propose("Dana prefers tea").task_id)

    def test_a_dropped_candidate_is_deleted_and_its_text_remembered(self) -> None:
        task_id = self.propose("Alex plays chess").task_id
        assert task_id is not None
        self.tasks.drop(task_id)

        report = self.harvest()

        self.assertEqual(self.tasks.items(include_completed=True), [])
        self.assertEqual(self.captures(), [])
        self.assertEqual(self.entries()[task_id]["state"], "dropped")
        self.assertEqual(self.entries()[task_id]["text"], "Alex plays chess")
        self.assertEqual(report.dropped, ["Alex plays chess"])

    def test_a_candidate_deleted_outside_the_product_counts_as_dropped_with_its_recorded_text(self) -> None:
        task_id = self.propose("Alex plays chess").task_id
        assert task_id is not None
        self.tasks.delete(task_id)

        self.harvest()

        self.assertEqual(self.entries()[task_id]["state"], "dropped")
        self.assertEqual(self.propose("Alex plays chess").refused, "dropped")

    def test_a_candidate_whose_task_file_cannot_be_read_is_not_taken_for_deleted(self) -> None:
        """Covers: B59"""
        task_id = self.propose("Alex plays chess").task_id
        assert task_id is not None
        task_file = self.root / "tasks" / f"{task_id}.md"
        task_file.write_text(task_file.read_text(encoding="utf-8").replace("status: open", "status: maybe"))

        self.harvest()

        self.assertEqual(self.entries()[task_id]["state"], "open")

    def test_dropped_entries_leave_the_file_after_90_days(self) -> None:
        task_id = self.propose("Alex plays chess").task_id
        assert task_id is not None
        self.tasks.drop(task_id)
        self.harvest()

        self.harvest(NOW + datetime.timedelta(days=90, seconds=1))

        self.assertEqual(self.entries(), {})

    def test_an_open_candidate_the_file_lost_is_recorded_and_left_open(self) -> None:
        task_id = self.tasks.add("Remember? Robin lives in Lyon", notes=markers.marker_line(markers.CANDIDATE))

        self.harvest()

        self.assertEqual(
            self.entries()[task_id], {"text": "Robin lives in Lyon", "state": "open", "since": NOW.isoformat()}
        )
        self.assertEqual(len(self.tasks.items()), 1)

    def test_with_an_evicted_candidate_capture_in_the_inbox_nothing_is_captured_or_deleted(self) -> None:
        task_id = self.propose("Dana prefers tea").task_id
        assert task_id is not None
        self.tasks.complete(task_id)
        evicted = mock.Mock(files=[], evicted=["inbox/20261107T020000Z-candidate-a1b2.md"])
        real_scan = self.store.scan
        with mock.patch.object(self.store, "scan", side_effect=lambda f: evicted if f == "inbox" else real_scan(f)):
            report = self.harvest()

        self.assertEqual(self.captures(), [])
        self.assertEqual(len(self.tasks.items(include_completed=True)), 1)
        self.assertEqual(len(report.problems), 1)
        self.assertIn("not downloaded", report.problems[0])


class HarvestBoundsTest(CandidateFixture):
    def ticked(self, text: str = "Dana prefers tea") -> str:
        task_id = self.propose(text).task_id
        assert task_id is not None
        self.tasks.complete(task_id)
        return task_id

    def corpus_capture(self, name: str, data: bytes) -> str:
        relative = f"corpus/{name[:4]}/{name[4:6]}/{name}"
        (self.root / relative).parent.mkdir(parents=True, exist_ok=True)
        (self.root / relative).write_bytes(data)
        return relative

    def test_an_open_candidate_whose_capture_exists_is_deleted_as_harvested(self) -> None:
        """A reopened reminder after a failed delete (Apple Reminders) must not come back as open."""
        task_id = self.propose("Dana prefers tea").task_id
        assert task_id is not None
        self.tasks.complete(task_id)
        with (
            mock.patch.object(self.tasks, "delete", side_effect=harvest.TasksError("crash")),
            self.assertRaises(harvest.TasksError),
        ):
            self.harvest()
        task_file = self.root / "tasks" / f"{task_id}.md"
        task_file.write_text(task_file.read_text(encoding="utf-8").replace("status: done", "status: open"))

        self.harvest()

        self.assertEqual(self.tasks.items(include_completed=True), [])
        self.assertEqual(self.entries(), {})
        self.assertEqual(len(self.captures()), 1)

    def test_an_evicted_corpus_capture_newer_than_the_oldest_open_proposal_blocks_capturing(self) -> None:
        task_id = self.ticked()
        evicted = self.corpus_capture("20261107T020000Z-candidate-a1b2.md", b"x")
        real_scan = self.store.scan

        def scan(folder: str) -> Any:
            found = real_scan(folder)
            if folder != "corpus":
                return found
            return mock.Mock(files=[f for f in found.files if f != evicted], evicted=[evicted])

        with mock.patch.object(self.store, "scan", side_effect=scan):
            report = self.harvest()

        self.assertEqual(self.captures(), [])
        self.assertEqual([task.id for task in self.tasks.items(include_completed=True)], [task_id])
        self.assertIn("not downloaded", report.problems[0])

    def test_candidate_captures_older_than_every_open_proposal_are_neither_read_nor_waited_for(self) -> None:
        self.ticked()
        old_evicted = self.corpus_capture("20250101T000000Z-candidate-0001.md", b"x")
        self.corpus_capture("20250102T000000Z-candidate-0002.md", b"\xff not utf-8")
        real_scan = self.store.scan

        def scan(folder: str) -> Any:
            found = real_scan(folder)
            if folder != "corpus":
                return found
            return mock.Mock(
                files=[f for f in found.files if f != old_evicted], evicted=[old_evicted, "corpus/2025/03"]
            )

        with mock.patch.object(self.store, "scan", side_effect=scan):
            report = self.harvest()

        self.assertEqual((len(self.captures()), report.problems), (1, []))

    def test_nothing_is_read_when_no_candidate_is_in_question(self) -> None:
        self.corpus_capture("20261107T020000Z-candidate-0001.md", b"\xff")
        with mock.patch.object(self.store, "read_text", side_effect=AssertionError("read")):
            self.assertEqual(self.harvest().problems, [])


class HarvestCertaintyTest(CandidateFixture):
    def test_an_evicted_inbox_folder_means_nothing_is_captured_or_dropped(self) -> None:
        ticked = self.propose("Dana prefers tea").task_id
        gone = self.propose("Alex plays chess").task_id
        assert ticked is not None and gone is not None
        self.tasks.complete(ticked)
        self.tasks.delete(gone)
        real_scan = self.store.scan
        with mock.patch.object(
            self.store,
            "scan",
            side_effect=lambda f: mock.Mock(files=[], evicted=["inbox"]) if f == "inbox" else real_scan(f),
        ):
            report = self.harvest()

        self.assertEqual((self.captures(), report.dropped), ([], []))
        self.assertEqual(self.entries()[gone]["state"], "open")
        self.assertIn("not downloaded (inbox)", report.problems[0])

    def test_an_unreadable_candidate_capture_is_named_as_unreadable(self) -> None:
        self.tasks.complete(self.propose("Dana prefers tea").task_id or "")
        (self.root / "inbox" / "20261107T040000Z-candidate-dddd.md").write_bytes(b"\xff broken")

        report = self.harvest()

        self.assertEqual(
            [path.name for path in (self.root / "inbox").iterdir()], ["20261107T040000Z-candidate-dddd.md"]
        )
        self.assertEqual(len(report.problems), 1)
        self.assertIn("cannot be read", report.problems[0])

    def test_a_dropped_entry_whose_task_shows_up_open_is_open_again(self) -> None:
        task_id = self.propose("Robin lives in Lyon").task_id
        assert task_id is not None
        task_file = self.root / "tasks" / f"{task_id}.md"
        kept = task_file.read_bytes()
        task_file.unlink()
        self.harvest()
        self.assertEqual(self.entries()[task_id]["state"], "dropped")

        task_file.write_bytes(kept)
        self.harvest()

        self.assertEqual(self.entries()[task_id]["state"], "open")


class UnknownAgeTest(CandidateFixture):
    def test_an_unknown_open_candidate_keeps_its_unknown_age_while_captures_cannot_be_checked(self) -> None:
        self.tasks.add("Remember? Robin lives in Lyon", notes=markers.marker_line(markers.CANDIDATE))
        real_scan = self.store.scan
        with mock.patch.object(
            self.store,
            "scan",
            side_effect=lambda f: mock.Mock(files=[], evicted=["inbox"]) if f == "inbox" else real_scan(f),
        ):
            self.harvest()

        self.assertEqual(self.entries(), {})


class HarvestOnRemindersTest(CandidateFixture):
    """The paths that depend on the backend: a dropped reminder is completed, deleting reopens it first."""

    def setUp(self) -> None:
        super().setUp()
        command, _ = test_tasks_backends.fake_reminders(Path(self._temp.name))
        self.tasks = AppleRemindersTasks(test_tasks_backends.TEST_LIST, command=command, timeout_seconds=10)

    def test_ticked_dropped_and_crashed_candidates(self) -> None:
        ticked = self.propose("Dana prefers tea").task_id
        dropped = self.propose("Alex plays chess").task_id
        crashed = self.propose("Robin lives in Lyon").task_id
        assert ticked and dropped and crashed
        self.tasks.complete(ticked)
        self.tasks.drop(dropped)
        self.tasks.complete(crashed)
        real_delete, real_uncomplete = self.tasks.delete, self.tasks.uncomplete

        def delete(task_id: str) -> None:
            if task_id == crashed:
                real_uncomplete(task_id)
                raise harvest.TasksError("crash after the reopen")
            real_delete(task_id)

        with mock.patch.object(self.tasks, "delete", side_effect=delete), self.assertRaises(harvest.TasksError):
            self.harvest()
        self.harvest()

        self.assertEqual(sorted(note.body for note in self.captures()), ["Dana prefers tea\n", "Robin lives in Lyon\n"])
        self.assertEqual(self.tasks.items(include_completed=True), [])
        self.assertEqual(self.entries(), {dropped: self.entries()[dropped]})
        self.assertEqual(self.entries()[dropped]["state"], "dropped")


class CandidateCommandTest(test_commands.CommandTest):
    def setUp(self) -> None:
        super().setUp()
        # The curation run calls these commands; outside it they are refused.
        self.environ["M2B_CURATION_RUN"] = "1"
        self.set_up(calendar="none")
        profile.save_profile(self.store, {"version": 1, "owner": "Alex", "language": "de"})

    def test_tasks_add_candidate_uses_the_profiles_prefix_and_reports_a_refusal(self) -> None:
        answer = self.run_json("tasks", "add", "--candidate", "Dana mag Tee")
        refused = self.run_json("tasks", "add", "--candidate", "Dana mag Tee")
        (task,) = self.run_json("tasks", "list")

        self.assertEqual(
            (task["id"], task["title"], task["marker"]), (answer["id"], "Merken? Dana mag Tee", "candidate")
        )
        self.assertEqual(refused, {"id": None, "refused": "open"})
        code, out, _ = self.run_command("tasks", "add", "--candidate", "Dana mag Tee")
        self.assertEqual((code, out), (cli.EXIT_OK, "refused: an open candidate has the same text\n"))

    def test_a_candidate_takes_no_notes_or_due_date(self) -> None:
        code, _, _ = self.run_command("tasks", "add", "--candidate", "Dana mag Tee", "--due", "2026-12-01")

        self.assertEqual(code, cli.EXIT_USAGE)

    def test_a_store_of_a_newer_format_takes_no_candidate(self) -> None:
        settings = test_commands.json.loads((self.store_root / "store.json").read_text(encoding="utf-8"))
        (self.store_root / "store.json").write_text(
            test_commands.json.dumps({**settings, "format": 99}), encoding="utf-8"
        )

        code, _, _ = self.run_command("tasks", "add", "--candidate", "Dana mag Tee")

        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertFalse((self.store_root / "state" / "core" / "candidates.json").exists())

    def test_harvest_prints_what_it_did(self) -> None:
        task_id = self.run_json("tasks", "add", "--candidate", "Dana mag Tee")["id"]
        self.run_command("tasks", "complete", task_id)

        answer = self.run_json("harvest")

        (captured,) = answer["captured"]
        self.assertTrue((self.store_root / captured).is_file())
        self.assertEqual((answer["dropped"], answer["problems"]), ([], []))


if __name__ == "__main__":
    unittest.main()
