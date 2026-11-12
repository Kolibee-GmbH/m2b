from __future__ import annotations

import contextlib
import io
import json
import os
import shlex
import shutil
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from typing import Any

from repo_tools import ingest_eval

DANA_PHONE = "20261109T070000Z-cli-1a01.md"
SAM = "20261109T070700Z-phone-1a02.md"
ROBIN_BIRTHDAY = "20261109T071400Z-cli-1a03.md"
COFFEE = "20261109T072100Z-claude-1a04.md"
DANA_MOVED = "20261109T072800Z-cli-1a05.md"
ACME_OFFICE = "20261109T073500Z-mac-1a06.md"
JO_MARTI = "20261109T074200Z-cli-1a07.md"
CHOIR = "20261109T074900Z-phone-1a08.md"
MIRA_KELLER = "20261109T075600Z-cli-1a09.md"
GLOBEX_TERM = "20261109T080300Z-claude-1a0a.md"
PLUMBER = "20261109T081000Z-cli-1a0b.md"
TAX = "20261109T081700Z-phone-1a0c.md"
GARAGE = "20261109T082400Z-cli-1a0d.md"
LOCK = "20261109T083100Z-mac-1a0e.md"
CELLAR = "20261109T083800Z-phone-1a0f.md"
ASK_ROBIN = "20261109T084500Z-phone-1a10.md"
ROBIN_ADDRESS = "20261109T085200Z-cli-1a11.md"
EXPORT = "20261109T085900Z-claude-1a12.md"
NORWAY = "20261109T090600Z-cli-1a13.md"
NOTHING = "20261109T091300Z-mac-1a14.md"
GIVEN_NOTE = "20261001T080000Z-cli-0a1b.md"

# The distillate after a filing with nothing to object to, written by hand.
MEMORY = """\
# Memory

## Facts

- Alex prefers green tea in the morning (alex.md)
- Alex drinks no coffee after 14:00 (alex.md)
- Dana is Alex's sister and lives in Bern (dana.md)
- Dana's phone number is 555 0142 (dana.md)
- Sam Weber, a neighbour, is allergic to nuts (sam-weber.md)
- Robin, Alex's brother, has his birthday on 12 May (robin.md)
- Robin lives at Mill Lane 4 in Thun (robin.md)

### Acme Ltd (Acme Ltd, Acme, Kim Lee, Jo Marti)
- Kim Lee leads Acme's IT and wants a status mail every Friday (kim-lee.md)
- Acme's office is at Harbour Street 12 (acme.md)
- Jo Marti is the project lead at Acme (jo-marti.md)

### Riverside Choir (Riverside Choir, Petra Lang)
- The choir rehearses on Tuesdays at 19:30 in the old school hall (riverside-choir.md)

### Globex AG (Globex AG, Globex, Mira Keller)
- Mira Keller is Alex's contact at Globex AG, a new customer (mira-keller.md)
- Globex pays invoices within 30 days (globex.md)

## Current

- Planning the trip to Porto
- Planning a hiking week in Norway for next summer (since 2026-11-09)

### Riverside Choir (Riverside Choir, Petra Lang)
- Rehearsing for the spring concert

### Acme Ltd (Acme Ltd, Acme, Kim Lee, Jo Marti)
- Building the data export for Acme Ltd (since 2026-11-09)
"""
# Each fact file with the notes its evidence links.
LINKS = {
    "alex.md": (GIVEN_NOTE, COFFEE),
    "dana.md": (GIVEN_NOTE, DANA_PHONE, DANA_MOVED),
    "kim-lee.md": (GIVEN_NOTE,),
    "sam-weber.md": (SAM,),
    "robin.md": (ROBIN_BIRTHDAY, ROBIN_ADDRESS),
    "acme.md": (ACME_OFFICE,),
    "jo-marti.md": (JO_MARTI,),
    "riverside-choir.md": (CHOIR,),
    "mira-keller.md": (MIRA_KELLER,),
    "globex.md": (GLOBEX_TERM,),
}
# What a fact file keeps under its heading of earlier values.
EARLIER = {"dana.md": "- Lived in Zurich (until 2026-11-09)\n"}
# Dana's fact file when it states her phone number, with the link to the capture that brought it.
DANA_WITH_PHONE = f"""\
# Dana

- Alex's sister.
- Lives in Bern.
- Phone number is 555 0142.

## Earlier

- Lived in Zurich (until 2026-11-09)

## Evidence

- [[{GIVEN_NOTE}]]
- [[{DANA_PHONE}]]
- [[{DANA_MOVED}]]
"""
# Each task as (capture, key, title, due).
TASKS = (
    (PLUMBER, "plumber", "Call the plumber about the boiler", "2026-11-20"),
    (TAX, "tax", "Send the tax papers to the trustee", "2026-11-13"),
    (GARAGE, "garage", "Pay the garage invoice", "2026-11-27"),
    (LOCK, "lock", "Buy a new bike lock", None),
    (CELLAR, "cellar", "Tidy the cellar", None),
    (ASK_ROBIN, "follow-up", "Ask Robin whether he comes for Christmas.", "2026-11-18"),
    (ROBIN_ADDRESS, "postcard", "Send Robin a postcard", None),
)
_GIVEN_LINES = (ingest_eval.FIXTURE / "given" / "memory" / "MEMORY.md").read_text(encoding="utf-8").splitlines()
NEW_LINES = [line for line in MEMORY.splitlines() if line.startswith("- ") and line not in _GIVEN_LINES]


def fact_file(notes: tuple[str, ...], earlier: str = "") -> str:
    """A fact file as far as the count reads it: its earlier values and the notes its evidence links."""
    kept = f"## Earlier\n\n{earlier}\n" if earlier else ""
    evidence = "".join(f"- [[{note}]]\n" for note in notes)
    return f"# A subject\n\n- A fact.\n\n{kept}## Evidence\n\n{evidence}"


def task_file(marker: str, title: str, due: str | None) -> str:
    due_line = f"due: {due}\n" if due is not None else ""
    return f"---\nstatus: open\n{due_line}created: 2026-11-12T08:00:00+01:00\n---\n{title}\n{marker}\n"


class Sandbox(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        self.inbox = ingest_eval.load_inbox(ingest_eval.FIXTURE / "inbox.json")

    def store_before(self) -> Path:
        store = Path(tempfile.mkdtemp(dir=self.root)) / "store"
        ingest_eval.write_store(ingest_eval.FIXTURE / "given", self.inbox, store)
        return store

    def read(self, store: Path) -> ingest_eval.Filed:
        return ingest_eval.read_filed(store, self.root / "tmp")

    def filed_store(
        self,
        memory: str = MEMORY,
        links: dict[str, tuple[str, ...]] | None = None,
        earlier: dict[str, str] | None = None,
        fact_texts: dict[str, str] | None = None,
        tasks: tuple[tuple[str, str, str, str | None], ...] = TASKS,
        task_files: tuple[str, ...] = (),
        waiting: tuple[str, ...] = (),
        deleted: tuple[str, ...] = (),
    ) -> Path:
        """The store after a run, built by hand: what the run wrote into memory and the task list,
        and every capture in the archive but the ones still ``waiting`` and the ones ``deleted``."""
        store = self.store_before()
        (store / "memory" / "MEMORY.md").write_text(memory, encoding="utf-8")
        kept = EARLIER if earlier is None else earlier
        for name, notes in (LINKS if links is None else links).items():
            (store / "memory" / name).write_text(fact_file(notes, kept.get(name, "")), encoding="utf-8")
        for name, text in (fact_texts or {}).items():
            (store / "memory" / name).write_text(text, encoding="utf-8")
        (store / "tasks").mkdir()
        texts = [task_file(f"m2b:capture {capture} {key}", title, due) for capture, key, title, due in tasks]
        for number, text in enumerate([*texts, *task_files]):
            (store / "tasks" / f"{number:012x}.md").write_text(text, encoding="utf-8")
        archive = store / "corpus" / "2026" / "11"
        archive.mkdir(parents=True)
        for capture in self.inbox.captures:
            if capture.file in deleted:
                (store / "inbox" / capture.file).unlink()
            elif capture.file not in waiting:
                shutil.move(str(store / "inbox" / capture.file), archive / capture.file)
        return store

    def score(self, **changes: Any) -> ingest_eval.Score:
        return ingest_eval.score(self.inbox, self.read(self.store_before()), self.read(self.filed_store(**changes)))

    def flaws(self, result: ingest_eval.Score) -> dict[str, tuple[str, ...]]:
        return {flaw.expectation.what: flaw.problems for flaw in result.flawed}


class InventedInboxTest(Sandbox):
    def test_twenty_captures_should_leave_twenty_things_and_one_capture_nothing(self) -> None:
        self.assertEqual(len(self.inbox.captures), 20)
        kinds = Counter(expectation.kind for expectation in self.inbox.expectations)
        self.assertEqual(kinds, {"fact": 11, "task": 7, "current": 2})
        self.assertEqual([capture.file for capture in self.inbox.captures if not capture.expected], [NOTHING])

    def test_four_tasks_name_a_day_and_three_none(self) -> None:
        days = [expectation.due for expectation in self.inbox.expectations if expectation.kind == "task"]

        self.assertEqual(sum(1 for day in days if day is not None), 4)
        self.assertEqual(sum(1 for day in days if day is None), 3)

    def test_every_capture_is_of_the_day_a_current_item_should_carry(self) -> None:
        days = {capture.created.date().isoformat() for capture in self.inbox.captures}

        self.assertEqual(days, {"2026-11-09"})

    def test_a_capture_waits_in_the_inbox_as_a_capture_is_written(self) -> None:
        store = self.store_before()

        self.assertEqual(
            (store / "inbox" / ASK_ROBIN).read_text(encoding="utf-8"),
            "---\ncreated: 2026-11-09T09:45:00+01:00\nsource: phone\nfollow_up: 2026-11-18\n---\n"
            "Ask Robin whether he comes for Christmas.\n",
        )
        self.assertEqual(len(list((store / "inbox").iterdir())), 20)

    def test_the_store_before_the_run_holds_nothing_the_inbox_should_bring(self) -> None:
        before = self.read(self.store_before())

        result = ingest_eval.score(self.inbox, before, before)

        self.assertEqual((result.found, result.extra, result.without_source), (0, (), ()))
        self.assertEqual(len(result.waiting), 20)


class BrokenInboxTest(Sandbox):
    def inbox_file(self, *captures: dict[str, Any]) -> Path:
        path = self.root / "inbox.json"
        path.write_text(json.dumps({"captures": list(captures)}), encoding="utf-8")
        return path

    def test_a_file_name_that_is_no_capture_name_is_refused(self) -> None:
        with self.assertRaisesRegex(ingest_eval.FixtureError, "no name of a capture"):
            ingest_eval.load_inbox(self.inbox_file({"file": "note.md", "text": "A note."}))

    def test_two_captures_of_one_name_are_refused(self) -> None:
        capture = {"file": SAM, "text": "A note."}

        with self.assertRaisesRegex(ingest_eval.FixtureError, "one file name"):
            ingest_eval.load_inbox(self.inbox_file(capture, capture))

    def test_an_expectation_of_an_unknown_kind_is_refused(self) -> None:
        expected = [{"what": "a ref", "kind": "ref", "words": ["example"]}]

        with self.assertRaisesRegex(ingest_eval.FixtureError, "of the kind 'ref'"):
            ingest_eval.load_inbox(self.inbox_file({"file": SAM, "text": "A note.", "expected": expected}))

    def test_a_task_that_does_not_say_its_day_is_refused_and_so_is_a_fact_that_does(self) -> None:
        task = [{"what": "a task", "kind": "task", "words": ["call"]}]
        fact = [{"what": "a fact", "kind": "fact", "words": ["Dana"], "due": None}]

        for expected in (task, fact):
            with self.subTest(expected=expected), self.assertRaisesRegex(ingest_eval.FixtureError, "due day"):
                ingest_eval.load_inbox(self.inbox_file({"file": SAM, "text": "A note.", "expected": expected}))

    def test_an_earlier_value_for_anything_but_a_fact_is_refused(self) -> None:
        expected = [{"what": "a task", "kind": "task", "words": ["call"], "due": None, "earlier": "Zurich"}]

        with self.assertRaisesRegex(ingest_eval.FixtureError, "only a fact replaces an earlier value"):
            ingest_eval.load_inbox(self.inbox_file({"file": SAM, "text": "A note.", "expected": expected}))

    def test_an_expectation_without_words_is_refused(self) -> None:
        expected = [{"what": "a fact", "kind": "fact", "words": []}]

        with self.assertRaisesRegex(ingest_eval.FixtureError, "names no words"):
            ingest_eval.load_inbox(self.inbox_file({"file": SAM, "text": "A note.", "expected": expected}))


class ScoreTest(Sandbox):
    def test_a_filing_with_everything_in_its_place_is_all_found_and_all_right(self) -> None:
        result = self.score()

        self.assertEqual((result.expected, result.found, result.right), (20, 20, 20))
        self.assertEqual((result.extra, result.without_source, result.from_nothing), ((), (), ()))
        self.assertTrue(result.nothing_left_behind)

    def test_each_line_that_is_missing_is_one_expectation_missed(self) -> None:
        self.assertEqual(len(NEW_LINES), 13)
        for line in NEW_LINES:
            with self.subTest(line=line):
                result = self.score(memory=MEMORY.replace(line + "\n", ""))

                self.assertEqual(len(result.missed), 1, [str(missed) for missed in result.missed])

    def test_a_missed_expectation_is_named_with_its_capture(self) -> None:
        line = "- Sam Weber, a neighbour, is allergic to nuts (sam-weber.md)\n"

        result = self.score(memory=MEMORY.replace(line, ""))

        self.assertEqual([str(missed) for missed in result.missed], [f"Sam's allergy (fact from {SAM})"])
        self.assertEqual((result.found, result.right), (19, 19))

    def test_a_fact_that_only_its_fact_file_states_is_missed_and_the_file_is_named(self) -> None:
        memory = MEMORY.replace("- Dana's phone number is 555 0142 (dana.md)\n", "")

        result = self.score(memory=memory, fact_texts={"dana.md": DANA_WITH_PHONE})

        self.assertEqual(
            [str(missed) for missed in result.missed],
            [f"Dana's phone number (fact from {DANA_PHONE}): dana.md holds it, no facts line does"],
        )
        self.assertEqual((result.found, result.right), (19, 19))

    def test_a_fact_file_that_does_not_link_the_capture_is_not_what_states_a_missed_fact(self) -> None:
        memory = MEMORY.replace("- Dana's phone number is 555 0142 (dana.md)\n", "")
        unlinked = DANA_WITH_PHONE.replace(f"- [[{DANA_PHONE}]]\n", "")

        result = self.score(memory=memory, fact_texts={"dana.md": unlinked})

        self.assertEqual([missed.fact_file for missed in result.missed], [None])

    def test_a_missed_current_item_is_not_looked_for_in_the_fact_files(self) -> None:
        memory = MEMORY.replace("- Building the data export for Acme Ltd (since 2026-11-09)\n", "")
        as_a_fact = (
            f"# Acme Ltd\n\n- Alex builds the data export.\n\n## Evidence\n\n- [[{ACME_OFFICE}]]\n- [[{EXPORT}]]\n"
        )

        result = self.score(memory=memory, fact_texts={"acme.md": as_a_fact})

        self.assertEqual([str(missed) for missed in result.missed], [f"the export for Acme (current from {EXPORT})"])

    def test_words_in_another_language_another_case_and_another_way_to_write_a_time_are_found(self) -> None:
        coffee = "Alex drinks no coffee after 14:00"
        for wording in ("Alex trinkt nach 14 Uhr keinen KAFFEE mehr", "Alex drinks no coffee after 2:00 pm"):
            with self.subTest(wording=wording):
                self.assertEqual(self.score(memory=MEMORY.replace(coffee, wording)).right, 20)

    def test_one_line_that_holds_two_expected_facts_counts_for_both(self) -> None:
        both = "- Dana is Alex's sister, lives in Bern and has the phone number 555 0142 (dana.md)\n"
        memory = MEMORY.replace("- Dana is Alex's sister and lives in Bern (dana.md)\n", both)
        memory = memory.replace("- Dana's phone number is 555 0142 (dana.md)\n", "")

        result = self.score(memory=memory)

        self.assertEqual((result.found, result.right, result.extra), (20, 20, ()))

    def test_a_line_that_holds_two_expected_facts_and_stands_twice_is_extra_once(self) -> None:
        both = "- Dana is Alex's sister, lives in Bern and has the phone number 555 0142 (dana.md)\n"
        memory = MEMORY.replace("- Dana is Alex's sister and lives in Bern (dana.md)\n", both + both)
        memory = memory.replace("- Dana's phone number is 555 0142 (dana.md)\n", "")

        result = self.score(memory=memory)

        self.assertEqual((result.right, len(result.extra)), (20, 1))

    def test_a_topic_fact_above_the_first_topic_is_found_and_not_right(self) -> None:
        line = "- Acme's office is at Harbour Street 12 (acme.md)\n"
        memory = MEMORY.replace(line, "").replace("## Facts\n\n", "## Facts\n\n" + line)

        result = self.score(memory=memory)

        self.assertEqual((result.found, result.right), (20, 19))
        self.assertEqual(
            self.flaws(result),
            {"Acme's office": ("stands above the first topic, belongs under a topic named like 'Acme'",)},
        )

    def test_a_fact_for_every_session_under_a_topic_is_not_right(self) -> None:
        line = "- Robin lives at Mill Lane 4 in Thun (robin.md)\n"
        memory = MEMORY.replace(line, "").replace("(globex.md)\n", "(globex.md)\n" + line)

        result = self.score(memory=memory)

        self.assertEqual(
            self.flaws(result),
            {"Robin's address": ("stands under the topic Globex AG, belongs above the first topic",)},
        )

    def test_a_fact_under_another_topic_than_its_own_is_not_right(self) -> None:
        line = "- Jo Marti is the project lead at Acme (jo-marti.md)\n"
        memory = MEMORY.replace(line, "").replace("(globex.md)\n", "(globex.md)\n" + line)

        result = self.score(memory=memory)

        self.assertEqual(
            self.flaws(result),
            {"Jo Marti at Acme": ("stands under the topic Globex AG, belongs under a topic named like 'Acme'",)},
        )

    def test_where_the_rules_leave_room_any_place_is_right(self) -> None:
        line = "- Sam Weber, a neighbour, is allergic to nuts (sam-weber.md)\n"
        memory = MEMORY.replace(line, "").replace("(globex.md)\n", "(globex.md)\n" + line)

        self.assertEqual(self.score(memory=memory).right, 20)

    def test_a_fact_whose_file_does_not_link_its_capture_is_not_right(self) -> None:
        result = self.score(links={**LINKS, "sam-weber.md": ()})

        self.assertEqual(self.flaws(result), {"Sam's allergy": ("sam-weber.md does not link the capture",)})

    def test_a_changed_fact_that_still_stands_with_its_old_value_is_not_right(self) -> None:
        old = "- Dana is Alex's sister and lives in Zurich (dana.md)\n"

        result = self.score(memory=MEMORY.replace("## Facts\n\n", "## Facts\n\n" + old))

        self.assertEqual(self.flaws(result), {"Dana lives in Bern": ("a facts line still says 'lives in Zurich'",)})

    def test_a_changed_fact_whose_file_keeps_no_earlier_value_is_not_right(self) -> None:
        result = self.score(earlier={})

        self.assertEqual(self.flaws(result), {"Dana lives in Bern": ("dana.md keeps no earlier value like 'Zurich'",)})

    def test_an_earlier_value_counts_only_under_its_own_heading(self) -> None:
        elsewhere = {**LINKS, "dana.md": (*LINKS["dana.md"], "a-note-from-zurich.md")}

        result = self.score(earlier={"dana.md": "- Had another phone number (until 2026-11-09)\n"}, links=elsewhere)

        self.assertEqual(self.flaws(result), {"Dana lives in Bern": ("dana.md keeps no earlier value like 'Zurich'",)})

    def test_a_current_item_without_the_day_of_its_capture_is_not_right(self) -> None:
        undated = self.score(memory=MEMORY.replace("next summer (since 2026-11-09)", "next summer"))
        misdated = self.score(memory=MEMORY.replace("next summer (since 2026-11-09)", "next summer (since 2026-11-12)"))

        norway = "the hiking week in Norway"
        self.assertEqual(self.flaws(undated), {norway: ("dated not at all, the capture is of 2026-11-09",)})
        self.assertEqual(self.flaws(misdated), {norway: ("dated 2026-11-12, the capture is of 2026-11-09",)})

    def test_a_current_item_of_a_topic_above_the_first_topic_is_not_right(self) -> None:
        line = "- Building the data export for Acme Ltd (since 2026-11-09)\n"
        memory = MEMORY.replace(line, "").replace(
            "- Planning the trip to Porto\n", "- Planning the trip to Porto\n" + line
        )

        result = self.score(memory=memory)

        self.assertEqual(
            self.flaws(result),
            {"the export for Acme": ("stands above the first topic, belongs under a topic named like 'Acme'",)},
        )

    def test_a_task_on_another_day_or_with_a_day_it_should_not_have_is_not_right(self) -> None:
        tasks = tuple(
            (capture, key, title, {"plumber": "2026-11-21", "lock": "2026-11-10", "tax": None}.get(key, due))
            for capture, key, title, due in TASKS
        )

        result = self.score(tasks=tasks)

        self.assertEqual((result.found, result.right), (20, 17))
        self.assertEqual(
            self.flaws(result),
            {
                "call the plumber": ("due 2026-11-21, expected 2026-11-20",),
                "send the tax papers": ("due on no day, expected 2026-11-13",),
                "buy a bike lock": ("due 2026-11-10, expected no day",),
            },
        )

    def test_a_task_due_at_a_time_of_the_right_day_is_right(self) -> None:
        timed = tuple(
            (capture, key, title, "2026-11-20T09:00:00+01:00" if key == "plumber" else due)
            for capture, key, title, due in TASKS
        )

        self.assertEqual(self.score(tasks=timed).right, 20)

    def test_a_task_with_the_words_from_another_capture_is_not_the_expected_one(self) -> None:
        swapped = tuple((LOCK if key == "plumber" else capture, key, title, due) for capture, key, title, due in TASKS)

        result = self.score(tasks=swapped)

        self.assertEqual([missed.expectation.what for missed in result.missed], ["call the plumber"])
        self.assertEqual(result.extra, (f"task 'Call the plumber about the boiler', from {LOCK}",))

    def test_a_line_no_expectation_accounts_for_is_extra_with_the_capture_it_came_from(self) -> None:
        memory = MEMORY.replace("## Facts\n\n", "## Facts\n\n- Sam Weber lives next door (sam-weber.md)\n")

        result = self.score(memory=memory)

        self.assertEqual(result.extra, (f"facts line 'Sam Weber lives next door' (sam-weber.md), from {SAM}",))
        self.assertEqual((result.right, result.without_source), (20, ()))
        self.assertTrue(result.nothing_left_behind)

    def test_a_second_line_for_one_expectation_is_extra(self) -> None:
        memory = MEMORY.replace("## Facts\n\n", "## Facts\n\n- Sam Weber cannot eat nuts (sam-weber.md)\n")

        result = self.score(memory=memory)

        self.assertEqual((result.right, len(result.extra)), (20, 1))

    def test_of_two_lines_for_one_expectation_the_one_without_a_flaw_counts(self) -> None:
        misplaced = "- Acme Ltd has its office at Harbour Street 12 (acme.md)\n"

        result = self.score(memory=MEMORY.replace("## Facts\n\n", "## Facts\n\n" + misplaced))

        self.assertEqual((result.right, len(result.extra)), (20, 1))

    def test_a_topic_started_that_the_inbox_does_not_name_is_extra(self) -> None:
        line = "- Sam Weber, a neighbour, is allergic to nuts (sam-weber.md)\n"
        memory = MEMORY.replace(line, "").replace(
            "\n## Current", f"\n### Sam Weber (Sam Weber, Weber)\n{line}\n## Current"
        )

        result = self.score(memory=memory)

        self.assertEqual((result.right, result.extra), (20, ("topic 'Sam Weber'",)))
        self.assertTrue(result.nothing_left_behind)

    def test_a_line_that_stands_twice_is_extra_once(self) -> None:
        new = "- Sam Weber, a neighbour, is allergic to nuts (sam-weber.md)\n"
        given = "- Alex prefers green tea in the morning (alex.md)\n"

        again_new = self.score(memory=MEMORY.replace(new, new + new))
        again_given = self.score(memory=MEMORY.replace(given, given + given))

        self.assertEqual(
            again_new.extra, (f"facts line 'Sam Weber, a neighbour, is allergic to nuts' (sam-weber.md), from {SAM}",)
        )
        self.assertEqual(
            again_given.extra, (f"facts line 'Alex prefers green tea in the morning' (alex.md), from {COFFEE}",)
        )
        self.assertEqual((again_new.right, again_given.right), (20, 20))

    def test_a_current_item_that_stands_twice_is_extra_once(self) -> None:
        new = "- Planning a hiking week in Norway for next summer (since 2026-11-09)\n"
        given = "- Planning the trip to Porto\n"

        again_new = self.score(memory=MEMORY.replace(new, new + new))
        again_given = self.score(memory=MEMORY.replace(given, given + given))

        self.assertEqual(again_new.extra, ("current item 'Planning a hiking week in Norway for next summer'",))
        self.assertEqual(again_given.extra, ("current item 'Planning the trip to Porto'",))

    def test_a_new_line_whose_fact_file_links_no_capture_of_the_inbox_is_without_a_source(self) -> None:
        memory = MEMORY.replace("(kim-lee.md)\n", "(kim-lee.md)\n- Kim Lee likes sailing (kim-lee.md)\n")

        result = self.score(memory=memory)

        self.assertEqual(result.without_source, ("facts line 'Kim Lee likes sailing' (kim-lee.md)",))
        self.assertFalse(result.nothing_left_behind)

    def test_a_current_item_no_expectation_accounts_for_is_extra(self) -> None:
        memory = MEMORY.replace("- Planning the trip to Porto\n", "- Planning the trip to Porto\n- Learning to sail\n")

        self.assertEqual(self.score(memory=memory).extra, ("current item 'Learning to sail'",))

    def test_a_task_that_names_no_capture_of_the_inbox_is_without_a_source(self) -> None:
        unmarked = task_file("bought on the way home", "Buy flowers", None)
        foreign = task_file(f"m2b:capture {GIVEN_NOTE} flowers", "Buy more flowers", None)

        result = self.score(task_files=(unmarked, foreign))

        self.assertEqual(result.without_source, ("task 'Buy flowers'", "task 'Buy more flowers'"))

    def test_the_tasks_of_the_curator_are_no_filing(self) -> None:
        review = task_file("m2b:review 2026-11-12", "Review the curation run", None)
        question = task_file("m2b:current 0a1b2c3d4e5f", "Still current? Planning the trip to Porto", None)

        result = self.score(task_files=(review, question))

        self.assertEqual((result.right, result.extra, result.without_source), (20, (), ()))

    def test_what_was_filed_from_the_capture_that_holds_nothing_is_named(self) -> None:
        memory = MEMORY.replace("## Facts\n\n", "## Facts\n\n- Alex is trying a new shortcut (shortcut.md)\n")
        task = task_file(f"m2b:capture {NOTHING} shortcut", "Try the new shortcut", None)

        result = self.score(memory=memory, links={**LINKS, "shortcut.md": (NOTHING,)}, task_files=(task,))

        self.assertEqual(
            result.from_nothing, (f"shortcut.md links {NOTHING}", f"task 'Try the new shortcut' from {NOTHING}")
        )
        self.assertFalse(result.nothing_left_behind)

    def test_a_capture_still_in_the_inbox_and_one_in_neither_place_are_named(self) -> None:
        result = self.score(waiting=(LOCK,), deleted=(CELLAR,))

        self.assertEqual((result.waiting, result.gone), ((LOCK,), (CELLAR,)))
        self.assertFalse(self.score(waiting=(LOCK,)).nothing_left_behind)
        self.assertFalse(self.score(deleted=(CELLAR,)).nothing_left_behind)

    def test_without_a_distillate_everything_filed_into_memory_is_missed(self) -> None:
        store = self.filed_store()
        (store / "memory" / "MEMORY.md").unlink()

        result = ingest_eval.score(self.inbox, self.read(self.store_before()), self.read(store))

        self.assertEqual(Counter(missed.expectation.kind for missed in result.missed), {"fact": 11, "current": 2})


class ReportTest(Sandbox):
    def without(self, lines: int) -> ingest_eval.Score:
        """A filing that left that many of the new lines out and is right about the rest."""
        memory = MEMORY
        for line in NEW_LINES[:lines]:
            memory = memory.replace(line + "\n", "")
        return self.score(memory=memory)

    def report(self, *outcomes: ingest_eval.Outcome) -> tuple[bool, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            passed = ingest_eval.report(outcomes)
        return passed, out.getvalue()

    def test_sixteen_of_twenty_found_and_right_meet_the_bar_and_fifteen_do_not(self) -> None:
        at_the_bar, _ = self.report(ingest_eval.Outcome("haiku", 61.4, self.without(4), ()))
        below, out = self.report(ingest_eval.Outcome("haiku", 61.4, self.without(5), ()))

        self.assertTrue(at_the_bar)
        self.assertFalse(below)
        self.assertIn("haiku run 1 (61 s): found 15 of 20, right 15, 0 extra\n", out)
        self.assertIn("found 0.75, right 0.75 over 1 runs, 0 of them failed or left something behind; misses", out)

    def test_enough_found_and_too_few_of_them_right_miss_the_bar(self) -> None:
        unlinked = {name: () for name in LINKS}

        passed, out = self.report(ingest_eval.Outcome("haiku", 1.0, self.score(links=unlinked), ()))

        self.assertFalse(passed)
        self.assertIn("ingest-eval: haiku: found 1.00, right 0.45 over 1 runs", out)

    def test_three_runs_that_add_up_to_exactly_the_bar_meet_it(self) -> None:
        runs = [ingest_eval.Outcome("haiku", 1.0, self.without(lines), ()) for lines in (8, 2, 2)]

        passed, out = self.report(*runs)

        self.assertTrue(passed, out)
        self.assertIn("found 0.80, right 0.80 over 3 runs, 0 of them failed or left something behind; meets", out)

    def test_the_numbers_of_a_model_are_the_average_of_its_runs(self) -> None:
        runs = [ingest_eval.Outcome("haiku", 1.0, self.without(lines), ()) for lines in (0, 8)]

        passed, out = self.report(*runs)

        self.assertTrue(passed)
        self.assertIn("ingest-eval: haiku: found 0.80, right 0.80 over 2 runs", out)

    def test_one_run_that_left_something_behind_fails_a_model_that_meets_the_numbers(self) -> None:
        runs = [
            ingest_eval.Outcome("haiku", 1.0, self.score(), ()),
            ingest_eval.Outcome("haiku", 1.0, self.score(waiting=(NOTHING,)), ()),
        ]

        passed, out = self.report(*runs)

        self.assertFalse(passed)
        self.assertIn("found 1.00, right 1.00 over 2 runs, 1 of them failed or left something behind; misses", out)

    def test_one_failed_run_fails_a_model_and_says_why(self) -> None:
        failed = ingest_eval.Outcome("haiku", 1.0, self.score(), ("the curation run ended with exit 1: no login",))

        passed, out = self.report(failed)

        self.assertFalse(passed)
        self.assertIn("  run: the curation run ended with exit 1: no login\n", out)

    def test_every_model_gets_its_line_and_one_below_the_bar_fails_the_call(self) -> None:
        haiku = ingest_eval.Outcome("haiku", 1.0, self.without(6), ())
        sonnet = ingest_eval.Outcome("sonnet", 1.0, self.score(), ())

        passed, out = self.report(haiku, sonnet)

        self.assertFalse(passed)
        self.assertIn("ingest-eval: haiku: found 0.70, right 0.70 over 1 runs", out)
        self.assertIn("ingest-eval: sonnet: found 1.00, right 1.00 over 1 runs", out)
        self.assertRegex(out, r"sonnet: [^\n]*; meets the bar of 0\.80 with every run clean\n")

    def test_every_deviation_of_a_run_is_printed_under_it(self) -> None:
        memory = MEMORY.replace("## Facts\n\n", "## Facts\n\n- Sam Weber lives next door (sam-weber.md)\n")
        memory = memory.replace("(kim-lee.md)\n", "(kim-lee.md)\n- Kim Lee likes sailing (kim-lee.md)\n")
        memory = memory.replace("- Robin lives at Mill Lane 4 in Thun (robin.md)\n", "")
        result = self.score(
            memory=memory, links={**LINKS, "acme.md": (), "shortcut.md": (NOTHING,)}, waiting=(LOCK,), deleted=(CELLAR,)
        )

        _, out = self.report(ingest_eval.Outcome("haiku", 1.0, result, ()))

        for line in (
            f"  missed: Robin's address (fact from {ROBIN_ADDRESS})",
            f"  flawed: Acme's office (fact from {ACME_OFFICE}): acme.md does not link the capture",
            f"  extra: facts line 'Sam Weber lives next door' (sam-weber.md), from {SAM}",
            "  without a source: facts line 'Kim Lee likes sailing' (kim-lee.md)",
            f"  filed from a capture that holds nothing: shortcut.md links {NOTHING}",
            f"  still in the inbox: {LOCK}",
            f"  in neither the inbox nor the archive: {CELLAR}",
        ):
            self.assertIn(line + "\n", out)


def bash(*words: str) -> dict[str, str]:
    return {"tool": "Bash", "command": " ".join(shlex.quote(word) for word in words)}


def write(path: str, content: str) -> dict[str, str]:
    return {"tool": "Write", "file_path": f"<store>/{path}", "content": content}


def filing_script(*extra_actions: dict[str, str], captures: tuple[str, ...] | None = None) -> dict[str, Any]:
    """What the scripted model does in the ingest step: the filing built by hand above, through the
    commands a model has, for every capture or for the ones named."""
    inbox = ingest_eval.load_inbox(ingest_eval.FIXTURE / "inbox.json")
    files = [capture.file for capture in inbox.captures] if captures is None else list(captures)
    actions = [bash("m2b", "ingest", "list", "--json"), bash("m2b", "ingest", "normalize", "--json")]
    if captures is None:
        actions.append(write("memory/MEMORY.md", MEMORY))
        for name, notes in LINKS.items():
            actions.append(write(f"memory/{name}", fact_file(notes, EARLIER.get(name, ""))))
    for capture, key, title, due in TASKS:
        if capture not in files:
            continue
        if key == "follow-up":
            actions.append(bash("m2b", "ingest", "task", capture, "--follow-up"))
        else:
            day = ("--due", due) if due is not None else ()
            actions.append(bash("m2b", "ingest", "task", capture, "--key", key, "--title", title, *day))
    for file in files:
        actions += [bash("m2b", "ingest", "note", file, "filed: by the script"), bash("m2b", "ingest", "finish", file)]
    return {"skills": {"/m2b:ingest": {"actions": [*actions, *extra_actions]}}}


# A model that does nothing in any step: the quickest curation run there is.
FILES_NOTHING: dict[str, Any] = {"skills": {}}


class MainTest(Sandbox):
    """Each test runs real curation runs, with the scripted stand-in for the model."""

    def setUp(self) -> None:
        super().setUp()
        self.environ = {"PATH": os.environ.get("PATH", ""), "HOME": str(self.root / "real-home")}
        self.sandbox = self.root / "sandbox"

    def run_main(self, script: dict[str, Any], *arguments: str) -> tuple[int, str]:
        script_file = self.root / "script.json"
        script_file.write_text(json.dumps(script), encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = ingest_eval.main(
                [*arguments, "--work-root", str(self.sandbox), "--script", str(script_file)], self.environ
            )
        return code, out.getvalue()

    def test_a_model_that_files_everything_in_its_place_meets_the_bar(self) -> None:
        code, out = self.run_main(filing_script(), "--model", "sonnet", "--runs", "1")

        self.assertEqual(code, ingest_eval.EXIT_PASSED, out)
        self.assertRegex(out, r"sonnet run 1 \(\d+ s\): found 20 of 20, right 20, 0 extra\n")
        self.assertIn(
            "ingest-eval: sonnet: found 1.00, right 1.00 over 1 runs, 0 of them failed or left something behind; meets",
            out,
        )
        self.assertNotIn("  ", out)

    def test_each_run_curates_with_its_model_in_a_sandbox_of_its_own_with_the_raised_limits(self) -> None:
        self.run_main(FILES_NOTHING, "--model", "sonnet", "--runs", "1")

        run = self.sandbox / "sonnet-1"
        config = json.loads((run / "home" / ".config" / "m2b" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["store"], {"backend": "folder", "path": str(run / "store")})
        self.assertEqual(config["curation"], {"model": "sonnet", "model_timeout_minutes": 20, "max_turns": 400})
        calls = [json.loads(line) for line in (run / "model.json.calls").read_text(encoding="utf-8").splitlines()]
        ingest = next(call["arguments"] for call in calls if "/m2b:ingest" in call["arguments"])
        self.assertEqual(ingest[ingest.index("--model") + 1], "sonnet")
        self.assertEqual(ingest[ingest.index("--max-turns") + 1], "400")

    def test_without_a_model_named_every_curation_model_runs_three_times(self) -> None:
        code, out = self.run_main(FILES_NOTHING)

        self.assertEqual(code, ingest_eval.EXIT_FAILED, out)
        runs = sorted(path.name for path in self.sandbox.iterdir())
        self.assertEqual(runs, ["haiku-1", "haiku-2", "haiku-3", "sonnet-1", "sonnet-2", "sonnet-3"])
        self.assertIn("ingest-eval: haiku: found 0.00, right 0.00 over 3 runs", out)
        self.assertIn("ingest-eval: sonnet: found 0.00, right 0.00 over 3 runs", out)

    def test_a_model_that_files_too_little_misses_the_bar_and_what_it_left_is_named(self) -> None:
        code, out = self.run_main(filing_script(captures=(PLUMBER, LOCK)), "--model", "haiku", "--runs", "1")

        self.assertEqual(code, ingest_eval.EXIT_FAILED, out)
        self.assertIn("found 2 of 20, right 2, 0 extra", out)
        self.assertIn(f"  missed: Sam's allergy (fact from {SAM})", out)
        self.assertIn(f"  still in the inbox: {SAM}", out)
        self.assertEqual(out.count("still in the inbox"), 18)
        self.assertIn(
            "ingest-eval: haiku: found 0.10, right 0.10 over 1 runs, 1 of them failed or left something behind; misses",
            out,
        )

    def test_a_run_with_a_denied_call_misses_the_bar_whatever_it_filed(self) -> None:
        code, out = self.run_main(filing_script(bash("ls")), "--model", "haiku", "--runs", "1")

        self.assertEqual(code, ingest_eval.EXIT_FAILED, out)
        self.assertIn("found 20 of 20, right 20", out)
        self.assertIn("  run: the curation run failed: ingest: denied 1 tool call(s) outside its rules\n", out)
        self.assertIn("1 of them failed or left something behind; misses", out)

    def test_a_model_runner_in_the_callers_environment_is_not_what_a_run_asks(self) -> None:
        runner = self.root / "runner-of-the-caller"
        runner.write_text('#!/bin/sh\necho asked >> "$0.asked"\n', encoding="utf-8")
        runner.chmod(0o755)
        # No claude on this PATH: a run that asks the real one, as it must, fails before any model is asked.
        environ = {
            **self.environ,
            "PATH": "/usr/bin:/bin",
            "M2B_PYTHON": sys.executable,
            "M2B_MODEL_RUNNER": str(runner),
        }
        out = io.StringIO()

        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = ingest_eval.main(["--model", "haiku", "--runs", "1", "--work-root", str(self.sandbox)], environ)

        self.assertFalse(Path(f"{runner}.asked").exists())
        self.assertEqual(code, ingest_eval.EXIT_FAILED, out.getvalue())
        self.assertIn("  run: ", out.getvalue())

    def test_a_run_that_leaves_no_run_record_is_a_failed_run_with_what_the_command_said(self) -> None:
        self.environ["M2B_PYTHON"] = str(self.root / "no-such-python")

        code, out = self.run_main(FILES_NOTHING, "--model", "haiku", "--runs", "1")

        self.assertEqual(code, ingest_eval.EXIT_FAILED, out)
        self.assertRegex(out, r"  run: the curation run ended with exit \d+ and left no run record: \S")

    def test_the_stores_of_the_runs_stay_until_the_next_call(self) -> None:
        _, out = self.run_main(FILES_NOTHING, "--model", "haiku", "--runs", "2")
        self.assertIn(f"the stores of the runs are in {self.sandbox} until the next call", out)
        self.assertTrue((self.sandbox / "haiku-2" / "store" / "memory" / "MEMORY.md").is_file())

        self.run_main(FILES_NOTHING, "--model", "sonnet", "--runs", "1")

        self.assertEqual([path.name for path in self.sandbox.iterdir()], ["sonnet-1"])

    def test_a_store_that_already_holds_what_the_inbox_should_bring_is_refused(self) -> None:
        fixture = self.root / "fixture"
        shutil.copytree(ingest_eval.FIXTURE, fixture)
        memory = fixture / "given" / "memory" / "MEMORY.md"
        memory.write_text(memory.read_text(encoding="utf-8").replace("Zurich", "Bern"), encoding="utf-8")

        code, out = self.run_main(FILES_NOTHING, "--model", "haiku", "--runs", "1", "--fixture", str(fixture))

        self.assertEqual(code, ingest_eval.EXIT_USAGE, out)
        self.assertIn("the store before the run already holds 1 of what the inbox should bring", out)

    def test_the_real_store_is_refused(self) -> None:
        real_config = Path(self.environ["HOME"]) / ".config" / "m2b" / "config.json"
        real_config.parent.mkdir(parents=True)
        store = {"backend": "folder", "path": str(self.root)}
        real_config.write_text(json.dumps({"version": 1, "machine_id": "m", "store": store}), encoding="utf-8")

        code, out = self.run_main(FILES_NOTHING, "--model", "haiku", "--runs", "1")

        self.assertEqual(code, ingest_eval.EXIT_REFUSED, out)
        self.assertFalse(self.sandbox.exists())

    def test_a_number_of_runs_below_one_is_a_usage_error(self) -> None:
        code, out = self.run_main(FILES_NOTHING, "--runs", "0")

        self.assertEqual(code, ingest_eval.EXIT_USAGE, out)


if __name__ == "__main__":
    unittest.main()
