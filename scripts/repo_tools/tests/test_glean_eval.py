from __future__ import annotations

import contextlib
import datetime
import io
import json
import os
import re
import stat
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from typing import Any

from m2b import glean

from repo_tools import REPO_ROOT, glean_eval

# Answers like `claude -p --output-format json`: what the answers file holds for the model (or for
# "*"), a crash for "crash" and a run that ended in an error for "refused". It records its
# arguments, where it ran and what it was given to read.
FAKE_CLAUDE = """#!{python}
import json, os, sys
argv = sys.argv[1:]
model = argv[argv.index("--model") + 1]
given = sys.stdin.read()
with open(os.environ["FAKE_CLAUDE_LOG"], "a", encoding="utf-8") as log:
    call = {{"argv": argv, "cwd": os.getcwd(), "files": os.listdir("."), "stdin": given}}
    log.write(json.dumps(dict(call, m2b_home=os.environ.get("M2B_HOME"))) + "\\n")
with open(os.environ["FAKE_CLAUDE_ANSWERS"], encoding="utf-8") as handle:
    answers = json.load(handle)
answer = answers.get(model, answers.get("*"))
if answer == "crash":
    print("boom", file=sys.stderr)
    sys.exit(1)
if answer == "refused":
    print(json.dumps({{"type": "result", "subtype": "error_max_turns", "is_error": True}}))
    sys.exit(0)
usage = {{"claude-" + model + "-test": {{}}}}
print(json.dumps({{"type": "result", "subtype": "success", "is_error": False, "result": answer, "modelUsage": usage}}))
"""


class Sandbox(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)

    def case(self, day: Path = glean_eval.DAY) -> glean_eval.Case:
        projects = Path(tempfile.mkdtemp(dir=self.root))
        return glean_eval.build_case(glean_eval.load_day(day), projects)

    def day_file(self, *sessions: dict[str, Any], captures: tuple[str, ...] = ()) -> Path:
        path = self.root / "day.json"
        day = {"day": "2026-03-04", "memory": ["# Memory"], "captures": list(captures), "sessions": list(sessions)}
        path.write_text(json.dumps(day), encoding="utf-8")
        return path


def session(name: str, *prompts: object) -> dict[str, Any]:
    return {"name": name, "folder": f"/home/alex/{name}", "starts": "09:00", "prompts": list(prompts)}


def entry(case: glean_eval.Case, statement: glean_eval.Statement, **changes: Any) -> dict[str, Any]:
    """A proposal that stands on the statement, as a model would write it."""
    number = [each.session_id for each in case.sessions].index(statement.session) + 1
    proposal = {"kind": statement.label, "text": "A fact.", "quote": statement.text, "session": number}
    proposal.update(changes)
    return proposal


def answer(*entries: dict[str, Any]) -> str:
    return json.dumps({"proposals": list(entries)})


def every_planted(case: glean_eval.Case) -> list[dict[str, Any]]:
    return [entry(case, statement) for statement in case.day.planted]


def trap(case: glean_eval.Case, label: str) -> glean_eval.Statement:
    (found,) = [each for each in case.day.traps if each.label == label]
    return found


class InventedDayTest(Sandbox):
    def test_the_day_plants_twenty_statements_five_of_each_kind(self) -> None:
        kinds = Counter(statement.label for statement in self.case().day.planted)

        self.assertEqual(kinds, dict.fromkeys(glean.KINDS, 5))

    def test_the_day_holds_one_trap_of_each_class(self) -> None:
        self.assertEqual(sorted(each.label for each in self.case().day.traps), sorted(glean_eval.TRAPS))

    def test_the_reader_gives_twelve_sessions_with_a_hundred_and_twenty_typed_prompts(self) -> None:
        case = self.case()

        self.assertEqual(len(case.sessions), 12)
        self.assertEqual(sum(len(each.prompts) for each in case.sessions), 120)

    def test_what_was_pasted_and_what_a_plugin_sent_does_not_reach_the_model(self) -> None:
        case = self.case()

        for label in glean_eval.TRAPS_OF_THE_READER:
            with self.subTest(label):
                self.assertNotIn(trap(case, label).text, case.step_input)
        self.assertEqual(glean_eval.score(case, answer()).sprung, ())

    def test_the_model_gets_the_memory_and_every_planted_statement(self) -> None:
        case = self.case()
        given = json.loads(case.step_input)

        self.assertIn("Kim Lee is Alex's accountant", given["memory"])
        for statement in case.day.planted:
            with self.subTest(statement.text):
                self.assertIn(statement.text, case.step_input)

    def test_the_sentence_the_person_captured_is_among_the_captures(self) -> None:
        case = self.case()

        self.assertTrue(any(trap(case, "captured").text in capture for capture in case.day.captures))

    def test_the_instruction_names_every_kind_and_every_field_of_a_proposal(self) -> None:
        instruction = glean.instruction()

        for word in (*glean.KINDS, "text", "quote", "session", "topic", "due", "proposals"):
            with self.subTest(word):
                self.assertIn(f"`{word}`" if word != "proposals" else '"proposals"', instruction)

    def test_the_instruction_gives_no_statement_of_the_day_as_an_example(self) -> None:
        instruction = glean.instruction()
        day = self.case().day

        for statement in (*day.planted, *day.traps):
            with self.subTest(statement.text):
                self.assertNotIn(statement.text, instruction)

    def test_the_instruction_names_nobody_and_no_company_of_the_day(self) -> None:
        instruction = glean.instruction()
        day = self.case().day
        words = {word for each in (*day.planted, *day.traps) for word in re.findall(r"\b[A-Z][a-z]{2,}\b", each.text)}

        named = sorted(word for word in words if re.search(rf"\b{word}\b", instruction))

        self.assertEqual(named, [])


class BrokenDayTest(Sandbox):
    def test_a_prompt_that_does_not_hold_its_statement_is_refused(self) -> None:
        day = self.day_file(session("shed", {"text": "Dana runs IT", "planted": "person", "statement": "Sam"}))

        with self.assertRaises(glean_eval.FixtureError):
            self.case(day)

    def test_a_planted_statement_the_reader_does_not_give_is_refused(self) -> None:
        sent = {"text": "Dana runs IT at Northwind", "sent_by": "plugin", "planted": "person"}
        day = self.day_file(session("shed", "hello there", {**sent, "statement": "Dana runs IT at Northwind"}))

        with self.assertRaises(glean_eval.FixtureError):
            self.case(day)

    def test_two_sessions_of_one_name_are_refused(self) -> None:
        day = self.day_file(session("shed", "one"), session("shed", "two"))

        with self.assertRaises(glean_eval.FixtureError):
            self.case(day)


class ScoreTest(Sandbox):
    def setUp(self) -> None:
        super().setUp()
        self.given = self.case()

    def score(self, *entries: dict[str, Any]) -> glean_eval.Score:
        return glean_eval.score(self.given, answer(*entries))

    def test_an_answer_with_every_planted_statement_and_nothing_else_is_all_found_and_all_right(self) -> None:
        result = self.score(*every_planted(self.given))

        self.assertEqual((result.found, result.kept, result.right, result.right_kind), (20, 20, 20, 20))
        self.assertEqual((result.recall, result.precision), (1.0, 1.0))
        self.assertEqual((result.missed, result.wrong, result.sprung), ((), (), ()))

    def test_an_answer_without_proposals_finds_nothing_and_is_right_about_nothing(self) -> None:
        result = self.score()

        self.assertEqual((result.recall, result.precision, len(result.missed)), (0.0, 0.0, 20))

    def test_a_second_proposal_for_the_same_statement_is_not_right(self) -> None:
        first = self.given.day.planted[0]

        result = self.score(*every_planted(self.given), entry(self.given, first, text="The same again."))

        self.assertEqual((result.found, result.right, result.kept), (20, 20, 21))
        self.assertEqual([wrong.text for wrong in result.wrong], ["The same again."])

    def test_a_quote_that_shares_half_of_itself_with_the_statement_stands_on_it(self) -> None:
        dana = self.given.day.planted[0]
        self.assertEqual(dana.text, "Dana runs IT at Northwind and signs off every release")

        for quote in (
            "Before you touch the export: Dana runs IT at Northwind and signs off every release, so the export",
            "runs IT at Northwind",
            "signs off every release, so the export",
        ):
            with self.subTest(quote):
                self.assertEqual(self.score(entry(self.given, dana, quote=quote)).found, 1)

    def test_a_quote_from_the_same_prompt_beside_the_statement_does_not_stand_on_it(self) -> None:
        dana = self.given.day.planted[0]

        for quote in ("so the export has to pass her checklist", "every release, so the export has to pass her"):
            with self.subTest(quote):
                result = self.score(entry(self.given, dana, quote=quote))

                self.assertEqual((result.found, result.kept, result.right), (0, 1, 0))

    def test_a_quote_of_the_statement_given_for_another_session_finds_nothing(self) -> None:
        dana = self.given.day.planted[0]

        result = self.score(entry(self.given, dana, session=12))

        self.assertEqual((result.found, result.not_quoted, result.kept), (0, 1, 0))

    def test_a_proposal_of_another_kind_finds_the_statement_with_the_wrong_kind(self) -> None:
        result = self.score(entry(self.given, self.given.day.planted[0], kind="personal"))

        self.assertEqual((result.found, result.right_kind), (1, 0))

    def test_a_proposal_from_a_trap_the_model_must_resist_springs_it_and_is_wrong(self) -> None:
        for label in ("hypothetical", "test-data", "project-todo", "in-memory"):
            with self.subTest(label):
                result = self.score(entry(self.given, trap(self.given, label), kind="person"))

                self.assertEqual(result.sprung, (label,))
                self.assertEqual((result.kept, result.right), (1, 0))

    def test_the_sentence_the_person_captured_is_taken_away_by_code_and_springs_nothing(self) -> None:
        captured = trap(self.given, "captured")

        for quote in (captured.text, f"merk dir: {captured.text}"):
            with self.subTest(quote):
                result = self.score(entry(self.given, captured, kind="person", quote=quote))

                self.assertEqual((result.already_captured, result.kept, result.sprung), (1, 0, ()))

    def test_a_quote_the_person_did_not_type_is_left_out_before_anything_is_counted(self) -> None:
        result = self.score(entry(self.given, self.given.day.planted[0], quote="Dana runs HR at Northwind"))

        self.assertEqual((result.proposals, result.not_quoted, result.kept, result.found), (1, 1, 0, 0))

    def test_words_of_a_reader_trap_among_the_typed_prompts_spring_it_whatever_the_answer(self) -> None:
        typed = {"text": "Sam Rivers is the release manager", "trap": "automation"}
        day = self.day_file(
            session("loop", "start the loop", {**typed, "statement": "Sam Rivers is the release manager"})
        )

        self.assertEqual(glean_eval.score(self.case(day), answer()).sprung, ("automation",))


class WithFakeClaude(Sandbox):
    def setUp(self) -> None:
        super().setUp()
        self.claude = self.root / "claude-command"
        self.claude.write_text(FAKE_CLAUDE.format(python=sys.executable), encoding="utf-8")
        self.claude.chmod(0o755)
        self.log = self.root / "claude-log.jsonl"
        self.answers = self.root / "answers.json"
        self.environ = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(self.root / "real-home"),
            "FAKE_CLAUDE_LOG": str(self.log),
            "FAKE_CLAUDE_ANSWERS": str(self.answers),
        }

    def answer_with(self, **answers: str) -> None:
        self.answers.write_text(json.dumps({name.replace("any", "*"): text for name, text in answers.items()}))

    def run_main(self, *arguments: str) -> tuple[int, str]:
        """Runs in a sandbox of its own, never in the folder a real run may be using right now."""
        work_root = () if "--work-root" in arguments else ("--work-root", str(self.root / "sandbox"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = glean_eval.main([*arguments, *work_root, "--claude", str(self.claude)], self.environ)
        return code, out.getvalue()

    def calls(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]


class MainTest(WithFakeClaude):
    def test_a_model_that_finds_every_statement_and_nothing_else_meets_the_bar(self) -> None:
        self.answer_with(any=answer(*every_planted(self.case())))

        code, out = self.run_main("--model", "haiku", "--runs", "2")

        self.assertEqual(code, glean_eval.EXIT_PASSED, out)
        self.assertIn("haiku run 2 (claude-haiku-test", out)
        self.assertIn("found 20 of 20, right 20 of 20 proposals, kind right 20 of 20", out)
        self.assertIn("glean-eval: haiku: found 1.00, right 1.00 over 2 runs, traps sprung: none; meets", out)

    def test_without_a_model_named_every_curation_model_is_asked_three_times(self) -> None:
        self.answer_with(any=answer(*every_planted(self.case())))

        code, out = self.run_main()

        self.assertEqual(code, glean_eval.EXIT_PASSED, out)
        models = Counter(call["argv"][call["argv"].index("--model") + 1] for call in self.calls())
        self.assertEqual(models, {"haiku": 3, "sonnet": 3})

    def test_a_model_below_the_bar_fails_and_its_misses_are_named(self) -> None:
        case = self.case()
        self.answer_with(haiku=answer(*every_planted(case)[1:11]), sonnet=answer(*every_planted(case)))

        code, out = self.run_main("--runs", "1")

        self.assertEqual(code, glean_eval.EXIT_FAILED, out)
        self.assertIn("glean-eval: haiku: found 0.50, right 1.00 over 1 runs, traps sprung: none; misses", out)
        self.assertIn("missed person in portal-morning: 'Dana runs IT at Northwind and signs off every release'", out)
        self.assertIn("glean-eval: sonnet: found 1.00, right 1.00 over 1 runs, traps sprung: none; meets", out)

    def test_a_sprung_trap_fails_a_model_that_meets_the_numbers(self) -> None:
        case = self.case()
        todo = entry(case, trap(case, "project-todo"), kind="commitment")
        self.answer_with(any=answer(*every_planted(case), todo))

        code, out = self.run_main("--model", "sonnet", "--runs", "2")

        self.assertEqual(code, glean_eval.EXIT_FAILED, out)
        self.assertIn("trap sprung: project-todo", out)
        self.assertIn("wrong commitment in portal-morning: 'we still need to add an index", out)
        self.assertIn("found 1.00, right 0.95 over 2 runs, traps sprung: project-todo in 2; misses", out)

    def test_an_answer_that_cannot_be_read_is_an_error_not_a_run_that_found_nothing(self) -> None:
        self.answer_with(any="I found nothing worth keeping.")

        code, out = self.run_main("--model", "haiku", "--runs", "1")

        self.assertEqual(code, glean_eval.EXIT_FAILED)
        self.assertIn("haiku run 1: error: the answer holds no JSON object", out)
        self.assertIn("glean-eval: haiku: 1 of 1 runs gave no answer", out)
        self.assertNotIn("found 0.00", out)

    def test_a_run_that_fails_or_ends_in_an_error_is_an_error(self) -> None:
        for model_answer, said in (
            ("crash", "exit 1 without a result: boom"),
            ("refused", "the model run failed (error_max_turns)"),
        ):
            with self.subTest(model_answer):
                self.answer_with(any=model_answer)

                code, out = self.run_main("--model", "haiku", "--runs", "1")

                self.assertEqual(code, glean_eval.EXIT_FAILED)
                self.assertIn(f"haiku run 1: error: {said}", out)

    def test_each_run_reads_the_day_from_its_input_in_an_empty_folder_away_from_the_real_setup(self) -> None:
        self.answer_with(any=answer())

        self.run_main("--model", "haiku", "--runs", "1")

        (call,) = self.calls()
        self.assertEqual(Path(call["cwd"]).resolve(), (self.root / "sandbox" / "work").resolve())
        self.assertEqual(call["files"], [])
        self.assertEqual(Path(call["m2b_home"]).resolve(), (self.root / "sandbox" / "home").resolve())
        self.assertEqual(call["argv"][1], glean.instruction())
        self.assertIn("Dana runs IT at Northwind", json.loads(call["stdin"])["sessions"][0]["prompts"][5])

    def test_the_real_store_is_refused(self) -> None:
        real_config = Path(self.environ["HOME"]) / ".config" / "m2b" / "config.json"
        real_config.parent.mkdir(parents=True)
        store = {"backend": "folder", "path": str(self.root)}
        real_config.write_text(json.dumps({"version": 1, "machine_id": "m", "store": store}), encoding="utf-8")
        self.answer_with(any=answer())

        code, out = self.run_main("--work-root", str(self.root / "sandbox"))

        self.assertEqual(code, glean_eval.EXIT_REFUSED, out)
        self.assertFalse(self.log.exists())

    def test_a_claude_that_cannot_be_started_is_reported_for_each_run(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = glean_eval.main(
                ["--model", "haiku", "--runs", "1", "--work-root", str(self.root / "sandbox"), "--claude", "/no/such"],
                self.environ,
            )

        self.assertEqual(code, glean_eval.EXIT_FAILED, out.getvalue())
        self.assertIn("haiku run 1: error: the command could not be started", out.getvalue())

    def test_a_number_of_runs_below_one_is_a_usage_error(self) -> None:
        code, out = self.run_main("--runs", "0")

        self.assertEqual(code, glean_eval.EXIT_USAGE, out)


class ReplayTest(WithFakeClaude):
    TODAY = datetime.date(2026, 3, 5)

    def setUp(self) -> None:
        super().setUp()
        self.projects = self.root / "claude" / "projects"
        self.environ["CLAUDE_CONFIG_DIR"] = str(self.root / "claude")
        self.out = self.root / "private" / "replay.md"
        self.transcript("first", datetime.date(2026, 3, 4), "Dana runs IT at Northwind.", "run the tests")
        self.transcript("second", self.TODAY, "the build is red again")
        said = {"kind": "person", "text": "Dana leads IT at Northwind.", "quote": "Dana runs IT at Northwind"}
        self.answer_with(any=answer({**said, "session": 1}))

    def transcript(self, name: str, day: datetime.date, *prompts: str) -> None:
        """A session at noon UTC, which is that day wherever this test runs."""
        folder = self.projects / f"-home-alex-{name}"
        folder.mkdir(parents=True, exist_ok=True)
        records = [
            {
                "type": "user",
                "timestamp": f"{day}T12:{minute:02d}:00Z",
                "cwd": f"/home/alex/{name}",
                "entrypoint": "cli",
                "promptSource": "typed",
                "origin": {"kind": "human"},
                "message": {"role": "user", "content": prompt},
            }
            for minute, prompt in enumerate(prompts)
        ]
        (folder / f"{name}.jsonl").write_text("".join(json.dumps(record) + "\n" for record in records))

    def replay(self, *arguments: str) -> tuple[int, str]:
        return self.run_main("--replay", "3", "--out", str(self.out), "--today", str(self.TODAY), *arguments)

    def test_the_proposals_of_each_day_go_to_the_file_with_the_words_they_stand_on(self) -> None:
        code, out = self.replay()

        self.assertEqual(code, glean_eval.EXIT_PASSED, out)
        page = self.out.read_text(encoding="utf-8")
        self.assertIn("## Wednesday 2026-03-04", page)
        self.assertIn("1. **person**: Dana leads IT at Northwind.", page)
        self.assertIn("you typed: “Dana runs IT at Northwind”", page)
        self.assertIn("in /home/alex/first", page)
        self.assertIn("not your memory and not your captures", page)

    def test_only_counts_are_printed(self) -> None:
        _, out = self.replay()

        self.assertEqual(
            out.splitlines(),
            [
                "2026-03-03: no prompts",
                "2026-03-04: 2 prompts in 1 sessions (left out: 0 pasted blocks, 0 sent by others, 0 suggested, "
                "0 unmarked, 0 transcripts not read), 1 proposals: 1 person, 0 agreement, 0 commitment, 0 personal; "
                "left out by code: 0 not quoted, 0 not in the form",
                "2026-03-05: 1 prompts in 1 sessions (left out: 0 pasted blocks, 0 sent by others, 0 suggested, "
                "0 unmarked, 0 transcripts not read), 0 proposals: 0 person, 0 agreement, 0 commitment, 0 personal; "
                "left out by code: 1 not quoted, 0 not in the form",
                f"glean-eval: 1 proposals from 3 days written to {self.out}",
            ],
        )

    def test_a_proposal_whose_quote_was_not_typed_that_day_is_not_in_the_file(self) -> None:
        self.replay()

        page = self.out.read_text(encoding="utf-8")
        self.assertEqual(page.count("Dana leads IT"), 1)

    def test_the_model_is_asked_once_for_each_day_with_prompts_and_gets_no_memory(self) -> None:
        self.replay()

        calls = self.calls()
        self.assertEqual(len(calls), 2)
        self.assertEqual({json.loads(call["stdin"])["memory"] for call in calls}, {""})
        self.assertEqual({call["argv"][call["argv"].index("--model") + 1] for call in calls}, {"haiku"})

    def test_the_file_is_readable_by_its_owner_only(self) -> None:
        self.out.parent.mkdir()
        self.out.write_text("an older replay", encoding="utf-8")
        self.out.chmod(0o644)

        self.replay()

        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o600)
        self.assertNotIn("an older replay", self.out.read_text(encoding="utf-8"))

    def test_an_older_file_is_closed_to_others_before_anything_is_written_to_it(self) -> None:
        self.out.parent.mkdir()
        self.out.write_text("an older replay", encoding="utf-8")
        self.out.chmod(0o644)

        descriptor = glean_eval.open_private(self.out)

        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o600)
        self.assertEqual(self.out.read_text(encoding="utf-8"), "an older replay")
        glean_eval.write_private(descriptor, "new")
        self.assertEqual(self.out.read_text(encoding="utf-8"), "new")

    def test_half_a_character_in_the_page_does_not_lose_the_page(self) -> None:
        descriptor = glean_eval.open_private(self.out)

        glean_eval.write_private(descriptor, "half \ud83d of an emoji")

        self.assertEqual(self.out.read_text(encoding="utf-8"), "half ? of an emoji")

    def test_a_file_that_cannot_be_written_is_refused_before_a_model_is_asked(self) -> None:
        self.out.mkdir(parents=True)

        code, out = self.replay()

        self.assertEqual(code, glean_eval.EXIT_USAGE, out)
        self.assertIn(f"glean-eval: cannot write {self.out}", out)
        self.assertFalse(self.log.exists())

    def test_a_day_without_an_answer_is_named_without_what_the_command_said(self) -> None:
        self.answer_with(any="crash")

        code, out = self.replay()

        self.assertEqual(code, glean_eval.EXIT_FAILED)
        self.assertIn("no answer: exit 1 without a result", out)
        self.assertNotIn("boom", out)
        self.assertIn("The command said: boom", self.out.read_text(encoding="utf-8"))

    def test_a_file_inside_the_repository_is_refused(self) -> None:
        inside = REPO_ROOT / "docs" / "notes" / "replay.md"

        code, out = self.run_main("--replay", "3", "--out", str(inside), "--today", str(self.TODAY))

        self.assertEqual(code, glean_eval.EXIT_REFUSED, out)
        self.assertFalse(self.log.exists())
        self.assertFalse(inside.exists())

    def test_a_file_inside_the_repository_is_refused_whatever_the_path_is_spelled_like(self) -> None:
        self.addCleanup((REPO_ROOT / "docs" / "replay.md").unlink, missing_ok=True)
        link = self.root / "elsewhere"
        link.symlink_to(REPO_ROOT / "docs", target_is_directory=True)
        spellings = [link / "replay.md", REPO_ROOT / "docs" / ".." / "docs" / "replay.md"]
        shouted = Path(str(REPO_ROOT).upper())
        if shouted.exists():  # a file system that does not tell upper case from lower case
            spellings.append(shouted / "docs" / "replay.md")
        for inside in spellings:
            with self.subTest(inside=inside):
                code, out = self.run_main("--replay", "3", "--out", str(inside), "--today", str(self.TODAY))

                self.assertEqual(code, glean_eval.EXIT_REFUSED, out)
                self.assertFalse((REPO_ROOT / "docs" / "replay.md").exists())
        self.assertFalse(self.log.exists())

    def test_replay_and_out_go_together_and_one_model_answers(self) -> None:
        for arguments in (
            ("--replay", "3"),
            ("--out", str(self.out)),
            ("--replay", "0", "--out", str(self.out)),
            ("--replay", "3", "--out", str(self.out), "--model", "haiku", "--model", "sonnet"),
        ):
            with self.subTest(arguments=arguments):
                code, out = self.run_main(*arguments)

                self.assertEqual(code, glean_eval.EXIT_USAGE, out)
        self.assertFalse(self.log.exists())

    def test_without_a_transcripts_folder_nothing_is_written(self) -> None:
        self.environ["CLAUDE_CONFIG_DIR"] = str(self.root / "nowhere")

        code, out = self.replay()

        self.assertEqual(code, glean_eval.EXIT_FAILED)
        self.assertIn("no Claude Code transcripts", out)
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
