"""Harvest settles the answers to proposals: a kept one becomes a capture, both stay known."""

from __future__ import annotations

import dataclasses
import datetime
import json
import unittest
from typing import Any
from unittest import mock

from m2b import fixes, glean, harvest, lessons, project_proposals, proposal_answers, proposals
from m2b.glean import Proposal
from m2b.notes.frontmatter import Note
from m2b.proposal_answers import DROP, KEEP
from m2b.tasks.base import UnconfirmedTaskError
from m2b.tasks.markdown import MarkdownTasks
from test_proposal_answers import DANA_ID, LADDER_ID, NOBODYS_ID, AnswerFixture
from test_proposals import DANA, LADDER, LESSON, NOW, POINTER, counts

LATER = NOW + datetime.timedelta(days=1)
SOMEDAY = Proposal("commitment", "Send Dana the offer.", "I still have to send Dana the offer", "shed")
SOMEDAY_ID = proposals.proposal_id(SOMEDAY)
LESSON_ID = proposals.proposal_id(LESSON)


class ProposalHarvestFixture(AnswerFixture):
    def setUp(self) -> None:
        super().setUp()
        self.tasks = MarkdownTasks(self.store)

    def answered(self, answer: str, *found: Proposal) -> None:
        self.kept(*found)
        proposal_answers.give(self.store, [proposals.proposal_id(proposal) for proposal in found], answer)

    def harvest(self, now: datetime.datetime = LATER) -> harvest.HarvestReport:
        return harvest.harvest(self.store, self.tasks, "Remember? ", now)

    def captures(self) -> list[Note]:
        return [Note.parse(path.read_text(encoding="utf-8")) for path in sorted((self.root / "inbox").glob("*.md"))]

    def state(self, proposal_id: str) -> tuple[str, str]:
        entry = self.written()["proposals"][proposal_id]
        return entry["state"], entry["since"]

    def frontmatter(self, note: Note) -> Any:
        assert note.frontmatter is not None
        return note.frontmatter


class KeptLessonTest(ProposalHarvestFixture):
    def test_a_kept_lesson_is_filed_in_code_as_a_lesson_and_never_as_a_capture(self) -> None:
        """Covers: B272"""
        self.answered(KEEP, LESSON)

        report = self.harvest()

        self.assertEqual(self.captures(), [])
        (filed,) = lessons.read_all(self.store)
        self.assertEqual(
            (filed.text, filed.kind, filed.target, filed.words),
            (LESSON.text, "action", "github.com/acme/portal", ("scripts/check",)),
        )
        self.assertEqual(self.state(LESSON_ID)[0], "kept")
        self.assertEqual(self.answer_files(), [])
        self.assertEqual(report.problems, [])
        self.assertEqual(len(report.lessons), 1)

    def test_a_kept_lesson_keeps_the_words_that_silence_it(self) -> None:
        """Covers: B295"""
        silenced = dataclasses.replace(LESSON, lesson=dataclasses.replace(LESSON.lesson, unless=("--quick",)))
        self.answered(KEEP, silenced)

        self.harvest()

        (filed,) = lessons.read_all(self.store)
        self.assertEqual((filed.words, filed.unless), (("scripts/check",), ("--quick",)))

    def test_a_kept_lesson_that_replaces_another_removes_it(self) -> None:
        """Covers: B284"""
        weak = self.root / "memory" / "lessons" / "weak.md"
        weak.parent.mkdir(parents=True, exist_ok=True)
        weak.write_text(
            "---\nkind: knowledge\ntarget: every project\nkept: 2026-02-01\n---\n# Weak\n\nKeep it short.\n"
        )
        part = dataclasses.replace(
            LESSON.lesson, kind="knowledge", target="every project", words=(), replaces="weak.md"
        )
        self.answered(KEEP, dataclasses.replace(LESSON, lesson=part))

        report = self.harvest()

        self.assertFalse(weak.exists())
        self.assertEqual(report.replaced, ["weak.md"])
        self.assertEqual(self.written()["format"], 4)

    def test_a_replaced_lesson_that_left_the_block_meanwhile_stays(self) -> None:
        """Covers: B284"""
        weak = self.root / "memory" / "lessons" / "weak.md"
        weak.parent.mkdir(parents=True, exist_ok=True)
        weak.write_text(
            "---\nkind: knowledge\ntarget: every project\nkept: 2026-02-01\nkept_at: ~/.claude/CLAUDE.md\n---\n"
            "# Weak\n\nKeep it short.\n"
        )
        part = dataclasses.replace(
            LESSON.lesson, kind="knowledge", target="every project", words=(), replaces="weak.md"
        )
        self.answered(KEEP, dataclasses.replace(LESSON, lesson=part))

        report = self.harvest()

        self.assertTrue(weak.exists())
        self.assertEqual(report.replaced, [])

    def kept_at(self, at_source: glean.AtSource, kind: str = "action") -> proposals.Entry:
        words = ("scripts/check",) if kind == "action" else ()
        part = dataclasses.replace(LESSON.lesson, kind=kind, words=words, at_source=at_source)
        self.answered(KEEP, dataclasses.replace(LESSON, lesson=part))
        return proposals.load(self.store).entries[LESSON_ID]

    def test_a_lesson_a_source_states_already_is_kept_as_a_pointer_to_it(self) -> None:
        """Covers: B272"""
        self.kept_at(glean.AtSource(glean.STATED, "~/.claude/CLAUDE.md", "- Run only the quick checks."), "knowledge")

        report = self.harvest()

        (filed,) = lessons.read_all(self.store)
        self.assertEqual(
            (filed.kept_at, filed.kind, filed.target), ("~/.claude/CLAUDE.md", "knowledge", "github.com/acme/portal")
        )
        self.assertEqual(lessons.block([filed]), "")
        self.assertEqual((self.state(LESSON_ID)[0], report.problems, self.captures()), ("kept", [], []))

    def test_a_pointer_to_a_file_of_a_repository_names_it_as_a_fix_would_not_by_this_machines_checkout(self) -> None:
        """Covers: B272"""
        stated = glean.AtSource(
            glean.STATED, "~/code/portal/CLAUDE.md", "- Never push.", None, "CLAUDE.md", ("github.com/acme/portal",)
        )
        self.kept_at(stated)

        self.harvest()

        (filed,) = lessons.read_all(self.store)
        self.assertEqual(filed.kept_at, "CLAUDE.md in github.com/acme/portal")

    def test_a_fix_marked_done_or_dropped_before_stays_so_and_the_review_says_it(self) -> None:
        """Covers: B272"""
        home = glean.AtSource(
            glean.FIX, "~/.claude/CLAUDE.md", "- Run the whole proof.", "- Run the quick checks.", "~/.claude/CLAUDE.md"
        )
        before = fixes.new_fix(
            "~/.claude/CLAUDE.md",
            (),
            "sb-test-m1",
            "- Run the whole proof.",
            "- Run the quick checks.",
            "x",
            "2026-03-01",
        )
        fixes.keep(self.store, before)
        fixes.settle(self.store, before.name, fixes.DROPPED)
        self.kept_at(home)

        report = harvest.harvest(self.store, self.tasks, "Remember? ", LATER, machine_id="sb-test-m1")

        self.assertEqual(report.fixes, [])
        self.assertEqual(
            report.problems,
            ["the lesson you kept is a fix of ~/.claude/CLAUDE.md you marked dropped before; it stays dropped"],
        )
        self.assertEqual(self.state(LESSON_ID)[0], "kept")

    def test_a_lesson_that_is_a_fix_of_its_source_is_kept_as_a_fix_for_this_machine_or_its_repository(self) -> None:
        """Covers: B272"""
        home = glean.AtSource(
            glean.FIX, "~/.claude/CLAUDE.md", "- Run the whole proof.", "- Run the quick checks.", "~/.claude/CLAUDE.md"
        )
        added = glean.AtSource(
            glean.FIX,
            "CLAUDE.md in github.com/acme/portal",
            None,
            "Name releases after the version.",
            "CLAUDE.md",
            ("github.com/acme/portal",),
        )
        for at_source, machine, line in ((home, "sb-test-m1", "- Run the whole proof."), (added, None, None)):
            with self.subTest(file=at_source.file):
                for leftover in (self.root / fixes.FOLDER).glob("*") if (self.root / fixes.FOLDER).is_dir() else ():
                    leftover.unlink()
                (self.root / proposals.PROPOSALS_FILE).unlink(missing_ok=True)
                self.kept_at(at_source)

                report = harvest.harvest(self.store, self.tasks, "Remember? ", LATER, machine_id="sb-test-m1")

                (kept,) = fixes.read_all(self.store)
                self.assertEqual(
                    (kept.fix.path, kept.fix.machine, kept.fix.line, kept.fix.wording, kept.state),
                    (at_source.path, machine, line, at_source.wording, fixes.WAITING),
                )
                self.assertIn(LESSON.quote, kept.fix.why)
                self.assertEqual(kept.fix.lesson, LESSON.text)
                self.assertEqual((lessons.read_all(self.store), self.captures(), report.problems), ([], [], []))
                self.assertEqual(report.fixes, [kept.fix.place])
                self.assertEqual(self.state(LESSON_ID)[0], "kept")

    def test_a_knowledge_lesson_for_one_project_waits_with_its_answer_and_says_why(self) -> None:
        """Covers: B272"""
        for_one_project = dataclasses.replace(
            LESSON, lesson=dataclasses.replace(LESSON.lesson, kind="knowledge", words=())
        )
        self.answered(KEEP, for_one_project)

        report = self.harvest()

        self.assertEqual((self.captures(), lessons.read_all(self.store)), ([], []))
        self.assertEqual(self.state(LESSON_ID)[0], "open")
        self.assertEqual(len(self.answer_files()), 1)
        (problem,) = report.problems
        self.assertTrue(problem.startswith(f"the lesson you kept waits: {LESSON.text}"))


class KeepTest(ProposalHarvestFixture):
    def test_a_kept_proposal_becomes_a_capture_stays_known_as_kept_and_its_answer_goes(self) -> None:
        """Covers: B121"""
        self.answered(KEEP, DANA)

        report = self.harvest()

        (note,) = self.captures()
        self.assertEqual(self.frontmatter(note).get("source"), "proposal")
        self.assertEqual(self.frontmatter(note).get("from_proposal"), DANA_ID)
        self.assertEqual(note.body, "Dana runs IT at Northwind.\n")
        self.assertEqual(self.state(DANA_ID), ("kept", LATER.isoformat()))
        self.assertEqual(self.answer_files(), [])
        self.assertEqual((len(report.captured), report.dropped, report.problems), (1, [], []))
        self.assertEqual(self.tasks.items(include_completed=True), [])

    def test_a_kept_project_becomes_the_capture_of_keep_this_project(self) -> None:
        """Covers: B276"""
        two = project_proposals.proposal(
            ("github.com/acme/portal", "gitlab.com/alex/portal"), [datetime.date(2026, 3, 1), NOW.date()]
        )
        self.answered(KEEP, two)

        report = self.harvest()

        (note,) = self.captures()
        self.assertEqual(
            note.body,
            "Keep this project: portal\nRepository: github.com/acme/portal\nRepository: gitlab.com/alex/portal\n",
        )
        self.assertEqual(self.frontmatter(note).get("from_proposal"), proposals.proposal_id(two))
        self.assertEqual(self.state(proposals.proposal_id(two))[0], "kept")
        self.assertEqual(report.problems, [])

    def test_a_kept_pointer_becomes_a_capture_of_its_line_with_its_repository(self) -> None:
        """Covers: B279"""
        self.answered(KEEP, POINTER)

        report = self.harvest()

        (note,) = self.captures()
        self.assertEqual(
            note.body,
            "Keep this pointer: Login moves to the customer's identity provider in March → docs/records/014-login.md\n"
            "Repository: github.com/acme/portal\n",
        )
        self.assertEqual(self.state(proposals.proposal_id(POINTER))[0], "kept")
        self.assertEqual(report.problems, [])

    def test_a_kept_commitment_with_a_day_has_its_task_at_once(self) -> None:
        """Covers: B121"""
        self.answered(KEEP, LADDER)

        self.harvest()

        (note,) = self.captures()
        (task,) = self.tasks.items()
        self.assertEqual((task.title, task.due), ("Call Sam about the ladder.", datetime.date(2026, 3, 6)))
        self.assertEqual(self.frontmatter(note).get_list("tasks"), [task.id])
        self.assertEqual(self.frontmatter(note).get("from_proposal"), LADDER_ID)

    def test_a_kept_commitment_without_a_day_is_a_capture_and_the_filing_makes_its_task(self) -> None:
        """Covers: B121"""
        self.answered(KEEP, SOMEDAY)

        self.harvest()

        (note,) = self.captures()
        self.assertEqual(note.body, "Send Dana the offer.\n")
        self.assertIsNone(self.frontmatter(note).get("tasks"))
        self.assertEqual(self.tasks.items(), [])

    def test_a_day_on_a_proposal_that_is_no_commitment_makes_no_task(self) -> None:
        agreed = Proposal(
            "agreement", "The offer goes out by Friday.", "we agreed the offer goes out", "shed", due=LATER.date()
        )
        self.answered(KEEP, agreed)

        self.harvest()

        self.assertEqual(len(self.captures()), 1)
        self.assertEqual(self.tasks.items(), [])

    def test_a_crash_between_the_capture_and_the_proposals_file_does_not_double_the_capture(self) -> None:
        """Covers: B121"""
        self.answered(KEEP, DANA)
        with mock.patch.object(proposals, "save", side_effect=OSError("crash")), self.assertRaises(OSError):
            self.harvest()
        self.assertEqual(len(self.captures()), 1)
        self.assertEqual(self.state(DANA_ID)[0], "open")

        report = self.harvest()

        self.assertEqual(len(self.captures()), 1)
        self.assertEqual(self.state(DANA_ID), ("kept", LATER.isoformat()))
        self.assertEqual((self.answer_files(), report.captured), ([], []))

    def test_a_capture_already_filed_into_the_archive_counts_as_written(self) -> None:
        """Covers: B121"""
        self.answered(KEEP, DANA)
        with mock.patch.object(proposals, "save", side_effect=OSError("crash")), self.assertRaises(OSError):
            self.harvest()
        (written,) = (self.root / "inbox").glob("*.md")
        filed = self.root / "corpus" / "2026" / "03" / written.name
        filed.parent.mkdir(parents=True)
        written.rename(filed)

        self.harvest()

        self.assertEqual(self.captures(), [])
        self.assertEqual(self.state(DANA_ID)[0], "kept")

    def test_a_crash_before_the_answer_file_goes_leaves_only_the_file_to_remove(self) -> None:
        """Covers: B121"""
        self.answered(KEEP, DANA)
        with mock.patch.object(proposal_answers, "remove", side_effect=OSError("crash")), self.assertRaises(OSError):
            self.harvest()
        self.assertEqual((self.state(DANA_ID)[0], self.answer_files()), ("kept", [f"{DANA_ID}.keep"]))

        self.harvest(LATER + datetime.timedelta(days=1))

        self.assertEqual(len(self.captures()), 1)
        self.assertEqual(self.state(DANA_ID), ("kept", LATER.isoformat()))
        self.assertEqual(self.answer_files(), [])

    def test_a_capture_whose_task_could_not_be_confirmed_is_kept_and_the_review_hears_of_it(self) -> None:
        self.answered(KEEP, LADDER)
        with mock.patch.object(self.tasks, "add", side_effect=UnconfirmedTaskError("the task list did not answer")):
            report = self.harvest()

        self.assertEqual(len(self.captures()), 1)
        self.assertEqual((self.state(LADDER_ID)[0], self.answer_files()), ("kept", []))
        (problem,) = report.problems
        self.assertIn("the task list did not answer", problem)


class CandidatesFailTest(ProposalHarvestFixture):
    def test_a_task_list_out_of_reach_fails_the_harvest_and_the_answers_are_settled_all_the_same(self) -> None:
        """Covers: B121"""
        self.answered(KEEP, DANA)
        self.answered(DROP, SOMEDAY)

        with (
            mock.patch.object(self.tasks, "items", side_effect=harvest.TasksError("the task list does not answer")),
            self.assertRaisesRegex(harvest.TasksError, "the task list does not answer"),
        ):
            self.harvest()

        self.assertEqual(len(self.captures()), 1)
        self.assertEqual((self.state(DANA_ID)[0], self.state(SOMEDAY_ID)[0]), ("kept", "dropped"))
        self.assertEqual(self.answer_files(), [])

    def test_what_stops_the_answers_beside_a_failing_task_list_still_reaches_the_review(self) -> None:
        """Covers: B121"""
        self.answered(KEEP, DANA)
        raw = self.written()
        raw["format"] = proposals.FORMAT + 1
        self.write(raw)
        report = harvest.HarvestReport()

        with (
            mock.patch.object(self.tasks, "items", side_effect=harvest.TasksError("the task list does not answer")),
            self.assertRaises(harvest.TasksError),
        ):
            harvest.harvest(self.store, self.tasks, "Remember? ", LATER, report)

        (problem,) = report.problems
        self.assertIn("update m2b on this machine", problem)

    def test_a_failure_while_settling_never_hides_the_failing_task_list(self) -> None:
        self.answered(KEEP, DANA)
        report = harvest.HarvestReport()

        with (
            mock.patch.object(self.tasks, "items", side_effect=harvest.TasksError("the task list does not answer")),
            mock.patch.object(proposals, "save", side_effect=OSError("the disk is full")),
            self.assertRaisesRegex(harvest.TasksError, "the task list does not answer"),
        ):
            harvest.harvest(self.store, self.tasks, "Remember? ", LATER, report)

        (problem,) = report.problems
        self.assertIn("the answers to proposals were not settled (the disk is full)", problem)

    def test_a_failure_while_settling_alone_fails_the_harvest(self) -> None:
        self.answered(KEEP, DANA)

        with mock.patch.object(proposals, "save", side_effect=OSError("the disk is full")), self.assertRaises(OSError):
            self.harvest()


class DropTest(ProposalHarvestFixture):
    def test_a_dropped_proposal_stays_known_as_dropped_and_nothing_is_captured(self) -> None:
        """Covers: B121"""
        self.answered(DROP, DANA)

        report = self.harvest()

        self.assertEqual(self.captures(), [])
        self.assertEqual(self.state(DANA_ID), ("dropped", LATER.isoformat()))
        self.assertEqual(self.answer_files(), [])
        self.assertEqual((report.captured, report.dropped), ([], ["Dana runs IT at Northwind."]))

    def test_keep_stands_where_both_answers_are_there_and_both_files_go(self) -> None:
        """Covers: B121"""
        self.answered(DROP, DANA)
        (self.root / proposal_answers.FOLDER / f"{DANA_ID}.keep").write_bytes(b"")

        self.harvest()

        self.assertEqual(len(self.captures()), 1)
        self.assertEqual((self.state(DANA_ID)[0], self.answer_files()), ("kept", []))


class LeftAloneTest(ProposalHarvestFixture):
    def test_an_answer_to_a_settled_or_unknown_proposal_only_loses_its_file(self) -> None:
        """Covers: B121"""
        self.answered(DROP, DANA)
        self.settle(DANA_ID, proposals.KEPT)
        folder = self.root / proposal_answers.FOLDER
        (folder / f"{NOBODYS_ID}.keep").write_bytes(b"")
        (folder / "notes.txt").write_bytes(b"mine")

        report = self.harvest()

        self.assertEqual(self.captures(), [])
        self.assertEqual(self.state(DANA_ID), ("kept", NOW.isoformat()))
        self.assertEqual(self.answer_files(), ["notes.txt"])
        self.assertEqual((report.captured, report.dropped, report.problems), ([], [], []))

    def test_without_an_answer_the_proposals_file_is_not_even_read(self) -> None:
        self.kept(DANA)
        before = (self.root / proposals.PROPOSALS_FILE).read_bytes()

        with mock.patch.object(proposals, "load", side_effect=AssertionError("read")):
            report = self.harvest()

        self.assertEqual((self.root / proposals.PROPOSALS_FILE).read_bytes(), before)
        self.assertEqual(report.problems, [])

    def test_an_open_proposal_without_an_answer_stays_as_it_is(self) -> None:
        self.answered(DROP, DANA)
        self.kept(LADDER)

        self.harvest()

        self.assertEqual(self.state(LADDER_ID), ("open", NOW.isoformat()))


class CountedTest(ProposalHarvestFixture):
    def test_each_answer_is_counted_for_the_kind_of_its_proposal(self) -> None:
        """Covers: B132"""
        self.kept(DANA, LADDER, SOMEDAY)
        proposal_answers.give(self.store, [DANA_ID, SOMEDAY_ID], KEEP)
        proposal_answers.give(self.store, [LADDER_ID], DROP)

        self.harvest()
        self.harvest(LATER + datetime.timedelta(days=1))

        self.assertEqual(
            self.written()["counts"],
            counts(person={"proposed": 1, "kept": 1}, commitment={"proposed": 2, "kept": 1, "dropped": 1}),
        )


class ExpiredTest(ProposalHarvestFixture):
    def expired(self, *found: Proposal) -> datetime.datetime:
        """Proposals that got no answer for 14 days, and the moment a run let them expire."""
        self.kept(*found)
        when = NOW + datetime.timedelta(days=14)
        proposal_answers.expire(self.store, when)
        return when

    def test_a_keep_for_an_expired_proposal_is_filed_like_any_keep(self) -> None:
        """Covers: B131"""
        when = self.expired(DANA)
        proposal_answers.give(self.store, [DANA_ID], KEEP)
        day_after = when + datetime.timedelta(days=1)

        report = self.harvest(day_after)

        (note,) = self.captures()
        self.assertEqual(self.frontmatter(note).get("from_proposal"), DANA_ID)
        self.assertEqual(self.state(DANA_ID), ("kept", day_after.isoformat()))
        self.assertEqual(self.answer_files(), [])
        self.assertEqual(self.written()["counts"], counts(person={"proposed": 1, "kept": 1}))
        self.assertEqual(report.problems, [])

    def test_a_drop_for_an_expired_proposal_only_loses_its_file(self) -> None:
        """Covers: B131"""
        when = self.expired(DANA)
        proposal_answers.give(self.store, [DANA_ID], DROP)

        report = self.harvest(when + datetime.timedelta(days=1))

        self.assertEqual(self.state(DANA_ID), ("expired", when.isoformat()))
        self.assertEqual(self.answer_files(), [])
        self.assertEqual((report.dropped, self.captures()), ([], []))


class CannotTellTest(ProposalHarvestFixture):
    def test_with_a_proposal_capture_that_is_not_downloaded_no_kept_proposal_is_captured(self) -> None:
        """Covers: B121"""
        self.answered(KEEP, DANA)
        self.answered(DROP, LADDER)
        evicted = mock.Mock(files=[], evicted=["inbox/20260305T040000Z-proposal-a1b2.md"])
        real_scan = self.store.scan
        with mock.patch.object(self.store, "scan", side_effect=lambda f: evicted if f == "inbox" else real_scan(f)):
            report = self.harvest()

        self.assertEqual(self.captures(), [])
        self.assertEqual(self.state(DANA_ID)[0], "open")
        self.assertEqual(self.state(LADDER_ID)[0], "dropped")
        self.assertEqual(self.answer_files(), [f"{DANA_ID}.keep"])
        (problem,) = report.problems
        self.assertIn("proposal captures not downloaded (inbox/20260305T040000Z-proposal-a1b2.md)", problem)

    def test_a_candidate_capture_is_never_taken_for_a_proposals(self) -> None:
        self.answered(KEEP, DANA)
        inbox = self.root / "inbox"
        inbox.mkdir()
        (inbox / "20260305T040000Z-candidate-a1b2.md").write_text(
            f"---\ncreated: 2026-03-05T04:00:00+00:00\nsource: candidate\nfrom_proposal: {DANA_ID}\n---\nOther\n",
            encoding="utf-8",
        )

        self.harvest()

        self.assertEqual(len(self.captures()), 2)

    def test_an_answers_folder_that_is_not_downloaded_waits_and_the_review_hears_of_it(self) -> None:
        """Covers: B121"""
        self.answered(KEEP, DANA)

        with self.not_downloaded("proposal-answers"):
            report = self.harvest()

        self.assertEqual(self.captures(), [])
        self.assertEqual(self.state(DANA_ID)[0], "open")
        (problem,) = report.problems
        self.assertIn("m2b store fetch state/core/proposal-answers", problem)

    def test_a_proposals_file_this_m2b_cannot_use_leaves_the_answers_waiting(self) -> None:
        """Covers: B121"""
        self.answered(KEEP, DANA)
        raw = self.written()
        raw["format"] = proposals.FORMAT + 1
        self.write(raw)

        report = self.harvest()

        self.assertEqual(self.captures(), [])
        self.assertEqual(self.answer_files(), [f"{DANA_ID}.keep"])
        self.assertEqual(json.loads((self.root / proposals.PROPOSALS_FILE).read_text(encoding="utf-8")), raw)
        (problem,) = report.problems
        self.assertIn("update m2b on this machine", problem)

    def test_a_proposals_file_that_is_no_json_leaves_the_answers_waiting_and_harvests_the_candidates(self) -> None:
        self.answered(KEEP, DANA)
        (self.root / proposals.PROPOSALS_FILE).write_text("{", encoding="utf-8")

        report = self.harvest()

        self.assertEqual(self.answer_files(), [f"{DANA_ID}.keep"])
        (problem,) = report.problems
        self.assertIn("the answers to proposals wait for the next run", problem)


if __name__ == "__main__":
    unittest.main()
