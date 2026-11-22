"""The proposals from the person's sessions as the store keeps them."""

from __future__ import annotations

import dataclasses
import datetime
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from m2b import project_proposals, proposals
from m2b.config.errors import ConfigError
from m2b.glean import FIX, KINDS, AtSource, Example, Examples, LessonPart, PointerPart, Proposal
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


NOTHING_COUNTED = {"proposed": 0, "kept": 0, "dropped": 0, "expired": 0, "not_quoted": 0}


def said(*found: Proposal) -> list[Said]:
    return [Said(proposal, DAY) for proposal in found]


def counts(**per_kind: dict[str, int]) -> dict[str, dict[str, int]]:
    """What the file holds under ``counts``: every kind, with the numbers named here and 0 for the rest."""
    return {kind: {**NOTHING_COUNTED, **per_kind.get(kind, {})} for kind in KINDS}


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
                "counts": counts(person={"proposed": 1}, commitment={"proposed": 1}),
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
        saved = dataclasses.replace(added.proposals, read_until=read_until)
        proposals.save(self.store, saved)

        loaded = proposals.load(self.store)

        self.assertEqual(loaded, saved)
        self.assertEqual(loaded.read_until, read_until)
        entry = loaded.entries[proposals.proposal_id(LADDER)]
        self.assertEqual((entry.due, entry.day, entry.state), (datetime.date(2026, 3, 6), DAY, proposals.OPEN))

    def test_an_id_is_twelve_hex_characters_from_the_session_and_the_quote_alone(self) -> None:
        """Covers: B118"""
        same_words = Proposal("personal", "Another wording.", "  Dana runs IT\nat Northwind ", "shed")
        other_session = Proposal("person", "Dana runs IT at Northwind.", "Dana runs IT at Northwind", "trip")

        self.assertRegex(proposals.proposal_id(DANA), r"\A[0-9a-f]{12}\Z")
        self.assertEqual(proposals.proposal_id(same_words), proposals.proposal_id(DANA))
        self.assertNotEqual(proposals.proposal_id(other_session), proposals.proposal_id(DANA))


class SourceTest(ProposalsFixture):
    PASTED = dataclasses.replace(DANA, source="pasted")
    PASTED_LADDER = dataclasses.replace(LADDER, source="pasted")

    def test_a_proposal_from_pasted_text_is_written_with_its_source_and_read_back_with_it(self) -> None:
        """Covers: B172"""
        self.kept(self.PASTED)

        (written,) = self.written()["proposals"].values()
        (loaded,) = proposals.load(self.store).entries.values()

        self.assertEqual(written["source"], "pasted")
        self.assertEqual(loaded.source, "pasted")

    def test_a_proposal_from_typed_words_is_written_as_before_the_source_was_known(self) -> None:
        """Covers: B172"""
        self.kept(DANA)

        (written,) = self.written()["proposals"].values()

        self.assertEqual(sorted(written), ["day", "due", "kind", "quote", "since", "state", "text", "topic"])
        self.assertEqual(self.written()["format"], 1)

    def test_a_file_with_a_proposal_from_pasted_text_has_a_format_an_m2b_before_the_source_refuses(self) -> None:
        """Covers: B172"""
        self.kept(DANA)
        without = self.written()["format"]
        self.kept(self.PASTED_LADDER)
        with_pasted = self.written()["format"]

        with (
            mock.patch.object(proposals, "FORMAT", proposals.FORMAT_WITHOUT_SOURCE),
            self.assertRaises(proposals.ProposalsError) as refused,
        ):
            proposals.load(self.store)

        self.assertEqual((without, with_pasted), (1, 2))
        self.assertIn("update m2b on this machine", str(refused.exception))

    def test_once_no_proposal_from_pasted_text_is_left_the_file_has_the_earlier_format_again(self) -> None:
        """Covers: B172"""
        self.kept(self.PASTED_LADDER)
        (key,) = self.written()["proposals"]
        self.settle(key, proposals.DROPPED, NOW - datetime.timedelta(days=91))

        self.kept(DANA)

        self.assertEqual(self.written()["format"], 1)
        self.assertEqual([entry.source for entry in proposals.load(self.store).entries.values()], ["typed"])

    def test_an_entry_without_a_source_was_typed(self) -> None:
        """Covers: B172"""
        self.kept(DANA)

        (loaded,) = proposals.load(self.store).entries.values()

        self.assertEqual(loaded.source, "typed")

    def test_a_source_this_m2b_does_not_know_is_kept_as_written_and_named_in_the_line(self) -> None:
        """Covers: B172"""
        self.kept(DANA)
        raw = self.written()
        (key,) = raw["proposals"]
        raw["proposals"][key]["source"] = "letter"
        self.write(raw)

        (loaded,) = proposals.load(self.store).entries.values()
        proposals.save(self.store, proposals.load(self.store))

        self.assertEqual(loaded.source, "letter")
        self.assertEqual(self.written()["proposals"][key]["source"], "letter")
        self.assertEqual(
            proposals.said_line(loaded, loaded.quote), 'from letter on 2026-03-04: "Dana runs IT at Northwind"'
        )

    def test_an_entry_whose_source_is_no_word_is_left_out(self) -> None:
        self.kept(DANA)
        for source in (7, None, "", "Two Words", "x" * 21, "on\nits own line"):
            with self.subTest(source=source):
                raw = self.written()
                (key,) = raw["proposals"]
                raw["proposals"][key]["source"] = source
                self.write(raw)

                self.assertEqual(dict(proposals.load(self.store).entries), {})

    def test_the_line_under_a_proposal_says_said_for_typed_words_and_pasted_for_pasted_ones(self) -> None:
        """Covers: B172"""
        self.kept(DANA, dataclasses.replace(LADDER, source="pasted"))
        lines = {
            entry.source: proposals.said_line(entry, entry.quote)
            for entry in proposals.load(self.store).entries.values()
        }

        self.assertEqual(lines["typed"], 'said on 2026-03-04: "Dana runs IT at Northwind"')
        self.assertTrue(lines["pasted"].startswith("pasted on 2026-03-04: "))


PROJECT = project_proposals.proposal(
    ("github.com/acme/portal",), [datetime.date(2026, 3, 1), datetime.date(2026, 3, 5)]
)
POINTER = Proposal(
    "pointer",
    "Login moves to the customer's identity provider in March → docs/records/014-login.md",
    "the login moves to the customer's identity provider in March",
    "shed",
    topic="Acme portal",
    pointer=PointerPart("docs/records/014-login.md", ("github.com/acme/portal",)),
)
LESSON = Proposal(
    "lesson",
    "Run only the quick checks unless the change gives a reason.",
    "only the quick round, not the whole proof",
    "first",
    lesson=LessonPart(
        "action", "github.com/acme/portal", ("scripts/check",), "no full check without a reason", "second"
    ),
)


class LessonInFileTest(ProposalsFixture):
    def test_a_lesson_is_written_with_its_kind_target_words_and_second_quote_and_read_back(self) -> None:
        """Covers: B270"""
        self.kept(LESSON)

        written = self.written()
        (entry,) = written["proposals"].values()
        self.assertEqual(
            entry["lesson"],
            {
                "kind": "action",
                "target": "github.com/acme/portal",
                "words": ["scripts/check"],
                "quote": "no full check without a reason",
                "session": "second",
            },
        )
        self.assertEqual(written["format"], 4)
        (loaded,) = proposals.load(self.store).entries.values()
        self.assertEqual(loaded.lesson, LESSON.lesson)

    def test_the_words_that_silence_a_lesson_are_written_and_read_back(self) -> None:
        """Covers: B295"""
        silenced = dataclasses.replace(LESSON, lesson=dataclasses.replace(LESSON.lesson, unless=("--quick",)))
        self.kept(silenced)

        (entry,) = self.written()["proposals"].values()
        self.assertEqual(entry["lesson"]["unless"], ["--quick"])
        (loaded,) = proposals.load(self.store).entries.values()
        assert loaded.lesson is not None
        self.assertEqual(loaded.lesson.unless, ("--quick",))

    def test_an_m2b_before_lessons_refuses_a_file_with_one_and_one_without_keeps_the_earlier_format(self) -> None:
        """Covers: B270"""
        self.kept(DANA)
        self.assertEqual(self.written()["format"], 1)
        self.kept(LESSON)

        with (
            mock.patch.object(proposals, "FORMAT", proposals.FORMAT_WITHOUT_LESSONS),
            self.assertRaises(proposals.ProposalsError),
        ):
            proposals.load(self.store)

    def test_a_lesson_kept_at_its_source_is_written_with_the_verdict_and_read_back(self) -> None:
        """Covers: B274"""
        fix = AtSource(
            FIX, "~/.claude/CLAUDE.md", "- Run the whole proof.", "- Run the quick checks.", "~/.claude/CLAUDE.md"
        )
        at_source = dataclasses.replace(LESSON, lesson=dataclasses.replace(LESSON.lesson, at_source=fix))

        self.kept(at_source)

        (entry,) = self.written()["proposals"].values()
        self.assertEqual(entry["lesson"]["at_source"]["verdict"], "fix")
        (loaded,) = proposals.load(self.store).entries.values()
        self.assertEqual(loaded.lesson.at_source if loaded.lesson else None, fix)

    def test_a_lesson_that_replaces_another_is_written_with_it_and_listed_so(self) -> None:
        """Covers: B284"""
        replacing = dataclasses.replace(LESSON, lesson=dataclasses.replace(LESSON.lesson, replaces="weak.md"))

        self.kept(replacing)

        written = self.written()
        (entry,) = written["proposals"].values()
        self.assertEqual((entry["lesson"]["replaces"], written["format"]), ("weak.md", 4))
        (loaded,) = proposals.load(self.store).entries.values()
        assert loaded.lesson is not None
        self.assertEqual(loaded.lesson.replaces, "weak.md")
        self.assertTrue(proposals.lesson_heading(loaded.lesson, str).endswith(", replaces weak.md"))
        # A path is no lesson's name: harvest would remove the file it names.
        (key,) = written["proposals"]
        for path in ("sub/x.md", "../MEMORY.md", "weak.txt"):
            with self.subTest(path):
                lesson = {**written["proposals"][key]["lesson"], "replaces": path}
                self.write({**written, "proposals": {key: {**written["proposals"][key], "lesson": lesson}}})
                self.assertEqual(proposals.load(self.store).entries, {})

    def test_a_lesson_without_its_part_or_one_left_for_this_project_is_left_out(self) -> None:
        """Covers: B270"""
        self.kept(LESSON)
        raw = self.written()
        (key,) = raw["proposals"]
        for broken in ({"lesson": None}, {"lesson": {**raw["proposals"][key]["lesson"], "target": "this project"}}):
            with self.subTest(broken=broken):
                self.write({**raw, "proposals": {key: {**raw["proposals"][key], **broken}}})
                self.assertEqual(proposals.load(self.store).entries, {})


class ProjectInFileTest(ProposalsFixture):
    def test_a_project_has_the_format_of_a_lesson_an_m2b_before_both_refuses_and_it_is_no_example(self) -> None:
        """Covers: B275"""
        self.kept(PROJECT)
        self.assertEqual(self.written()["format"], 4)
        self.kept(LESSON)
        written = self.written()
        self.assertEqual(written["format"], 4)
        (entry,) = (each for each in written["proposals"].values() if each["kind"] == "project")
        self.assertEqual((entry["quote"], entry["source"]), ("github.com/acme/portal", "worked"))
        with (
            mock.patch.object(proposals, "FORMAT", proposals.FORMAT_WITHOUT_LESSONS),
            self.assertRaises(proposals.ProposalsError),
        ):
            proposals.load(self.store)
        for key in written["proposals"]:
            self.settle(key, proposals.KEPT)

        current = proposals.load(self.store)

        self.assertEqual([example.kind for example in proposals.examples(current, NOW).kept], ["lesson"])
        self.assertEqual(proposals.proposal_id(PROJECT), proposals.proposal_id(dataclasses.replace(PROJECT, text="")))

    def test_a_project_is_listed_as_standing_on_the_sessions_that_worked_in_it(self) -> None:
        """Covers: B275"""
        self.kept(PROJECT)
        (loaded,) = proposals.load(self.store).entries.values()

        self.assertEqual(
            proposals.said_line(loaded, loaded.quote),
            'sessions worked in it, the last on 2026-03-04: "github.com/acme/portal"',
        )


class PointerInFileTest(ProposalsFixture):
    def test_a_pointer_is_written_with_its_path_and_repository_and_read_back_and_one_without_is_left_out(self) -> None:
        """Covers: B278"""
        self.kept(POINTER)

        written = self.written()
        (key,) = written["proposals"]
        self.assertEqual(
            written["proposals"][key]["pointer"],
            {"path": "docs/records/014-login.md", "repositories": ["github.com/acme/portal"]},
        )
        self.assertEqual(written["format"], 4)
        (loaded,) = proposals.load(self.store).entries.values()
        self.assertEqual(loaded.pointer, POINTER.pointer)
        for broken in ({"pointer": None}, {"pointer": {"path": "docs/x.md", "repositories": []}}):
            with self.subTest(broken=broken):
                self.write({**written, "proposals": {key: {**written["proposals"][key], **broken}}})
                self.assertEqual(proposals.load(self.store).entries, {})


class HandedInTest(ProposalsFixture):
    """A proposal a session handed in, as the file keeps it."""

    READ = dataclasses.replace(DANA, source="tool")
    WRITTEN = dataclasses.replace(LADDER, source="agent")

    def handed_in(self, proposal: Proposal, tool: str | None = None, now: datetime.datetime = NOW) -> proposals.Added:
        found = [Said(proposal, DAY, tool, proposals.SESSION)]
        added = proposals.add(proposals.load(self.store), found, now)
        proposals.save(self.store, added.proposals)
        return added

    def test_a_handed_in_proposal_keeps_its_source_its_tool_and_who_proposed(self) -> None:
        """Covers: B179"""
        self.handed_in(self.READ, "Read")

        (written,) = self.written()["proposals"].values()
        (loaded,) = proposals.load(self.store).entries.values()

        self.assertEqual((written["source"], written["tool"], written["by"]), ("tool", "Read", "session"))
        self.assertEqual((loaded.source, loaded.tool, loaded.by), ("tool", "Read", "session"))
        self.assertEqual(proposals.proposer_of(loaded), "handed in by a session")

    def test_a_proposal_of_a_reading_is_written_without_a_tool_and_without_who_proposed(self) -> None:
        """Covers: B179"""
        self.kept(DANA, dataclasses.replace(LADDER, source="pasted"))

        for written in self.written()["proposals"].values():
            self.assertNotIn("tool", written)
            self.assertNotIn("by", written)
        self.assertEqual(list(map(proposals.proposer_of, proposals.load(self.store).entries.values())), [None, None])

    def test_the_file_has_format_3_while_a_handed_in_proposal_or_one_on_a_result_or_an_answer_is_in_it(self) -> None:
        """Covers: B179"""
        typed_by_a_session = dataclasses.replace(DANA, source="typed")
        for proposal, tool in ((self.READ, "Read"), (self.WRITTEN, None), (typed_by_a_session, None)):
            with self.subTest(source=proposal.source):
                (self.root / proposals.PROPOSALS_FILE).unlink(missing_ok=True)
                self.handed_in(proposal, tool)

                self.assertEqual(self.written()["format"], 3)

    def test_an_m2b_that_knows_typed_and_pasted_words_only_refuses_such_a_file(self) -> None:
        """Covers: B179"""
        self.handed_in(self.READ, "Read")

        with (
            mock.patch.object(proposals, "FORMAT", proposals.FORMAT_OF_A_READING),
            self.assertRaises(proposals.ProposalsError) as refused,
        ):
            proposals.load(self.store)

        self.assertIn("update m2b on this machine", str(refused.exception))

    def test_once_no_such_proposal_is_left_the_file_has_the_format_of_what_is(self) -> None:
        """Covers: B179"""
        self.handed_in(self.READ, "Read")
        (key,) = self.written()["proposals"]
        self.settle(key, proposals.DROPPED, NOW - datetime.timedelta(days=91))

        self.kept(dataclasses.replace(LADDER, source="pasted"))
        with_pasted = self.written()["format"]
        (key,) = self.written()["proposals"]
        self.settle(key, proposals.DROPPED, NOW - datetime.timedelta(days=91))
        self.kept(dataclasses.replace(DANA, quote="Dana runs the IT at Northwind", text="Dana runs the IT there."))

        self.assertEqual((with_pasted, self.written()["format"]), (2, 1))

    def test_the_line_names_the_tool_of_a_result_and_claude_for_an_answer(self) -> None:
        """Covers: B179"""
        self.handed_in(self.READ, "mcp__mail__get_message")
        self.handed_in(self.WRITTEN)
        lines = {
            entry.source: proposals.said_line(entry, entry.quote)
            for entry in proposals.load(self.store).entries.values()
        }

        self.assertEqual(
            lines["tool"], 'in a result of mcp__mail__get_message on 2026-03-04: "Dana runs IT at Northwind"'
        )
        self.assertEqual(lines["agent"], 'Claude wrote on 2026-03-04: "I still have to call Sam"')

    def test_a_result_whose_tool_is_not_named_is_a_result_of_a_tool(self) -> None:
        """Covers: B179"""
        self.handed_in(self.READ)

        (loaded,) = proposals.load(self.store).entries.values()

        self.assertEqual(
            proposals.said_line(loaded, loaded.quote),
            'in a result of a tool on 2026-03-04: "Dana runs IT at Northwind"',
        )

    def test_an_entry_whose_tool_is_no_tools_name_or_whose_proposer_is_no_word_is_left_out(self) -> None:
        """Covers: B179"""
        self.handed_in(self.READ, "Read")
        (key,) = self.written()["proposals"]
        for field, value in (
            ("tool", "Read me"),
            ("tool", "Read\u202e"),
            ("tool", 7),
            ("tool", ""),
            ("tool", "x" * 129),
            ("by", "A Session"),
            ("by", 7),
        ):
            with self.subTest(field=field, value=value):
                raw = self.written()
                raw["proposals"][key][field] = value
                self.write(raw)

                self.assertEqual(dict(proposals.load(self.store).entries), {})
                raw["proposals"][key][field] = {"tool": "Read", "by": "session"}[field]
                self.write(raw)

    def test_what_a_session_handed_in_and_the_person_answered_is_no_example_for_a_reading(self) -> None:
        """Covers: B179"""
        self.handed_in(self.READ, "Read")
        self.kept(LADDER)
        read, handed = sorted(self.written()["proposals"], key=lambda key: self.written()["proposals"][key]["kind"])
        self.settle(read, proposals.KEPT)
        self.settle(handed, proposals.DROPPED)

        examples = proposals.examples(proposals.load(self.store), NOW)

        self.assertEqual([example.text for example in examples.kept], ["Call Sam about the ladder."])
        self.assertEqual(examples.dropped, ())

    def test_a_proposer_this_m2b_does_not_know_is_named_and_is_no_reading_either(self) -> None:
        """Covers: B179"""
        found = [Said(self.READ, DAY, None, "mail")]
        proposals.save(self.store, proposals.add(proposals.load(self.store), found, NOW).proposals)
        (key,) = self.written()["proposals"]
        self.settle(key, proposals.KEPT)

        (loaded,) = proposals.load(self.store).entries.values()

        self.assertEqual(proposals.proposer_of(loaded), "proposed by mail")
        self.assertEqual(self.written()["format"], 3)
        self.assertEqual(proposals.examples(proposals.load(self.store), NOW), Examples())

    def test_what_waits_and_how_the_last_days_ended_is_counted_per_way_and_source(self) -> None:
        """Covers: B181"""
        self.handed_in(self.READ, "Read")
        self.handed_in(self.WRITTEN)
        self.kept(dataclasses.replace(DANA, quote="Riley signs the orders", text="Riley signs the orders."))
        self.kept(dataclasses.replace(LADDER, quote="Morgan gets the draft", text="Morgan gets it.", source="pasted"))
        keys = {entry["text"]: key for key, entry in self.written()["proposals"].items()}
        self.settle(keys["Dana runs IT at Northwind."], proposals.KEPT)
        self.settle(keys["Morgan gets it."], proposals.DROPPED, NOW - datetime.timedelta(days=40))

        counted = proposals.by_way_and_source(proposals.load(self.store), NOW - proposals.KEEP_RATE_PERIOD)

        self.assertEqual(
            counted,
            {
                "session": {"tool": proposals.WayCounts(kept=1), "agent": proposals.WayCounts(waiting=1)},
                "reading": {"typed": proposals.WayCounts(waiting=1)},
            },
        )


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


class ExpiringTest(ProposalsFixture):
    def aged(self, days: float, answered: tuple[str, ...] = ()) -> proposals.Aged:
        return proposals.aged(proposals.load(self.store), answered, NOW + datetime.timedelta(days=days))

    def test_an_open_proposal_without_an_answer_expires_after_fourteen_days(self) -> None:
        """Covers: B131"""
        self.kept(DANA)
        dana = proposals.proposal_id(DANA)

        early = self.aged(13.99)
        late = self.aged(14)

        self.assertEqual((early.expired, early.proposals.entries[dana].state), (0, proposals.OPEN))
        entry = late.proposals.entries[dana]
        self.assertEqual(late.expired, 1)
        self.assertEqual((entry.state, entry.since), (proposals.EXPIRED, NOW + datetime.timedelta(days=14)))

    def test_a_proposal_whose_answer_waits_for_a_run_does_not_expire(self) -> None:
        """Covers: B131"""
        self.kept(DANA, LADDER)
        dana, ladder = proposals.proposal_id(DANA), proposals.proposal_id(LADDER)

        aged = self.aged(20, answered=(dana,))

        states = {key: entry.state for key, entry in aged.proposals.entries.items()}
        self.assertEqual(states, {dana: proposals.OPEN, ladder: proposals.EXPIRED})
        self.assertEqual(aged.expired, 1)

    def test_an_expired_proposal_is_refused_for_ninety_days_by_its_id_and_by_its_text(self) -> None:
        """Covers: B118"""
        self.kept(DANA)
        self.settle(proposals.proposal_id(DANA), proposals.EXPIRED)
        said_again = Proposal("person", "Dana runs IT at Northwind.", "Dana is the one who runs IT there", "trip")

        again = self.kept(DANA, said_again, now=NOW + datetime.timedelta(days=89))
        after = self.kept(DANA, now=NOW + datetime.timedelta(days=90))

        self.assertEqual((again.added, again.like_an_expired_one, again.like_a_dropped_one), (0, 2, 0))
        self.assertEqual(again.added_before, 2)
        self.assertEqual((after.added, after.like_an_expired_one), (1, 0))

    def test_what_was_answered_or_expired_ninety_days_ago_is_forgotten_and_what_waits_is_not(self) -> None:
        """Covers: B131"""
        tea = Proposal("personal", "Alex drinks green tea.", "I only drink green tea", "kitchen")
        offer = Proposal("commitment", "Send Dana the offer.", "I still have to send Dana the offer", "shed")
        self.kept(DANA, LADDER, tea, offer)
        for proposal, state in ((DANA, proposals.KEPT), (LADDER, proposals.DROPPED), (tea, proposals.EXPIRED)):
            self.settle(proposals.proposal_id(proposal), state)

        before = self.aged(89.99, answered=(proposals.proposal_id(offer),))
        after = self.aged(90, answered=(proposals.proposal_id(offer),))

        self.assertEqual(len(before.proposals.entries), 4)
        self.assertEqual(list(after.proposals.entries), [proposals.proposal_id(offer)])
        self.assertEqual((before.forgotten, after.forgotten, after.expired), (0, 3, 0))

    def test_a_store_where_nothing_is_due_stays_as_it_is(self) -> None:
        self.kept(DANA)
        current = proposals.load(self.store)

        self.assertEqual(proposals.aged(current, (), NOW + datetime.timedelta(days=1)).proposals, current)


class CountingTest(ProposalsFixture):
    def test_a_proposal_is_counted_for_its_kind_when_it_is_added_and_a_refused_one_is_not(self) -> None:
        """Covers: B132"""
        self.kept(DANA, LADDER)

        self.kept(DANA, Proposal("person", "Kim Lee leads Acme's IT.", "Kim Lee leads Acme's IT", "shed"))

        self.assertEqual(self.written()["counts"], counts(person={"proposed": 2}, commitment={"proposed": 1}))

    def test_each_end_of_a_proposal_is_counted_once_for_its_kind(self) -> None:
        """Covers: B132"""
        tea = Proposal("personal", "Alex drinks green tea.", "I only drink green tea", "kitchen")
        current = self.kept(DANA, LADDER, tea).proposals
        later = NOW + datetime.timedelta(days=1)

        current = proposals.settled(current, proposals.proposal_id(DANA), proposals.KEPT, later)
        current = proposals.settled(current, proposals.proposal_id(LADDER), proposals.DROPPED, later)
        current = proposals.aged(current, (), NOW + datetime.timedelta(days=14)).proposals
        proposals.save(self.store, current)

        self.assertEqual(
            self.written()["counts"],
            counts(
                person={"proposed": 1, "kept": 1},
                commitment={"proposed": 1, "dropped": 1},
                personal={"proposed": 1, "expired": 1},
            ),
        )
        entry = current.entries[proposals.proposal_id(DANA)]
        self.assertEqual((entry.state, entry.since), (proposals.KEPT, later))

    def test_a_proposal_kept_after_it_expired_is_counted_as_kept_and_no_longer_as_expired(self) -> None:
        """Covers: B132"""
        current = self.kept(DANA).proposals
        expired = proposals.aged(current, (), NOW + datetime.timedelta(days=14)).proposals

        kept = proposals.settled(
            expired, proposals.proposal_id(DANA), proposals.KEPT, NOW + datetime.timedelta(days=15)
        )

        self.assertEqual(expired.tally("person"), proposals.Tally(proposed=1, expired=1))
        self.assertEqual(kept.tally("person"), proposals.Tally(proposed=1, kept=1))

    def test_an_end_the_file_never_counted_is_not_counted_below_nothing_when_it_changes(self) -> None:
        self.kept(DANA)
        self.settle(proposals.proposal_id(DANA), proposals.EXPIRED)
        raw = self.written()
        del raw["counts"]
        self.write(raw)

        kept = proposals.settled(proposals.load(self.store), proposals.proposal_id(DANA), proposals.KEPT, NOW)

        self.assertEqual(kept.tally("person"), proposals.Tally(kept=1))

    def test_what_the_quote_check_refused_is_counted_although_it_is_never_kept(self) -> None:
        """Covers: B132"""
        current = proposals.counted(proposals.load(self.store), "agreement", "not_quoted", 2)
        proposals.save(self.store, proposals.counted(current, "agreement", "not_quoted"))

        self.assertEqual(self.written()["counts"], counts(agreement={"not_quoted": 3}))
        self.assertEqual(proposals.load(self.store).tally("agreement").not_quoted, 3)

    def test_the_counts_outlast_the_proposals_they_counted(self) -> None:
        """Covers: B132"""
        self.kept(DANA)
        current = proposals.settled(proposals.load(self.store), proposals.proposal_id(DANA), proposals.DROPPED, NOW)

        aged = proposals.aged(current, (), NOW + datetime.timedelta(days=90)).proposals

        self.assertEqual(aged.entries, {})
        self.assertEqual(aged.tally("person"), proposals.Tally(proposed=1, dropped=1))

    def test_a_file_without_counts_or_with_counts_that_are_no_numbers_counts_nothing(self) -> None:
        self.kept(DANA)
        raw = self.written()
        raw["counts"] = {"person": {"proposed": "many", "kept": -1, "dropped": True}, "stranger": {"proposed": 4}}
        self.write(raw)
        with_odd_counts = proposals.load(self.store)
        del raw["counts"]
        self.write(raw)

        self.assertEqual(with_odd_counts.counts, {})
        self.assertEqual(proposals.load(self.store).counts, {})
        self.assertEqual(with_odd_counts.tally("person"), proposals.Tally())


class OutcomesTest(ProposalsFixture):
    def test_the_proposals_settled_since_a_moment_are_counted_by_their_end(self) -> None:
        """Covers: B133"""
        tea = Proposal("personal", "Alex drinks green tea.", "I only drink green tea", "kitchen")
        offer = Proposal("commitment", "Send Dana the offer.", "I still have to send Dana the offer", "shed")
        self.kept(DANA, LADDER, tea, offer)
        self.settle(proposals.proposal_id(DANA), proposals.KEPT, NOW)
        self.settle(proposals.proposal_id(LADDER), proposals.KEPT, NOW - datetime.timedelta(seconds=1))
        self.settle(proposals.proposal_id(tea), proposals.DROPPED, NOW + datetime.timedelta(days=3))
        self.settle(proposals.proposal_id(offer), proposals.EXPIRED, NOW + datetime.timedelta(days=4))

        outcomes = proposals.outcomes_since(proposals.load(self.store), NOW)

        self.assertEqual(outcomes, proposals.Outcomes(kept=1, dropped=1, expired=1))
        self.assertEqual(outcomes.keep_rate, 0.5)

    def test_without_an_answer_there_is_no_keep_rate_also_when_proposals_expired(self) -> None:
        """Covers: B133"""
        self.kept(DANA, LADDER)
        self.settle(proposals.proposal_id(DANA), proposals.EXPIRED, NOW)

        outcomes = proposals.outcomes_since(proposals.load(self.store), NOW)

        self.assertEqual(outcomes, proposals.Outcomes(kept=0, dropped=0, expired=1))
        self.assertIsNone(outcomes.keep_rate)

    def test_the_window_of_the_keep_rate_lies_within_the_time_an_answer_is_remembered(self) -> None:
        self.assertLessEqual(proposals.KEEP_RATE_PERIOD, proposals.REMEMBER_SETTLED)


class ExamplesTest(ProposalsFixture):
    def examples(self, now: datetime.datetime = NOW + datetime.timedelta(days=3)) -> Examples:
        return proposals.examples(proposals.load(self.store), now)

    def settled_entries(self, state: str, number: int) -> dict[str, dict[str, Any]]:
        """``number`` proposals in the state as the file holds them, each settled a minute after the one before."""
        return {
            f"{len(state):x}{index:011x}": {
                **_entry(),
                "text": f"{state} {index}",
                "state": state,
                "since": (NOW + datetime.timedelta(minutes=index)).isoformat(),
            }
            for index in range(number)
        }

    def test_what_the_person_kept_and_dropped_are_examples_the_last_settled_first(self) -> None:
        tea = Proposal("personal", "Alex drinks green tea.", "I only drink green tea", "kitchen")
        offer = Proposal("commitment", "Send Dana the offer.", "I still have to send Dana the offer", "shed")
        self.kept(DANA, LADDER, tea, offer)
        self.settle(proposals.proposal_id(DANA), proposals.KEPT, NOW)
        self.settle(proposals.proposal_id(offer), proposals.KEPT, NOW + datetime.timedelta(days=2))
        self.settle(proposals.proposal_id(tea), proposals.DROPPED, NOW + datetime.timedelta(days=1))
        self.settle(proposals.proposal_id(LADDER), proposals.DROPPED, NOW + datetime.timedelta(hours=1))

        examples = self.examples()

        self.assertEqual(
            examples.kept,
            (
                Example("commitment", "Send Dana the offer.", "I still have to send Dana the offer"),
                Example("person", "Dana runs IT at Northwind.", "Dana runs IT at Northwind"),
            ),
        )
        self.assertEqual(
            examples.dropped,
            (
                Example("personal", "Alex drinks green tea.", "I only drink green tea"),
                Example("commitment", "Call Sam about the ladder.", "I still have to call Sam"),
            ),
        )

    def test_what_a_reading_found_that_waits_is_shown_apart_the_last_added_first(self) -> None:
        """Covers: B246"""
        self.write(
            {
                "format": 3,
                "proposals": {
                    **self.settled_entries("open", 31),
                    **self.settled_entries("kept", 1),
                    "f" * 12: {
                        **_entry(),
                        "text": "handed in",
                        "state": "open",
                        "by": "session",
                        "since": (NOW + datetime.timedelta(hours=1)).isoformat(),
                    },
                },
            }
        )

        waiting = proposals.waiting_examples(proposals.load(self.store))

        self.assertEqual([example.text for example in waiting], [f"open {index}" for index in range(30, 0, -1)])

    def test_a_proposal_that_waits_or_expired_is_no_example(self) -> None:
        self.kept(DANA, LADDER)
        self.settle(proposals.proposal_id(LADDER), proposals.EXPIRED)

        self.assertEqual(self.examples(), Examples())

    def test_of_each_answer_the_thirty_settled_last_are_examples(self) -> None:
        self.write(
            {"format": 1, "proposals": {**self.settled_entries("kept", 32), **self.settled_entries("dropped", 31)}}
        )

        examples = self.examples()

        self.assertEqual([example.text for example in examples.kept], [f"kept {index}" for index in range(31, 1, -1)])
        self.assertEqual(
            [example.text for example in examples.dropped], [f"dropped {index}" for index in range(30, 0, -1)]
        )

    def test_a_proposal_settled_ninety_days_ago_is_no_example_also_while_the_file_still_holds_it(self) -> None:
        tea = Proposal("personal", "Alex drinks green tea.", "I only drink green tea", "kitchen")
        self.kept(DANA, tea)
        self.settle(proposals.proposal_id(DANA), proposals.KEPT, NOW)
        self.settle(proposals.proposal_id(tea), proposals.DROPPED, NOW + datetime.timedelta(seconds=1))

        examples = self.examples(NOW + proposals.REMEMBER_SETTLED)

        self.assertEqual(examples.kept, ())
        self.assertEqual([example.text for example in examples.dropped], ["Alex drinks green tea."])
        self.assertEqual(len(self.written()["proposals"]), 2)

    def test_proposals_settled_in_one_run_are_examples_in_the_same_order_every_time(self) -> None:
        together = {key: {**entry, "since": NOW.isoformat()} for key, entry in self.settled_entries("kept", 5).items()}
        self.write({"format": 1, "proposals": together})
        backwards = {"format": 1, "proposals": dict(reversed(list(together.items())))}

        first = self.examples()
        self.write(backwards)

        self.assertEqual(self.examples(), first)
        self.assertEqual(len(first.kept), 5)


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
        self.write({"format": proposals.FORMAT + 1, "proposals": {}})

        with self.assertRaisesRegex(proposals.ProposalsError, f"format {proposals.FORMAT + 1}.*update m2b"):
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
