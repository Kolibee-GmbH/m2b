"""A session hands in a proposal: what the check at the call takes, what it refuses and what it writes."""

from __future__ import annotations

import datetime
import io
import json
from pathlib import Path
from typing import Any
from unittest import mock

import test_commands
from m2b import cli, folders_left_out, handed_in, session_remotes
from m2b.commands import proposals as proposals_commands
from m2b.config.machine import load_machine_config
from m2b.config.profile import save_profile
from m2b.glean import AGENT, PASTED, TOOL, TYPED
from m2b.handed_in import Given, RefusedError
from m2b.prompt_hook import CURATION_RUN_VARIABLE
from m2b.store.guard import DatalessGuard
from test_session_places import SESSION, answer, call, numbered, result, thought
from test_sessions import at, pasted_block, typed

NOW = datetime.datetime(2026, 3, 4, 18, tzinfo=datetime.timezone.utc)
QUOTE = "Dana Whitfield runs purchasing at Acme"
TEXT = "Dana Whitfield runs purchasing at Acme."
DANA = {"kind": "person", "text": TEXT, "quote": QUOTE, "session": SESSION}


class HandedInFixture(test_commands.CommandTest):
    def setUp(self) -> None:
        super().setUp()
        self.set_up(calendar="none", sessions={"propose": True})
        self.leaving_out()
        self.shed = Path(self._temp.name).resolve() / "projects" / "shed"
        self.shed.mkdir(parents=True)
        self.claude = Path(self._temp.name) / "claude"
        self.environ["CLAUDE_CONFIG_DIR"] = str(self.claude)

    def leaving_out(self, **left_out: Any) -> None:
        save_profile(self.store, {"version": 2, "owner": "Alex", "language": "en", "worklog_leave_out": left_out})

    def session(self, *records: dict[str, Any], session: str = SESSION, project: str = "-shed") -> Path:
        """A transcript of records that worked in the shed, unless a record names another folder."""
        path = self.claude / "projects" / project / f"{session}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        written = [
            record if record.get("cwd") != "/home/alex/projects/shed" else {**record, "cwd": str(self.shed)}
            for record in records
        ]
        path.write_text("".join(json.dumps(record) + "\n" for record in written), encoding="utf-8")
        return path

    def read_notes(self, text: str = QUOTE, tool: str = "Read", **given: Any) -> list[dict[str, Any]]:
        """A call of a tool and its result ``text``, as the session's records."""
        given = given or {"file_path": str(self.shed / "notes.md")}
        returned = numbered(text) if tool == "Read" else text
        return [call("c1", tool, given, at(9)), result("c1", returned, at(9, 1))]

    def hand_in(self, **changes: Any) -> handed_in.Outcome:
        config = load_machine_config(self.machine)
        given = handed_in.parse({**DANA, **changes})
        return handed_in.hand_in(self.store, config, self.machine, self.environ, given, NOW)

    def refused(self, **changes: Any) -> str:
        with self.assertRaises(RefusedError) as caught:
            self.hand_in(**changes)
        self.assertEqual(self.files(), [], "a refused proposal writes nothing")
        return str(caught.exception)

    def files(self) -> list[str]:
        folder = self.store_root / handed_in.FOLDER
        return sorted(path.name for path in folder.iterdir()) if folder.is_dir() else []

    def file(self) -> dict[str, Any]:
        (name,) = self.files()
        written: dict[str, Any] = json.loads((self.store_root / handed_in.FOLDER / name).read_text(encoding="utf-8"))
        return written


class WhatIsWrittenTest(HandedInFixture):
    def test_a_quote_from_a_tools_result_gives_one_file_with_the_tool_and_no_folder(self) -> None:
        """Covers: B177"""
        self.session(*self.read_notes(f"Call notes\n\n{QUOTE}\nand signs every order."))

        outcome = self.hand_in(due="2026-03-09")

        self.assertTrue(outcome.is_new)
        self.assertEqual(
            self.file(),
            {
                "format": 1,
                "kind": "person",
                "text": TEXT,
                "quote": QUOTE,
                "due": "2026-03-09",
                "session": SESSION,
                "day": "2026-03-04",
                "source": TOOL,
                "tool": "Read",
                "at": NOW.isoformat(),
            },
        )
        (name,) = self.files()
        self.assertRegex(name, rf"^{SESSION}\.[0-9a-f]{{12}}\.json$")
        self.assertNotIn(str(self.shed), json.dumps(self.file()))

    def test_the_day_is_the_day_of_the_text_where_the_person_is(self) -> None:
        """Covers: B177"""
        note = str(self.shed / "n.md")
        self.session(call("c1", "Read", {"file_path": note}, at(23, 40)), result("c1", numbered(QUOTE), at(23, 45)))
        an_hour_east = datetime.datetime(2026, 3, 5, 0, 50, tzinfo=datetime.timezone(datetime.timedelta(hours=1)))
        config = load_machine_config(self.machine)
        outcome = handed_in.hand_in(self.store, config, self.machine, self.environ, handed_in.parse(DANA), an_hour_east)
        self.assertEqual(outcome.proposal.day, datetime.date(2026, 3, 5))

    def test_the_same_call_twice_gives_one_file_and_says_so(self) -> None:
        """Covers: B177"""
        self.session(*self.read_notes())
        self.assertTrue(self.hand_in().is_new)
        self.assertFalse(self.hand_in().is_new)
        self.assertEqual(len(self.files()), 1)

    def test_the_same_words_under_another_text_or_kind_are_refused_with_what_to_do(self) -> None:
        """Covers: B177"""
        line = "Dana runs finance and Sam runs IT"
        self.session(*self.read_notes(line))
        self.hand_in(quote=line, text="Dana runs finance.")
        for other in ({"text": "Sam runs IT."}, {"text": "Dana runs finance.", "kind": "agreement"}):
            with self.subTest(other=other), self.assertRaisesRegex(RefusedError, "quote the words that name this one"):
                self.hand_in(quote=line, **other)
        self.assertFalse(self.hand_in(quote=line, text="dana  runs FINANCE.").is_new)
        self.assertEqual(len(self.files()), 1)

    def test_a_file_under_the_proposals_name_that_cannot_be_read_is_could_not_look(self) -> None:
        """Covers: B177"""
        self.session(*self.read_notes())
        self.hand_in()
        (name,) = self.files()
        (self.store_root / handed_in.FOLDER / name).write_text('{"kind": "pers', encoding="utf-8")
        with self.assertRaisesRegex(RefusedError, "could not look whether this proposal was handed in before"):
            self.hand_in()

    def test_the_eleventh_proposal_of_a_session_that_waits_is_refused(self) -> None:
        """Covers: B177"""
        lines = [f"Person number {number} runs team {number}" for number in range(11)]
        self.session(*self.read_notes("\n".join(lines)))
        for line in lines[: handed_in.WAITING_PER_SESSION]:
            self.hand_in(quote=line, text=f"{line}.")
        with self.assertRaisesRegex(RefusedError, "10 proposals of this session wait"):
            self.hand_in(quote=lines[10], text=f"{lines[10]}.")
        self.assertFalse(self.hand_in(quote=lines[0], text=f"{lines[0]}.").is_new)
        self.assertEqual(len(self.files()), handed_in.WAITING_PER_SESSION)

    def test_a_folder_of_waiting_proposals_that_is_not_downloaded_refuses(self) -> None:
        """Covers: B177"""
        self.session(*self.read_notes())
        (self.store_root / handed_in.FOLDER).mkdir(parents=True)
        folder = Path(handed_in.FOLDER).name
        not_downloaded = mock.patch.object(
            DatalessGuard, "is_evicted", side_effect=lambda path: Path(path).name == folder
        )
        with not_downloaded, self.assertRaisesRegex(RefusedError, "could not look how many"):
            self.hand_in()

    def test_a_waiting_proposal_that_is_not_downloaded_counts_by_its_name(self) -> None:
        """Covers: B177"""
        lines = [f"Person number {number} runs team {number}" for number in range(11)]
        self.session(*self.read_notes("\n".join(lines)))
        for line in lines[: handed_in.WAITING_PER_SESSION]:
            self.hand_in(quote=line, text=f"{line}.")
        evicted = mock.patch.object(
            DatalessGuard, "is_evicted", side_effect=lambda path: Path(path).parent.name == "handed-in"
        )
        with evicted, self.assertRaisesRegex(RefusedError, "10 proposals of this session wait"):
            self.hand_in(quote=lines[10], text=f"{lines[10]}.")

    def test_the_proposals_file_is_never_touched(self) -> None:
        """Covers: B177"""
        proposals_file = self.store_root / "state" / "core" / "proposals.json"
        proposals_file.parent.mkdir(parents=True, exist_ok=True)
        proposals_file.write_text('{"format": 1, "proposals": {}}', encoding="utf-8")
        self.session(*self.read_notes())
        self.hand_in()
        self.assertEqual(proposals_file.read_text(encoding="utf-8"), '{"format": 1, "proposals": {}}')


class WhereTheQuoteStandsTest(HandedInFixture):
    def source_of(self, *records: dict[str, Any], **changes: Any) -> tuple[str, str | None]:
        self.session(*records)
        proposal = self.hand_in(**changes).proposal
        return proposal.source, proposal.tool

    def test_typed_wins_over_pasted_over_a_tools_result_over_an_answer(self) -> None:
        """Covers: B175"""
        said = typed(f"note that {QUOTE}", at(11))
        pasted = typed(f"see {pasted_block(QUOTE)}", at(10, 30))
        answered = answer(f"I see that {QUOTE}.", at(10))
        read = self.read_notes()
        self.assertEqual(self.source_of(*read, answered, pasted, said), (TYPED, None))
        self.assertEqual(self.source_of(*read, answered, pasted), (PASTED, None))
        self.assertEqual(self.source_of(*read, answered), (TOOL, "Read"))
        self.assertEqual(self.source_of(answered), (AGENT, None))

    def test_of_two_texts_of_the_same_source_the_earlier_gives_the_day(self) -> None:
        """Covers: B175"""
        yesterday = datetime.datetime(2026, 3, 3, 9, tzinfo=datetime.timezone.utc)
        self.session(typed(f"first: {QUOTE}", yesterday), typed(f"again: {QUOTE}", at(9)))
        self.assertEqual(self.hand_in().proposal.day, datetime.date(2026, 3, 3))

    def test_the_quote_stands_as_whole_words(self) -> None:
        """Covers: B175"""
        self.session(typed("I am unhappy with them and Dana Whitfield runs purchasing at Acme now", at(9)))
        for cut_out in ("happy with them", "na Whitfield runs purchasing", "Dana Whitfield ru"):
            with self.subTest(cut_out=cut_out):
                self.assertIn("do not stand in this session", self.refused(quote=cut_out, text="They are happy."))
        self.assertTrue(self.hand_in(quote="unhappy with them", text="They are unhappy.").is_new)

    def test_what_claude_wrote_before_a_result_gave_it_back_is_claudes_own_text(self) -> None:
        """Covers: B175"""
        shed = str(self.shed)
        written_then_read = [
            call("c1", "Write", {"file_path": f"{shed}/n.md", "content": QUOTE}, at(9)),
            result("c1", "File created", at(9, 1)),
            call("c2", "Read", {"file_path": f"{shed}/n.md"}, at(9, 2)),
            result("c2", numbered(QUOTE), at(9, 3)),
        ]
        said_then_read = [
            answer(f"I think {QUOTE}.", at(9)),
            call("c2", "Read", {"file_path": f"{shed}/n.md"}, at(9, 2)),
            result("c2", numbered(QUOTE), at(9, 3)),
        ]
        for records in (written_then_read, said_then_read):
            with self.subTest(records=str(records)[:50]):
                self.assertEqual(self.source_of(*records), (AGENT, None))

    def test_what_claude_wrote_into_a_call_without_a_text_of_its_own_still_counts_as_written(self) -> None:
        """Covers: B175"""
        shed = str(self.shed)
        read_back = [
            call("c2", "Read", {"file_path": f"{shed}/n.md"}, at(9, 2)),
            result("c2", numbered(QUOTE), at(9, 3)),
        ]
        through_a_subagent = [
            call("c1", "Agent", {"prompt": f"Write this to {shed}/n.md: {QUOTE}"}, at(9)),
            result("c1", [{"type": "text", "text": "done"}], at(9, 1)),
        ]
        without_output = [
            call("c1", "Bash", {"command": f"echo '{QUOTE}' > {shed}/n.md"}, at(9)),
            result("c1", "", at(9, 1)),
        ]
        for written in (through_a_subagent, without_output):
            with self.subTest(written=str(written)[:50]):
                self.assertEqual(self.source_of(*written, *read_back), (AGENT, None))
        self.assertEqual(self.source_of(*read_back, *without_output), (TOOL, "Read"))

    def test_a_quote_that_ends_inside_a_word_does_not_stand(self) -> None:
        """Covers: B175"""
        inside_a_word = ("Acme\u0301 now", "Acme\u200dX now", "Acme_corp now", "Acme2 now")
        for ending in inside_a_word:
            with self.subTest(ending=ending.encode("unicode_escape")):
                self.session(typed(f"Dana Whitfield runs purchasing at {ending}", at(9)))
                self.assertIn("do not stand in this session", self.refused())
        self.session(typed(f"so: {QUOTE}, and (as said) {QUOTE}.", at(9)))
        self.assertTrue(self.hand_in().is_new)

    def test_a_quote_joined_from_two_texts_stands_nowhere(self) -> None:
        """Covers: B175"""
        self.session(*self.read_notes("Dana Whitfield runs"), answer("purchasing at Acme", at(10)))
        self.assertIn("do not stand in this session", self.refused())

    def test_a_quote_across_two_numbered_lines_and_one_in_a_json_string_stand(self) -> None:
        """Covers: B175"""
        self.assertEqual(self.source_of(*self.read_notes("Dana Whitfield runs\npurchasing at Acme")), (TOOL, "Read"))
        mail = json.dumps({"subject": "x", "body": "Hello,\nDana Whitfield runs purchasing\nat Acme now."})
        records = self.read_notes(mail, "mcp__mail__get_message", id="m1")
        self.assertEqual(self.source_of(*records), (TOOL, "mcp__mail__get_message"))

    def test_a_result_that_gives_back_the_input_of_its_call_is_claudes_own_text(self) -> None:
        """Covers: B175"""
        records = self.read_notes(QUOTE, "Bash", command=f"echo {QUOTE}")
        self.assertEqual(self.source_of(*records), (AGENT, None))

    def test_what_stands_only_where_no_place_is_stands_nowhere(self) -> None:
        """Covers: B175"""
        nowhere: list[list[dict[str, Any]]] = [
            [call("c1", "Bash", {"command": f"grep '{QUOTE}' notes.md"}, at(9))],
            self.read_notes(QUOTE, "mcp__m2b__search", terms=["Dana"]),
            self.read_notes(f"memory/people.md:3: {QUOTE}", "Bash", command='m2b search --json -- "Dana"'),
            self.read_notes(f"memory/people.md:3: {QUOTE}", "Bash", command="~/.local/bin/m2b-worklog facts"),
            [thought(QUOTE, at(9))],
            [answer(QUOTE, at(9), isSidechain=True)],
            [typed(QUOTE, at(9), origin=None, promptSource="sdk")],
            [typed(QUOTE, at(9), isMeta=True)],
            self.read_notes(f"<system-reminder>{QUOTE}</system-reminder>", "Bash", command="cat x"),
        ]
        for records in nowhere:
            with self.subTest(records=str(records)[:60]):
                self.session(typed("hello there Sam", at(8)), *records)
                self.assertIn("do not stand in this session", self.refused())

    def test_a_result_of_a_command_that_only_names_m2b_is_a_place(self) -> None:
        """Covers: B175"""
        records = self.read_notes(QUOTE, "Bash", command="cat notes-about-m2b.md")
        self.assertEqual(self.source_of(*records), (TOOL, "Bash"))

    def test_m2b_anywhere_in_a_command_and_a_call_that_names_the_store_give_back_the_memory(self) -> None:
        """Covers: B175"""
        memory = f"memory/people.md:3: {QUOTE}"
        commands = (
            "env X=1 m2b search Dana",
            "sh -c 'm2b search Dana'",
            "cd /tmp && m2b search Dana",
            "echo Dana | xargs m2b search",
            '"m2b" search Dana',
            "(m2b search Dana)",
            f"cat {self.store_root}/memory/people.md",
        )
        for command in commands:
            with self.subTest(command=command):
                self.session(typed("hello there Sam", at(8)), *self.read_notes(memory, "Bash", command=command))
                self.assertIn("do not stand in this session", self.refused())
        read_from_the_store = self.read_notes(QUOTE, "Read", file_path=f"{self.store_root}/memory/people.md")
        self.session(typed("hello there Sam", at(8)), *read_from_the_store)
        self.assertIn("do not stand in this session", self.refused())

    def test_a_refusal_never_repeats_the_quote_or_the_text(self) -> None:
        """Covers: B174"""
        self.session(typed("hello there Sam", at(8)))
        refusal = self.refused(quote="Sam Ortega takes over", text="Sam Ortega takes over the rollout.")
        self.assertNotIn("Ortega", refusal)


class NoCredentialTest(HandedInFixture):
    def test_a_quote_whose_value_is_named_right_before_it_is_refused(self) -> None:
        """Covers: B175"""
        notes = "notes: the db password is hunter2 and the replica runs at night"
        self.session(*self.read_notes(notes, "Bash", command="cat x"))
        self.assertIn(
            "credential", self.refused(quote="hunter2 and the replica runs", text="The replica runs at night.")
        )

    def test_a_credential_at_any_spot_the_quote_stands_at_refuses_it(self) -> None:
        """Covers: B175"""
        twice = "hunter2 and the replica runs at noon. the db password is hunter2 and the replica runs at night"
        parted = "the db password is <system-reminder>x</system-reminder> hunter2 and the replica runs"
        two_pastes = f"look {pasted_block('the api key is', 'a1')}{pasted_block('hunter2 and the replica runs', 'b2')}"
        in_json = json.dumps({"service": "db", "password": "hunter2 and the replica runs"})
        sessions = (
            self.read_notes(twice, "Bash", command="cat x"),
            self.read_notes(parted, "Bash", command="cat x"),
            [typed(two_pastes, at(9))],
            self.read_notes(in_json, "Bash", command="cat x"),
            [
                *self.read_notes("the password is hunter2 and the replica runs", "Bash", command="cat x"),
                answer("hunter2 and the replica runs fine", at(10)),
            ],
        )
        for records in sessions:
            with self.subTest(records=str(records)[-60:]):
                self.session(*records)
                refusal = self.refused(quote="hunter2 and the replica runs", text="The replica runs.")
                self.assertIn("credential", refusal)

    def test_a_credential_that_shows_only_with_what_follows_the_quote_refuses_it(self) -> None:
        """Covers: B175"""
        address = "DATABASE at postgres://app:Sup3rS3cretPw@db.internal:5432/main for the app"
        self.session(*self.read_notes(address, "Bash", command="cat x"))
        refusal = self.refused(quote="DATABASE at postgres://app:Sup3rS3cretPw", text="The database is at db.internal.")
        self.assertIn("credential", refusal)

    def test_a_text_that_begins_with_a_credentials_value_gives_no_quote_at_all(self) -> None:
        """Covers: B175"""
        named_by = (
            {"passphrase": "correct horse battery staple and more"},
            {"password": {"value": "correct horse battery staple and more"}},
            {"env": [{"name": "DB_PASSWORD", "value": "correct horse battery staple and more"}]},
            [["DB_PASSWORD", "correct horse battery staple and more"]],
        )
        for returned in named_by:
            with self.subTest(returned=str(returned)[:40]):
                self.session(*self.read_notes(json.dumps(returned), "Bash", command="cat x"))
                self.assertIn("credential", self.refused(quote="horse battery staple", text="A staple."))

    def test_the_same_words_beside_the_quote_do_not_answer_for_a_spot_that_is_a_credential(self) -> None:
        """Covers: B175"""
        self.session(*self.read_notes("password: hunter2 hunter2 hunter2 hunter2", "Bash", command="cat x"))
        self.assertIn("credential", self.refused(quote="hunter2 hunter2 hunter2", text="Hunter runs."))

    def test_a_name_at_the_end_of_the_text_part_or_answer_before_is_seen(self) -> None:
        """Covers: B175"""
        value = "hunter2 and the replica runs"
        two_parts = [{"type": "text", "text": "the db password is"}, {"type": "text", "text": f"{value} fine"}]
        records = (
            [call("c1", "mcp__x__get", {"id": "1"}, at(9)), result("c1", two_parts, at(9, 1))],
            [answer("the db password is", at(9)), answer(f"{value} fine", at(9, 1))],
        )
        for session in records:
            with self.subTest(session=str(session)[:40]):
                self.session(*session)
                self.assertIn("credential", self.refused(quote=value, text="The replica runs."))

    def test_a_value_pasted_right_behind_its_typed_name_is_refused(self) -> None:
        """Covers: B175"""
        self.session(typed(f"the api key is {pasted_block('abc123 and it runs out in May')}", at(9)))
        self.assertIn("credential", self.refused(quote="abc123 and it runs out", text="The key runs out in May."))

    def test_a_text_or_a_quote_that_holds_a_credential_itself_is_refused_by_its_form(self) -> None:
        """Covers: B174"""
        for changes in ({"text": "The password is hunter2."}, {"quote": "the password is hunter2 for now"}):
            with self.subTest(changes=changes), self.assertRaisesRegex(RefusedError, "credential"):
                handed_in.parse({**DANA, **changes})


class TheSessionTest(HandedInFixture):
    def test_a_session_without_a_transcript_on_this_machine_is_refused(self) -> None:
        """Covers: B175"""
        self.assertIn("not on this machine", self.refused())

    def test_two_transcripts_with_the_sessions_id_are_refused(self) -> None:
        """Covers: B175"""
        self.session(*self.read_notes(), project="-a")
        self.session(*self.read_notes(), project="-b")
        self.assertIn("more than one transcript", self.refused())

    def test_a_session_that_names_no_folder_is_refused(self) -> None:
        """Covers: B176"""
        records = [{key: value for key, value in record.items() if key != "cwd"} for record in self.read_notes()]
        self.session(*records)
        self.assertIn("cannot be told whole", self.refused())

    def test_a_session_that_named_more_paths_than_are_kept_is_refused(self) -> None:
        """Covers: B176"""
        many = call("c9", "mcp__files__read", {"paths": [str(self.shed / f"{n}.md") for n in range(5001)]}, at(8))
        self.session(many, *self.read_notes())
        self.assertIn("cannot be told whole", self.refused())

    def test_a_session_whose_subagents_transcript_cannot_be_read_is_refused(self) -> None:
        """Covers: B176"""
        transcript = self.session(*self.read_notes())
        (transcript.parent / SESSION / "subagents" / "agent-a1.jsonl").mkdir(parents=True)
        self.assertIn("cannot be told whole", self.refused())


class WorkLeftOutTest(HandedInFixture):
    def test_a_session_that_worked_in_a_folder_the_profile_leaves_out_hands_nothing_in(self) -> None:
        """Covers: B176"""
        customers = self.home / "customers"
        (customers / "acme").mkdir(parents=True)
        self.leaving_out(path_under=["~/customers"])
        ways_in = (
            [answer("ok", at(8), cwd=str(customers / "acme"))],
            [call("c5", "Read", {"file_path": str(customers / "acme" / "contract.md")}, at(8))],
            [call("c5", "Bash", {"command": f"cd {customers}/acme && cat contract.md"}, at(8))],
            [call("c5", "Bash", {"command": "cat ../../home/customers/acme/x.md"}, at(8))],
        )
        for records in ways_in:
            with self.subTest(records=str(records)[-70:]):
                self.session(*self.read_notes(), *records)
                self.assertIn("a folder m2b does not read", self.refused())
        self.session(*self.read_notes())
        self.assertTrue(self.hand_in().is_new)

    def test_a_session_in_a_folder_without_the_distillate_hands_nothing_in(self) -> None:
        """Covers: B176"""
        self.set_up(calendar="none", sessions={"propose": True}, distillate={"skip_under": [str(self.shed)]})
        self.session(*self.read_notes())
        self.assertIn("a folder m2b does not read", self.refused())

    def test_a_subagent_that_worked_in_a_folder_left_out_keeps_the_session_from_handing_in(self) -> None:
        """Covers: B176"""
        customers = self.home / "customers"
        customers.mkdir(parents=True)
        self.leaving_out(path_under=["~/customers"])
        transcript = self.session(*self.read_notes())
        subagents = transcript.parent / SESSION / "subagents"
        subagents.mkdir(parents=True)
        of_a_subagent = call("c7", "Read", {"file_path": "x.md"}, at(8), cwd=str(customers))
        (subagents / "agent-a1.jsonl").write_text(json.dumps(of_a_subagent) + "\n", encoding="utf-8")
        self.assertIn("a folder m2b does not read", self.refused())

    def test_a_repository_left_out_by_its_remote_is_asked_with_the_short_time_for_git(self) -> None:
        """Covers: B176"""
        self.leaving_out(git_remote_contains=["globex-ag/"])
        self.session(*self.read_notes())
        asked: list[float] = []

        def remotes(folder: Path, git: str = "git", timeout: float = 0.0, **_: Any) -> frozenset[str]:
            asked.append(timeout)
            return frozenset({"https://git.example/globex-ag/portal.git"})

        with (
            mock.patch.object(folders_left_out, "usable_git", return_value="git") as usable_git,
            mock.patch.object(session_remotes, "remotes_in", remotes),
        ):
            self.assertIn("a folder m2b does not read", self.refused())
        self.assertEqual(set(asked), {handed_in.GIT_SECONDS})
        self.assertEqual(usable_git.call_args.kwargs, {"timeout": handed_in.GIT_SECONDS})

    def test_a_look_at_where_the_session_worked_that_takes_too_long_refuses(self) -> None:
        """Covers: B176"""
        self.session(*self.read_notes())
        with mock.patch.object(handed_in, "LOOK_SECONDS", -1.0):
            self.assertIn("cannot be told whole", self.refused())

    def test_a_profile_that_cannot_be_read_is_could_not_look_not_a_folder_left_out(self) -> None:
        """Covers: B176"""
        self.session(*self.read_notes())
        with mock.patch.object(DatalessGuard, "is_evicted", side_effect=lambda path: Path(path).name == "profile.json"):
            self.assertIn("could not look which work m2b leaves out", self.refused())
        (self.store_root / "profile.json").write_text("{not json", encoding="utf-8")
        self.assertIn("could not look which work m2b leaves out", self.refused())
        (self.store_root / "profile.json").unlink()
        self.assertIn("could not look which work m2b leaves out", self.refused())


class TheSwitchTest(HandedInFixture):
    def test_without_the_switch_nothing_is_handed_in(self) -> None:
        """Covers: B173"""
        self.set_up(calendar="none")
        self.session(*self.read_notes())
        self.assertIn("handing in is off on this machine", self.refused())

    def test_a_curation_run_hands_nothing_in(self) -> None:
        """Covers: B173"""
        self.session(*self.read_notes())
        self.environ[CURATION_RUN_VARIABLE] = "1"
        self.assertIn("a curation run hands nothing in", self.refused())
        self.environ[CURATION_RUN_VARIABLE] = "0"
        self.assertTrue(self.hand_in().is_new)


class TheFormTest(HandedInFixture):
    def test_what_is_not_in_the_form_is_refused_with_the_part_named(self) -> None:
        """Covers: B174"""
        not_in_the_form = {
            "kind": ({"kind": "todo"}, {"kind": None}),
            "text": ({"text": ""}, {"text": "x" * 301}, {"text": 7}),
            "quote": ({"quote": "two words"}, {"quote": "word " * 120}, {"quote": None}),
            "hides or reorders": (
                {"text": "Dana \u202eruns it."},
                {"quote": "Dana runs \u2066purchasing at Acme"},
                {"text": "Dana \x1b[8mhidden\x1b[0m runs it."},
                {"quote": "Dana \x07runs purchasing at Acme"},
            ),
            "session": ({"session": "session-1"}, {"session": "../x"}, {"session": None}),
            "due": ({"due": "tomorrow"}, {"due": "20260309"}, {"due": 7}),
        }
        for part, cases in not_in_the_form.items():
            for changes in cases:
                with self.subTest(changes=str(changes)[:40]), self.assertRaisesRegex(RefusedError, part):
                    handed_in.parse({**DANA, **changes})
        with self.assertRaisesRegex(RefusedError, "JSON object"):
            handed_in.parse([DANA])

    def test_the_text_and_the_quote_are_taken_as_one_line(self) -> None:
        """Covers: B174"""
        given = handed_in.parse(
            {**DANA, "text": "Dana  runs\npurchasing.", "quote": "Dana Whitfield\n runs  purchasing", "due": ""}
        )
        self.assertEqual(
            given, Given("person", "Dana runs purchasing.", "Dana Whitfield runs purchasing", SESSION, None)
        )

    def test_a_character_that_draws_nothing_is_refused_and_the_selector_of_an_emoji_is_not(self) -> None:
        """Covers: B174"""
        for hidden in ("\u200e", "\u200f", "\u061c", "\u00ad", "\u3164", "\U000e0100"):
            with self.subTest(hidden=hidden.encode("unicode_escape")), self.assertRaisesRegex(RefusedError, "hides"):
                handed_in.parse({**DANA, "text": f"Dana{hidden} runs purchasing."})
        self.assertEqual(handed_in.parse({**DANA, "text": "Dana \u2764\ufe0f tea."}).text, "Dana \u2764\ufe0f tea.")


class TheCommandTest(HandedInFixture):
    def add(self, given: object, *arguments: str) -> tuple[int, str, str]:
        """Runs the command with ``given`` on standard input: bytes or a text as they are, anything else as JSON."""
        written = given if isinstance(given, (bytes, str)) else json.dumps(given)
        as_bytes = written if isinstance(written, bytes) else written.encode("utf-8")
        with mock.patch("sys.stdin", io.TextIOWrapper(io.BytesIO(as_bytes), encoding="utf-8")):
            return self.run_command("proposals", "add", *arguments)

    def test_it_reads_a_proposal_from_standard_input_and_answers_with_one_line(self) -> None:
        """Covers: B174"""
        self.session(*self.read_notes())

        code, out, err = self.add(DANA, "-")

        self.assertEqual((code, out, err), (cli.EXIT_OK, proposals_commands.HANDED_IN + "\n", ""))
        self.assertEqual(self.file()["source"], TOOL)
        self.assertEqual(self.add(DANA), (cli.EXIT_OK, proposals_commands.HANDED_IN_BEFORE + "\n", ""))

    def test_the_answer_says_nothing_of_where_the_quote_stands(self) -> None:
        """Covers: B174"""
        self.session(typed(f"note that {QUOTE}", at(8)))
        code, out, _ = self.add(DANA)
        self.assertEqual((code, out), (cli.EXIT_OK, proposals_commands.HANDED_IN + "\n"))
        self.assertNotIn("typed", out)
        self.assertEqual(self.add(DANA, "--json")[0], cli.EXIT_USAGE)

    def test_a_call_with_more_than_the_input_is_a_wrong_call(self) -> None:
        """Covers: B174"""
        self.session(*self.read_notes())
        self.assertEqual(self.add(DANA, "extra")[0], cli.EXIT_USAGE)
        self.assertEqual(self.files(), [])

    def test_input_that_is_json_and_no_object_is_not_taken(self) -> None:
        """Covers: B174"""
        for given in ([DANA], 7, '"person"'):
            with self.subTest(given=str(given)[:20]):
                code, _, err = self.add(given)
                self.assertEqual(code, cli.EXIT_PROBLEM)
                self.assertIn("nothing handed in: a proposal is a JSON object", err)

    def test_input_longer_than_a_proposal_or_nested_too_deep_is_a_wrong_call(self) -> None:
        """Covers: B174"""
        too_long = json.dumps({**DANA, "more": "x" * proposals_commands.INPUT_LENGTH})
        no_text = b"\xff\xfe{"
        for written in (too_long, "[" * 100_000, '{"a":' * 100_000, no_text):
            with self.subTest(written=written[:12]):
                code, _, err = self.add(written)
                self.assertEqual(code, cli.EXIT_USAGE)
                self.assertIn("reads one JSON object from standard input", err)

    def test_a_proposal_that_is_not_taken_ends_with_the_line_that_says_why(self) -> None:
        """Covers: B174"""
        self.session(typed("hello there Sam", at(8)))
        code, out, err = self.add(DANA)
        self.assertEqual((code, out), (cli.EXIT_PROBLEM, ""))
        self.assertRegex(err, r"^m2b: nothing handed in: the words do not stand in this session as given")
        self.assertNotIn("Dana", err)
        self.assertEqual(self.files(), [])

    def test_without_the_switch_the_command_refuses_before_it_reads_anything(self) -> None:
        """Covers: B173"""
        self.set_up(calendar="none")
        self.session(*self.read_notes())
        for given in (DANA, {"kind": "todo"}, "no json"):
            with self.subTest(given=str(given)[:20]):
                code, _, err = self.add(given)
                self.assertEqual(code, cli.EXIT_PROBLEM)
                self.assertIn("handing in is off on this machine (sessions.propose in the m2b config)", err)
        self.assertEqual(self.files(), [])

    def test_no_session_turns_the_switch_on(self) -> None:
        """Covers: B173"""
        self.set_up(calendar="none")
        self.environ["CLAUDECODE"] = "1"
        for arguments in (("sessions.propose", "true"), ("sessions", '{"propose": true}')):
            with self.subTest(arguments=arguments):
                code, _, err = self.run_command("config", "set", *arguments)
                self.assertEqual(code, cli.EXIT_USAGE)
                self.assertIn("in a terminal of your own, outside Claude Code", err)
                self.assertFalse(load_machine_config(self.machine).sessions.propose)
        self.assertEqual(self.run_command("config", "set", "sessions.propose", "false")[0], cli.EXIT_OK)
        del self.environ["CLAUDECODE"]
        self.assertEqual(self.run_command("config", "set", "sessions.propose", "true")[0], cli.EXIT_OK)
        self.assertTrue(load_machine_config(self.machine).sessions.propose)

    def test_what_is_no_json_is_a_wrong_call(self) -> None:
        """Covers: B174"""
        code, _, err = self.add("kind: person")
        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertIn("reads one JSON object from standard input", err)

    def test_a_store_that_cannot_be_reached_is_said_and_nothing_is_written(self) -> None:
        """Covers: B177"""
        self.session(*self.read_notes())
        self.store_root.rename(self.store_root.with_name("gone"))
        code, out, err = self.add(DANA)
        self.assertEqual((code, out), (cli.EXIT_UNREACHABLE, ""))
        self.assertTrue(err.startswith("m2b: "), err)
        self.assertFalse(self.store_root.exists())


if __name__ == "__main__":
    import unittest

    unittest.main()
