"""The curation step that reads what the person typed and keeps what a model proposes from it."""

from __future__ import annotations

import datetime
import json
from typing import Any
from unittest import mock

import test_runner
import test_sessions
from m2b import glean, proposal_answers, proposals
from m2b.config.profile import save_profile
from m2b.curate import machine_state, model
from m2b.run_record import SUCCEEDED, load_run_record
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
        self, *entries: dict[str, Any], outcome: str = "success", skills: dict[str, list[dict[str, Any]]] | None = None
    ) -> None:
        self.model(skills or {})
        script = json.loads(self.actions.read_text(encoding="utf-8"))
        script["text"] = {"answer": json.dumps({"proposals": list(entries)}), "outcome": outcome}
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
                f"read 1 session with 2 typed prompts since {START - DAY:%Y-%m-%d %H:%M}: 1 proposal added, "
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

    def test_what_the_reader_left_out_of_the_sessions_is_counted_in_the_runs_information(self) -> None:
        """Covers: B115"""
        self.reading()
        self.typed(f'{DANA_SAID} <pasted_content id="a1">a mail</pasted_content id="a1">', START - 4 * HOUR)
        self.record(test_sessions.sent_by("plugin", "build the next part", START - 3 * HOUR))
        self.record(test_sessions.sent_by("task-notification", "the build is done", START - 3 * HOUR))
        self.record(test_sessions.typed("yes, do that", START - 2 * HOUR, promptSource="suggestion_accepted"))
        self.record(test_sessions.unmarked("ls -la", START - HOUR))
        self.answers()

        self.run_curate()

        self.assertIn(
            "left out of these sessions: 2 prompts that a plugin, a task or another agent sent, "
            "1 suggestion that was only accepted, 1 pasted block, 1 text without Claude Code's mark of who sent it",
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

    def test_the_deadline_of_the_run_counts_the_reading_as_one_more_model_step(self) -> None:
        self.reading()
        seen = self.addon("worklog", "before_ingest")

        self.run_curate()

        (step,) = [json.loads(line) for line in seen.read_text(encoding="utf-8").splitlines()]
        deadline = datetime.datetime.fromisoformat(step["record"]["deadline_at"])
        supervised = 5 * (datetime.timedelta(minutes=15) + datetime.timedelta(seconds=model.DEFAULT_GRACE_SECONDS))
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
        self.write(proposals.PROPOSALS_FILE, json.dumps({**self.kept(), "format": 2}))
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
        self.write(proposals.PROPOSALS_FILE, json.dumps({"format": 2, "proposals": {}}))

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertIn(("proposals", "failed"), self.steps())
        (review,) = self.review_tasks()
        self.assertIn(
            "The step proposals failed: the task for the proposals that wait was not brought up to date: "
            "state/core/proposals.json has format 2 and this m2b knows 1: update m2b on this machine",
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
        self.assertEqual(self.run_json("band")["proposals"], {"proposals": [], "answered": 0})
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
        from_a_newer_m2b = json.dumps({"format": 2, "proposals": {"aaaaaaaaaaaa": {"shape": "unknown here"}}})
        self.write(proposals.PROPOSALS_FILE, from_a_newer_m2b)
        self.answers(DANA, skills={"m2b:ingest": INGEST_FILES_THE_CAPTURE})

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.steps()[:3], [("harvest", "succeeded"), ("glean", "failed"), ("ingest", "succeeded")])
        self.assertEqual((self.store_root / proposals.PROPOSALS_FILE).read_text(encoding="utf-8"), from_a_newer_m2b)
        self.assertEqual([call for call in self.calls() if "stdin" in call], [])
        (review,) = self.review_tasks()
        self.assertIn("has format 2 and this m2b knows 1", review.notes)

    def test_a_transcript_that_cannot_be_read_is_counted_and_the_others_are_read(self) -> None:
        self.reading()
        self.typed(DANA_SAID, START - HOUR)
        self.record(test_sessions.typed("we are away in December", START - HOUR, cwd=None), "nowhere")
        self.answers()

        self.run_curate()

        self.assertEqual(self.prompts_asked(), [[DANA_SAID]])
        self.assertIn("1 transcript could not be read", self.info())
