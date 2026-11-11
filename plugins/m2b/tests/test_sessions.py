from __future__ import annotations

import datetime
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any

from m2b import claude_code, sessions
from m2b.sessions import LeftOut, Prompt

UTC = datetime.timezone.utc
DAY = datetime.datetime(2026, 3, 4, tzinfo=UTC)
NEXT_DAY = DAY + datetime.timedelta(days=1)
NOTHING_LEFT_OUT = LeftOut(pasted_blocks=0, sent_by_others=0, suggested=0, unmarked=0)


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


def unmarked(text: object, when: datetime.datetime, **changes: Any) -> dict[str, Any]:
    return typed(text, when, **{"promptSource": None, "origin": None, **changes})


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
        self.transcript(typed("word " * 1000, at(9)))

        (text,) = self.texts()

        self.assertEqual(len(text), sessions.PROMPT_LENGTH)
        self.assertTrue(text.startswith("word word "))

    def test_a_credential_in_a_prompt_is_redacted(self) -> None:
        self.transcript(typed("deploy with PGPASSWORD=hunter2 psql -h db.example", at(9)))

        self.assertEqual(self.texts(), ["deploy with PGPASSWORD=[removed] psql -h db.example"])

    def test_a_prompt_typed_in_the_desktop_app_or_while_claude_was_busy_is_the_persons(self) -> None:
        self.transcript(
            typed("from the desktop app", at(9), promptSource="sdk", entrypoint="claude-desktop"),
            typed("typed while it worked", at(10), promptSource="queued"),
        )

        self.assertEqual(self.texts(), ["from the desktop app", "typed while it worked"])

    def test_a_prompt_that_quotes_a_command_tag_is_still_a_prompt(self) -> None:
        self.transcript(typed("why does <command-name>/clear</command-name> show up here?", at(9)))

        self.assertEqual(self.texts(), ["why does <command-name>/clear</command-name> show up here?"])


class PastedTextTest(SessionsFixture):
    def test_a_pasted_block_is_left_out_with_what_it_holds_and_counted(self) -> None:
        mail = '<pasted_content id="4ce7">From Kim Lee: the contract ends on 30 June.</pasted_content id="4ce7">'
        self.transcript(typed(f"Answer this mail politely: {mail} and keep it short.", at(9)))

        session = self.only_session()

        self.assertEqual([prompt.text for prompt in session.prompts], ["Answer this mail politely: and keep it short."])
        self.assertEqual(session.left_out.pasted_blocks, 1)

    def test_a_closing_tag_inside_the_paste_does_not_end_it(self) -> None:
        paste = '<pasted_content id="ab12">one</pasted_content> Sam owes 40 euros</pasted_content id="ab12">'
        self.transcript(typed(f"see {paste} done", at(9)))

        self.assertEqual(self.texts(), ["see done"])

    def test_a_paste_that_never_closes_takes_the_rest_of_the_prompt_with_it(self) -> None:
        self.transcript(typed('before <pasted_content id="ab12">a mail without an end, Sam owes 40 euros', at(9)))

        session = self.only_session()

        self.assertEqual([prompt.text for prompt in session.prompts], ["before"])
        self.assertEqual(session.left_out.pasted_blocks, 1)

    def test_a_prompt_that_is_only_a_paste_is_no_prompt(self) -> None:
        self.transcript(typed('<pasted_content id="ab12">a whole document</pasted_content id="ab12">', at(9)))

        session = self.only_session()

        self.assertEqual(session.prompts, ())
        self.assertEqual(session.left_out.pasted_blocks, 1)

    def test_two_pastes_in_one_prompt_both_go(self) -> None:
        first = '<pasted_content id="aa11">first</pasted_content id="aa11">'
        second = '<pasted_content id="bb22">second</pasted_content id="bb22">'
        self.transcript(typed(f"compare {first} with {second} please", at(9)))

        session = self.only_session()

        self.assertEqual([prompt.text for prompt in session.prompts], ["compare with please"])
        self.assertEqual(session.left_out.pasted_blocks, 2)


class ClaudeCodesBlocksTest(SessionsFixture):
    def test_what_claude_code_writes_into_a_typed_prompt_is_taken_out(self) -> None:
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
        self.transcript(unmarked("<command-name>/catchup</command-name>", at(9), origin={"kind": "plugin"}))

        session = self.only_session()

        self.assertEqual(session.prompts, ())
        self.assertEqual(session.left_out.sent_by_others, 1)


class NotThePersonTest(SessionsFixture):
    def test_what_a_sender_other_than_a_human_sent_is_left_out_and_counted(self) -> None:
        self.transcript(
            typed("build the shed door", at(9)),
            sent_by("plugin", "The loop plugin sent a message: build step 5, Dana signs the renewals", at(10)),
            sent_by("task-notification", "<task-notification>done</task-notification>", at(11)),
            sent_by("peer", "Sam owes 40 euros", at(12)),
            sent_by("a-kind-not-seen-yet", "Kim Lee moved to Globex", at(13), promptSource="typed"),
        )

        session = self.only_session()

        self.assertEqual([prompt.text for prompt in session.prompts], ["build the shed door"])
        self.assertEqual(session.left_out, LeftOut(pasted_blocks=0, sent_by_others=4, suggested=0, unmarked=0))

    def test_a_suggestion_the_person_only_accepted_is_left_out_and_counted(self) -> None:
        self.transcript(typed("yes, commit it", at(9), promptSource="suggestion_accepted"))

        session = self.only_session()

        self.assertEqual(session.prompts, ())
        self.assertEqual(session.left_out.suggested, 1)

    def test_text_without_the_mark_of_who_sent_it_is_left_out_and_counted(self) -> None:
        self.transcript(unmarked("Dana runs IT at Northwind", at(9)))

        session = self.only_session()

        self.assertEqual(session.prompts, ())
        self.assertEqual(session.left_out.unmarked, 1)

    def test_what_claude_code_writes_around_a_prompt_is_neither_a_prompt_nor_counted(self) -> None:
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
        with self.assertRaises(sessions.SessionsError) as failed:
            sessions.read_sessions(self.projects / "gone", DAY, NEXT_DAY)

        self.assertIn("gone", str(failed.exception))

    def test_a_transcript_with_prompts_that_names_no_folder_is_named_as_not_read(self) -> None:
        self.transcript(typed("first of the day", at(9), cwd=None), session="no-folder")
        self.transcript(typed("the day after", NEXT_DAY, cwd=None), session="nothing-of-the-period")

        found = self.read()

        self.assertEqual(found.sessions, ())
        self.assertEqual(found.unreadable, ("-shed/no-folder.jsonl",))

    def test_a_transcript_that_cannot_be_read_is_named_and_the_others_are_read(self) -> None:
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
