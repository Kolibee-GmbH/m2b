"""A curation run takes in what sessions handed in: what becomes a proposal that waits, what is removed, what stays."""

from __future__ import annotations

import dataclasses
import datetime
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from m2b import glean, handed_in, proposals
from m2b.capture import capture
from m2b.curate import handed_in_intake
from m2b.handed_in import HandedIn
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard
from test_session_places import OTHER_SESSION, SESSION

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 3, 5, 3, 0, tzinfo=UTC)
DAY = datetime.date(2026, 3, 4)
CALLED = datetime.datetime(2026, 3, 4, 18, 0, tzinfo=UTC)
DANA = HandedIn(
    "person",
    "Dana Whitfield runs purchasing at Acme.",
    "Dana Whitfield runs purchasing at Acme",
    SESSION,
    DAY,
    "tool",
    CALLED,
    "Read",
)
DRAFT = HandedIn(
    "commitment",
    "Send Morgan the draft.",
    "I send Morgan the draft by Tuesday",
    SESSION,
    DAY,
    "typed",
    CALLED + datetime.timedelta(minutes=1),
    None,
    datetime.date(2026, 3, 10),
)


def proposal_id(proposal: HandedIn) -> str:
    return proposals.proposal_id(glean.Proposal(proposal.kind, proposal.text, proposal.quote, proposal.session))


def name_of(proposal: HandedIn) -> str:
    return f"{proposal.session}.{proposal_id(proposal)}.json"


class IntakeFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="sb-test-intake-")
        self.addCleanup(self._temp.cleanup)
        base = Path(self._temp.name)
        self.root = base / "sb-test-store"
        self.root.mkdir()
        self.store = FolderStore(self.root, base / "machine-tmp", DatalessGuard(False))
        self.folder = self.root / handed_in.FOLDER

    def handed_in(self, proposal: HandedIn, name: str | None = None, **changes: Any) -> Path:
        """The file a session's call wrote, or one with ``changes`` to what such a file holds."""
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / (name or name_of(proposal))
        path.write_text(json.dumps({**handed_in.as_json(proposal), **changes}), encoding="utf-8")
        return path

    def take_in(self, now: datetime.datetime = NOW) -> handed_in_intake.Intake:
        return handed_in_intake.take_in(self.store, now)

    def waiting(self) -> dict[str, proposals.Entry]:
        return dict(proposals.load(self.store).entries)

    def files(self) -> list[str]:
        return sorted(path.name for path in self.folder.iterdir()) if self.folder.is_dir() else []


class TakingInTest(IntakeFixture):
    def test_a_handed_in_file_becomes_a_proposal_that_waits_and_the_file_is_gone(self) -> None:
        """Covers: B180"""
        self.handed_in(DANA)

        told = self.take_in()

        (key,) = self.waiting()
        entry = self.waiting()[key]
        self.assertEqual(key, proposal_id(DANA))
        self.assertEqual((entry.kind, entry.text, entry.quote), (DANA.kind, DANA.text, DANA.quote))
        self.assertEqual((entry.day, entry.state, entry.since), (DAY, proposals.OPEN, NOW))
        self.assertEqual((entry.source, entry.tool, entry.by), ("tool", "Read", "session"))
        self.assertEqual(self.files(), [])
        self.assertEqual(
            told.notes,
            (
                "took in what sessions handed in: 1 proposal added, 0 like one that waits, is answered or expired, "
                "0 captured already, 0 not in the form, 0 beyond 10 of one session",
            ),
        )
        self.assertEqual(told.problems, ())

    def test_a_commitment_keeps_its_day_and_typed_words_stay_typed_but_handed_in(self) -> None:
        """Covers: B180"""
        self.handed_in(DRAFT)

        self.take_in()

        (entry,) = self.waiting().values()
        self.assertEqual((entry.due, entry.source, entry.tool, entry.by), (DRAFT.due, "typed", None, "session"))

    def test_who_proposed_is_set_by_the_run_and_never_read_from_the_file(self) -> None:
        """Covers: B180"""
        self.handed_in(DANA, by="reading", topic="Acme", state="kept")

        self.take_in()

        (entry,) = self.waiting().values()
        self.assertEqual((entry.by, entry.topic, entry.state), ("session", None, proposals.OPEN))

    def test_a_store_without_a_handed_in_file_is_not_written_and_nothing_is_told(self) -> None:
        """Covers: B180"""
        told = self.take_in()

        self.assertEqual(told, handed_in_intake.Intake())
        self.assertFalse((self.root / proposals.PROPOSALS_FILE).exists())

    def test_the_proposal_is_counted_for_its_kind_with_those_a_reading_found(self) -> None:
        """Covers: B180"""
        self.handed_in(DANA)

        self.take_in()

        self.assertEqual(proposals.load(self.store).tally("person").proposed, 1)


class NotAddedTest(IntakeFixture):
    def test_one_like_a_proposal_that_waits_was_answered_or_expired_is_not_added_and_its_file_goes(self) -> None:
        """Covers: B180"""
        for state in proposals.STATES:
            with self.subTest(state=state):
                (self.root / proposals.PROPOSALS_FILE).unlink(missing_ok=True)
                read = glean.Proposal("person", "dana whitfield runs  purchasing at Acme.", "Dana runs purchasing", "x")
                current = proposals.add(proposals.Proposals({}), [proposals.Said(read, DAY)], NOW).proposals
                (key,) = current.entries
                if state != proposals.OPEN:
                    current = proposals.settled(current, key, state, NOW)
                proposals.save(self.store, current)
                self.handed_in(DANA)

                told = self.take_in()

                self.assertEqual(list(self.waiting()), [key])
                self.assertEqual(self.files(), [])
                self.assertIn("0 proposals added, 1 like one that waits, is answered or expired", told.notes[0])

    def test_the_same_fact_handed_in_by_two_sessions_waits_once(self) -> None:
        """Covers: B180"""
        self.handed_in(DANA)
        self.handed_in(dataclasses.replace(DANA, session=OTHER_SESSION, at=CALLED + datetime.timedelta(hours=1)))

        told = self.take_in()

        (entry,) = self.waiting().values()
        self.assertEqual(entry.text, DANA.text)
        self.assertEqual(self.files(), [])
        self.assertIn("1 proposal added, 1 like one that waits", told.notes[0])

    def test_what_the_person_captured_since_its_day_is_not_added(self) -> None:
        """Covers: B180"""
        captured_at = datetime.datetime(2026, 3, 4, 19, 0, tzinfo=UTC)
        for note in (
            "Dana Whitfield runs purchasing at Acme.",
            "Acme: Dana Whitfield runs purchasing at Acme, since May",
        ):
            with self.subTest(note=note):
                for path in (self.root / "inbox").glob("*"):
                    path.unlink()
                capture(self.store, note, "claude", now=captured_at)
                self.handed_in(DANA)

                told = self.take_in()

                self.assertEqual(self.waiting(), {})
                self.assertEqual(self.files(), [])
                self.assertIn(
                    "0 proposals added, 0 like one that waits, is answered or expired, 1 captured already",
                    told.notes[0],
                )

    def test_a_capture_from_before_its_day_or_about_something_else_does_not_stand_in_its_way(self) -> None:
        """Covers: B180"""
        capture(self.store, DANA.text, "claude", now=datetime.datetime(2026, 3, 2, 12, 0, tzinfo=UTC))
        capture(self.store, "Riley signs the orders at Contoso.", "claude", now=NOW - datetime.timedelta(hours=2))
        self.handed_in(DANA)

        self.take_in()

        self.assertEqual(len(self.waiting()), 1)

    def test_a_capture_of_the_evening_before_counts_because_the_session_may_be_in_another_zone(self) -> None:
        """Covers: B180"""
        capture(self.store, DANA.text, "claude", now=datetime.datetime(2026, 3, 3, 20, 0, tzinfo=UTC))
        self.handed_in(DANA)

        told = self.take_in()

        self.assertEqual(self.waiting(), {})
        self.assertIn("1 captured already", told.notes[0])

    def test_a_day_long_ago_does_not_make_the_run_read_more_than_a_month_of_captures(self) -> None:
        """Covers: B180"""
        self.handed_in(dataclasses.replace(DANA, day=datetime.date(2019, 1, 1)))

        with mock.patch.object(
            handed_in_intake.period_captures, "captures_since", wraps=handed_in_intake.period_captures.captures_since
        ) as read:
            self.take_in()

        (start,) = [call.args[1] for call in read.call_args_list]
        self.assertEqual(start, NOW - handed_in_intake.CAPTURES_BACK)


class NotInFormTest(IntakeFixture):
    def assert_removed(self, told: handed_in_intake.Intake) -> None:
        waiting = self.waiting()
        # Whatever a failing case left behind does not fail the cases after it.
        (self.root / proposals.PROPOSALS_FILE).unlink(missing_ok=True)
        self.assertEqual(waiting, {})
        self.assertEqual(self.files(), [])
        self.assertIn("0 proposals added", told.notes[0])
        self.assertIn("1 not in the form", told.notes[0])

    def test_a_file_whose_content_is_out_of_the_form_is_removed_and_counted(self) -> None:
        """Covers: B180"""
        changes: list[dict[str, Any]] = [
            {"kind": "todo"},
            {"text": "x" * 301},
            {"text": "two\nlines"},
            {"text": "Dana Whitfield  runs purchasing at Acme."},
            {"quote": " Dana Whitfield runs purchasing at Acme"},
            {"quote": "two words"},
            {"quote": "Dana Whitfield runs purchasing at Acme\u202e"},
            {"text": "Dana\u200b Whitfield runs purchasing at Acme."},
            {"quote": "the password is hunter2hunter2 for Acme"},
            {"source": "letter"},
            {"source": None},
            {"tool": "Read me"},
            {"tool": 7},
            {"source": "agent", "tool": "Read"},
            {"tool": "mcp__m2b__search"},
            {"day": "yesterday"},
            {"day": None},
            {"day": "20260304"},
            {"day": "2999-01-01"},
            {"day": "2026-03-06"},
            {"at": "2026-03-04T18:00:00"},
            {"at": "2026-03-04 18:00:00+00:00"},
            {"at": "2026-03-07T18:00:00+00:00"},
            {"at": 7},
            {"format": "1"},
            {"format": 0},
            {"format": True},
            {"format": None},
            {"due": "next week"},
            {"session": OTHER_SESSION},
        ]
        for change in changes:
            with self.subTest(change=change):
                self.handed_in(DANA, **change)

                self.assert_removed(self.take_in())

    def test_a_quote_that_changes_the_id_is_out_of_the_form_under_the_old_name(self) -> None:
        """Covers: B180"""
        self.handed_in(DANA, quote="Dana Whitfield runs all purchasing at Acme")

        self.assert_removed(self.take_in())

    def test_a_file_whose_name_is_not_the_one_a_call_gives_is_removed_and_counted(self) -> None:
        """Covers: B180"""
        names = [
            f"{SESSION}.{proposal_id(DANA)} (conflicted copy).json",
            f"{SESSION}.{proposal_id(DANA)}.json.tmp",
            f"{SESSION}.aaaaaaaaaaaa.json",
            f"not-a-session.{proposal_id(DANA)}.json",
            "notes.txt",
        ]
        for name in names:
            with self.subTest(name=name):
                self.handed_in(DANA, name)

                self.assert_removed(self.take_in())

    def test_a_file_that_is_no_json_object_or_no_text_is_removed_and_counted(self) -> None:
        """Covers: B180"""
        self.folder.mkdir(parents=True)
        for content in (b"", b"[]", b'"proposal"', b"{", b"\xff\xfe\x00", b"[" * 100_000):
            with self.subTest(content=content[:8]):
                (self.folder / name_of(DANA)).write_bytes(content)

                self.assert_removed(self.take_in())

    def test_a_file_far_larger_than_a_proposal_is_removed_unread(self) -> None:
        """Covers: B180"""
        path = self.handed_in(DANA)
        path.write_bytes(path.read_bytes() + b" " * handed_in_intake.LARGEST_FILE)

        with mock.patch.object(self.store, "read_text", side_effect=AssertionError("opened")):
            self.assert_removed(self.take_in())

    def test_a_file_of_a_newer_format_under_a_name_no_call_gives_is_removed(self) -> None:
        """Covers: B180"""
        self.handed_in(DANA, f"{SESSION}.zz0.json", format=handed_in.FORMAT + 1)

        self.assert_removed(self.take_in())

    def test_a_file_in_a_folder_below_is_removed_and_counted(self) -> None:
        """Covers: B180"""
        below = self.folder / "old"
        below.mkdir(parents=True)
        (below / name_of(DANA)).write_text(json.dumps(handed_in.as_json(DANA)), encoding="utf-8")

        told = self.take_in()

        self.assertEqual(self.waiting(), {})
        self.assertFalse((below / name_of(DANA)).exists())
        self.assertIn("1 not in the form", told.notes[0])

    def test_a_file_of_a_newer_format_stays_and_the_run_says_to_update(self) -> None:
        """Covers: B180"""
        self.handed_in(DANA, format=handed_in.FORMAT + 1, shape="unknown here", kind="something new")

        told = self.take_in()

        self.assertEqual(self.waiting(), {})
        self.assertEqual(self.files(), [name_of(DANA)])
        self.assertEqual(told.notes, ())
        self.assertEqual(
            told.problems, ("1 handed-in proposal written by a newer m2b waits: update m2b on this machine",)
        )


class ListedTest(IntakeFixture):
    """A run that commits takes in only what its listing of the store holds."""

    def test_a_file_that_came_in_after_the_run_listed_the_store_waits_for_the_next_run(self) -> None:
        """Covers: B182"""
        listed = self.handed_in(DANA)
        late = self.handed_in(DRAFT)

        told = handed_in_intake.take_in(self.store, NOW, {f"{handed_in.FOLDER}/{listed.name}", "memory/MEMORY.md"})

        self.assertEqual([entry.text for entry in self.waiting().values()], [DANA.text])
        self.assertEqual(self.files(), [late.name])
        self.assertIn("1 proposal added", told.notes[0])
        self.assertEqual(
            told.notes[-1], "1 handed-in proposal no commit holds yet, left for the next run, which commits first"
        )

        handed_in_intake.take_in(self.store, NOW)

        self.assertEqual(len(self.waiting()), 2)
        self.assertEqual(self.files(), [])

    def test_a_symlink_in_the_folder_is_not_read_and_is_named(self) -> None:
        """Covers: B180"""
        self.folder.mkdir(parents=True)
        outside = self.root.parent / "outside.json"
        outside.write_text(json.dumps(handed_in.as_json(DANA)), encoding="utf-8")
        (self.folder / name_of(DANA)).symlink_to(outside)

        told = self.take_in()

        self.assertEqual(self.waiting(), {})
        self.assertTrue(outside.exists())
        self.assertEqual(told.notes, ("1 symlink in the folder of handed-in proposals: m2b follows none",))


class LimitTest(IntakeFixture):
    def test_of_one_session_the_ten_earliest_are_taken_and_the_rest_removed(self) -> None:
        """Covers: B180"""
        for number in range(12):
            words = f"Colleague number {number} runs the desk"
            self.handed_in(
                dataclasses.replace(
                    DANA, text=f"{words}.", quote=words, at=CALLED + datetime.timedelta(minutes=12 - number)
                )
            )
        self.handed_in(dataclasses.replace(DRAFT, session=OTHER_SESSION))

        told = self.take_in()

        texts = sorted(entry.text for entry in self.waiting().values())
        self.assertEqual(len(texts), 11)
        self.assertNotIn("Colleague number 0 runs the desk.", texts)
        self.assertNotIn("Colleague number 1 runs the desk.", texts)
        self.assertIn("Send Morgan the draft.", texts)
        self.assertEqual(self.files(), [])
        self.assertIn("11 proposals added", told.notes[0])
        self.assertIn("2 beyond 10 of one session", told.notes[0])


class WaitingTest(IntakeFixture):
    def test_a_file_that_is_not_downloaded_stays_and_is_counted_while_the_others_are_taken(self) -> None:
        """Covers: B180"""
        self.handed_in(DANA)
        waiting = self.handed_in(DRAFT)
        real = self.store.scan

        def scan(folder: str) -> Any:
            found = real(folder)
            relative = f"{handed_in.FOLDER}/{waiting.name}"
            if relative in found.files:
                found.files.remove(relative)
                found.evicted.append(relative)
            return found

        with mock.patch.object(self.store, "scan", side_effect=scan):
            told = self.take_in()

        self.assertEqual([entry.text for entry in self.waiting().values()], [DANA.text])
        self.assertEqual(self.files(), [waiting.name])
        self.assertEqual(told.notes[-1], "1 handed-in proposal not downloaded, left for the next run")

    def test_a_folder_that_is_not_downloaded_waits_whole(self) -> None:
        """Covers: B180"""
        self.handed_in(DANA)
        evicted = mock.Mock(files=[], evicted=[handed_in.FOLDER])

        with mock.patch.object(self.store, "scan", return_value=evicted):
            told = self.take_in()

        self.assertEqual(self.files(), [name_of(DANA)])
        self.assertEqual(told.notes, ("what sessions handed in is not downloaded and waits for the next run",))

    def test_a_file_that_cannot_be_read_stays_and_is_counted(self) -> None:
        """Covers: B180"""
        self.handed_in(DANA)

        with mock.patch.object(self.store, "read_text", side_effect=PermissionError("denied")):
            told = self.take_in()

        self.assertEqual(self.files(), [name_of(DANA)])
        self.assertEqual(told.notes, ("1 handed-in proposal could not be read, left for the next run",))

    def test_a_proposals_file_this_m2b_cannot_use_leaves_every_file_where_it_is(self) -> None:
        """Covers: B180"""
        self.handed_in(DANA)
        target = self.root / proposals.PROPOSALS_FILE
        target.write_text(json.dumps({"format": proposals.FORMAT + 1, "proposals": {}}), encoding="utf-8")

        told = self.take_in()

        self.assertEqual(self.files(), [name_of(DANA)])
        self.assertEqual(told.notes, ())
        self.assertIn("what sessions handed in waits for the next run: ", told.problems[0])
        self.assertIn("update m2b on this machine", told.problems[0])

    def test_a_run_that_stopped_before_it_removed_the_file_takes_it_for_one_that_waits_already(self) -> None:
        """Covers: B180"""
        self.handed_in(DANA)
        with mock.patch.object(self.store, "delete", side_effect=OSError("stopped")):
            self.take_in()
        self.assertEqual(self.files(), [name_of(DANA)])

        told = self.take_in(NOW + datetime.timedelta(days=1))

        (entry,) = self.waiting().values()
        self.assertEqual(entry.since, NOW)
        self.assertEqual(self.files(), [])
        self.assertIn("0 proposals added, 1 like one that waits", told.notes[0])


if __name__ == "__main__":
    unittest.main()
