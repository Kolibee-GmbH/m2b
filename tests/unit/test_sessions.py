from __future__ import annotations

import datetime
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from random import Random
from typing import Any

from m2b import claude_code, sessions
from m2b.sessions import LeftOut, Prompt

UTC = datetime.timezone.utc
DAY = datetime.datetime(2026, 3, 4, tzinfo=UTC)
NEXT_DAY = DAY + datetime.timedelta(days=1)
NOTHING_LEFT_OUT = LeftOut(sent_by_others=0, suggested=0, unmarked=0)


def at(hour: int, minute: int = 0) -> datetime.datetime:
    return DAY.replace(hour=hour, minute=minute)


def typed(text: object, when: datetime.datetime, **changes: Any) -> dict[str, Any]:
    """A user record as Claude Code writes one for a prompt the person typed."""
    record = {
        "type": "user",
        "timestamp": when.isoformat().replace("+00:00", "Z"),
        "cwd": "/home/alex/projects/shed",
        "entrypoint": "cli",
        "promptSource": "typed",
        "origin": {"kind": "human"},
        "message": {"role": "user", "content": text},
    }
    record.update(changes)
    return {key: value for key, value in record.items() if value is not None}


def sent_by(kind: str, text: str, when: datetime.datetime, **changes: Any) -> dict[str, Any]:
    return typed(text, when, **{"promptSource": "system", "origin": {"kind": kind}, **changes})


def pasted_block(text: str, block_id: str = "a1") -> str:
    """``text`` as Claude Code writes a paste into a prompt."""
    return f'<pasted_content id="{block_id}">{text}</pasted_content id="{block_id}">'


def unmarked(text: object, when: datetime.datetime, **changes: Any) -> dict[str, Any]:
    return typed(text, when, **{"promptSource": None, "origin": None, **changes})


def queued(text: object, when: datetime.datetime, **changes: Any) -> dict[str, Any]:
    """An attachment as Claude Code writes one for a message sent while it worked, taken into that turn."""
    stamp = when.isoformat().replace("+00:00", "Z")
    attachment = {
        "type": "queued_command",
        "prompt": text,
        "source_uuid": "7d5f8723-0000-4000-8000-000000000001",
        "delivery_id": "212cecbe-0000-4000-8000-000000000002",
        "commandMode": "prompt",
        "origin": {"kind": "human"},
        "timestamp": stamp,
    }
    attachment.update(changes)
    return {
        "type": "attachment",
        "timestamp": stamp,
        "cwd": "/home/alex/projects/shed",
        "entrypoint": "cli",
        "isSidechain": False,
        "attachment": {key: value for key, value in attachment.items() if value is not None},
    }


class SessionsFixture(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory(prefix="sb-test-sessions-")
        self.addCleanup(folder.cleanup)
        self.projects = Path(folder.name) / "projects"
        self.projects.mkdir()

    def transcript(self, *records: Any, session: str = "session-1", project: str = "-shed") -> Path:
        path = self.projects / project / f"{session}.jsonl"
        path.parent.mkdir(exist_ok=True)
        path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        return path

    def read(self) -> sessions.Sessions:
        return sessions.read_sessions(self.projects, DAY, NEXT_DAY)

    def only_session(self) -> sessions.Session:
        found = self.read()
        self.assertEqual(len(found.sessions), 1, found)
        return found.sessions[0]

    def texts(self) -> list[str]:
        return [prompt.text for prompt in self.only_session().prompts]


class TypedPromptsTest(SessionsFixture):
    def test_a_session_gives_what_was_typed_with_its_time_its_id_and_its_folder(self) -> None:
        """Covers: B112"""
        self.transcript(
            typed("Dana runs IT at Northwind\nand signs   the renewals.", at(9)),
            {"type": "assistant", "timestamp": "2026-03-04T09:00:05Z", "message": {"content": "Noted."}},
            typed([{"type": "text", "text": "Who else is in the team?"}], at(9, 30), cwd="/home/alex/elsewhere"),
            session="abc",
        )

        session = self.only_session()

        self.assertEqual(session.session_id, "abc")
        self.assertEqual(session.folder, "/home/alex/projects/shed")
        self.assertEqual(
            session.prompts,
            (
                Prompt(at(9), "Dana runs IT at Northwind and signs the renewals."),
                Prompt(at(9, 30), "Who else is in the team?"),
            ),
        )
        self.assertEqual(session.left_out, NOTHING_LEFT_OUT)

    def test_a_long_prompt_is_kept_up_to_its_first_two_thousand_characters(self) -> None:
        """Covers: B113"""
        self.transcript(typed("word " * 1000, at(9)))

        (text,) = self.texts()

        self.assertEqual(len(text), sessions.PROMPT_LENGTH)
        self.assertTrue(text.startswith("word word "))

    def test_a_credential_in_a_prompt_is_redacted(self) -> None:
        """Covers: B113"""
        self.transcript(typed("deploy with PGPASSWORD=hunter2 psql -h db.example", at(9)))

        self.assertEqual(self.texts(), ["deploy with PGPASSWORD=[removed] psql -h db.example"])

    def test_half_a_character_in_a_prompt_becomes_a_question_mark_so_the_text_can_be_written(self) -> None:
        self.transcript(typed("half \ud83d of an emoji", at(9)))

        (text,) = self.texts()

        self.assertEqual(text, "half ? of an emoji")
        self.assertEqual(text.encode("utf-8").decode("utf-8"), text)

    def test_a_prompt_typed_in_the_desktop_app_or_while_claude_was_busy_is_the_persons(self) -> None:
        """Covers: B112"""
        self.transcript(
            typed("from the desktop app", at(9), promptSource="sdk", entrypoint="claude-desktop"),
            typed("typed while it worked", at(10), promptSource="queued"),
        )

        self.assertEqual(self.texts(), ["from the desktop app", "typed while it worked"])

    def test_a_message_sent_while_claude_worked_and_taken_into_its_turn_is_the_persons(self) -> None:
        """Covers: B112"""
        self.transcript(
            typed("Draft the reply to Dana", at(9)),
            {"type": "assistant", "timestamp": "2026-03-04T09:00:05Z", "message": {"content": "On it."}},
            queued("Dana is the new head of purchasing at Northwind", at(9, 1)),
        )

        prompts = self.only_session().prompts

        self.assertEqual(
            [p.text for p in prompts], ["Draft the reply to Dana", "Dana is the new head of purchasing at Northwind"]
        )
        self.assertEqual(prompts[1].time, at(9, 1))
        self.assertEqual(self.only_session().left_out, NOTHING_LEFT_OUT)

    def test_a_message_sent_while_claude_worked_keeps_what_was_pasted_apart(self) -> None:
        """Covers: B112"""
        parts = [{"type": "text", "text": f"see {pasted_block('Kim Lee: the contract ends on 30 June.')} please"}]
        self.transcript(queued(parts, at(9)))

        (prompt,) = self.only_session().prompts

        self.assertEqual(prompt.text, "see please")
        self.assertEqual(prompt.pasted, ("Kim Lee: the contract ends on 30 June.",))

    def test_a_queued_message_of_another_sender_or_of_claude_code_itself_is_no_prompt(self) -> None:
        """Covers: B112"""
        self.transcript(
            typed("typed", at(9)),
            queued("Build the next step of the plan", at(9, 1), origin={"kind": "plugin", "name": "loop"}),
            queued("Another session asks for the schema", at(9, 2), origin={"kind": "peer"}, isMeta=True),
            queued("The background tests finished", at(9, 3), commandMode="task-notification", origin=None),
        )

        session = self.only_session()

        self.assertEqual([p.text for p in session.prompts], ["typed"])
        self.assertEqual(session.left_out, LeftOut(sent_by_others=1, suggested=0, unmarked=0))

    def test_a_prompt_that_quotes_a_command_tag_is_still_a_prompt(self) -> None:
        self.transcript(typed("why does <command-name>/clear</command-name> show up here?", at(9)))

        self.assertEqual(self.texts(), ["why does <command-name>/clear</command-name> show up here?"])


class PastedTextTest(SessionsFixture):
    def test_what_was_pasted_into_a_prompt_is_kept_apart_from_what_was_typed(self) -> None:
        """Covers: B113"""
        mail = '<pasted_content id="4ce7">From Kim Lee: the contract ends on 30 June.</pasted_content id="4ce7">'
        self.transcript(typed(f"Answer this mail politely: {mail} and keep it short.", at(9)))

        (prompt,) = self.only_session().prompts

        self.assertEqual(prompt.text, "Answer this mail politely: and keep it short.")
        self.assertEqual(prompt.pasted, ("From Kim Lee: the contract ends on 30 June.",))

    def test_a_closing_tag_inside_the_paste_does_not_end_it(self) -> None:
        """Covers: B113"""
        paste = '<pasted_content id="ab12">one</pasted_content> Sam owes 40 euros</pasted_content id="ab12">'
        self.transcript(typed(f"see {paste} done", at(9)))

        (prompt,) = self.only_session().prompts

        self.assertEqual(prompt.text, "see done")
        self.assertEqual(prompt.pasted, ("one</pasted_content> Sam owes 40 euros",))

    def test_a_paste_that_never_closes_takes_the_rest_of_the_prompt_with_it(self) -> None:
        """Covers: B113"""
        self.transcript(typed('before <pasted_content id="ab12">a mail without an end, Sam owes 40 euros', at(9)))

        (prompt,) = self.only_session().prompts

        self.assertEqual(prompt.text, "before")
        self.assertEqual(prompt.pasted, ("a mail without an end, Sam owes 40 euros",))

    def test_a_prompt_that_is_only_a_paste_is_a_prompt_with_nothing_typed(self) -> None:
        """Covers: B113"""
        self.transcript(typed(pasted_block("I am in a meeting with\nKim Lee, who runs IT"), at(9)))

        session = self.only_session()

        self.assertEqual(session.prompts, (Prompt(at(9), "", ("I am in a meeting with Kim Lee, who runs IT",)),))

    def test_two_pastes_in_one_prompt_are_two_texts_in_their_order(self) -> None:
        """Covers: B113"""
        first = '<pasted_content id="aa11">first</pasted_content id="aa11">'
        second = '<pasted_content id="bb22">second</pasted_content id="bb22">'
        self.transcript(typed(f"compare {first} with {second} please", at(9)))

        (prompt,) = self.only_session().prompts

        self.assertEqual(prompt.text, "compare with please")
        self.assertEqual(prompt.pasted, ("first", "second"))

    def test_a_paste_gets_the_room_the_typed_text_leaves_and_pushes_out_no_typed_word(self) -> None:
        """Covers: B113"""
        typed_words = "word " * 300
        paste = f'<pasted_content id="aa11">{"pasted " * 300}</pasted_content id="aa11">'
        later = '<pasted_content id="bb22">never reached</pasted_content id="bb22">'
        self.transcript(typed(f"{paste} {typed_words} {later}", at(9)))

        (prompt,) = self.only_session().prompts

        self.assertEqual(prompt.text, typed_words.strip())
        self.assertEqual(len(prompt.text) + sum(len(text) for text in prompt.pasted), sessions.PROMPT_LENGTH)
        self.assertEqual(len(prompt.pasted), 1)
        self.assertTrue(prompt.pasted[0].startswith("pasted pasted"))

    def test_typed_text_that_fills_the_prompt_leaves_a_paste_no_room(self) -> None:
        """Covers: B113"""
        paste = '<pasted_content id="aa11">Kim Lee runs IT</pasted_content id="aa11">'
        self.transcript(typed(f"{'word ' * 500} {paste}", at(9)))

        (prompt,) = self.only_session().prompts

        self.assertEqual(len(prompt.text), sessions.PROMPT_LENGTH)
        self.assertEqual(prompt.pasted, ())

    def test_a_credential_in_pasted_text_is_redacted_like_one_that_was_typed(self) -> None:
        """Covers: B113"""
        paste = '<pasted_content id="aa11">export API_TOKEN=sk-live-9f8e7d6c5b4a3f2e1d0c</pasted_content id="aa11">'
        self.transcript(typed(f"why does this fail? {paste}", at(9)))

        (prompt,) = self.only_session().prompts

        self.assertNotIn("9f8e7d6c5b4a3f2e1d0c", "".join(prompt.pasted))

    def test_what_claude_code_writes_into_a_prompt_is_taken_out_of_pasted_text_too(self) -> None:
        """Covers: B113"""
        reminder = "<system-reminder>The file notes.md changed: Kim Lee moved to Globex.</system-reminder>"
        paste = f'<pasted_content id="aa11">Sam owes 40 euros {reminder}</pasted_content id="aa11">'
        self.transcript(typed(f"see {paste}", at(9)))

        (prompt,) = self.only_session().prompts

        self.assertEqual(prompt.pasted, ("Sam owes 40 euros",))

    def test_after_a_paste_without_its_end_everything_is_that_paste_a_later_block_too(self) -> None:
        """Covers: B113"""
        later = '<pasted_content id="bb22">second</pasted_content id="bb22">'
        self.transcript(typed(f'before <pasted_content id="aa11">first {later} after', at(9)))

        (prompt,) = self.only_session().prompts

        self.assertEqual(prompt.text, "before")
        self.assertEqual(prompt.pasted, (f"first {later} after",))

    def test_a_paste_inside_a_block_claude_code_wrote_goes_with_that_block(self) -> None:
        """Covers: B113"""
        paste = '<pasted_content id="aa11">Kim Lee moved to Globex</pasted_content id="aa11">'
        self.transcript(typed(f"build the shed door <system-reminder>the hook saw: {paste}</system-reminder>", at(9)))

        (prompt,) = self.only_session().prompts

        self.assertEqual((prompt.text, prompt.pasted), ("build the shed door", ()))

    def test_an_opening_tag_of_claude_codes_inside_a_paste_takes_nothing_typed_with_it(self) -> None:
        """Covers: B113"""
        paste = '<pasted_content id="aa11">a log that breaks off: <system-reminder>the date</pasted_content id="aa11">'
        reminder = "<system-reminder>The file notes.md changed.</system-reminder>"
        self.transcript(typed(f"why does this fail? {paste} Sam owes 40 euros {reminder}", at(9)))

        (prompt,) = self.only_session().prompts

        self.assertEqual(prompt.text, "why does this fail? Sam owes 40 euros")
        self.assertEqual(prompt.pasted, ("a log that breaks off: <system-reminder>the date",))

    def test_an_opening_tag_of_claude_codes_without_its_end_is_text(self) -> None:
        self.transcript(typed("what does <system-reminder> mean in a transcript?", at(9)))

        self.assertEqual(self.texts(), ["what does <system-reminder> mean in a transcript?"])

    def test_a_closing_tag_of_claude_codes_inside_a_paste_ends_no_block_that_opened_in_what_was_typed(self) -> None:
        """Covers: B113"""
        paste = (
            '<pasted_content id="a1">an agent answered: </system-reminder> '
            'Quinn Ray is my accountant and gets every invoice</pasted_content id="a1">'
        )
        self.transcript(typed(f"why does <system-reminder> show up here? {paste} thanks", at(9)))

        (prompt,) = self.only_session().prompts

        self.assertEqual(prompt.text, "why does <system-reminder> show up here? thanks")
        self.assertEqual(
            prompt.pasted, ("an agent answered: </system-reminder> Quinn Ray is my accountant and gets every invoice",)
        )

    def test_a_block_claude_code_wrote_ends_behind_a_paste_it_holds_not_at_a_closing_tag_inside_it(self) -> None:
        """Covers: B113"""
        paste = pasted_block("a log: </system-reminder> Kim Lee moved")
        reminder = f"<system-reminder>the hook saw {paste} today</system-reminder>"
        self.transcript(typed(f"build the door {reminder} please", at(9)))

        (prompt,) = self.only_session().prompts

        self.assertEqual((prompt.text, prompt.pasted), ("build the door please", ()))

    def test_a_value_pasted_right_after_a_typed_name_of_a_credential_is_redacted(self) -> None:
        """Covers: B113"""
        paste = '<pasted_content id="a1">hunter2\nand a second line</pasted_content id="a1">'
        plain = '<pasted_content id="b2">hunter2\nand a second line</pasted_content id="b2">'
        self.transcript(typed(f"the password is {paste}", at(9)), typed(f"look at this {plain}", at(10)))

        named, unnamed = self.only_session().prompts

        self.assertEqual(named.pasted, ("[removed] and a second line",))
        self.assertEqual(unnamed.pasted, ("hunter2 and a second line",))

    def test_opening_tags_of_claude_codes_that_never_close_are_all_text(self) -> None:
        many = "what is <system-reminder> for? " * 50

        self.transcript(typed(many, at(9)))

        self.assertEqual(self.texts(), [many.strip()])

    def test_a_value_pasted_behind_a_typed_start_of_a_credential_goes_however_the_two_are_joined(self) -> None:
        for before, value in (
            ('export DB_PASSWORD="', "hunter2"),
            ("curl -u admin:", "hunter2 https://example.org"),
            ("Authorization: Bearer ", "abc123def"),
            ("the token: ", "\nhunter2 and more"),
            ("psql https://admin:", "hunter2@db.example.org now"),
        ):
            with self.subTest(before=before):
                pasted = sessions._pasted(f"{before}{pasted_block(value)}")

                self.assertNotIn(value.split()[0], "".join(pasted))

    def test_a_paste_keeps_its_first_word_where_the_text_typed_before_it_names_no_credential(self) -> None:
        # The last one: the name of a credential stands where the look back at the typed text begins,
        # as the end of another word.
        far_back = f"long text xpassword for {'a' * 70} {'b' * 70} {'c' * 41} is "
        for before, paste in (
            ("look at this ", "hunter2 here"),
            ("my token ", "hunter2 here"),
            ("git push -u origin ", "hunter2 here"),
            ("see https://a:b@example.org and ", "hunter2 here"),
            ("Bearer ", "tokens are explained in RFC 6750"),
            ("Release2026abcdef", "notes for today"),
            (far_back, "hello world"),
        ):
            with self.subTest(before=before):
                self.assertEqual(sessions._pasted(f"{before}{pasted_block(paste)}"), [paste])

    def test_only_the_paste_right_behind_a_typed_name_of_a_credential_loses_its_first_word(self) -> None:
        text = f"the password: {pasted_block('hunter2 one')}{pasted_block('second two', 'b2')}"

        self.assertEqual(sessions._pasted(text), ["[removed] one", "second two"])

    def test_a_paste_ends_at_its_own_closing_tag_whatever_characters_the_prompt_holds(self) -> None:
        """Covers: B113"""
        almost = '</pasted_content\x00id="a1">'
        paste = pasted_block(f"a dump {almost} Quinn Ray is my accountant")
        self.transcript(typed(f"what\x00 is this? {paste} thanks", at(9)))

        (prompt,) = self.only_session().prompts

        self.assertEqual(prompt.text, "what\x00 is this? thanks")
        self.assertEqual(prompt.pasted, (f"a dump {almost} Quinn Ray is my accountant",))

    def test_a_prompt_with_every_character_a_paste_is_marked_with_has_no_paste_read(self) -> None:
        marks = "".join(chr(code) for code in range(9))
        self.transcript(typed(f"a dump {marks} {pasted_block('Kim Lee runs IT')} thanks", at(9)))

        (prompt,) = self.only_session().prompts

        self.assertEqual((prompt.text, prompt.pasted), (f"a dump {marks} thanks", ()))

    def test_a_paste_without_its_end_inside_a_block_claude_code_wrote_goes_with_that_block(self) -> None:
        """Covers: B113"""
        earlier = pasted_block("Kim Lee moved to Globex")
        reminder = f'<system-reminder>a hook saw {earlier} and <pasted_content id="b2"> there</system-reminder>'
        self.transcript(typed(f"build the shed door {reminder} and paint it", at(9)))

        (prompt,) = self.only_session().prompts

        self.assertEqual(prompt.pasted, ())

    def test_a_long_paste_full_of_opening_tags_that_never_close_is_read_from_its_start(self) -> None:
        long_paste = "Kim Lee runs IT " + "<system-reminder> x " * 20_000
        for name, paste in (("closed", pasted_block(long_paste)), ("open", f'<pasted_content id="a1">{long_paste}')):
            with self.subTest(name):
                (pasted,) = sessions._as_far_as_fits(sessions._pasted(f"see {paste}"), sessions.PROMPT_LENGTH)

                self.assertTrue(pasted.startswith("Kim Lee runs IT <system-reminder> x"))
                self.assertEqual(len(pasted), sessions.PROMPT_LENGTH)

    def test_what_was_typed_is_what_the_reader_gave_before_it_kept_what_was_pasted(self) -> None:
        """Covers: B113"""
        pieces = (
            "Dana",
            "runs",
            "IT",
            " ",
            " ",
            "\n",
            "<",
            ">",
            "x>",
            "\x00",
            "\x01",
            '<pasted_content id="a1">',
            '</pasted_content id="a1">',
            '</pasted_content\x00id="a1">',
            '<pasted_content id="b2">',
            '</pasted_content id="b2">',
            "<pasted_content>",
            "</pasted_content>",
            '<pasted_content id="a1"',
            "<pasted_content",
            "<pasted_content >",
            "</pasted_content\x00>",
            "<system-reminder>",
            "</system-reminder>",
            "<system-reminder",
            '<system-reminder kind="x">',
            "<task-notification>",
            "</task-notification>",
            "<local-command-stdout>",
            "</local-command-stdout>",
        )
        random = Random(20261114)

        def as_before(text: str) -> str:
            text = re.sub(r"<pasted_content\b([^>]*)>.*?</pasted_content\1>", " ", text, flags=re.S)
            text = re.sub(r"<pasted_content\b[^>]*>.*", " ", text, flags=re.S)
            return claude_code.PROMPT_BLOCK.sub(" ", text)

        for _ in range(4_000):
            text = "".join(random.choice(pieces) for _ in range(random.randint(1, 24)))

            self.assertEqual(sessions._typed(text), as_before(text), text)
            # Each pasted text stands in the prompt as it was written, behind the one before it.
            behind = 0
            for paste in sessions._pasted(text):
                self.assertIn(paste, text[behind:], text)
                behind = text.index(paste, behind) + len(paste)

    def test_a_paste_that_holds_nothing_is_no_prompt(self) -> None:
        """Covers: B113"""
        self.transcript(typed('<pasted_content id="ab12">   </pasted_content id="ab12">', at(9)))

        self.assertEqual(self.read().sessions, ())


class ClaudeCodesBlocksTest(SessionsFixture):
    def test_what_claude_code_writes_into_a_typed_prompt_is_taken_out(self) -> None:
        """Covers: B113"""
        reminder = "<system-reminder>The file notes.md changed: Kim Lee moved to Globex.</system-reminder>"
        hook = "<user-prompt-submit-hook>Northwind: Dana signs the renewals</user-prompt-submit-hook>"
        self.transcript(
            typed([{"type": "text", "text": reminder}, {"type": "text", "text": "Fix the invoice export"}], at(9)),
            typed(f"Fix the import too {hook}", at(10)),
        )

        self.assertEqual(self.texts(), ["Fix the invoice export", "Fix the import too"])

    def test_a_long_block_before_the_prompt_does_not_use_up_its_length(self) -> None:
        reminder = f"<system-reminder>{'changed ' * 400}</system-reminder>"
        self.transcript(typed(f"{reminder}\nFix the invoice export", at(9)))

        self.assertEqual(self.texts(), ["Fix the invoice export"])

    def test_a_prompt_that_is_only_such_a_block_is_no_prompt_and_not_counted(self) -> None:
        self.transcript(typed("<system-reminder>The date changed.</system-reminder>", at(9)))

        self.assertEqual(self.read().sessions, ())


class LongPromptTest(SessionsFixture):
    def test_a_credential_at_the_edge_of_what_is_redacted_does_not_come_through_in_part(self) -> None:
        """Covers: B113"""
        filler = "word " * 1636
        prompt = f"{filler}PGPASSWORD=hunter2hunter2hunter2 psql"
        self.assertLess(len(filler), 8 * 1024)
        self.assertGreater(len(filler) + len("PGPASSWORD=hunter2"), 8 * 1024)
        long_enough_to_show_the_edge = 9000

        original = sessions.PROMPT_LENGTH
        sessions.PROMPT_LENGTH = long_enough_to_show_the_edge
        self.addCleanup(setattr, sessions, "PROMPT_LENGTH", original)
        self.transcript(typed(prompt, at(9)))

        (text,) = self.texts()

        self.assertNotIn("hunter2", text)
        self.assertTrue(text.endswith("word"), text[-40:])


class SlashCommandTest(SessionsFixture):
    def test_a_slash_command_is_only_its_name(self) -> None:
        """Covers: B113"""
        command = (
            "<command-message>m2b:capture</command-message>\n<command-name>/m2b:capture</command-name>\n"
            "<command-args>Dana's birthday is 3 May</command-args>"
        )
        self.transcript(
            unmarked(command, at(9), origin={"kind": "human"}),
            unmarked("<command-name>/clear</command-name>", at(10)),
        )

        self.assertEqual(self.texts(), ["/m2b:capture", "/clear"])

    def test_the_tags_further_into_a_text_are_no_command(self) -> None:
        self.transcript(unmarked("the docs say <command-name>/deploy</command-name> runs it", at(9)))

        session = self.only_session()

        self.assertEqual(session.prompts, ())
        self.assertEqual(session.left_out.unmarked, 1)

    def test_a_command_a_plugin_ran_is_not_the_persons(self) -> None:
        """Covers: B112"""
        self.transcript(unmarked("<command-name>/catchup</command-name>", at(9), origin={"kind": "plugin"}))

        session = self.only_session()

        self.assertEqual(session.prompts, ())
        self.assertEqual(session.left_out.sent_by_others, 1)


class NotThePersonTest(SessionsFixture):
    def test_what_a_sender_other_than_a_human_sent_is_left_out_and_counted(self) -> None:
        """Covers: B112"""
        self.transcript(
            typed("build the shed door", at(9)),
            sent_by("plugin", "The loop plugin sent a message: build step 5, Dana signs the renewals", at(10)),
            sent_by("task-notification", "<task-notification>done</task-notification>", at(11)),
            sent_by("peer", "Sam owes 40 euros", at(12)),
            sent_by("a-kind-not-seen-yet", "Kim Lee moved to Globex", at(13), promptSource="typed"),
        )

        session = self.only_session()

        self.assertEqual([prompt.text for prompt in session.prompts], ["build the shed door"])
        self.assertEqual(session.left_out, LeftOut(sent_by_others=4, suggested=0, unmarked=0))

    def test_a_suggestion_the_person_only_accepted_is_left_out_and_counted(self) -> None:
        """Covers: B112"""
        self.transcript(typed("yes, commit it", at(9), promptSource="suggestion_accepted"))

        session = self.only_session()

        self.assertEqual(session.prompts, ())
        self.assertEqual(session.left_out.suggested, 1)

    def test_the_output_of_a_shell_line_in_several_blocks_is_neither_a_prompt_nor_counted(self) -> None:
        """Covers: B112"""
        self.transcript(
            typed("build the shed door", at(9)),
            unmarked("<bash-stdout>On branch main</bash-stdout><bash-stderr></bash-stderr>", at(9, 1)),
            unmarked(
                "<bash-stdout>a</bash-stdout>\n<bash-stderr>b</bash-stderr>\n<bash-stdout>c</bash-stdout>", at(9, 2)
            ),
        )

        session = self.only_session()

        self.assertEqual([prompt.text for prompt in session.prompts], ["build the shed door"])
        self.assertEqual(session.left_out, NOTHING_LEFT_OUT)

    def test_blocks_with_words_around_them_or_a_block_that_never_closes_are_text_without_the_mark(self) -> None:
        """Covers: B112"""
        self.transcript(
            unmarked("<bash-stdout>a</bash-stdout><bash-stderr>b</bash-stderr> Dana runs IT", at(9)),
            unmarked("<bash-stdout>a</bash-stdout> Dana runs IT <bash-stderr>b</bash-stderr>", at(9, 1)),
            unmarked("<bash-stdout>a</bash-stdout><bash-stderr>b", at(9, 2)),
            unmarked("Dana runs IT <bash-stdout>a</bash-stdout>", at(9, 3)),
        )

        session = self.only_session()

        self.assertEqual(session.prompts, ())
        self.assertEqual(session.left_out.unmarked, 4)

    def test_text_without_the_mark_of_who_sent_it_is_left_out_and_counted(self) -> None:
        """Covers: B112"""
        self.transcript(unmarked("Dana runs IT at Northwind", at(9)))

        session = self.only_session()

        self.assertEqual(session.prompts, ())
        self.assertEqual(session.left_out.unmarked, 1)

    def test_what_claude_code_writes_around_a_prompt_is_neither_a_prompt_nor_counted(self) -> None:
        """Covers: B112"""
        self.transcript(
            typed("build the shed door", at(9)),
            unmarked("<local-command-stdout>Set model to haiku</local-command-stdout>", at(9, 1)),
            unmarked("<bash-input>git status</bash-input>", at(9, 2)),
            unmarked("[Request interrupted by user]", at(9, 3)),
            unmarked("Base directory for this skill: /plugins/x", at(9, 4), isMeta=True),
            sent_by("peer", "<agent-message>Sam owes 40 euros</agent-message>", at(9, 4), isMeta=True),
            unmarked("<bash-stdout>see <command-name>/deploy</command-name> in the docs</bash-stdout>", at(9, 4)),
            unmarked("This session is being continued from a previous one.", at(9, 5), isCompactSummary=True),
            typed("a subagent's task", at(9, 6), isSidechain=True),
            unmarked([{"type": "tool_result", "tool_use_id": "t1", "content": "Dana runs IT"}], at(9, 7)),
            unmarked([{"type": "image", "source": {}}], at(9, 8)),
            {"type": "assistant", "timestamp": "2026-03-04T09:09:00Z", "message": {"content": "Sam owes 40 euros."}},
            "not a record",
        )

        session = self.only_session()

        self.assertEqual([prompt.text for prompt in session.prompts], ["build the shed door"])
        self.assertEqual(session.left_out, NOTHING_LEFT_OUT)


class WhichSessionsTest(SessionsFixture):
    def test_only_prompts_of_the_period_count_and_a_session_without_any_is_not_there(self) -> None:
        """Covers: B114"""
        self.transcript(
            typed("the evening before", DAY - datetime.timedelta(minutes=1)),
            typed("first of the day", DAY),
            typed("the next morning", NEXT_DAY),
            session="spans-days",
        )
        self.transcript(typed("another day", NEXT_DAY + datetime.timedelta(hours=3)), session="later")

        found = self.read()

        self.assertEqual([session.session_id for session in found.sessions], ["spans-days"])
        self.assertEqual([prompt.text for prompt in found.sessions[0].prompts], ["first of the day"])

    def test_a_session_of_which_everything_was_left_out_is_there_with_its_counts(self) -> None:
        self.transcript(sent_by("plugin", "build step 5", at(9)))

        session = self.only_session()

        self.assertEqual((session.prompts, session.left_out.sent_by_others), ((), 1))

    def test_a_headless_run_is_left_out_whole(self) -> None:
        """Covers: B114"""
        self.transcript(
            typed("file the inbox", at(9)),
            typed("and the next step", at(9, 1), entrypoint="sdk-cli"),
        )

        self.assertEqual(self.read().sessions, ())

    def test_sessions_come_in_the_order_of_their_first_prompt(self) -> None:
        tool_result = unmarked([{"type": "tool_result", "tool_use_id": "t1", "content": "done"}], at(0, 5))
        self.transcript(tool_result, typed("afternoon", at(15)), session="a-later")
        self.transcript(typed("morning", at(8)), session="z-earlier", project="-boat")

        self.assertEqual([session.session_id for session in self.read().sessions], ["z-earlier", "a-later"])

    def test_a_transcript_not_written_since_the_period_began_is_not_opened(self) -> None:
        path = self.transcript(typed("first of the day", at(9)))
        before = (DAY - datetime.timedelta(hours=1)).timestamp()
        os.utime(path, (before, before))

        self.assertEqual(self.read().sessions, ())

    def test_broken_lines_and_times_are_skipped_and_the_rest_is_read(self) -> None:
        path = self.transcript(typed("first of the day", at(9)), typed("no time", at(10), timestamp="yesterday"))
        with path.open("a", encoding="utf-8") as handle:
            handle.write('{"type": "user", "timestamp": "2026-03-04T11:00:00Z", "message": \n')

        self.assertEqual(self.texts(), ["first of the day"])


class CouldNotLookTest(SessionsFixture):
    def test_a_missing_folder_is_an_error_not_an_empty_day(self) -> None:
        """Covers: B114"""
        with self.assertRaises(sessions.SessionsError) as failed:
            sessions.read_sessions(self.projects / "gone", DAY, NEXT_DAY)

        self.assertIn("gone", str(failed.exception))

    def test_a_transcript_with_prompts_that_names_no_folder_is_named_as_not_read(self) -> None:
        """Covers: B114"""
        self.transcript(typed("first of the day", at(9), cwd=None), session="no-folder")
        self.transcript(typed("the day after", NEXT_DAY, cwd=None), session="nothing-of-the-period")

        found = self.read()

        self.assertEqual(found.sessions, ())
        self.assertEqual(found.unreadable, ("-shed/no-folder.jsonl",))

    def test_a_line_nested_deeper_than_python_reads_is_passed_over(self) -> None:
        path = self.transcript(typed("Dana runs purchasing", at(9)))
        deep = '{"type": "user", "toolUseResult": ' + "[" * 100_000 + "]" * 100_000 + "}"
        path.write_text(deep + "\n" + path.read_text(encoding="utf-8"), encoding="utf-8")
        self.assertEqual(self.texts(), ["Dana runs purchasing"])

    def test_a_transcript_that_cannot_be_read_is_named_and_the_others_are_read(self) -> None:
        """Covers: B114"""
        self.transcript(typed("first of the day", at(9)), session="readable")
        (self.projects / "-shed" / "broken.jsonl").mkdir()

        found = self.read()

        self.assertEqual([session.session_id for session in found.sessions], ["readable"])
        self.assertEqual(found.unreadable, ("-shed/broken.jsonl",))


class TranscriptsFolderTest(unittest.TestCase):
    def test_the_transcripts_are_under_the_home_folders_claude_folder(self) -> None:
        self.assertEqual(claude_code.transcripts_folder({"HOME": "/home/alex"}), Path("/home/alex/.claude/projects"))

    def test_claude_config_dir_moves_them_as_it_does_for_claude_code(self) -> None:
        environ = {"HOME": "/home/alex", "CLAUDE_CONFIG_DIR": "/srv/claude"}

        self.assertEqual(claude_code.transcripts_folder(environ), Path("/srv/claude/projects"))


if __name__ == "__main__":
    unittest.main()
