"""The proposals from the person's sessions as the store keeps them."""

from __future__ import annotations

import datetime
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from m2b import proposals
from m2b.config.errors import ConfigError
from m2b.glean import Proposal
from m2b.proposals import Said
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 3, 5, 3, 0, tzinfo=UTC)
DAY = datetime.date(2026, 3, 4)
DANA = Proposal("person", "Dana runs IT at Northwind.", "Dana runs IT at Northwind", "shed", topic="Northwind")
LADDER = Proposal(
    "commitment", "Call Sam about the ladder.", "I still have to call Sam", "shed", due=datetime.date(2026, 3, 6)
)


def said(*found: Proposal) -> list[Said]:
    return [Said(proposal, DAY) for proposal in found]


class ProposalsFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="sb-test-proposals-")
        self.addCleanup(self._temp.cleanup)
        base = Path(self._temp.name)
        self.root = base / "sb-test-store"
        self.root.mkdir()
        self.store = FolderStore(self.root, base / "machine-tmp", DatalessGuard(False))

    def written(self) -> dict[str, Any]:
        raw: dict[str, Any] = json.loads((self.root / proposals.PROPOSALS_FILE).read_text(encoding="utf-8"))
        return raw

    def write(self, raw: object) -> None:
        target = self.root / proposals.PROPOSALS_FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(raw), encoding="utf-8")

    def kept(self, *found: Proposal, now: datetime.datetime = NOW) -> proposals.Added:
        """Adds to what the store holds and saves it, as a curation run does."""
        added = proposals.add(proposals.load(self.store), said(*found), now)
        proposals.save(self.store, added.proposals)
        return added

    def drop(self, proposal_id: str, when: datetime.datetime) -> None:
        self.settle(proposal_id, proposals.DROPPED, when)

    def settle(self, proposal_id: str, state: str, when: datetime.datetime = NOW) -> None:
        """Marks a proposal as the curation run does once it has settled the person's answer."""
        raw = self.written()
        raw["proposals"][proposal_id].update({"state": state, "since": when.isoformat()})
        self.write(raw)


class KeepingTest(ProposalsFixture):
    def test_a_store_without_the_file_holds_no_proposal_and_was_never_read(self) -> None:
        self.assertEqual(proposals.load(self.store), proposals.Proposals({}, None))

    def test_a_proposal_is_kept_open_with_its_words_its_day_and_what_it_would_become(self) -> None:
        added = self.kept(DANA, LADDER)

        self.assertEqual((added.added, added.like_an_open_one, added.like_a_dropped_one), (2, 0, 0))
        dana, ladder = proposals.proposal_id(DANA), proposals.proposal_id(LADDER)
        self.assertEqual(
            self.written(),
            {
                "format": 1,
                "read_until": None,
                "announced_until": None,
                "proposals": dict(
                    sorted(
                        {
                            dana: {
                                "kind": "person",
                                "text": "Dana runs IT at Northwind.",
                                "quote": "Dana runs IT at Northwind",
                                "topic": "Northwind",
                                "due": None,
                                "day": "2026-03-04",
                                "state": "open",
                                "since": NOW.isoformat(),
                            },
                            ladder: {
                                "kind": "commitment",
                                "text": "Call Sam about the ladder.",
                                "quote": "I still have to call Sam",
                                "topic": None,
                                "due": "2026-03-06",
                                "day": "2026-03-04",
                                "state": "open",
                                "since": NOW.isoformat(),
                            },
                        }.items()
                    )
                ),
            },
        )

    def test_what_was_saved_is_what_is_loaded(self) -> None:
        added = self.kept(DANA, LADDER)
        read_until = NOW - datetime.timedelta(minutes=5)
        proposals.save(self.store, proposals.Proposals(added.proposals.entries, read_until))

        loaded = proposals.load(self.store)

        self.assertEqual(loaded, proposals.Proposals(added.proposals.entries, read_until))
        entry = loaded.entries[proposals.proposal_id(LADDER)]
        self.assertEqual((entry.due, entry.day, entry.state), (datetime.date(2026, 3, 6), DAY, proposals.OPEN))

    def test_an_id_is_twelve_hex_characters_from_the_session_and_the_quote_alone(self) -> None:
        """Covers: B118"""
        same_words = Proposal("personal", "Another wording.", "  Dana runs IT\nat Northwind ", "shed")
        other_session = Proposal("person", "Dana runs IT at Northwind.", "Dana runs IT at Northwind", "trip")

        self.assertRegex(proposals.proposal_id(DANA), r"\A[0-9a-f]{12}\Z")
        self.assertEqual(proposals.proposal_id(same_words), proposals.proposal_id(DANA))
        self.assertNotEqual(proposals.proposal_id(other_session), proposals.proposal_id(DANA))


class RefusingTest(ProposalsFixture):
    def test_reading_the_same_period_a_second_time_adds_nothing(self) -> None:
        """Covers: B118"""
        self.kept(DANA, LADDER)
        before = self.written()

        again = self.kept(DANA, LADDER, now=NOW + datetime.timedelta(days=1))

        self.assertEqual((again.added, again.like_an_open_one, again.like_a_dropped_one), (0, 2, 0))
        self.assertEqual(self.written(), before)

    def test_a_second_reading_that_words_the_same_quote_anew_adds_nothing(self) -> None:
        """Covers: B118"""
        self.kept(DANA)
        worded_anew = Proposal("person", "Northwind's IT is run by Dana.", "Dana runs IT at Northwind", "shed")

        again = self.kept(worded_anew)

        self.assertEqual((again.added, again.like_an_open_one), (0, 1))
        self.assertEqual(self.written()["proposals"][proposals.proposal_id(DANA)]["text"], DANA.text)

    def test_a_proposal_with_the_text_of_an_open_one_is_refused_also_from_another_session(self) -> None:
        """Covers: B118"""
        self.kept(DANA)
        said_again = Proposal("person", "dana runs  IT at northwind.", "Dana is the one who runs IT there", "trip")

        again = self.kept(said_again)

        self.assertEqual((again.added, again.like_an_open_one), (0, 1))
        self.assertEqual(list(self.written()["proposals"]), [proposals.proposal_id(DANA)])

    def test_two_proposals_with_one_text_in_one_answer_are_one_proposal(self) -> None:
        """Covers: B118"""
        twice = Proposal("person", "Dana runs IT at Northwind.", "she signs the renewals too", "shed")

        added = self.kept(DANA, twice)

        self.assertEqual((added.added, added.like_an_open_one), (1, 1))

    def test_a_proposal_dropped_within_ninety_days_is_refused_by_its_id_and_by_its_text(self) -> None:
        """Covers: B118"""
        self.kept(DANA)
        self.drop(proposals.proposal_id(DANA), NOW)
        said_again = Proposal("person", "Dana runs IT at Northwind.", "Dana is the one who runs IT there", "trip")

        later = NOW + datetime.timedelta(days=89)
        again = self.kept(DANA, said_again, now=later)

        self.assertEqual((again.added, again.like_an_open_one, again.like_a_dropped_one), (0, 0, 2))
        self.assertEqual(self.written()["proposals"][proposals.proposal_id(DANA)]["state"], "dropped")

    def test_an_entry_under_a_key_that_is_no_id_is_left_out(self) -> None:
        self.kept(DANA)
        raw = self.written()
        entry = raw["proposals"][proposals.proposal_id(DANA)]
        raw["proposals"].update({"../outside": entry, "\x1b[8mhidden": entry, "ABCDEF012345": entry, "abc": entry})
        self.write(raw)

        self.assertEqual(list(proposals.load(self.store).entries), [proposals.proposal_id(DANA)])

    def test_a_proposal_kept_within_ninety_days_is_refused_by_its_id_and_by_its_text(self) -> None:
        """Covers: B118"""
        self.kept(DANA)
        self.settle(proposals.proposal_id(DANA), proposals.KEPT)
        said_again = Proposal("person", "Dana runs IT at Northwind.", "Dana is the one who runs IT there", "trip")

        later = NOW + datetime.timedelta(days=89)
        again = self.kept(DANA, said_again, now=later)

        self.assertEqual((again.added, again.like_a_kept_one, again.like_a_dropped_one), (0, 2, 0))
        entry = self.written()["proposals"][proposals.proposal_id(DANA)]
        self.assertEqual((entry["state"], entry["since"]), ("kept", NOW.isoformat()))

    def test_after_ninety_days_a_kept_proposal_is_forgotten_and_may_come_again(self) -> None:
        """Covers: B118"""
        self.kept(DANA)
        self.settle(proposals.proposal_id(DANA), proposals.KEPT)

        later = NOW + datetime.timedelta(days=90)
        again = self.kept(DANA, now=later)

        self.assertEqual((again.added, again.like_a_kept_one), (1, 0))
        self.assertEqual(self.written()["proposals"][proposals.proposal_id(DANA)]["state"], "open")

    def test_after_ninety_days_a_dropped_proposal_is_forgotten_and_may_come_again(self) -> None:
        """Covers: B118"""
        self.kept(DANA)
        self.drop(proposals.proposal_id(DANA), NOW)

        later = NOW + datetime.timedelta(days=90)
        again = self.kept(DANA, now=later)

        self.assertEqual((again.added, again.like_a_dropped_one), (1, 0))
        entry = self.written()["proposals"][proposals.proposal_id(DANA)]
        self.assertEqual((entry["state"], entry["since"]), ("open", later.isoformat()))

    def test_a_dropped_proposal_past_ninety_days_leaves_the_file_at_the_next_reading(self) -> None:
        self.kept(DANA)
        self.drop(proposals.proposal_id(DANA), NOW)

        self.kept(LADDER, now=NOW + datetime.timedelta(days=91))

        self.assertEqual(list(self.written()["proposals"]), [proposals.proposal_id(LADDER)])


class UnreadableFileTest(ProposalsFixture):
    def test_an_entry_that_is_not_in_the_form_is_left_out_and_the_others_are_read(self) -> None:
        self.kept(DANA)
        raw = self.written()
        raw["proposals"].update(
            {"aaaaaaaaaaaa": {"kind": "person"}, "bbbbbbbbbbbb": "open", "cccccccccccc": {**_entry(), "day": "soon"}}
        )
        raw["read_until"] = "yesterday"
        self.write(raw)

        loaded = proposals.load(self.store)

        self.assertEqual(list(loaded.entries), [proposals.proposal_id(DANA)])
        self.assertIsNone(loaded.read_until)

    def test_an_entry_with_half_a_character_is_left_out_since_no_answer_could_carry_it(self) -> None:
        self.kept(DANA)
        raw = self.written()
        half = "Dana \ud800 runs IT"
        raw["proposals"].update(
            {
                "aaaaaaaaaaaa": {**_entry(), "text": half},
                "bbbbbbbbbbbb": {**_entry(), "quote": half},
                "cccccccccccc": {**_entry(), "topic": half},
            }
        )
        self.write(raw)

        loaded = proposals.load(self.store)

        self.assertEqual(list(loaded.entries), [proposals.proposal_id(DANA)])

    def test_a_time_without_an_offset_counts_as_utc(self) -> None:
        self.write({"format": 1, "read_until": "2026-03-04T03:00:00", "proposals": {"aaaaaaaaaaaa": _entry()}})

        loaded = proposals.load(self.store)

        self.assertEqual(loaded.read_until, datetime.datetime(2026, 3, 4, 3, tzinfo=UTC))
        self.assertEqual(loaded.entries["aaaaaaaaaaaa"].since, datetime.datetime(2026, 3, 4, 3, tzinfo=UTC))

    def test_a_file_a_newer_m2b_wrote_is_not_read_so_it_is_not_written_over(self) -> None:
        self.write({"format": 2, "proposals": {}})

        with self.assertRaisesRegex(proposals.ProposalsError, "format 2.*update m2b"):
            proposals.load(self.store)

    def test_a_file_that_is_not_json_is_an_error_not_a_store_without_proposals(self) -> None:
        target = self.root / proposals.PROPOSALS_FILE
        target.parent.mkdir(parents=True)
        target.write_text("{", encoding="utf-8")

        with self.assertRaises(ConfigError):
            proposals.load(self.store)


def _entry() -> dict[str, Any]:
    return {
        "kind": "person",
        "text": "Kim Lee leads Acme's IT.",
        "quote": "Kim Lee leads Acme's IT",
        "topic": None,
        "due": None,
        "day": "2026-03-03",
        "state": "open",
        "since": "2026-03-04T03:00:00",
    }


if __name__ == "__main__":
    unittest.main()
