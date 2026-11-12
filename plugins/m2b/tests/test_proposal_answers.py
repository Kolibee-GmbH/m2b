"""What the person answers to a proposal, from any client: one added file per answer."""

from __future__ import annotations

import datetime
import unittest
from pathlib import Path
from unittest import mock

from m2b import proposal_answers, proposals
from m2b.glean import Proposal
from m2b.proposal_answers import DROP, KEEP
from m2b.store.base import EvictedFileError
from test_proposals import DANA, LADDER, NOW, ProposalsFixture, Said

DANA_ID = proposals.proposal_id(DANA)
LADDER_ID = proposals.proposal_id(LADDER)
TEA = Proposal("personal", "Alex drinks green tea.", "I only drink green tea", "kitchen")
TEA_ID = proposals.proposal_id(TEA)
NOBODYS_ID = "0123456789ab"


class AnswerFixture(ProposalsFixture):
    def answer_files(self) -> list[str]:
        folder = self.root / proposal_answers.FOLDER
        return sorted(path.name for path in folder.iterdir()) if folder.is_dir() else []

    def not_downloaded(self, name: str) -> mock._patch[mock.MagicMock]:
        return mock.patch.object(self.store.guard, "is_evicted", side_effect=lambda path: Path(path).name == name)


class GiveTest(AnswerFixture):
    def test_keep_and_drop_each_add_one_empty_file_and_change_nothing_else(self) -> None:
        """Covers: B120"""
        self.kept(DANA, LADDER)
        before = (self.root / proposals.PROPOSALS_FILE).read_bytes()

        kept = proposal_answers.give(self.store, [DANA_ID], KEEP)
        dropped = proposal_answers.give(self.store, [LADDER_ID], DROP)

        self.assertEqual(self.answer_files(), sorted([f"{DANA_ID}.keep", f"{LADDER_ID}.drop"]))
        self.assertEqual((self.root / proposal_answers.FOLDER / f"{DANA_ID}.keep").read_bytes(), b"")
        self.assertEqual((self.root / proposals.PROPOSALS_FILE).read_bytes(), before)
        self.assertEqual((kept.given, kept.already), ((DANA_ID,), {}))
        self.assertEqual((dropped.given, dropped.already), ((LADDER_ID,), {}))

    def test_a_second_answer_writes_nothing_and_names_the_answer_that_stands(self) -> None:
        """Covers: B120"""
        self.kept(DANA)
        proposal_answers.give(self.store, [DANA_ID], KEEP)

        other = proposal_answers.give(self.store, [DANA_ID], DROP)
        same = proposal_answers.give(self.store, [DANA_ID, DANA_ID], KEEP)

        self.assertEqual(self.answer_files(), [f"{DANA_ID}.keep"])
        self.assertEqual((other.given, other.already), ((), {DANA_ID: KEEP}))
        self.assertEqual((same.given, same.already), ((), {DANA_ID: KEEP}))

    def test_an_answer_the_curation_run_has_settled_stands_too(self) -> None:
        """Covers: B120"""
        self.kept(DANA, LADDER)
        self.settle(DANA_ID, proposals.KEPT)
        self.settle(LADDER_ID, proposals.DROPPED)

        answered = proposal_answers.give(self.store, [DANA_ID, LADDER_ID], DROP)

        self.assertEqual(self.answer_files(), [])
        self.assertEqual((answered.given, answered.already), ((), {DANA_ID: KEEP, LADDER_ID: DROP}))

    def test_one_unknown_proposal_and_no_answer_is_written(self) -> None:
        """Covers: B120"""
        self.kept(DANA)

        with self.assertRaisesRegex(proposal_answers.UnknownProposalError, f"no proposal has the id {NOBODYS_ID}"):
            proposal_answers.give(self.store, [DANA_ID, NOBODYS_ID], KEEP)

        self.assertEqual(self.answer_files(), [])

    def test_a_key_of_the_proposals_file_that_is_no_id_never_becomes_a_file_name(self) -> None:
        self.kept(DANA)
        raw = self.written()
        raw["proposals"]["../../../outside"] = raw["proposals"][DANA_ID]
        self.write(raw)

        with self.assertRaises(proposal_answers.UnknownProposalError):
            proposal_answers.give(self.store, ["../../../outside"], KEEP)

        self.assertEqual(list(self.root.parent.rglob("outside*")), [])
        self.assertEqual(self.answer_files(), [])

    def test_the_same_answer_another_client_adds_at_the_same_moment_is_no_error(self) -> None:
        self.kept(DANA)
        target = self.root / proposal_answers.FOLDER / f"{DANA_ID}.keep"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"")

        with mock.patch.object(proposal_answers, "read", return_value={}):
            answered = proposal_answers.give(self.store, [DANA_ID], KEEP)

        self.assertEqual((answered.given, answered.already), ((), {DANA_ID: KEEP}))


class WaitingTest(AnswerFixture):
    def test_what_waits_is_each_open_proposal_without_an_answer_the_earliest_said_first(self) -> None:
        """Covers: B120"""
        earlier = NOW.date() - datetime.timedelta(days=3)
        added = proposals.add(
            proposals.load(self.store), [Said(DANA, NOW.date()), Said(LADDER, NOW.date()), Said(TEA, earlier)], NOW
        )
        proposals.save(self.store, added.proposals)
        proposal_answers.give(self.store, [LADDER_ID], DROP)

        waiting = proposal_answers.waiting(self.store)

        self.assertEqual([key for key, _ in waiting.proposals], [TEA_ID, DANA_ID])
        self.assertEqual(waiting.proposals[0][1].text, "Alex drinks green tea.")
        self.assertEqual(waiting.answered, 1)

    def test_a_proposal_the_run_has_settled_neither_waits_nor_counts_as_answered(self) -> None:
        self.kept(DANA, LADDER)
        self.settle(DANA_ID, proposals.KEPT)

        waiting = proposal_answers.waiting(self.store)

        self.assertEqual(([key for key, _ in waiting.proposals], waiting.answered), ([LADDER_ID], 0))

    def test_keep_stands_where_a_keep_and_a_drop_for_one_proposal_meet(self) -> None:
        """Covers: B120"""
        self.kept(DANA)
        folder = self.root / proposal_answers.FOLDER
        folder.mkdir(parents=True)
        for name in (f"{DANA_ID}.drop", f"{DANA_ID}.keep", "notes.txt", f"{DANA_ID}.keep 2", "short.keep"):
            (folder / name).write_bytes(b"")

        (folder / "earlier").mkdir()
        (folder / "earlier" / f"{LADDER_ID}.keep").write_bytes(b"")

        self.assertEqual(proposal_answers.read(self.store), {DANA_ID: KEEP})

    def test_keep_stands_also_against_a_drop_that_is_not_downloaded(self) -> None:
        """Covers: B120"""
        self.kept(DANA)
        folder = self.root / proposal_answers.FOLDER
        folder.mkdir(parents=True)
        for name in (f"{DANA_ID}.drop", f"{DANA_ID}.keep"):
            (folder / name).write_bytes(b"")

        with self.not_downloaded(f"{DANA_ID}.drop"):
            answers = proposal_answers.read(self.store)

        self.assertEqual(answers, {DANA_ID: KEEP})

    def test_an_answer_file_that_is_not_downloaded_is_an_answer_by_its_name(self) -> None:
        """Covers: B120"""
        self.kept(DANA)
        proposal_answers.give(self.store, [DANA_ID], DROP)

        with self.not_downloaded(f"{DANA_ID}.drop"):
            answers = proposal_answers.read(self.store)

        self.assertEqual(answers, {DANA_ID: DROP})

    def test_an_answers_folder_that_is_not_downloaded_is_not_taken_for_no_answer(self) -> None:
        """Covers: B120"""
        self.kept(DANA)
        proposal_answers.give(self.store, [DANA_ID], DROP)

        with self.not_downloaded("proposal-answers"), self.assertRaises(EvictedFileError) as refused:
            proposal_answers.waiting(self.store)

        self.assertIn("m2b store fetch state/core/proposal-answers", str(refused.exception))


class ExpireTest(AnswerFixture):
    def test_after_fourteen_days_without_an_answer_a_proposal_waits_no_longer(self) -> None:
        """Covers: B131"""
        self.kept(DANA, LADDER)
        proposal_answers.give(self.store, [LADDER_ID], KEEP)
        later = NOW + datetime.timedelta(days=14)

        aged = proposal_answers.expire(self.store, later)

        self.assertEqual((aged.expired, aged.forgotten), (1, 0))
        written = self.written()["proposals"]
        self.assertEqual((written[DANA_ID]["state"], written[DANA_ID]["since"]), ("expired", later.isoformat()))
        self.assertEqual(written[LADDER_ID]["state"], "open")
        waiting = proposal_answers.waiting(self.store)
        self.assertEqual((waiting.proposals, waiting.answered), ((), 1))

    def test_when_the_answers_cannot_be_looked_at_no_proposal_expires(self) -> None:
        """Covers: B131"""
        self.kept(DANA)
        proposal_answers.give(self.store, [DANA_ID], KEEP)
        before = (self.root / proposals.PROPOSALS_FILE).read_bytes()

        with self.not_downloaded("proposal-answers"), self.assertRaises(EvictedFileError):
            proposal_answers.expire(self.store, NOW + datetime.timedelta(days=30))

        self.assertEqual((self.root / proposals.PROPOSALS_FILE).read_bytes(), before)

    def test_a_store_where_nothing_is_due_is_not_written(self) -> None:
        self.assertEqual(proposal_answers.expire(self.store, NOW).expired, 0)
        self.assertFalse((self.root / proposals.PROPOSALS_FILE).exists())

        self.kept(DANA)
        before = (self.root / proposals.PROPOSALS_FILE).stat().st_mtime_ns
        self.assertEqual(proposal_answers.expire(self.store, NOW + datetime.timedelta(days=13)).expired, 0)
        self.assertEqual((self.root / proposals.PROPOSALS_FILE).stat().st_mtime_ns, before)

    def test_an_expired_proposal_still_takes_a_keep_by_its_id(self) -> None:
        """Covers: B131"""
        self.kept(DANA)
        proposal_answers.expire(self.store, NOW + datetime.timedelta(days=14))

        kept = proposal_answers.give(self.store, [DANA_ID], KEEP)

        self.assertEqual((kept.given, kept.already), ((DANA_ID,), {}))
        self.assertEqual(self.answer_files(), [f"{DANA_ID}.keep"])

    def test_a_keep_for_an_expired_proposal_waits_for_the_run_and_a_drop_of_one_does_not(self) -> None:
        self.kept(DANA, LADDER)
        proposal_answers.expire(self.store, NOW + datetime.timedelta(days=14))
        proposal_answers.give(self.store, [DANA_ID], KEEP)
        proposal_answers.give(self.store, [LADDER_ID], DROP)

        waiting = proposal_answers.waiting(self.store)

        self.assertEqual((waiting.proposals, waiting.answered), ((), 1))


if __name__ == "__main__":
    unittest.main()
