"""The curation step that reads what the person typed and keeps what a model proposes from it."""

from __future__ import annotations

import dataclasses
import datetime
import json
from typing import Any, ClassVar
from unittest import mock

import test_proposals
import test_runner
import test_sessions
from m2b import (
    fixes,
    folders_left_out,
    glean,
    lesson_counts,
    lesson_sources,
    lessons,
    project_proposals,
    proposal_answers,
    proposals,
    remembered_corrections,
    session_remotes,
)
from m2b.config.profile import save_profile
from m2b.curate import machine_state, model
from m2b.run_record import SUCCEEDED, load_run_record
from m2b.store.base import StoreError
from m2b.tasks import markers
from m2b.tasks.base import TasksError
from m2b.tasks.markdown import MarkdownTasks
from test_proposals import counts
from test_runner import INGEST_FILES_THE_CAPTURE, START

HOUR = datetime.timedelta(hours=1)
DAY = datetime.timedelta(days=1)
DANA_SAID = "Dana runs IT at Northwind and signs the renewals."
DANA = {
    "kind": "person",
    "text": "Dana runs IT at Northwind.",
    "quote": "Dana runs IT at Northwind",
    "session": 1,
    "topic": None,
    "due": None,
}
DANA_ID = proposals.proposal_id(glean.Proposal("person", "", "Dana runs IT at Northwind", "shed"))
# Proposals of earlier readings, as the proposals file and the model's input hold what they say.
KIM = {"kind": "person", "text": "Kim Lee is the accountant.", "quote": "Kim Lee is my accountant"}
TEA = {"kind": "personal", "text": "Alex drinks green tea.", "quote": "I only drink green tea"}
OFFER = {"kind": "commitment", "text": "Send Robin the offer.", "quote": "I still owe Robin the offer"}
BOAT = {"kind": "agreement", "text": "Sam lends the boat in May.", "quote": "Sam lends us the boat in May"}
MIA = {"kind": "personal", "text": "Mia starts school in August.", "quote": "Mia starts school in August"}
PLYWOOD = {"kind": "agreement", "text": "Sam brings the plywood.", "quote": "Sam brings the plywood on Friday"}


def capture(text: str, hour: int) -> str:
    return f"---\ncreated: 2026-11-07T{hour:02d}:00:00+00:00\nsource: cli\n---\n{text}\n"


def nothing_kept(read_until: datetime.datetime) -> dict[str, Any]:
    """The proposals file of a store that was read up to then and holds no proposal."""
    return {
        "format": 1,
        "read_until": read_until.isoformat(),
        "announced_until": None,
        "counts": counts(),
        "proposals": {},
    }


class GleanStepTest(test_runner.RunnerTest):
    def reading(self, **extra: Any) -> None:
        """A curating machine that reads the sessions, with a transcripts folder that holds none yet."""
        self.curating(**{"curation": {"read_sessions": True}, **extra})
        self.projects = self.claude_settings.parent / "projects"
        self.projects.mkdir(parents=True)

    def typed(
        self, text: str, when: datetime.datetime, session: str = "shed", folder: str = "/home/alex/projects/shed"
    ) -> None:
        self.record(test_sessions.typed(text, when.astimezone(datetime.timezone.utc), cwd=folder), session)

    def record(self, record: dict[str, Any], session: str = "shed") -> None:
        path = self.projects / "-project" / f"{session}.jsonl"
        path.parent.mkdir(exist_ok=True)
        with path.open("a", encoding="utf-8") as transcript:
            transcript.write(json.dumps(record) + "\n")

    def answers(
        self,
        *entries: dict[str, Any],
        outcome: str = "success",
        skills: dict[str, list[dict[str, Any]]] | None = None,
        verdicts: list[dict[str, Any]] | None = None,
        singles: list[dict[str, Any]] | None = None,
    ) -> None:
        """What the reading's model answers, and where it found a lesson, what the check of its sources answers."""
        self.model(skills or {})
        script = json.loads(self.actions.read_text(encoding="utf-8"))
        answer: dict[str, Any] = {"proposals": list(entries)}
        if singles is not None:
            answer["single_corrections"] = singles
        script["text"] = {"answer": json.dumps(answer), "outcome": outcome}
        if verdicts is not None:
            script["text"] = [script["text"], {"answer": json.dumps({"verdicts": verdicts}), "outcome": "success"}]
        self.actions.write_text(json.dumps(script), encoding="utf-8")

    def asked(self) -> list[dict[str, Any]]:
        """What each run without tools was given: the instruction, and the sessions and the memory it read."""
        return [
            {"instruction": call["arguments"][1], **json.loads(call["stdin"])}
            for call in self.calls()
            if "stdin" in call
        ]

    def prompts_asked(self) -> list[list[str]]:
        return [[prompt for session in asked["sessions"] for prompt in session["prompts"]] for asked in self.asked()]

    def kept(self) -> dict[str, Any]:
        raw: dict[str, Any] = json.loads((self.store_root / proposals.PROPOSALS_FILE).read_text(encoding="utf-8"))
        return raw

    def steps(self) -> list[tuple[str, str]]:
        record = load_run_record(self.store)
        assert record is not None
        return [(step.name, step.result) for step in record.steps]

    def info(self, step: str = "glean") -> list[str]:
        record = load_run_record(self.store)
        assert record is not None
        return [finding.text for finding in record.findings if finding.step == step]

    def read_until(self, moment: datetime.datetime) -> None:
        proposals.save(self.store, proposals.Proposals({}, moment))


class ReadingTest(GleanStepTest):
    def test_a_run_asks_the_model_about_what_was_typed_and_keeps_its_proposals(self) -> None:
        """Covers: B115"""
        self.reading()
        self.write("memory/MEMORY.md", "# Memory\n\n## Facts\n\n- Sam brings plywood (sam.md)\n\n## Current\n")
        self.write("memory/sam.md", "# Sam\n\n- Brings plywood.\n")
        self.typed(DANA_SAID, START - 2 * HOUR)
        self.typed("run the tests again", START - HOUR)
        self.answers(DANA)

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.steps()[:3], [("harvest", "succeeded"), ("glean", "succeeded"), ("ingest", "skipped")])
        (asked,) = self.asked()
        self.assertEqual(asked["instruction"], glean.instruction())
        self.assertIn("Sam brings plywood", asked["memory"])
        self.assertEqual(
            [(session["folder"], session["prompts"]) for session in asked["sessions"]],
            [("/home/alex/projects/shed", [DANA_SAID, "run the tests again"])],
        )
        (call,) = self.calls()
        self.assertEqual(call["arguments"][call["arguments"].index("--tools") + 1], "")
        self.assertEqual(call["environment"]["M2B_CURATION_RUN"], "1")
        kept = self.kept()
        self.assertEqual(kept["read_until"], START.isoformat())
        self.assertEqual(
            kept["proposals"],
            {
                DANA_ID: {
                    "kind": "person",
                    "text": "Dana runs IT at Northwind.",
                    "quote": "Dana runs IT at Northwind",
                    "topic": None,
                    "due": None,
                    "day": (START - 2 * HOUR).date().isoformat(),
                    "state": "open",
                    "since": START.isoformat(),
                }
            },
        )
        self.assertEqual(
            self.info(),
            [
                f"read 1 session with 2 prompts since {START - DAY:%Y-%m-%d %H:%M}: 1 proposal added, "
                "0 like one that waits, is answered or expired, 0 without the person's words, 0 captured already, "
                "0 not in the form"
            ],
        )
        self.assertEqual(self.review_tasks(), [])

    def test_while_the_switch_is_off_the_step_is_not_in_the_run(self) -> None:
        """Covers: B115"""
        self.reading(curation={})
        self.typed(DANA_SAID, START - HOUR)
        self.answers(DANA)

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertNotIn("glean", [name for name, _ in self.steps()])
        self.assertEqual(self.calls(), [])
        self.assertFalse((self.store_root / proposals.PROPOSALS_FILE).exists())

    def test_without_a_session_that_has_a_typed_prompt_no_model_starts(self) -> None:
        """Covers: B115"""
        self.reading()
        self.record(test_sessions.sent_by("plugin", "build the next part", START - HOUR))
        self.answers(DANA)

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.steps()[1], ("glean", "skipped"))
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.kept(), nothing_kept(read_until=START))

    def test_a_proposal_from_a_prompt_that_was_pasted_whole_waits_and_says_that_it_was_pasted(self) -> None:
        """Covers: B172"""
        self.reading()
        notes = "I am in a meeting with Northwind. Dana runs IT at Northwind and signs the renewals."
        self.typed(f'<pasted_content id="a1">{notes}</pasted_content id="a1">', START - 2 * HOUR)
        self.answers(DANA)

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        (asked,) = self.asked()
        self.assertEqual(asked["sessions"][0]["prompts"], [{"typed": "", "pasted": [notes]}])
        (kept,) = self.kept()["proposals"].values()
        self.assertEqual((kept["text"], kept["source"]), ("Dana runs IT at Northwind.", "pasted"))
        self.assertIn("1 pasted text was read with the prompts they stand in", self.info())

    def test_a_period_in_which_everything_was_pasted_shows_that_claude_code_marks_who_sent_it(self) -> None:
        self.reading()
        self.typed(
            '<pasted_content id="a1">notes of mine about the shed roof</pasted_content id="a1">', START - 2 * HOUR
        )
        self.record(test_sessions.unmarked("ls -la", START - HOUR))
        self.answers()

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.steps()[1], ("glean", "succeeded"))

    def test_what_the_reader_left_out_of_the_sessions_is_counted_in_the_runs_information(self) -> None:
        """Covers: B115"""
        self.reading()
        self.typed(DANA_SAID, START - 4 * HOUR)
        self.record(test_sessions.sent_by("plugin", "build the next part", START - 3 * HOUR))
        self.record(test_sessions.sent_by("task-notification", "the build is done", START - 3 * HOUR))
        self.record(test_sessions.typed("yes, do that", START - 2 * HOUR, promptSource="suggestion_accepted"))
        self.record(test_sessions.unmarked("ls -la", START - HOUR))
        self.answers()

        self.run_curate()

        self.assertIn(
            "left out of these sessions: 2 prompts that a plugin, a task or another agent sent, "
            "1 suggestion that was only accepted, 1 text without Claude Code's mark of who sent it",
            self.info(),
        )

    def test_the_first_reading_goes_back_a_day_and_the_next_starts_where_it_ended(self) -> None:
        """Covers: B115"""
        self.reading()
        self.typed("we talked about the shed two days ago", START - 30 * HOUR)
        self.typed(DANA_SAID, START - 2 * HOUR)
        self.typed("I still have to call Sam about the ladder", START + 3 * HOUR)
        self.answers()

        self.run_curate()
        self.clock = START + DAY
        self.run_curate()

        self.assertEqual(self.prompts_asked(), [[DANA_SAID], ["I still have to call Sam about the ladder"]])
        self.assertEqual(self.kept()["read_until"], (START + DAY).isoformat())

    def test_a_reading_goes_back_seven_days_at_most_and_says_what_it_left(self) -> None:
        """Covers: B115"""
        self.reading()
        self.read_until(START - 10 * DAY)
        self.typed("we talked about the shed last week", START - 8 * DAY)
        self.typed(DANA_SAID, START - 6 * DAY)
        self.answers()

        self.run_curate()

        self.assertEqual(self.prompts_asked(), [[DANA_SAID]])
        self.assertIn(
            f"what was typed before {START - 7 * DAY:%Y-%m-%d %H:%M} was not read: a reading goes back 7 days at most",
            self.info(),
        )

    def test_a_run_that_starts_before_the_last_reading_ended_reads_nothing_and_keeps_its_end(self) -> None:
        self.reading()
        self.read_until(START + HOUR)
        self.typed(DANA_SAID, START - HOUR)
        self.answers(DANA)

        self.run_curate()

        self.assertEqual(self.steps()[1], ("glean", "skipped"))
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.kept()["read_until"], (START + HOUR).isoformat())

    def test_the_deadline_of_the_run_counts_the_reading_as_three_more_model_steps(self) -> None:
        self.reading()
        seen = self.addon("worklog", "before_ingest")

        self.run_curate()

        (step,) = [json.loads(line) for line in seen.read_text(encoding="utf-8").splitlines()]
        deadline = datetime.datetime.fromisoformat(step["record"]["deadline_at"])
        supervised = 7 * (datetime.timedelta(minutes=15) + datetime.timedelta(seconds=model.DEFAULT_GRACE_SECONDS))
        fetch = 2 * datetime.timedelta(seconds=5)
        self.assertEqual(deadline - START, fetch + supervised + test_runner.runner.CODE_STEPS_MARGIN)


class FoldersLeftOutTest(GleanStepTest):
    def test_a_session_in_a_folder_that_is_left_out_does_not_reach_the_model(self) -> None:
        """Covers: B116"""
        client = self.machine.home / "code" / "acme"
        private = self.machine.home / "private"
        self.reading(distillate={"skip_under": [str(private)]})
        save_profile(
            self.store,
            {"version": 2, "owner": "Alex", "language": "en", "worklog_leave_out": {"path_under": ["~/code/acme"]}},
        )
        self.typed(
            "Kim Lee leads Acme's IT and wants the report on Friday", START - 3 * HOUR, "acme", str(client / "app")
        )
        self.typed("the doctor moved my appointment to Tuesday", START - 2 * HOUR, "private", str(private))
        self.typed(DANA_SAID, START - HOUR)
        self.answers()

        self.run_curate()

        self.assertEqual(self.prompts_asked(), [[DANA_SAID]])
        self.assertIn("2 sessions in a folder that is left out were not read", self.info())

    def test_a_session_whose_folder_cannot_be_compared_is_left_out(self) -> None:
        """Covers: B116"""
        self.reading()
        self.typed("the doctor moved my appointment to Tuesday", START - 2 * HOUR, "somewhere", "")
        self.typed(DANA_SAID, START - HOUR)
        self.answers()

        self.run_curate()

        self.assertEqual(self.prompts_asked(), [[DANA_SAID]])
        self.assertIn("1 session in a folder that is left out was not read", self.info())

    def test_when_every_session_is_in_such_a_folder_no_model_starts(self) -> None:
        """Covers: B116"""
        self.reading()
        save_profile(
            self.store,
            {"version": 2, "owner": "Alex", "language": "en", "worklog_leave_out": {"path_under": ["code/acme"]}},
        )
        self.typed("Kim Lee leads Acme's IT", START - HOUR, "acme", str(self.machine.home / "code" / "acme"))
        self.answers(DANA)

        self.run_curate()

        self.assertEqual(self.steps()[1], ("glean", "skipped"))
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.info(), ["1 session in a folder that is left out was not read"])


class RemotesLeftOutTest(GleanStepTest):
    GLOBEX = "https://git.globex.example/globex-ag/portal.git"

    def leaving_out(self, *parts: str) -> None:
        self.reading()
        left_out = {"git_remote_contains": list(parts)}
        save_profile(self.store, {"version": 2, "owner": "Alex", "language": "en", "worklog_leave_out": left_out})

    def started_in(self, folder: str, *remotes: str) -> None:
        """What the session-start hook noted for a folder that is gone by the time of the run."""
        notes = self.machine.state_dir / session_remotes.NOTES_FOLDER
        session_remotes.note(notes, folder, frozenset(remotes), START - DAY, lambda path, text: path.write_text(text))

    def test_a_session_of_a_repository_named_by_its_remote_does_not_reach_the_model(self) -> None:
        """Covers: B152"""
        self.leaving_out("github.com/globex-ag/", "git.globex.example/")
        self.started_in("/home/alex/worktrees/portal-fix", self.GLOBEX)
        self.started_in("/home/alex/worktrees/portal-ssh", "git@github.com:Globex-AG/portal.git")
        self.started_in("/home/alex/projects/shed", "git@github.com:alex/shed.git")
        self.typed("Kim Lee leads Globex's IT", START - 3 * HOUR, "fix", "/home/alex/worktrees/portal-fix")
        self.typed("Kim wants the report on Friday", START - 2 * HOUR, "ssh", "/home/alex/worktrees/portal-ssh")
        self.typed(DANA_SAID, START - HOUR)
        self.answers()

        self.run_curate()

        self.assertEqual(self.prompts_asked(), [[DANA_SAID]])
        self.assertIn("2 sessions of a repository that is left out were not read", self.info())

    def test_a_session_whose_remotes_nobody_can_tell_is_not_read_and_counted(self) -> None:
        """Covers: B152"""
        self.leaving_out("globex-ag/")
        self.started_in("/home/alex/projects/shed")
        self.typed("Kim Lee leads Globex's IT", START - 3 * HOUR, "fix", "/home/alex/worktrees/portal-fix")
        self.typed("Kim wants the report on Friday", START - 2 * HOUR, "docs", "/home/alex/worktrees/portal-docs")
        self.typed(DANA_SAID, START - HOUR)
        self.answers()

        self.run_curate()

        self.assertEqual(self.prompts_asked(), [[DANA_SAID]])
        self.assertIn(
            "2 sessions were not read, because no git remote is known for their folders (the folders are gone or "
            "git did not answer) and the profile leaves work out by git remote",
            self.info(),
        )

    def test_on_a_machine_without_a_git_to_start_a_session_nobody_noted_is_not_read(self) -> None:
        """Covers: B152"""
        self.leaving_out("globex-ag/")
        there = self.machine.home / "code" / "shed"
        there.mkdir(parents=True)
        self.typed("the doctor moved my appointment to Tuesday", START - 2 * HOUR, "there", str(there))
        self.started_in("/home/alex/projects/shed")
        self.typed(DANA_SAID, START - HOUR)
        self.answers()

        with mock.patch.object(folders_left_out, "usable_git", return_value=None):
            self.run_curate()

        self.assertEqual(self.prompts_asked(), [[DANA_SAID]])
        self.assertIn(
            "1 session was not read, because no git remote is known for its folder (the folder is gone or git did "
            "not answer) and the profile leaves work out by git remote",
            self.info(),
        )

    def test_while_the_profile_names_no_remote_a_session_in_a_folder_that_is_gone_is_read(self) -> None:
        """Covers: B152"""
        self.leaving_out()
        self.typed(DANA_SAID, START - HOUR)
        self.answers()

        self.run_curate()

        self.assertEqual(self.prompts_asked(), [[DANA_SAID]])
        self.assertFalse((self.machine.state_dir / session_remotes.NOTES_FOLDER).exists())


PROJECT_LESSON = {
    "kind": "lesson",
    "text": "Never push to main here.",
    "quote": "do not push to main here",
    "session": 1,
    "topic": None,
    "due": None,
    "lesson": {
        "kind": "knowledge",
        "target": "this project",
        "words": [],
        "quote": "again, never push to main",
        "session": 2,
    },
}


class ProjectLessonTest(GleanStepTest):
    def two_sessions(self, first_remote: str, second_remote: str) -> None:
        self.reading()
        notes = self.machine.state_dir / session_remotes.NOTES_FOLDER
        for folder, remote in (
            ("/home/alex/projects/portal", first_remote),
            ("/home/alex/trees/portal-fix", second_remote),
        ):
            session_remotes.note(
                notes, folder, frozenset([remote]), START - HOUR, lambda path, text: path.write_text(text)
            )
        self.typed("do not push to main here", START - 3 * HOUR, "one", "/home/alex/projects/portal")
        self.typed("again, never push to main", START - 2 * HOUR, "two", "/home/alex/trees/portal-fix")
        self.answers(PROJECT_LESSON, verdicts=[{"lesson": 1, "verdict": "none"}])

    def test_a_lesson_for_this_project_is_for_the_repository_both_sessions_worked_in(self) -> None:
        """Covers: B270"""
        self.two_sessions("git@github.com:Acme/portal.git", "https://github.com/acme/portal")

        self.assertEqual(self.run_curate().state, SUCCEEDED)

        (entry,) = self.kept()["proposals"].values()
        self.assertEqual(entry["kind"], "lesson")
        self.assertEqual(entry["lesson"]["target"], "github.com/acme/portal")
        self.assertEqual(entry["lesson"]["session"], "two")
        # No file the sessions load says it, so it is a fix that adds it to the project's CLAUDE.md.
        self.assertEqual(
            entry["lesson"]["at_source"],
            {
                "verdict": "fix",
                "file": "CLAUDE.md in github.com/acme/portal",
                "line": None,
                "wording": "Never push to main here.",
                "path": "CLAUDE.md",
                "repositories": ["github.com/acme/portal"],
            },
        )

    def test_the_sources_of_a_lesson_are_checked_by_a_second_model_run_with_the_files_its_sessions_load(self) -> None:
        """Covers: B274"""
        self.two_sessions("git@github.com:acme/portal.git", "git@github.com:acme/portal.git")
        claude_md = self.claude_settings.parent / "CLAUDE.md"
        claude_md.write_text("# Global\n- Never push to main; open a pull request.\n", encoding="utf-8")
        self.answers(PROJECT_LESSON, verdicts=[{"lesson": 1, "verdict": "right", "source": 1, "line": 2}])

        self.assertEqual(self.run_curate().state, SUCCEEDED)

        _, check = self.asked()
        self.assertEqual(check["instruction"], lesson_sources.instruction())
        self.assertEqual(check["lessons"][0]["said"], ["do not push to main here", "again, never push to main"])
        self.assertIn("2: - Never push to main; open a pull request.", check["sources"][0]["lines"])
        (entry,) = self.kept()["proposals"].values()
        self.assertEqual(entry["lesson"]["at_source"]["verdict"], "stated")
        self.assertEqual(entry["lesson"]["at_source"]["line"], "- Never push to main; open a pull request.")

    def test_a_check_of_the_sources_without_an_answer_leaves_the_lesson_out_and_says_why(self) -> None:
        """Covers: B274"""
        self.two_sessions("git@github.com:acme/portal.git", "git@github.com:acme/portal.git")

        self.answers(PROJECT_LESSON, verdicts=[])
        script = json.loads(self.actions.read_text(encoding="utf-8"))
        script["text"][1] = {"answer": "no idea", "outcome": "success"}
        self.actions.write_text(json.dumps(script), encoding="utf-8")

        self.assertEqual(self.run_curate().state, SUCCEEDED)

        self.assertEqual(self.kept()["proposals"], {})
        self.assertTrue(
            any(note.startswith("1 lesson left out: their sources could not be checked") for note in self.info())
        )

    def test_a_lesson_that_could_never_be_kept_or_is_kept_already_is_not_proposed(self) -> None:
        """Covers: B270"""
        self.reading()
        before = (START - 4 * HOUR).astimezone(datetime.timezone.utc)
        self.record(test_sessions.answered("Running.", before, "scripts/check", "ruff --select=E,W"), "one")
        self.typed("only the quick round please", START - 3 * HOUR, "one")
        self.typed("again only the quick round", START - 2 * HOUR, "two")
        action = {
            **PROJECT_LESSON,
            "text": "Run only the quick checks.",
            "quote": "only the quick round please",
            "lesson": {
                "kind": "action",
                "target": "every project",
                "words": ["--select=E,W"],
                "quote": "again only the quick round",
                "session": 2,
            },
        }
        known = {**action, "lesson": {**action["lesson"], "words": ["scripts/check"]}}
        self.write(
            "memory/lessons/quick.md",
            "---\nkind: action\ntarget: every project\nkept: 2026-11-01\nwords: [scripts/check]\n---\n"
            "# Quick\n\nRun only the quick checks.\n",
        )
        self.answers(action, known)

        self.assertEqual(self.run_curate().state, SUCCEEDED)

        self.assertEqual(self.kept()["proposals"], {})
        self.assertIn("1 lesson left out: not in the form a lesson is kept in", self.info())
        self.assertIn("1 lesson left out: a lesson like it is kept already", self.info())

    def test_without_a_repository_both_sessions_worked_in_the_lesson_is_left_out_and_counted(self) -> None:
        """Covers: B270"""
        self.two_sessions("git@github.com:acme/portal.git", "git@github.com:acme/shop.git")

        self.assertEqual(self.run_curate().state, SUCCEEDED)

        self.assertEqual(self.kept()["proposals"], {})
        self.assertEqual(self.kept()["counts"]["lesson"]["not_quoted"], 1)
        self.assertIn(
            "1 lesson for one project left out: no repository is known that its sessions worked in", self.info()
        )


class InPortalTest(GleanStepTest):
    PORTAL = "/home/alex/projects/portal"

    def portal_noted(self, folder: str = PORTAL, remote: str = "git@github.com:acme/portal.git") -> None:
        notes = self.machine.state_dir / session_remotes.NOTES_FOLDER
        session_remotes.note(notes, folder, frozenset([remote]), START - HOUR, lambda path, text: path.write_text(text))


class ProjectProposalTest(InPortalTest):
    def days_file(self) -> Any:
        return json.loads((self.machine.state_dir / project_proposals.DAYS_FILE).read_text(encoding="utf-8"))

    def remembered(self, *days: str) -> None:
        self.machine.state_dir.mkdir(parents=True, exist_ok=True)
        (self.machine.state_dir / project_proposals.DAYS_FILE).write_text(
            json.dumps({"days": {"github.com/acme/portal": list(days)}}), encoding="utf-8"
        )

    def project_entries(self) -> list[dict[str, Any]]:
        return [entry for entry in self.kept()["proposals"].values() if entry["kind"] == "project"]

    def test_a_repository_worked_in_on_two_days_without_a_topic_is_proposed_as_a_project(self) -> None:
        """Covers: B275"""
        self.reading()
        self.portal_noted()
        self.read_until(START - 3 * DAY)
        self.typed("the login page needs a second button", START - 2 * DAY, "one", self.PORTAL)
        self.typed("now the footer", START - HOUR, "two", self.PORTAL)
        self.answers()

        self.assertEqual(self.run_curate().state, SUCCEEDED)

        (entry,) = self.project_entries()
        self.assertEqual(
            (entry["quote"], entry["source"], entry["day"], entry["state"]),
            ("github.com/acme/portal", "worked", "2026-11-07", "open"),
        )
        self.assertEqual(
            entry["text"],
            "portal (github.com/acme/portal) is a repository you worked in on 2026-11-05 and 2026-11-07, "
            "with no topic: keep it as a project",
        )
        self.assertEqual(self.kept()["format"], 4)
        self.assertIn("1 repository without a topic was worked in on two days and proposed as a project", self.info())
        self.assertEqual(self.days_file(), {"days": {"github.com/acme/portal": ["2026-11-05", "2026-11-07"]}})

    def test_a_project_that_waits_already_is_not_proposed_or_announced_again(self) -> None:
        """Covers: B275"""
        self.reading()
        self.portal_noted()
        self.remembered("2026-11-02")
        waiting = project_proposals.proposal(("github.com/acme/portal",), [datetime.date(2026, 11, 2)])
        added = proposals.add(proposals.Proposals({}), [proposals.Said(waiting, datetime.date(2026, 11, 2))], START)
        proposals.save(self.store, added.proposals)
        self.typed("now the footer", START - HOUR, "two", self.PORTAL)
        self.answers()

        self.run_curate()

        (entry,) = self.project_entries()
        self.assertIn("on 2026-11-02 and 2026-11-02", entry["text"])
        self.assertFalse(any("proposed as a project" in note for note in self.info()))

    def test_a_day_remembered_from_an_earlier_reading_is_one_of_the_two(self) -> None:
        """Covers: B275"""
        self.reading()
        self.portal_noted()
        self.remembered("2026-11-02")
        self.typed("now the footer", START - HOUR, "two", self.PORTAL)
        self.answers()

        self.run_curate()

        (entry,) = self.project_entries()
        self.assertIn("on 2026-11-02 and 2026-11-07", entry["text"])

    def test_one_day_proposes_nothing_and_is_remembered_and_a_day_older_than_30_days_is_forgotten(self) -> None:
        """Covers: B275"""
        self.reading()
        self.portal_noted()
        self.remembered("2026-10-07")
        self.typed("now the footer", START - HOUR, "two", self.PORTAL)
        self.answers()

        self.run_curate()

        self.assertEqual(self.project_entries(), [])
        self.assertEqual(self.days_file(), {"days": {"github.com/acme/portal": ["2026-11-07"]}})

    def test_a_repository_a_topic_names_or_whose_capture_waits_is_not_proposed(self) -> None:
        """Covers: B275"""
        for known in (
            (
                "memory/MEMORY.md",
                "# Memory\n\n## Facts\n\n### Portal (portal)\n- Repository: github.com/acme/portal (portal.md)\n",
            ),
            (
                "inbox/20261106-0900-cli.md",
                "---\ncreated: 2026-11-06T09:00:00+00:00\nsource: cli\n---\n"
                "Keep this project: portal\nRepository: github.com/acme/portal\n",
            ),
        ):
            with self.subTest(known[0]):
                self.setUp()
                self.reading()
                self.portal_noted()
                self.remembered("2026-11-02")
                self.write(*known)
                self.typed("now the footer", START - HOUR, "two", self.PORTAL)
                self.answers()

                self.run_curate()

                self.assertEqual(self.project_entries(), [])

    def test_a_session_in_a_folder_left_out_or_without_a_noted_remote_counts_for_no_repository(self) -> None:
        """Covers: B275"""
        self.reading()
        client = str(self.machine.home / "code" / "portal")
        save_profile(
            self.store,
            {"version": 2, "owner": "Alex", "language": "en", "worklog_leave_out": {"path_under": ["~/code/portal"]}},
        )
        self.portal_noted(client)
        self.remembered("2026-11-02")
        self.typed("now the footer", START - HOUR, "two", client)
        self.typed("the shed needs paint", START - 2 * HOUR, "shed", "/home/alex/projects/shed")
        self.answers()

        self.run_curate()

        self.assertEqual(self.project_entries(), [])
        self.assertEqual(self.days_file(), {"days": {"github.com/acme/portal": ["2026-11-02"]}})

    def test_a_reading_that_fails_remembers_no_day(self) -> None:
        """Covers: B275"""
        self.reading()
        self.portal_noted()
        self.typed("now the footer", START - HOUR, "two", self.PORTAL)
        self.answers(outcome="error")

        self.run_curate()

        self.assertFalse((self.machine.state_dir / project_proposals.DAYS_FILE).exists())


FULL_CHECK = {
    "matter": "the whole proof is run again although CI ran it on the same code",
    "quote": "why the full check again",
    "session": 1,
    "kind": "action",
    "target": "every project",
}


class RememberedCorrectionTest(InPortalTest):
    def corrections_file(self) -> Any:
        return json.loads((self.machine.state_dir / remembered_corrections.FILE).read_text(encoding="utf-8"))

    def corrected(self, session: str = "one", hours_ago: int = 2) -> None:
        before = (START - (hours_ago + 1) * HOUR).astimezone(datetime.timezone.utc)
        self.record(test_sessions.answered("Running the proof.", before, "scripts/check"), session)
        self.typed("why the full check again, CI ran it", START - hours_ago * HOUR, session, self.PORTAL)

    def test_a_correction_in_one_session_is_remembered_in_machine_state_and_not_proposed(self) -> None:
        """Covers: B297"""
        self.reading()
        self.portal_noted()
        self.corrected()
        self.answers(singles=[FULL_CHECK])

        self.assertEqual(self.run_curate().state, SUCCEEDED)

        self.assertEqual(self.kept()["proposals"], {})
        (entry,) = self.corrections_file()["corrections"]
        self.assertEqual(
            {key: value for key, value in entry.items() if key != "id"},
            {
                "session": "one",
                "day": "2026-11-07",
                "quote": "why the full check again",
                "commands": ["scripts/check"],
                "addresses": ["github.com/acme/portal"],
                "matter": "the whole proof is run again although CI ran it on the same code",
                "kind": "action",
                "target": "every project",
            },
        )
        self.assertIn("1 unsure correction remembered: unclear whether it holds beyond its task", self.info())

    def test_a_correction_a_lesson_of_the_same_answer_stands_on_is_not_remembered(self) -> None:
        """Covers: B297"""
        self.reading()
        self.portal_noted()
        self.corrected("one", 3)
        self.typed("no full check without a reason", START - HOUR, "two", self.PORTAL)
        lesson = {
            "kind": "lesson",
            "text": "Run the whole proof only with a reason.",
            "quote": "why the full check again",
            "session": 1,
            "topic": None,
            "due": None,
            "lesson": {
                "kind": "knowledge",
                "target": "every project",
                "words": [],
                "quote": "no full check without a reason",
                "session": 2,
            },
        }
        self.answers(
            lesson,
            singles=[FULL_CHECK, {**FULL_CHECK, "quote": "no full check without a reason", "session": 2}],
            verdicts=[{"lesson": 1, "verdict": "none"}],
        )

        self.assertEqual(self.run_curate().state, SUCCEEDED)

        self.assertEqual(len(self.kept()["proposals"]), 1)
        self.assertFalse((self.machine.state_dir / remembered_corrections.FILE).exists())

    def test_a_correction_whose_words_were_not_typed_or_that_is_not_in_the_form_is_counted_apart(self) -> None:
        """Covers: B297"""
        self.reading()
        self.portal_noted()
        self.corrected()
        self.answers(singles=[{**FULL_CHECK, "quote": "never run the full check"}, {**FULL_CHECK, "kind": "rule"}])

        self.assertEqual(self.run_curate().state, SUCCEEDED)

        self.assertFalse((self.machine.state_dir / remembered_corrections.FILE).exists())
        self.assertIn("2 unsure corrections left out: not in the form or not in what was typed in it", self.info())
        self.assertEqual(self.kept()["counts"]["lesson"]["not_quoted"], 0)

    def test_a_correction_for_one_project_without_a_known_repository_is_not_remembered(self) -> None:
        """Covers: B297"""
        self.reading()
        self.corrected()
        self.answers(singles=[{**FULL_CHECK, "target": "this project"}])

        self.assertEqual(self.run_curate().state, SUCCEEDED)

        self.assertFalse((self.machine.state_dir / remembered_corrections.FILE).exists())
        self.assertIn(
            "1 unsure correction for one project left out: no repository is known for its session",
            self.info(),
        )

    def test_corrections_older_than_30_days_and_beyond_300_are_forgotten_the_oldest_first(self) -> None:
        """Covers: B297"""
        self.reading()
        self.portal_noted()
        earlier = [
            remembered_corrections.Correction(
                f"old{number:03d}",
                f"s{number}",
                datetime.date(2026, 11, 6) - datetime.timedelta(days=number % 29),
                "only the quick round",
                (),
                (),
                "the whole proof",
                "knowledge",
                "every project",
            )
            for number in range(300)
        ]
        outdated = dataclasses.replace(earlier[0], id="outdated", day=datetime.date(2026, 10, 8))
        written = remembered_corrections.remember(
            self.machine.state_dir, [*earlier, outdated], datetime.date(2026, 10, 9), self.machine.temp_dir
        )
        self.assertIsNone(written)
        self.corrected()
        self.answers(singles=[FULL_CHECK])

        self.run_curate()

        ids = [entry["id"] for entry in self.corrections_file()["corrections"]]
        self.assertEqual(len(ids), remembered_corrections.MOST)
        self.assertNotIn("outdated", ids)
        self.assertIn(remembered_corrections.correction_id("one", START - 2 * HOUR), ids)
        oldest = min(earlier, key=lambda each: each.day)
        self.assertEqual(
            sum(each.day == oldest.day for each in earlier) - 1,
            sum(entry["day"] == oldest.day.isoformat() for entry in self.corrections_file()["corrections"]),
        )

    def test_a_period_read_again_remembers_no_correction_twice_whatever_words_of_its_prompt_are_quoted(self) -> None:
        """Covers: B297"""
        self.reading()
        self.portal_noted()
        self.corrected()
        self.answers(singles=[FULL_CHECK])
        self.run_curate()
        self.read_until(START - 2 * DAY)
        self.answers(singles=[{**FULL_CHECK, "quote": "the full check again, CI ran it"}])

        self.run_curate()

        self.assertEqual(len(self.corrections_file()["corrections"]), 1)
        self.assertFalse(any("unsure correction remembered" in note for note in self.info()))

    def test_a_reading_that_fails_remembers_no_correction(self) -> None:
        """Covers: B297"""
        self.reading()
        self.portal_noted()
        self.corrected()
        self.answers(singles=[FULL_CHECK], outcome="error")

        self.run_curate()

        self.assertFalse((self.machine.state_dir / remembered_corrections.FILE).exists())

    def test_a_file_that_cannot_be_read_is_said_and_the_reading_goes_on(self) -> None:
        """Covers: B297"""
        self.reading()
        self.portal_noted()
        self.machine.state_dir.mkdir(parents=True, exist_ok=True)
        (self.machine.state_dir / remembered_corrections.FILE).write_text("{not json", encoding="utf-8")
        self.corrected()
        self.answers(DANA, singles=[FULL_CHECK])
        self.typed(DANA_SAID, START - HOUR, "one", self.PORTAL)

        self.assertEqual(self.run_curate().state, SUCCEEDED)

        self.assertEqual(len(self.kept()["proposals"]), 1)
        self.assertEqual(len(self.corrections_file()["corrections"]), 1)
        self.assertTrue(
            any(note.startswith("the corrections remembered from earlier readings were lost:") for note in self.info())
        )

    def test_a_file_that_cannot_be_written_is_said_and_the_proposals_are_kept(self) -> None:
        """Covers: B297"""
        self.reading()
        self.portal_noted()
        self.corrected()
        self.answers(singles=[FULL_CHECK])

        with mock.patch.object(remembered_corrections, "write_text_atomically", side_effect=OSError("disk full")):
            self.assertEqual(self.run_curate().state, SUCCEEDED)

        self.assertIn("the unsure corrections could not be remembered: disk full", self.info())
        self.assertEqual(self.kept()["read_until"], START.isoformat())


ONE_CORRECTION = {
    "kind": "lesson",
    "text": "Run the whole proof only with a reason.",
    "quote": "why the full check again",
    "session": 1,
    "topic": None,
    "due": None,
    "lesson": {"kind": "action", "target": "every project", "words": ["scripts/check"]},
}


class OneCorrectionLessonTest(InPortalTest):
    def corrected(self) -> None:
        before = (START - 3 * HOUR).astimezone(datetime.timezone.utc)
        self.record(test_sessions.answered("Running the proof.", before, "scripts/check"), "one")
        self.typed("why the full check again, CI ran it", START - 2 * HOUR, "one", self.PORTAL)

    def test_a_correction_beyond_the_task_in_one_session_is_proposed_as_a_lesson(self) -> None:
        """Covers: B270"""
        self.reading()
        self.portal_noted()
        self.corrected()
        self.answers(ONE_CORRECTION, verdicts=[{"lesson": 1, "verdict": "none"}])

        self.assertEqual(self.run_curate().state, SUCCEEDED)

        (entry,) = self.kept()["proposals"].values()
        self.assertEqual((entry["kind"], entry["quote"]), ("lesson", "why the full check again"))
        self.assertEqual((entry["lesson"]["quote"], entry["lesson"]["session"]), ("", ""))
        self.assertEqual(entry["lesson"]["words"], ["scripts/check"])
        _, check = self.asked()
        self.assertEqual(check["lessons"][0]["said"], ["why the full check again"])
        self.assertFalse((self.machine.state_dir / remembered_corrections.FILE).exists())

    def test_a_lesson_for_one_project_on_one_correction_is_for_its_sessions_repository(self) -> None:
        """Covers: B270"""
        self.reading()
        self.portal_noted()
        self.corrected()
        for_the_project = {**ONE_CORRECTION, "lesson": {**ONE_CORRECTION["lesson"], "target": "this project"}}
        self.answers(for_the_project, verdicts=[{"lesson": 1, "verdict": "none"}])

        self.assertEqual(self.run_curate().state, SUCCEEDED)

        (entry,) = self.kept()["proposals"].values()
        self.assertEqual(entry["lesson"]["target"], "github.com/acme/portal")
        _, check = self.asked()
        self.assertEqual(check["lessons"][0]["said"], ["why the full check again"])

    def test_a_lesson_for_one_project_on_one_correction_without_a_known_repository_is_left_out(self) -> None:
        """Covers: B270"""
        self.reading()
        self.corrected()
        self.answers({**ONE_CORRECTION, "lesson": {**ONE_CORRECTION["lesson"], "target": "this project"}})

        self.assertEqual(self.run_curate().state, SUCCEEDED)

        self.assertEqual(self.kept()["proposals"], {})
        self.assertIn(
            "1 lesson for one project left out: no repository is known that its sessions worked in", self.info()
        )


POINTER = {
    "kind": "pointer",
    "text": "Login moves to the customer's identity provider in March.",
    "quote": "the login moves to the customer's identity provider in March",
    "session": 1,
    "topic": None,
    "due": None,
    "file": "docs/records/014-login.md",
}
PORTAL_TOPIC = (
    "# Memory\n\n## Facts\n\n### Acme portal (portal)\n- Repository: github.com/acme/portal (acme-portal.md)\n"
)


class PointerProposalTest(InPortalTest):
    def decided(self, *written: str) -> None:
        self.reading()
        self.portal_noted()
        self.typed(POINTER["quote"] + ", write that into the record", START - 2 * HOUR, "one", self.PORTAL)
        when = (START - 2 * HOUR + datetime.timedelta(minutes=1)).astimezone(datetime.timezone.utc)
        self.record(test_sessions.wrote(when, *(("Write", path) for path in written), cwd=self.PORTAL), "one")

    def test_a_decision_a_session_wrote_into_a_file_of_a_project_is_proposed_as_a_pointer_to_it(self) -> None:
        """Covers: B278"""
        self.decided(self.PORTAL + "/docs/records/014-login.md", "/home/alex/.claude/CLAUDE.md")
        self.write("memory/MEMORY.md", PORTAL_TOPIC)
        self.answers(POINTER)

        self.assertEqual(self.run_curate().state, SUCCEEDED)

        (asked,) = self.asked()
        self.assertEqual(asked["sessions"][0]["written"], ["docs/records/014-login.md"])
        (entry,) = self.kept()["proposals"].values()
        self.assertEqual(
            (entry["kind"], entry["text"], entry["topic"]),
            (
                "pointer",
                "Login moves to the customer's identity provider in March → docs/records/014-login.md",
                "Acme portal",
            ),
        )
        self.assertEqual(
            entry["pointer"], {"path": "docs/records/014-login.md", "repositories": ["github.com/acme/portal"]}
        )
        self.assertEqual(self.kept()["format"], 4)

    def test_a_session_in_a_subfolder_whose_note_names_no_top_names_its_files_from_the_repositorys_folder(
        self,
    ) -> None:
        """Covers: B278"""
        top = self.machine.home / "code" / "portal"
        (top / ".git").mkdir(parents=True)
        subfolder = str(top / "plugins")
        self.reading()
        self.portal_noted(subfolder)
        self.typed(POINTER["quote"] + ", write that into the record", START - 2 * HOUR, "one", subfolder)
        when = (START - 2 * HOUR + datetime.timedelta(minutes=1)).astimezone(datetime.timezone.utc)
        self.record(test_sessions.wrote(when, ("Write", str(top / "docs/records/014-login.md")), cwd=subfolder), "one")
        self.write("memory/MEMORY.md", PORTAL_TOPIC)
        self.answers(POINTER)

        self.run_curate()

        self.assertEqual(self.asked()[0]["sessions"][0]["written"], ["docs/records/014-login.md"])

    def test_a_decision_written_into_no_file_of_the_repository_is_no_pointer(self) -> None:
        """Covers: B278"""
        self.decided()
        self.write("memory/MEMORY.md", PORTAL_TOPIC)
        self.answers(POINTER)

        self.run_curate()

        self.assertNotIn("written", self.asked()[0]["sessions"][0])
        self.assertEqual(self.kept()["proposals"], {})
        self.assertEqual(self.kept()["counts"]["pointer"]["not_quoted"], 1)

    def test_without_a_project_topic_the_model_sees_no_file_and_no_pointer_is_kept(self) -> None:
        """Covers: B278"""
        self.decided(self.PORTAL + "/docs/records/014-login.md")
        self.answers(POINTER)

        self.run_curate()

        self.assertNotIn("written", self.asked()[0]["sessions"][0])
        self.assertEqual([entry["kind"] for entry in self.kept()["proposals"].values()], [])


class CorrectedAgainTest(GleanStepTest):
    def test_a_correction_of_a_kept_lesson_is_counted_under_it_and_said(self) -> None:
        """Covers: B280"""
        self.reading()
        self.write(
            "memory/lessons/quick.md",
            "---\nkind: knowledge\ntarget: every project\nkept: 2026-11-01\n---\n"
            "# Quick\n\nRun only the quick checks.\n",
        )
        self.typed("no, again only the quick round please", START - HOUR)
        self.model({})
        script = json.loads(self.actions.read_text(encoding="utf-8"))
        said = {"lesson": "quick.md", "quote": "again only the quick round", "session": 1}
        script["text"] = {"answer": json.dumps({"proposals": [], "corrected_again": [said]}), "outcome": "success"}
        self.actions.write_text(json.dumps(script), encoding="utf-8")

        self.assertEqual(self.run_curate().state, SUCCEEDED)

        (asked,) = self.asked()
        self.assertEqual(
            asked["lessons"], [{"name": "quick.md", "text": "Run only the quick checks.", "kept": "2026-11-01"}]
        )
        self.assertEqual(lesson_counts.corrected_again(self.store, {"quick.md": "2026-11-01"}), {"quick.md": 1})
        self.assertIn("1 correction of a kept lesson counted: Claude was corrected on it again", self.info())

    def test_a_lesson_kept_as_a_fix_is_shown_and_counted_under_the_fixs_name(self) -> None:
        """Covers: B289"""
        self.reading()
        fix = fixes.new_fix(
            "~/.claude/CLAUDE.md",
            (),
            "sb-test-m1",
            "- Run the whole proof.",
            "- Run the quick checks.",
            "you said it twice",
            "2026-11-01",
            lesson="Run only the quick checks.",
        )
        fixes.keep(self.store, fix)
        dropped = fixes.new_fix(
            "~/.claude/CLAUDE.md", (), "sb-test-m1", None, "- Something else.", "why", "2026-11-01", lesson="Other."
        )
        fixes.keep(self.store, dropped)
        fixes.settle(self.store, dropped.name, fixes.DROPPED)
        self.typed("no, again only the quick round please", START - HOUR)
        self.model({})
        script = json.loads(self.actions.read_text(encoding="utf-8"))
        said = {"lesson": fix.name, "quote": "again only the quick round", "session": 1}
        script["text"] = {"answer": json.dumps({"proposals": [], "corrected_again": [said]}), "outcome": "success"}
        self.actions.write_text(json.dumps(script), encoding="utf-8")

        self.assertEqual(self.run_curate().state, SUCCEEDED)

        (asked,) = self.asked()
        self.assertEqual(
            asked["lessons"], [{"name": fix.name, "text": "Run only the quick checks.", "kept": "2026-11-01"}]
        )
        self.assertEqual(lesson_counts.corrected_again(self.store, {fix.name: "2026-11-01"}), {fix.name: 1})

    def test_fixes_that_cannot_be_read_keep_their_counts_and_nothing_is_counted(self) -> None:
        """Covers: B289"""
        self.reading()
        self.write(
            "memory/lessons/quick.md",
            "---\nkind: knowledge\ntarget: every project\nkept: 2026-11-01\n---\n"
            "# Quick\n\nRun only the quick checks.\n",
        )
        counts = {"format": 1, "lessons": {"fix-3f9c2a71b0de": {"kept": "2026-11-01", "corrected_again": ["a1"]}}}
        self.write(lesson_counts.COUNTS_FILE, json.dumps(counts))
        self.typed("no, again only the quick round please", START - HOUR)
        self.model({})
        script = json.loads(self.actions.read_text(encoding="utf-8"))
        said = {"lesson": "quick.md", "quote": "again only the quick round", "session": 1}
        script["text"] = {"answer": json.dumps({"proposals": [], "corrected_again": [said]}), "outcome": "success"}
        self.actions.write_text(json.dumps(script), encoding="utf-8")

        with mock.patch("m2b.fixes.read_all", side_effect=StoreError("state/core/fixes cannot be listed")):
            self.assertEqual(self.run_curate().state, SUCCEEDED)

        self.assertEqual(json.loads(self.store.read_bytes(lesson_counts.COUNTS_FILE)), counts)
        self.assertTrue(
            any(note.startswith("the corrections of kept lessons were not counted") for note in self.info())
        )

    def test_a_counts_file_that_cannot_be_read_is_said_and_the_proposals_are_kept(self) -> None:
        """Covers: B280"""
        self.reading()
        self.write(lesson_counts.COUNTS_FILE, "{not json")
        self.write(
            "memory/lessons/quick.md",
            "---\nkind: knowledge\ntarget: every project\nkept: 2026-11-01\n---\n"
            "# Quick\n\nRun only the quick checks.\n",
        )
        self.typed(DANA_SAID, START - 2 * HOUR)
        self.typed("no, again only the quick round please", START - HOUR)
        self.model({})
        script = json.loads(self.actions.read_text(encoding="utf-8"))
        said = {"lesson": "quick.md", "quote": "again only the quick round", "session": 1}
        answer = {"proposals": [DANA], "corrected_again": [said]}
        script["text"] = {"answer": json.dumps(answer), "outcome": "success"}
        self.actions.write_text(json.dumps(script), encoding="utf-8")

        self.assertEqual(self.run_curate().state, SUCCEEDED)

        self.assertEqual(list(self.kept()["proposals"]), [DANA_ID])
        self.assertTrue(
            any(note.startswith("the corrections of kept lessons were not counted") for note in self.info())
        )


class LessonRecheckTest(GleanStepTest):
    LESSON = (
        "---\nkind: knowledge\ntarget: every project\nkept: 2026-11-01\n---\n# Quick\n\nRun only the quick checks.\n"
    )

    def stated_in_claude_md(self) -> None:
        self.reading()
        self.write("memory/lessons/quick.md", self.LESSON)
        claude_md = self.claude_settings.parent / "CLAUDE.md"
        claude_md.write_text("# Rules\n\nRun only the quick checks.\n", encoding="utf-8")
        self.typed("the shed roof needs new felt", START - HOUR)

    def test_a_reading_checks_the_block_again_and_keeps_a_stated_lesson_at_its_source(self) -> None:
        """Covers: B291"""
        self.stated_in_claude_md()
        self.model({})
        script = json.loads(self.actions.read_text(encoding="utf-8"))
        verdict = {"verdicts": [{"lesson": 1, "verdict": "right", "source": 1, "line": 3}]}
        script["text"] = [
            {"answer": json.dumps(verdict), "outcome": "success"},
            {"answer": json.dumps({"proposals": []}), "outcome": "success"},
        ]
        self.actions.write_text(json.dumps(script), encoding="utf-8")

        self.assertEqual(self.run_curate().state, SUCCEEDED)

        recheck, reading = self.asked()
        self.assertEqual(recheck["lessons"], [{"lesson": 1, "text": "Run only the quick checks."}])
        self.assertIn("sessions", reading)
        (lesson,) = lessons.read_all(self.store)
        self.assertEqual(lesson.kept_at, "~/.claude/CLAUDE.md")
        self.assertIn(
            "the lesson quick.md is stated in ~/.claude/CLAUDE.md now and left the block, kept at its source",
            self.info(),
        )

    def test_a_check_without_an_answer_is_said_and_the_reading_goes_on(self) -> None:
        """Covers: B291"""
        self.stated_in_claude_md()
        self.model({})
        script = json.loads(self.actions.read_text(encoding="utf-8"))
        script["text"] = [
            {"answer": "", "outcome": "error_max_budget_usd"},
            {"answer": json.dumps({"proposals": []}), "outcome": "success"},
        ]
        self.actions.write_text(json.dumps(script), encoding="utf-8")

        self.assertEqual(self.run_curate().state, SUCCEEDED)

        self.assertIn(("glean", "succeeded"), self.steps())
        (lesson,) = lessons.read_all(self.store)
        self.assertIsNone(lesson.kept_at)
        self.assertTrue(
            any(note.startswith("the kept lessons were not checked again against the files") for note in self.info())
        )


class StartBudgetTest(GleanStepTest):
    KNOWN = "---\nkind: knowledge\ntarget: every project\nkept: {kept}\n---\n# {name}\n\n{text}\n"
    NEW: ClassVar[dict[str, Any]] = {
        "kind": "lesson",
        "text": "Name herdr an agent runtime.",
        "quote": "herdr is an agent runtime, say so",
        "session": 1,
        "topic": None,
        "due": None,
        "lesson": {
            "kind": "knowledge",
            "target": "every project",
            "words": [],
            "quote": "again: herdr is an agent runtime",
            "session": 2,
        },
    }

    LONG = "# Memory\n\n## Facts\n\n" + "".join(f"- Fact number {n} about the shed (shed.md)\n" for n in range(80))
    SHORT = "# Memory\n\n## Facts\n\n- Sam brings plywood (sam.md)\n"
    SECOND: ClassVar[dict[str, Any]] = {
        **NEW,
        "text": "Call the band the band.",
        "quote": "it is the band, not the bar",
        "lesson": {**NEW["lesson"], "quote": "again, the band, not the bar"},
    }

    def proposed(
        self, distillate: str, counted: bool = True, *found: dict[str, Any], full: bool = True
    ) -> list[dict[str, Any]]:
        self.reading()
        self.write("memory/MEMORY.md", distillate)
        self.write("memory/lessons/old.md", self.KNOWN.format(kept="2026-10-01", name="Old", text="Say it once."))
        self.write("memory/lessons/weak.md", self.KNOWN.format(kept="2026-10-20", name="Weak", text="Keep it short."))
        if full:
            self.fill_the_block()
        if counted:
            self.write(
                lesson_counts.COUNTS_FILE,
                json.dumps(
                    {"format": 1, "lessons": {"weak.md": {"kept": "2026-10-20", "corrected_again": ["a1", "b2"]}}}
                ),
            )
        self.typed("herdr is an agent runtime, say so. it is the band, not the bar", START - 3 * HOUR, "one")
        self.typed("again: herdr is an agent runtime. again, the band, not the bar", START - 2 * HOUR, "two")
        entries = found or (self.NEW,)
        self.answers(*entries, verdicts=[{"lesson": n, "verdict": "none"} for n in range(1, len(entries) + 1)])

        self.assertEqual(self.run_curate().state, SUCCEEDED)
        return [dict(entry["lesson"]) for entry in self.kept()["proposals"].values() if entry["state"] == "open"]

    def fill_the_block(self) -> None:
        """Kept lessons until the block is ten characters short of its limit: no new lesson fits."""
        for number in range(10):
            text = f"Filler lesson {number} " + "about a careful way of working " * 6
            self.write(
                f"memory/lessons/f{number}.md", self.KNOWN.format(kept=f"2026-11-{number + 1:02d}", name="F", text=text)
            )
        size = len(lessons.block(lessons.read_all(self.store)))
        self.assertLess(size, lessons.MAX_BLOCK_CHARACTERS - 10)
        last = "Last filler lesson " + "x" * (
            lessons.MAX_BLOCK_CHARACTERS - 10 - size - len("- Last filler lesson ") - 1
        )
        self.write("memory/lessons/g.md", self.KNOWN.format(kept="2026-11-10", name="G", text=last))
        self.assertEqual(len(lessons.block(lessons.read_all(self.store))), lessons.MAX_BLOCK_CHARACTERS - 10)

    def test_a_new_lesson_that_would_pass_the_blocks_limit_names_the_weakest_it_would_replace(self) -> None:
        """Covers: B284"""
        (lesson,) = self.proposed(self.SHORT)

        self.assertEqual(lesson["replaces"], "weak.md")

    def test_without_counts_the_oldest_is_named_and_two_new_lessons_name_two(self) -> None:
        """Covers: B284"""
        (lesson,) = self.proposed(self.SHORT, False)
        self.assertEqual(lesson["replaces"], "old.md")

        self.setUp()
        both = self.proposed(self.SHORT, True, self.NEW, self.SECOND)
        self.assertEqual({each["replaces"] for each in both}, {"weak.md", "old.md"})

    def test_a_lesson_a_waiting_proposal_names_already_is_not_named_again(self) -> None:
        """Covers: B284"""
        waiting = glean.Proposal(
            "lesson",
            "Write dates as days.",
            "write the date as a day",
            "earlier",
            lesson=glean.LessonPart("knowledge", "every project", (), "again a day", "later", replaces="weak.md"),
        )
        added = proposals.add(proposals.Proposals({}), [proposals.Said(waiting, datetime.date(2026, 11, 6))], START)
        proposals.save(self.store, added.proposals)

        (lesson,) = [each for each in self.proposed(self.SHORT) if each["quote"] != "again a day"]

        self.assertEqual(lesson["replaces"], "old.md")

    def test_a_block_with_room_replaces_none_however_long_the_distillate(self) -> None:
        """Covers: B284"""
        for distillate in (self.SHORT, self.LONG):
            with self.subTest(long=distillate is self.LONG):
                self.setUp()
                (lesson,) = self.proposed(distillate, full=False)

                self.assertNotIn("replaces", lesson)


class KeptFixTest(GleanStepTest):
    def test_a_run_names_the_fix_kept_from_a_lesson_in_its_information(self) -> None:
        """Covers: B272"""
        self.curating()
        fix = glean.AtSource(
            glean.FIX, "~/.claude/CLAUDE.md", "- Run the whole proof.", "- Run the quick checks.", "~/.claude/CLAUDE.md"
        )
        lesson = dataclasses.replace(test_proposals.LESSON.lesson, at_source=fix)
        found = dataclasses.replace(test_proposals.LESSON, lesson=lesson)
        added = proposals.add(proposals.load(self.store), [proposals.Said(found, test_proposals.DAY)], START - DAY)
        proposals.save(self.store, added.proposals)
        proposal_answers.give(self.store, [proposals.proposal_id(found)], proposal_answers.KEEP)

        self.assertEqual(self.run_curate().state, SUCCEEDED)

        self.assertIn(
            "a fix you kept waits for ~/.claude/CLAUDE.md: the next session there applies it", self.info("harvest")
        )


class ChecksTest(GleanStepTest):
    def test_a_reading_counts_per_kind_what_it_added_and_what_stood_on_no_words_of_the_person(self) -> None:
        """Covers: B132"""
        self.reading()
        self.typed(DANA_SAID, START - 4 * HOUR)
        self.typed("remember that I would rather sit at the window", START - 3 * HOUR)
        self.write("inbox/20261107T050100Z-cli-a1b2.md", capture("I would rather sit at the window.", 5))
        self.answers(
            DANA,
            {**DANA, "text": "Dana signs the contracts.", "quote": "Dana signs every contract"},
            {**DANA, "kind": "agreement", "text": "Sam brings plywood.", "quote": "Sam brings the plywood on Friday"},
            {**DANA, "kind": "agreement", "text": "Kim sends the offer.", "quote": "Kim sends the offer by Monday"},
            {
                **DANA,
                "kind": "personal",
                "text": "Alex prefers the window.",
                "quote": "I would rather sit at the window",
            },
            skills={"m2b:ingest": []},
        )

        self.run_curate()

        self.assertEqual(
            self.kept()["counts"],
            counts(person={"proposed": 1, "not_quoted": 1}, agreement={"not_quoted": 2}),
        )

    def test_a_proposal_without_the_persons_words_or_captured_already_is_counted_and_not_kept(self) -> None:
        """Covers: B117"""
        self.reading()
        self.typed(DANA_SAID, START - 4 * HOUR)
        self.typed("remember that I would rather sit at the window", START - 3 * HOUR)
        self.typed("Sam brings the plywood on Friday, note that", START - 2 * HOUR)
        self.write("inbox/20261107T050100Z-cli-a1b2.md", capture("I would rather sit at the window.", 5))
        self.write("corpus/2026/11/20261107T060100Z-cli-c3d4.md", capture("Sam brings the plywood on Friday", 6))
        self.answers(
            DANA,
            {**DANA, "text": "Dana signs the contracts.", "quote": "Dana signs every contract"},
            {
                **DANA,
                "kind": "personal",
                "text": "Alex prefers the window.",
                "quote": "I would rather sit at the window",
            },
            {**DANA, "kind": "agreement", "text": "Sam brings plywood.", "quote": "Sam brings the plywood on Friday"},
            {**DANA, "kind": "rumour"},
            skills={"m2b:ingest": []},
        )

        self.run_curate()

        self.assertEqual(list(self.kept()["proposals"]), [DANA_ID])
        self.assertIn(
            "1 proposal added, 0 like one that waits, is answered or expired, 1 without the person's words, "
            "2 captured already, 1 not in the form",
            self.info()[0],
        )

    def test_a_note_dropped_into_the_inbox_under_a_name_of_its_own_is_a_capture_of_the_period(self) -> None:
        """Covers: B117"""
        self.reading()
        self.typed(DANA_SAID, START - HOUR)
        self.write("inbox/dana.md", "Dana runs IT at Northwind\n")
        self.write("inbox/plan.pdf", "Dana runs IT at Northwind\n")
        self.answers(DANA, skills={"m2b:ingest": []})

        self.run_curate()

        self.assertEqual(self.kept()["proposals"], {})
        self.assertIn(
            "0 proposals added, 0 like one that waits, is answered or expired, 0 without the person's words, "
            "1 captured",
            self.info()[0],
        )

    def test_a_capture_from_before_the_period_does_not_take_a_proposal_away(self) -> None:
        self.reading()
        self.typed(DANA_SAID, START - HOUR)
        self.write("corpus/2026/11/20261105T060100Z-cli-c3d4.md", capture("Dana runs IT at Northwind", 6))
        self.answers(DANA)

        self.run_curate()

        self.assertEqual(list(self.kept()["proposals"]), [DANA_ID])

    def test_a_capture_of_the_period_that_is_not_downloaded_is_named_and_the_proposals_stay(self) -> None:
        self.reading()
        self.typed(DANA_SAID, START - HOUR)
        self.write("corpus/2026/11/20261107T060100Z-cli-c3d4.md", capture("Dana runs IT at Northwind", 6))
        self.eviction.evicted.add(self.store_root / "corpus/2026/11/20261107T060100Z-cli-c3d4.md")
        self.answers(DANA)

        self.run_curate()

        self.assertEqual(list(self.kept()["proposals"]), [DANA_ID])
        self.assertIn(
            "1 capture of the period is not downloaded, so a proposal may repeat it",
            self.info(),
        )

    def test_reading_a_period_a_second_time_adds_nothing(self) -> None:
        """Covers: B118"""
        self.reading()
        self.typed(DANA_SAID, START - HOUR)
        self.answers(DANA)
        self.run_curate()
        once = self.kept()
        self.write(proposals.PROPOSALS_FILE, json.dumps({**once, "read_until": None}))

        self.run_curate()

        self.assertEqual(self.kept(), once)
        self.assertIn("0 proposals added, 1 like one that waits, is answered or expired", self.info()[0])


class ExamplesTest(GleanStepTest):
    def answered_before(self) -> None:
        """A store whose earlier readings left two kept, a dropped, an expired and a waiting proposal.

        A sixth was kept 91 days ago: the file still holds it, since a run removes such a one only in its last step.
        """

        def entry(example: dict[str, str], state: str, hours_ago: int) -> dict[str, Any]:
            since = (START - DAY - hours_ago * HOUR).isoformat()
            return {**example, "topic": None, "due": None, "day": "2026-11-01", "state": state, "since": since}

        ends = {
            "a" * 12: entry(KIM, "kept", 2),
            "b" * 12: entry(TEA, "dropped", 3),
            "c" * 12: entry(OFFER, "expired", 4),
            "d" * 12: entry(BOAT, "open", 5),
            "e" * 12: entry(MIA, "kept", 6),
            "f" * 12: entry(PLYWOOD, "kept", 90 * 24),
        }
        self.write(proposals.PROPOSALS_FILE, json.dumps({**nothing_kept(START - DAY), "proposals": ends}))

    def test_a_reading_shows_the_model_what_the_person_kept_and_dropped_and_nothing_else_of_the_file(self) -> None:
        """Covers: B134"""
        self.reading()
        self.answered_before()
        self.typed(DANA_SAID, START - HOUR)
        self.answers(DANA)

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        (asked,) = self.asked()
        self.assertEqual(asked["answered"], {"kept": [KIM, MIA], "dropped": [TEA]})
        self.assertIn("the model was shown 2 kept and 1 dropped proposal as examples", self.info())

    def test_a_reading_shows_the_model_what_waits_for_an_answer_and_says_so(self) -> None:
        """Covers: B246"""
        self.reading()
        self.answered_before()
        self.typed(DANA_SAID, START - HOUR)
        self.answers(DANA)

        self.run_curate()

        (asked,) = self.asked()
        self.assertEqual(asked["waiting"], [BOAT])
        self.assertIn("the model was shown 1 proposal that waits for an answer", self.info())

    def test_a_reading_before_any_answer_shows_no_example_and_says_nothing_of_it(self) -> None:
        """Covers: B134"""
        self.reading()
        self.typed(DANA_SAID, START - HOUR)
        self.answers(DANA)

        self.run_curate()

        (asked,) = self.asked()
        self.assertEqual(asked["answered"], {"kept": [], "dropped": []})
        self.assertEqual(asked["waiting"], [])
        self.assertEqual([note for note in self.info() if "examples" in note or "for an answer" in note], [])

    def test_a_proposal_that_quotes_an_example_and_no_prompt_is_refused_by_the_quote_check(self) -> None:
        """Covers: B134"""
        self.reading()
        self.answered_before()
        self.typed(DANA_SAID, START - HOUR)
        again = {**DANA, **TEA, "text": "Alex drinks only green tea."}
        self.answers(DANA, again)

        self.run_curate()

        kept = self.kept()
        self.assertEqual(sorted(kept["proposals"]), sorted([*(letter * 12 for letter in "abcde"), DANA_ID]))
        self.assertEqual(kept["counts"]["personal"]["not_quoted"], 1)
        self.assertIn("1 proposal added, 0 like one that waits, is answered or expired, 1 without", self.info()[0])


class AnsweredTest(GleanStepTest):
    def test_a_run_files_what_the_person_kept_before_it_reads_and_does_not_propose_it_again(self) -> None:
        """Covers: B121"""
        self.reading()
        self.typed(DANA_SAID, START - HOUR)
        in_other_words = {**DANA, "text": "Dana is head of IT at Northwind."}
        self.answers(in_other_words)
        self.run_curate()
        proposal_answers.give(self.store, [DANA_ID], proposal_answers.KEEP)
        self.write(proposals.PROPOSALS_FILE, json.dumps({**self.kept(), "read_until": None}))
        files_it = [
            {"tool": "Bash", "command": "m2b ingest list --json"},
            {"tool": "Bash", "command": "m2b ingest note <capture:proposal> 'filed: fact dana.md'"},
            {"tool": "Bash", "command": "m2b ingest finish <capture:proposal>"},
        ]
        self.answers(in_other_words, skills={"m2b:ingest": files_it})

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.steps()[:3], [("harvest", "succeeded"), ("glean", "succeeded"), ("ingest", "succeeded")])
        (filed,) = (self.store_root / "corpus").rglob("*-proposal-*.md")
        self.assertIn(f"from_proposal: {DANA_ID}\n", filed.read_text(encoding="utf-8"))
        self.assertIn("\nDana is head of IT at Northwind.\n", filed.read_text(encoding="utf-8"))
        self.assertEqual(self.kept()["proposals"][DANA_ID]["state"], "kept")
        self.assertEqual(list((self.store_root / proposal_answers.FOLDER).iterdir()), [])
        self.assertIn("0 proposals added, 1 like one that waits, is answered or expired", self.info()[0])
        self.assertEqual(self.review_tasks(), [])

    def test_a_run_settles_the_answers_also_while_it_does_not_read_the_sessions(self) -> None:
        """Covers: B121"""
        self.reading()
        self.typed(DANA_SAID, START - HOUR)
        self.answers(DANA)
        self.run_curate()
        proposal_answers.give(self.store, [DANA_ID], proposal_answers.DROP)
        self.curating()

        self.run_curate()

        self.assertNotIn("glean", [name for name, _ in self.steps()])
        self.assertEqual(self.kept()["proposals"][DANA_ID]["state"], "dropped")
        self.assertEqual(list((self.store_root / proposal_answers.FOLDER).iterdir()), [])

    def test_what_stops_the_answers_is_in_the_review_also_when_the_harvest_fails(self) -> None:
        """Covers: B121"""
        self.reading()
        self.typed(DANA_SAID, START - HOUR)
        self.answers(DANA)
        self.run_curate()
        proposal_answers.give(self.store, [DANA_ID], proposal_answers.KEEP)
        self.write(proposals.PROPOSALS_FILE, json.dumps({**self.kept(), "format": proposals.FORMAT + 1}))
        real_items = MarkdownTasks.items

        def items(tasks: MarkdownTasks, *arguments: Any, **options: Any) -> Any:
            if options.get("marker") == markers.CANDIDATE:
                raise TasksError("the task list does not answer")
            return real_items(tasks, *arguments, **options)

        with mock.patch.object(MarkdownTasks, "items", items):
            self.run_curate()

        self.assertEqual(self.steps()[0], ("harvest", "failed"))
        notes = "\n".join(task.notes for task in self.review_tasks())
        self.assertIn("the task list does not answer", notes)
        self.assertIn("the answers to proposals wait for the next run", notes)


class WaitingTaskTest(GleanStepTest):
    def proposed(self) -> None:
        """A run that read the sessions and left one proposal waiting."""
        self.reading()
        self.typed(DANA_SAID, START - HOUR)
        self.answers(DANA)
        self.run_curate()

    def proposals_tasks(self) -> list[Any]:
        return self.tasks().items(marker=markers.PROPOSALS, include_completed=True)

    def test_a_run_that_leaves_a_proposal_waiting_leaves_one_task_for_it(self) -> None:
        """Covers: B124"""
        self.proposed()

        self.assertEqual(self.steps()[-2:], [("proposals", "succeeded"), ("review", "succeeded")])
        (task,) = self.proposals_tasks()
        self.assertFalse(task.completed)
        self.assertIn("\nOne proposal from your sessions waits for your answer", task.notes)
        self.assertEqual(self.review_tasks(), [])

        self.run_curate()

        self.assertEqual([task.id], [again.id for again in self.proposals_tasks()])

    def test_a_run_that_does_not_read_the_sessions_completes_the_task_once_all_are_answered(self) -> None:
        """Covers: B124"""
        self.proposed()
        proposal_answers.give(self.store, [DANA_ID], proposal_answers.DROP)
        self.curating()

        self.run_curate()

        self.assertNotIn("glean", [name for name, _ in self.steps()])
        (task,) = self.proposals_tasks()
        self.assertTrue(task.completed)
        self.assertEqual(self.kept()["announced_until"], START.isoformat())

    def test_completing_the_task_keeps_and_drops_nothing_and_is_not_the_persons_work(self) -> None:
        """Covers: B125"""
        self.proposed()
        tasks = self.tasks()
        (task,) = self.proposals_tasks()
        tasks.complete(task.id)
        tasks.complete(tasks.add("Call Dana"))
        self.clock = START + DAY

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.kept()["proposals"][DANA_ID]["state"], "open")
        self.assertEqual(list(self.store_root.glob("inbox/*")), [])
        self.assertEqual([again.completed for again in self.proposals_tasks()], [True])
        journaled = "".join(path.read_text(encoding="utf-8") for path in self.store_root.rglob("*-done.md"))
        self.assertIn("Call Dana", journaled)
        self.assertNotIn("proposals from your sessions", journaled)

    def test_a_task_list_that_does_not_answer_for_the_task_fails_that_step_alone(self) -> None:
        """Covers: B124"""
        self.proposed()
        proposal_answers.give(self.store, [DANA_ID], proposal_answers.DROP)
        self.capture()
        self.answers(DANA, skills={"m2b:ingest": INGEST_FILES_THE_CAPTURE})
        real_items = MarkdownTasks.items

        def items(tasks: MarkdownTasks, *arguments: Any, **options: Any) -> Any:
            if options.get("marker") == markers.PROPOSALS:
                raise TasksError("the task list does not answer")
            return real_items(tasks, *arguments, **options)

        with mock.patch.object(MarkdownTasks, "items", items):
            outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.kept()["proposals"][DANA_ID]["state"], "dropped")
        self.assertIn(("ingest", "succeeded"), self.steps())
        self.assertIn(("proposals", "failed"), self.steps())
        self.assertIn(
            "The step proposals failed: the task for the proposals that wait was not brought up to date "
            "(the task list does not answer); the next run does it",
            "\n".join(task.notes for task in self.review_tasks()),
        )
        self.assertEqual([task.completed for task in self.proposals_tasks()], [False])

        self.run_curate()

        self.assertEqual([task.completed for task in self.proposals_tasks()], [True])

    def test_a_cause_that_does_not_clear_by_itself_is_not_left_to_the_next_run(self) -> None:
        self.curating()
        self.write(proposals.PROPOSALS_FILE, json.dumps({"format": proposals.FORMAT + 1, "proposals": {}}))

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertIn(("proposals", "failed"), self.steps())
        (review,) = self.review_tasks()
        self.assertIn(
            "The step proposals failed: the task for the proposals that wait was not brought up to date: "
            f"state/core/proposals.json has format {proposals.FORMAT + 1} and this m2b knows {proposals.FORMAT}: "
            "update m2b on this machine",
            review.notes,
        )
        self.assertNotIn("the next run does it", review.notes)

    def test_a_run_that_does_not_read_the_sessions_lets_a_proposal_without_an_answer_expire(self) -> None:
        """Covers: B131"""
        self.proposed()
        self.curating()
        self.clock = START + datetime.timedelta(days=13)
        self.run_curate()
        still_open = self.kept()["proposals"][DANA_ID]["state"], self.proposals_tasks()[0].completed

        self.clock = START + datetime.timedelta(days=14)
        self.run_curate()

        self.assertEqual(still_open, ("open", False))
        self.assertNotIn("glean", [name for name, _ in self.steps()])
        entry = self.kept()["proposals"][DANA_ID]
        self.assertEqual((entry["state"], entry["since"]), ("expired", self.clock.isoformat()))
        self.assertEqual(self.kept()["counts"]["person"]["expired"], 1)
        (task,) = self.proposals_tasks()
        self.assertTrue(task.completed)
        self.assertEqual(self.run_json("band")["proposals"], {"proposals": [], "answered": 0, "handed_in": 0})
        self.assertEqual(
            self.info("proposals"), ["1 proposal from the sessions got no answer for 14 days and waits no longer"]
        )
        self.assertEqual(self.review_tasks(), [])

    def test_a_step_that_let_a_proposal_expire_did_run_also_when_its_task_was_put_away_before(self) -> None:
        """Covers: B131"""
        self.proposed()
        self.tasks().complete(self.proposals_tasks()[0].id)
        self.curating()

        self.clock = START + datetime.timedelta(days=14)
        self.run_curate()
        expiring = self.steps()
        self.clock = START + datetime.timedelta(days=15)
        self.run_curate()

        self.assertIn(("proposals", "succeeded"), expiring)
        self.assertIn(("proposals", "skipped"), self.steps())
        self.assertEqual(self.kept()["proposals"][DANA_ID]["state"], "expired")

    def test_a_run_that_does_not_read_the_sessions_forgets_what_was_settled_ninety_days_ago(self) -> None:
        """Covers: B131"""
        self.proposed()
        proposal_answers.give(self.store, [DANA_ID], proposal_answers.DROP)
        self.curating()
        self.clock = START + datetime.timedelta(days=1)
        self.run_curate()

        self.clock = START + datetime.timedelta(days=90)
        self.run_curate()
        remembered = [entry["state"] for entry in self.kept()["proposals"].values()]
        self.clock = START + datetime.timedelta(days=91)
        self.run_curate()

        self.assertEqual(remembered, ["dropped"])
        self.assertEqual(self.kept()["proposals"], {})
        self.assertIn(("proposals", "succeeded"), self.steps())
        self.assertEqual(self.kept()["counts"]["person"]["dropped"], 1)

    def test_without_a_proposal_the_step_has_nothing_to_do(self) -> None:
        self.curating()

        self.run_curate()

        self.assertIn(("proposals", "skipped"), self.steps())
        self.assertEqual(self.tasks().items(include_completed=True), [])


class FailingReadingTest(GleanStepTest):
    def failed_reading(self) -> None:
        """A run whose reading fails: it is in the review, the run succeeded, the inbox is filed, the mark stays."""
        self.capture()
        read_before = START - 5 * HOUR
        self.read_until(read_before)

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertIn("glean", outcome.message)
        self.assertEqual(self.steps()[:3], [("harvest", "succeeded"), ("glean", "failed"), ("ingest", "succeeded")])
        self.assertEqual(list((self.store_root / "inbox").iterdir()), [])
        self.assertEqual(self.kept(), nothing_kept(read_until=read_before))
        record = load_run_record(self.store)
        assert record is not None
        self.assertEqual(record.last_success, record.finished_at)
        self.assertIsNone(machine_state.load_backoff(self.machine))

    def test_a_model_that_gives_no_answer_fails_the_reading_alone(self) -> None:
        """Covers: B13, B119"""
        self.reading()
        self.typed(DANA_SAID, START - HOUR)
        self.answers(DANA, outcome="error", skills={"m2b:ingest": INGEST_FILES_THE_CAPTURE})

        self.failed_reading()

        (review,) = self.review_tasks()
        self.assertIn("The step glean failed: the sessions were not read for proposals (", review.notes)
        self.assertIn("); the next run reads them again", review.notes)

    def test_an_answer_that_cannot_be_read_fails_the_reading_alone(self) -> None:
        """Covers: B119"""
        self.reading()
        self.typed(DANA_SAID, START - HOUR)
        self.answers(skills={"m2b:ingest": INGEST_FILES_THE_CAPTURE})
        script = json.loads(self.actions.read_text(encoding="utf-8"))
        script["text"]["answer"] = "I found nothing worth keeping."
        self.actions.write_text(json.dumps(script), encoding="utf-8")

        self.failed_reading()

        (review,) = self.review_tasks()
        self.assertIn("(the answer holds no JSON object with a list of proposals)", review.notes)

    def test_transcripts_that_cannot_be_looked_at_fail_the_reading_alone(self) -> None:
        """Covers: B119"""
        self.reading()
        self.projects.rmdir()
        self.answers(skills={"m2b:ingest": INGEST_FILES_THE_CAPTURE})

        self.failed_reading()

        (review,) = self.review_tasks()
        self.assertIn("(no Claude Code transcripts in", review.notes)
        self.assertEqual([call for call in self.calls() if "stdin" in call], [])

    def test_a_period_in_which_nothing_carries_the_mark_of_who_sent_it_fails_the_reading_alone(self) -> None:
        """Covers: B119"""
        self.reading()
        self.record(test_sessions.unmarked(DANA_SAID, START - 2 * HOUR))
        self.record(test_sessions.unmarked("<command-name>/clear</command-name>", START - HOUR))
        self.answers(DANA, skills={"m2b:ingest": INGEST_FILES_THE_CAPTURE})

        self.failed_reading()

        (review,) = self.review_tasks()
        self.assertIn(
            f"(nothing typed since {START - 5 * HOUR:%Y-%m-%d %H:%M} carries Claude Code's mark of who sent it, "
            "1 text is without it: Claude Code may write its transcripts in a way this m2b does not read)",
            review.notes,
        )
        self.assertEqual([call for call in self.calls() if "stdin" in call], [])

    def test_a_period_with_only_the_output_of_a_shell_line_is_one_in_which_nothing_was_typed(self) -> None:
        """Covers: B119"""
        self.reading()
        self.record(test_sessions.unmarked("<bash-input>git status</bash-input>", START - 2 * HOUR))
        self.record(
            test_sessions.unmarked("<bash-stdout>On branch main</bash-stdout><bash-stderr></bash-stderr>", START - HOUR)
        )
        self.answers()

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.steps()[1], ("glean", "skipped"))
        self.assertEqual(self.kept()["read_until"], START.isoformat())
        self.assertEqual(self.review_tasks(), [])

    def test_a_text_without_the_mark_beside_marked_ones_does_not_fail_the_reading(self) -> None:
        self.reading()
        self.record(test_sessions.sent_by("plugin", "build the next part", START - 2 * HOUR))
        self.record(test_sessions.unmarked("ls -la", START - HOUR))
        self.answers()

        self.run_curate()

        self.assertEqual(self.steps()[1], ("glean", "skipped"))
        self.assertEqual(self.kept()["read_until"], START.isoformat())

    def test_a_proposals_file_this_m2b_cannot_use_fails_the_reading_alone_and_stays_as_it_is(self) -> None:
        """Covers: B119"""
        self.reading()
        self.typed(DANA_SAID, START - HOUR)
        self.capture()
        from_a_newer_m2b = json.dumps(
            {"format": proposals.FORMAT + 1, "proposals": {"aaaaaaaaaaaa": {"shape": "unknown here"}}}
        )
        self.write(proposals.PROPOSALS_FILE, from_a_newer_m2b)
        self.answers(DANA, skills={"m2b:ingest": INGEST_FILES_THE_CAPTURE})

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.steps()[:3], [("harvest", "succeeded"), ("glean", "failed"), ("ingest", "succeeded")])
        self.assertEqual((self.store_root / proposals.PROPOSALS_FILE).read_text(encoding="utf-8"), from_a_newer_m2b)
        self.assertEqual([call for call in self.calls() if "stdin" in call], [])
        (review,) = self.review_tasks()
        self.assertIn(f"has format {proposals.FORMAT + 1} and this m2b knows {proposals.FORMAT}", review.notes)

    def test_a_transcript_that_cannot_be_read_is_counted_and_the_others_are_read(self) -> None:
        self.reading()
        self.typed(DANA_SAID, START - HOUR)
        self.record(test_sessions.typed("we are away in December", START - HOUR, cwd=None), "nowhere")
        self.answers()

        self.run_curate()

        self.assertEqual(self.prompts_asked(), [[DANA_SAID]])
        self.assertIn("1 transcript could not be read", self.info())
