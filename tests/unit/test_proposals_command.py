"""``m2b proposals``: what waits for the person's answer, and keep and drop from the command line."""

from __future__ import annotations

import dataclasses
import json
import unittest
from pathlib import Path
from unittest import mock

import test_commands
from m2b import cli, handed_in, proposal_answers, proposals
from m2b.glean import STATED, AtSource
from m2b.store.base import StoreError
from m2b.store.guard import DatalessGuard
from test_proposal_answers import DANA_ID, LADDER_ID, LESSON_ID, NOBODYS_ID
from test_proposals import DANA, DAY, LADDER, LESSON, NOW, Said


class ProposalsCommandTest(test_commands.CommandTest):
    def setUp(self) -> None:
        super().setUp()
        self.set_up(calendar="none")

    def proposed(self, *found: proposals.Proposal) -> None:
        added = proposals.add(proposals.load(self.store), [Said(proposal, DAY) for proposal in found], NOW)
        proposals.save(self.store, added.proposals)

    def answer_files(self) -> list[str]:
        folder = self.store_root / proposal_answers.FOLDER
        return sorted(path.name for path in folder.iterdir()) if folder.is_dir() else []

    def not_downloaded(self, name: str) -> mock._patch[mock.MagicMock]:
        return mock.patch.object(DatalessGuard, "is_evicted", side_effect=lambda path: Path(path).name == name)


class HandedInCountTest(ProposalsCommandTest):
    WORDS = "words no check has seen"

    def handed_in_file(self, name: str) -> None:
        target = self.store_root / handed_in.FOLDER / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.WORDS, encoding="utf-8")

    def folder_cannot_be_listed(self) -> mock._patch[mock.MagicMock]:
        return mock.patch("m2b.handed_in.waiting", side_effect=StoreError("state/core/handed-in cannot be listed"))

    def test_the_listing_says_how_many_handed_in_proposals_wait_for_a_run_and_never_their_words(self) -> None:
        """Covers: B240"""
        self.handed_in_file("s1.a1b2c3d4e5f6.json")

        code, out, err = self.run_command("proposals")
        self.assertEqual((code, err), (cli.EXIT_OK, ""))
        self.assertEqual(
            out.splitlines(),
            [
                "no proposal waits for an answer",
                "1 proposal handed in by a session waits for the next curation run, which takes it in",
            ],
        )

        self.assertNotIn(self.WORDS, out)

        self.handed_in_file("s2.b2c3d4e5f6a1.json")
        code, as_json, _ = self.run_command("proposals", "--json")
        self.assertEqual(json.loads(as_json), {"proposals": [], "answered": 0, "handed_in": 2})
        self.assertNotIn(self.WORDS, as_json)
        listing = self.run_command("proposals")[1]
        self.assertIn("2 proposals handed in by sessions wait for the next curation run", listing)

    def test_a_folder_that_cannot_be_listed_is_said_for_itself_and_the_proposals_are_still_listed(self) -> None:
        """Covers: B240"""
        self.proposed(DANA)

        with self.folder_cannot_be_listed():
            code, out, err = self.run_command("proposals")
            as_json = self.run_json("proposals")

        self.assertEqual((code, err), (cli.EXIT_OK, ""))
        self.assertIn("1 proposal waits for an answer", out)
        self.assertIn("Dana runs IT at Northwind", out)
        self.assertEqual(out.splitlines()[-1], "handed in: could not look: state/core/handed-in cannot be listed")
        self.assertEqual([proposal["id"] for proposal in as_json["proposals"]], [DANA_ID])
        self.assertIsNone(as_json["handed_in"])

    def test_a_handed_in_file_that_is_not_downloaded_counts_like_one_that_is(self) -> None:
        """Covers: B240"""
        self.handed_in_file("s1.a1b2c3d4e5f6.json")
        self.handed_in_file("s2.b2c3d4e5f6a1.json")

        with self.not_downloaded("s1.a1b2c3d4e5f6.json"):
            answer = self.run_json("proposals")

        self.assertEqual(answer["handed_in"], 2)

    def test_a_folder_of_handed_in_proposals_that_is_not_downloaded_counts_as_one(self) -> None:
        """Covers: B240"""
        self.handed_in_file("s1.a1b2c3d4e5f6.json")
        self.handed_in_file("s2.b2c3d4e5f6a1.json")

        with self.not_downloaded("handed-in"):
            answer = self.run_json("proposals")

        self.assertEqual(answer["handed_in"], 1)


class ListTest(ProposalsCommandTest):
    def test_a_lesson_kept_at_its_source_says_what_becomes_of_the_source(self) -> None:
        """Covers: B273"""
        stated = AtSource(STATED, "~/.claude/CLAUDE.md", "- Run only the quick checks.")
        self.proposed(dataclasses.replace(LESSON, lesson=dataclasses.replace(LESSON.lesson, at_source=stated)))

        out = self.run_command("proposals")[1]
        listed = self.run_json("proposals")["proposals"][0]

        self.assertIn('  stated already in ~/.claude/CLAUDE.md: "- Run only the quick checks."\n', out)
        self.assertEqual(listed["lesson"]["at_source"]["verdict"], "stated")

    def test_a_lesson_for_one_project_comes_with_how_to_keep_it_for_every_project(self) -> None:
        """Covers: B300"""
        self.proposed(LESSON)
        with_lesson = self.run_command("proposals")[1]
        (self.store_root / proposals.PROPOSALS_FILE).unlink()
        self.proposed(DANA)
        without = self.run_command("proposals")[1]

        hint = "a lesson for one project is kept for every project with: m2b proposals keep --every-project <id>..."
        self.assertIn(hint, with_lesson)
        self.assertNotIn(hint, without)

    def test_a_lesson_on_one_correction_is_listed_without_a_line_said_again(self) -> None:
        """Covers: B273"""
        once = dataclasses.replace(LESSON, lesson=dataclasses.replace(LESSON.lesson, quote="", session=""))
        self.proposed(once)

        out = self.run_command("proposals")[1]

        self.assertIn(f'  said on 2026-03-04: "{LESSON.quote}"\n', out)
        self.assertNotIn("and again", out)
        self.assertEqual(self.run_json("proposals")["proposals"][0]["lesson"]["quote"], "")

    def test_a_lesson_is_listed_with_its_kind_target_words_and_the_correction_said_again(self) -> None:
        """Covers: B273"""
        self.proposed(LESSON)
        key = proposals.proposal_id(LESSON)

        out = self.run_command("proposals")[1]
        listed = self.run_json("proposals")["proposals"][0]

        self.assertIn(
            f"{key}  lesson, action for github.com/acme/portal, on a command with scripts/check\n"
            f"  {LESSON.text}\n"
            f'  said on 2026-03-04: "{LESSON.quote}"\n'
            '  and again in another session: "no full check without a reason"\n',
            out,
        )
        self.assertEqual(
            listed["lesson"],
            {
                "kind": "action",
                "target": "github.com/acme/portal",
                "words": ["scripts/check"],
                "quote": "no full check without a reason",
                "at_source": None,
                "replaces": None,
            },
        )

    def test_it_lists_each_waiting_proposal_with_its_kind_text_words_day_and_id(self) -> None:
        """Covers: B122"""
        self.proposed(DANA, LADDER)

        code, out, err = self.run_command("proposals")

        self.assertEqual((code, err), (cli.EXIT_OK, ""))
        blocks = {
            LADDER_ID: (
                f"{LADDER_ID}  commitment, due 2026-03-06\n"
                "  Call Sam about the ladder.\n"
                '  said on 2026-03-04: "I still have to call Sam"\n'
            ),
            DANA_ID: (
                f"{DANA_ID}  person, topic Northwind\n"
                "  Dana runs IT at Northwind.\n"
                '  said on 2026-03-04: "Dana runs IT at Northwind"\n'
            ),
        }
        self.assertEqual(
            out,
            "2 proposals wait for an answer:\n\n"
            + "\n".join(blocks[key] for key in sorted(blocks))
            + "\nkeep with: m2b proposals keep <id>... (or keep --all); drop with: m2b proposals drop <id>...\n",
        )

    def test_characters_that_steer_a_terminal_are_shown_and_never_sent_to_it(self) -> None:
        """Covers: B122"""
        self.proposed(DANA)
        target = self.store_root / proposals.PROPOSALS_FILE
        raw = json.loads(target.read_text(encoding="utf-8"))
        raw["proposals"][DANA_ID].update(
            {
                "text": "Dana runs IT.\x1b[8m And owes Sam 40 euros.\x1b[0m",
                "quote": "Dana runs\r\nIT at Northwind\x07",
                "topic": "North\x9bwind",
            }
        )
        target.write_text(json.dumps(raw), encoding="utf-8")

        _, listed, _ = self.run_command("proposals")
        _, kept, _ = self.run_command("proposals", "keep", DANA_ID)

        self.assertIn("  Dana runs IT.\\x1b[8m And owes Sam 40 euros.\\x1b[0m\n", listed)
        self.assertIn('"Dana runs IT at Northwind\\x07"\n', listed)
        self.assertIn("topic North\\x9bwind\n", listed)
        self.assertIn(": Dana runs IT.\\x1b[8m And owes Sam 40 euros.\\x1b[0m\n", kept)
        for shown in (listed, kept):
            self.assertEqual([character for character in shown if ord(character) < 32 and character != "\n"], [])
            self.assertNotIn("\x9b", shown)

    def test_a_proposal_that_stands_on_pasted_text_says_pasted_where_the_others_say_said(self) -> None:
        """Covers: B172"""
        self.proposed(DANA, dataclasses.replace(LADDER, source="pasted"))

        code, out, _ = self.run_command("proposals")
        listed = {entry["id"]: entry["source"] for entry in self.run_json("proposals")["proposals"]}

        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn('  pasted on 2026-03-04: "I still have to call Sam"\n', out)
        self.assertIn('  said on 2026-03-04: "Dana runs IT at Northwind"\n', out)
        self.assertEqual(listed, {DANA_ID: "typed", LADDER_ID: "pasted"})

    def test_a_proposal_a_session_handed_in_says_so_and_names_the_tool_or_claude(self) -> None:
        """Covers: B179"""
        read = dataclasses.replace(DANA, source="tool")
        written = dataclasses.replace(LADDER, source="agent")
        found = [Said(read, DAY, "mcp__mail__get_message", proposals.SESSION), Said(written, DAY, None, "session")]
        proposals.save(self.store, proposals.add(proposals.load(self.store), found, NOW).proposals)

        _, out, _ = self.run_command("proposals")
        listed = {entry["id"]: entry for entry in self.run_json("proposals")["proposals"]}

        self.assertIn(
            f"{DANA_ID}  person, topic Northwind, handed in by a session\n"
            "  Dana runs IT at Northwind.\n"
            '  in a result of mcp__mail__get_message on 2026-03-04: "Dana runs IT at Northwind"\n',
            out,
        )
        self.assertIn(
            f"{LADDER_ID}  commitment, due 2026-03-06, handed in by a session\n"
            "  Call Sam about the ladder.\n"
            '  Claude wrote on 2026-03-04: "I still have to call Sam"\n',
            out,
        )
        self.assertEqual(
            [(listed[key]["source"], listed[key]["tool"], listed[key]["by"]) for key in (DANA_ID, LADDER_ID)],
            [("tool", "mcp__mail__get_message", "session"), ("agent", None, "session")],
        )

    def test_json_gives_the_same_for_a_client(self) -> None:
        """Covers: B122"""
        self.proposed(DANA, LADDER)
        self.run_command("proposals", "drop", LADDER_ID)

        listed = self.run_json("proposals")

        self.assertEqual(
            listed,
            {
                "proposals": [
                    {
                        "id": DANA_ID,
                        "kind": "person",
                        "text": "Dana runs IT at Northwind.",
                        "quote": "Dana runs IT at Northwind",
                        "day": "2026-03-04",
                        "topic": "Northwind",
                        "due": None,
                        "source": "typed",
                        "tool": None,
                        "by": None,
                        "lesson": None,
                    }
                ],
                "answered": 1,
                "handed_in": 0,
            },
        )

    def test_an_answered_proposal_is_no_longer_listed_and_is_named_as_waiting_for_the_run(self) -> None:
        """Covers: B122"""
        self.proposed(DANA)
        self.run_command("proposals", "keep", DANA_ID)

        code, out, _ = self.run_command("proposals")

        self.assertEqual(code, cli.EXIT_OK)
        self.assertEqual(out, "no proposal waits for an answer\n1 answer waits for the next curation run\n")

    def test_a_store_without_proposals_says_that_none_waits(self) -> None:
        code, out, err = self.run_command("proposals")

        self.assertEqual((code, out, err), (cli.EXIT_OK, "no proposal waits for an answer\n", ""))
        self.assertEqual(self.run_json("proposals"), {"proposals": [], "answered": 0, "handed_in": 0})

    def test_a_proposals_file_that_is_not_downloaded_is_could_not_look_with_the_command_that_fetches_it(self) -> None:
        """Covers: B6, B122"""
        self.proposed(DANA)

        with self.not_downloaded("proposals.json"):
            code, out, err = self.run_command("proposals")
            answered = self.run_command("proposals", "keep", "--all")

        self.assertEqual((code, out), (cli.EXIT_UNREACHABLE, ""))
        self.assertIn("state/core/proposals.json is not downloaded to this machine", err)
        self.assertIn("m2b store fetch state/core/proposals.json", err)
        self.assertEqual(answered[0], cli.EXIT_UNREACHABLE)
        self.assertEqual(self.answer_files(), [])

    def test_answers_that_are_not_downloaded_are_could_not_look_too(self) -> None:
        """Covers: B6, B122"""
        self.proposed(DANA)
        self.run_command("proposals", "drop", DANA_ID)

        with self.not_downloaded("proposal-answers"):
            code, out, err = self.run_command("proposals", "--json")

        self.assertEqual((code, out), (cli.EXIT_UNREACHABLE, ""))
        self.assertIn("m2b store fetch state/core/proposal-answers", err)

    def test_a_proposals_file_a_newer_m2b_wrote_is_a_problem_the_person_can_act_on(self) -> None:
        target = self.store_root / proposals.PROPOSALS_FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"format": proposals.FORMAT + 1, "proposals": {}}), encoding="utf-8")

        code, out, err = self.run_command("proposals")

        self.assertEqual((code, out), (cli.EXIT_PROBLEM, ""))
        self.assertIn("update m2b on this machine", err)


class AnswerTest(ProposalsCommandTest):
    def test_keep_and_drop_add_the_answer_and_say_what_was_answered(self) -> None:
        """Covers: B122"""
        self.proposed(DANA, LADDER)

        kept = self.run_command("proposals", "keep", DANA_ID)
        dropped = self.run_command("proposals", "drop", LADDER_ID)

        self.assertEqual(
            kept,
            (
                cli.EXIT_OK,
                f"keep {DANA_ID}: Dana runs IT at Northwind.\nthe next curation run files what is kept\n",
                "",
            ),
        )
        self.assertEqual(dropped, (cli.EXIT_OK, f"drop {LADDER_ID}: Call Sam about the ladder.\n", ""))
        self.assertEqual(self.answer_files(), sorted([f"{DANA_ID}.keep", f"{LADDER_ID}.drop"]))

    def test_keep_for_every_project_answers_a_lesson_for_one_project_and_says_so(self) -> None:
        """Covers: B300"""
        self.proposed(LESSON, DANA)

        widened = self.run_command("proposals", "keep", "--every-project", LESSON_ID)
        refused = self.run_command("proposals", "keep", "--every-project", DANA_ID)

        self.assertEqual(
            widened,
            (
                cli.EXIT_OK,
                f"keep for every project {LESSON_ID}: {LESSON.text}\nthe next curation run files what is kept\n",
                "",
            ),
        )
        self.assertEqual((refused[0], refused[1]), (cli.EXIT_PROBLEM, ""))
        self.assertIn(f"only a lesson for one project can be kept for every project, not {DANA_ID}", refused[2])
        self.assertEqual(self.answer_files(), [f"{LESSON_ID}.every-project"])

    def test_keep_for_every_project_takes_ids_and_never_all(self) -> None:
        self.proposed(LESSON)

        code, _, _ = self.run_command("proposals", "keep", "--every-project", "--all")

        self.assertEqual((code, self.answer_files()), (cli.EXIT_USAGE, []))

    def test_keep_all_answers_every_proposal_that_waits(self) -> None:
        """Covers: B122"""
        self.proposed(DANA, LADDER)
        self.run_command("proposals", "drop", LADDER_ID)

        answered = self.run_json("proposals", "keep", "--all")
        again = self.run_command("proposals", "keep", "--all")

        self.assertEqual(answered, {"given": [DANA_ID], "already": {}, "left": []})
        self.assertEqual(self.answer_files(), sorted([f"{DANA_ID}.keep", f"{LADDER_ID}.drop"]))
        self.assertEqual(again, (cli.EXIT_OK, "no proposal waits for an answer\n", ""))

    def test_keep_all_leaves_what_a_session_handed_in_and_says_how_many(self) -> None:
        """Covers: B179"""
        self.proposed(DANA)
        found = [Said(dataclasses.replace(LADDER, source="tool"), DAY, "Read", proposals.SESSION)]
        proposals.save(self.store, proposals.add(proposals.load(self.store), found, NOW).proposals)

        code, out, err = self.run_command("proposals", "keep", "--all")
        again = self.run_json("proposals", "keep", "--all")
        by_id = self.run_json("proposals", "keep", LADDER_ID)

        self.assertEqual((code, err), (cli.EXIT_OK, ""))
        self.assertEqual(
            out,
            f"keep {DANA_ID}: Dana runs IT at Northwind.\n"
            "the next curation run files what is kept\n"
            "1 proposal a session handed in waits: --all leaves it, keep or drop by id\n",
        )
        self.assertEqual(again, {"given": [], "already": {}, "left": [LADDER_ID]})
        self.assertEqual(by_id, {"given": [LADDER_ID], "already": {}})
        self.assertEqual(self.answer_files(), sorted([f"{DANA_ID}.keep", f"{LADDER_ID}.keep"]))

    def test_the_same_answer_twice_is_said_and_no_problem(self) -> None:
        """Covers: B122"""
        self.proposed(DANA)
        self.run_command("proposals", "keep", DANA_ID)

        code, out, err = self.run_command("proposals", "keep", DANA_ID)

        self.assertEqual((code, out, err), (cli.EXIT_OK, f"{DANA_ID} is answered with keep already\n", ""))

    def test_another_answer_than_the_one_that_stands_is_a_problem_and_changes_nothing(self) -> None:
        """Covers: B122"""
        self.proposed(DANA, LADDER)
        self.run_command("proposals", "keep", DANA_ID)

        code, out, err = self.run_command("proposals", "drop", LADDER_ID, DANA_ID)
        as_json = self.run_command("proposals", "drop", DANA_ID, "--json")

        self.assertEqual(code, cli.EXIT_PROBLEM)
        self.assertEqual(out, f"drop {LADDER_ID}: Call Sam about the ladder.\n")
        self.assertEqual(err, f"m2b: {DANA_ID} is answered with keep already; that answer stands\n")
        self.assertEqual(self.answer_files(), sorted([f"{DANA_ID}.keep", f"{LADDER_ID}.drop"]))
        self.assertEqual(as_json[0], cli.EXIT_PROBLEM)
        self.assertEqual(json.loads(as_json[1]), {"given": [], "already": {DANA_ID: "keep"}})

    def test_an_unknown_id_is_an_error_and_nothing_is_answered(self) -> None:
        """Covers: B122"""
        self.proposed(DANA)

        code, out, err = self.run_command("proposals", "keep", DANA_ID, NOBODYS_ID)

        self.assertEqual((code, out), (cli.EXIT_PROBLEM, ""))
        self.assertIn(f"no proposal has the id {NOBODYS_ID}", err)
        self.assertEqual(self.answer_files(), [])

    def test_an_answer_names_its_proposals_or_all_of_them_never_both_or_neither(self) -> None:
        self.proposed(DANA)

        neither = self.run_command("proposals", "keep")
        both = self.run_command("proposals", "keep", "--all", DANA_ID)
        drop_all = self.run_command("proposals", "drop", "--all")

        self.assertEqual((neither[0], both[0], drop_all[0]), (cli.EXIT_USAGE, cli.EXIT_USAGE, cli.EXIT_USAGE))
        self.assertEqual(self.answer_files(), [])

    def test_a_store_of_a_newer_format_takes_no_answer(self) -> None:
        self.proposed(DANA)
        settings = json.loads((self.store_root / "store.json").read_text(encoding="utf-8"))
        (self.store_root / "store.json").write_text(json.dumps({**settings, "format": 99}), encoding="utf-8")

        code, _, _ = self.run_command("proposals", "keep", DANA_ID)

        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertEqual(self.answer_files(), [])

    def test_an_answer_never_changes_the_proposals_file(self) -> None:
        """Covers: B120"""
        self.proposed(DANA, LADDER)
        before = (self.store_root / proposals.PROPOSALS_FILE).read_bytes()

        self.run_command("proposals", "keep", "--all")

        self.assertEqual((self.store_root / proposals.PROPOSALS_FILE).read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
