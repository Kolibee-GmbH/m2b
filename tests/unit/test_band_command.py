"""``m2b band``: what the band above the prompt shows, with the status line, in one answer."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any
from unittest import mock

import test_proposals_command
import test_runner
from m2b import cli, launcher, proposals, topic_state
from m2b.commands import band, doctor
from m2b.store.base import StoreError
from m2b.tasks import markers
from test_proposal_answers import DANA_ID, LADDER_ID
from test_proposals import DANA, LADDER


class BandCommandTest(test_runner.RunnerTest):
    def band(self) -> dict[str, Any]:
        result: dict[str, Any] = self.run_json("band")
        return result

    def test_candidates_questions_the_review_and_the_status_come_in_one_answer(self) -> None:
        """Covers: B93"""
        self.curating()
        tasks = self.tasks()
        tasks.add("Remember? Sam brings the plywood", notes=markers.marker_line(markers.CANDIDATE))
        tasks.add(
            "Still current? Planning the trip to Porto", notes=markers.marker_line(markers.CURRENT, "1a2b3c4d5e6f")
        )
        tasks.add("m2b: review", notes=markers.marker_line(markers.REVIEW) + "\n\nlint: broken link in a.md")
        tasks.add("Buy screws")
        tasks.add("m2b: proposals from your sessions", notes=markers.marker_line(markers.PROPOSALS))
        done = tasks.add("Remember? Settled already", notes=markers.marker_line(markers.CANDIDATE))
        tasks.complete(done)
        self.capture()

        answer = self.band()

        self.assertEqual([t["title"] for t in answer["tasks"]["candidates"]], ["Remember? Sam brings the plywood"])
        self.assertEqual(
            [t["title"] for t in answer["tasks"]["questions"]], ["Still current? Planning the trip to Porto"]
        )
        self.assertEqual([t["title"] for t in answer["tasks"]["reviews"]], ["m2b: review"])
        self.assertEqual(answer["status"]["inbox"], {"count": 1, "evicted": 0})
        self.assertEqual(answer["status"]["backends"]["tasks"]["state"], "reachable")

    def test_a_question_whether_a_lesson_is_still_needed_comes_with_the_questions(self) -> None:
        """Covers: B283"""
        self.curating()
        self.tasks().add(
            "Still needed? Run the whole proof only with a reason.",
            notes=markers.marker_line(markers.LESSON, "1a2b3c4d5e6f"),
        )

        answer = self.band()

        self.assertEqual(
            [t["title"] for t in answer["tasks"]["questions"]],
            ["Still needed? Run the whole proof only with a reason."],
        )

    def test_on_apple_reminders_one_answer_asks_reminders_twice_also_when_the_status_probes(self) -> None:
        """Covers: B93"""
        self.curating(tasks={"backend": "apple-reminders", "list": "sb-test-inbox"})
        calls = self.bin.parent / "reminders-calls.txt"
        wrapper = self.bin / "reminders"
        fake = wrapper.read_text(encoding="utf-8")
        wrapper.write_text(fake.replace("exec ", f'echo "$1" >> "{calls}"\nexec ', 1), encoding="utf-8")
        cache = self.machine.state_dir / "status-cache.json"
        self.assertFalse(cache.exists())

        answer = self.band()

        self.assertEqual(calls.read_text(encoding="utf-8").split(), ["show-lists", "show"])
        self.assertTrue(cache.exists())
        self.assertEqual(answer["status"]["backends"]["tasks"]["state"], "reachable")

    def test_the_answer_names_the_installed_version(self) -> None:
        """Covers: B96"""
        self.curating()

        self.assertEqual(self.band()["version"], launcher.core_version())

    def test_tasks_due_today_or_overdue_come_without_curator_tasks_and_without_later_ones(self) -> None:
        """Covers: B102"""
        self.curating()
        tasks = self.tasks()
        today = datetime.date.today()
        tasks.add("Call Dana", due=today)
        tasks.add("Return the drill", due=today - datetime.timedelta(days=2))
        tasks.add("Book the trip", due=today + datetime.timedelta(days=1))
        tasks.add("Buy screws")
        tasks.add("Remember? Sam moved", notes=markers.marker_line(markers.CANDIDATE), due=today)
        tasks.add("m2b: proposals from your sessions", notes=markers.marker_line(markers.PROPOSALS), due=today)
        done = tasks.add("Water the plants", due=today)
        tasks.complete(done)

        due = self.band()["tasks"]["due_by_today"]

        self.assertEqual([task["title"] for task in due], ["Return the drill", "Call Dana"])
        self.assertEqual([task["overdue"] for task in due], [True, False])

    def test_the_tasks_due_are_named_however_the_band_shows_them_and_the_answer_says_how(self) -> None:
        """Covers: B102"""
        self.curating()
        self.tasks().add("Call Dana", due=datetime.date.today())

        self.assertEqual(self.band()["band"]["due_tasks"], "count")
        for written, shown in (("off", "off"), ("count", "count"), ("list", "list"), (True, "list"), (False, "off")):
            with self.subTest(written=written):
                self.write_band_settings(due_tasks=written)
                answer = self.band()
                self.assertEqual(answer["band"]["due_tasks"], shown)
                self.assertEqual([task["title"] for task in answer["tasks"]["due_by_today"]], ["Call Dana"])

    def test_the_answer_names_what_the_band_shows_as_the_config_says(self) -> None:
        """Covers: B202"""
        self.curating()

        self.assertEqual(self.band()["band"], {"place": None, "due_tasks": "count", "topics": False})
        self.write_band_settings(due_tasks="list", topics=True)
        self.assertEqual(self.band()["band"], {"place": None, "due_tasks": "list", "topics": True})

    def test_the_answer_names_where_the_band_stands_beside_what_a_band_before_it_reads(self) -> None:
        """Covers: B213"""
        self.curating()

        for place in ("below", "waiting", "above"):
            with self.subTest(place=place):
                self.write_band_settings(place=place)
                self.assertEqual(self.band()["band"], {"place": place, "due_tasks": "count", "topics": False})

    def test_a_band_from_before_the_three_values_is_handed_the_tasks_only_where_they_are_listed(self) -> None:
        """Covers: B102"""
        self.curating()
        self.tasks().add("Call Dana", due=datetime.date.today())

        self.assertNotIn("due", self.band()["tasks"])
        self.write_band_settings(due_tasks="off")
        self.assertNotIn("due", self.band()["tasks"])
        self.write_band_settings(due_tasks="list")
        self.assertEqual([task["title"] for task in self.band()["tasks"]["due"]], ["Call Dana"])

    def write_band_settings(self, **band: object) -> None:
        config = json.loads(self.machine.config_file.read_text(encoding="utf-8"))
        config["band"] = band
        self.machine.config_file.write_text(json.dumps(config), encoding="utf-8")

    def test_tasks_only_leaves_the_status_out(self) -> None:
        """Covers: B93"""
        self.curating()

        answer: dict[str, Any] = self.run_json("band", "--tasks-only")

        self.assertEqual(sorted(answer), ["tasks"])

    def test_the_calendar_probe_of_the_band_keeps_to_its_own_short_budget(self) -> None:
        """Covers: B93"""
        self.curating()
        seen: list[int] = []

        def calendar_check(config: Any) -> Any:
            seen.append(config.calendar.timeout_seconds)
            return doctor.Check("calendar", doctor.NOT_CONFIGURED)

        config = json.loads(self.machine.config_file.read_text(encoding="utf-8"))
        config["calendar"]["timeout_seconds"] = 60
        self.machine.config_file.write_text(json.dumps(config), encoding="utf-8")
        with mock.patch("m2b.commands.status.calendar_check", calendar_check):
            self.band()

        self.assertEqual(seen, [band.CALENDAR_BUDGET_SECONDS])

    def test_a_task_list_that_cannot_be_reached_is_named_in_both_parts(self) -> None:
        """Covers: B93"""
        self.curating(tasks={"backend": "apple-reminders", "list": "sb-test-missing"})

        answer = self.band()

        self.assertIn("sb-test-missing", answer["tasks"]["error"])
        self.assertEqual(answer["status"]["backends"]["tasks"]["state"], "not reachable")


SESSION = "ea4af7eb-7f1d-4eab-aac2-987397455c4b"
STARTED = datetime.datetime(2026, 11, 8, 9, 0).astimezone()
# The folder the tests run in: what the command looks at where Claude Code names no project.
HERE = str(Path.cwd().resolve())


class BandSessionTest(test_runner.RunnerTest):
    """What m2b gave one session: its topics with their lines, and the distillate."""

    def session_part(self, session_id: str = SESSION) -> dict[str, Any]:
        answer: dict[str, Any] = self.run_json("band", "--session", session_id)
        part: dict[str, Any] = answer["session"]
        return part

    def start(self, *given: topic_state.Given, printed: str | None = topic_state.WHOLE) -> None:
        topic_state.start_session(self.machine, SESSION, "startup", given, STARTED, printed)

    def test_the_topics_a_session_was_given_come_with_their_lines_and_how_the_start_printed(self) -> None:
        """Covers: B183"""
        self.curating()
        self.start(topic_state.Given("Globex", 2, 0), topic_state.Given("Acme Ltd", 3, 1))

        self.assertEqual(
            self.session_part(),
            {
                "id": SESSION,
                "known": True,
                "topics": [
                    {"name": "Acme Ltd", "facts": 3, "current": 1},
                    {"name": "Globex", "facts": 2, "current": 0},
                ],
                "distillate": {"at_start": "whole", "off_under": None, "folder": HERE},
            },
        )

    def test_a_start_that_cut_the_distillate_or_had_none_is_named_so(self) -> None:
        """Covers: B183"""
        self.curating()
        for printed in (topic_state.CUT, topic_state.NONE):
            with self.subTest(printed=printed):
                self.start(printed=printed)
                self.assertEqual(self.session_part()["distillate"]["at_start"], printed)

    def test_a_session_this_machine_noted_nothing_of_is_not_known_and_has_no_topics(self) -> None:
        """Covers: B183"""
        self.curating()

        self.assertEqual(
            self.session_part(),
            {
                "id": SESSION,
                "known": False,
                "topics": [],
                "distillate": {"at_start": None, "off_under": None, "folder": HERE},
            },
        )

    def test_a_folder_the_distillate_is_off_for_is_named_as_it_is_now(self) -> None:
        """Covers: B183"""
        self.curating()
        self.start(topic_state.Given("Acme Ltd", 3, 1))
        customer = self.home / "code" / "acme"
        (customer / "api").mkdir(parents=True)
        self.run_command("distillate", "off", str(customer))
        self.environ["CLAUDE_PROJECT_DIR"] = str(customer / "api")

        part = self.session_part()

        self.assertEqual(
            part["distillate"],
            {"at_start": "whole", "off_under": str(customer.resolve()), "folder": str((customer / "api").resolve())},
        )
        self.assertEqual([topic["name"] for topic in part["topics"]], ["Acme Ltd"])

    def test_without_a_project_named_the_folder_is_the_one_the_command_runs_in(self) -> None:
        """Covers: B183"""
        self.curating()
        customer = self.home / "code" / "acme"
        customer.mkdir(parents=True)
        self.run_command("distillate", "off", str(customer))

        with mock.patch("m2b.hook_input.os.getcwd", return_value=str(customer)):
            part = self.session_part()

        self.assertEqual(part["distillate"]["off_under"], str(customer.resolve()))

    def test_the_folder_the_answer_names_is_the_one_distillate_off_and_on_take(self) -> None:
        """Covers: B183"""
        self.curating()
        project = self.home / "code" / "acme"
        project.mkdir(parents=True)
        (self.home / "code" / "link").symlink_to(project)
        self.environ["CLAUDE_PROJECT_DIR"] = str(self.home / "code" / "link")

        folder = self.session_part()["distillate"]["folder"]
        self.assertEqual(folder, str(project.resolve()))

        self.run_command("distillate", "off", "--", folder)
        self.assertEqual(self.session_part()["distillate"]["off_under"], folder)

        self.run_command("distillate", "on", "--", self.session_part()["distillate"]["off_under"])
        self.assertIsNone(self.session_part()["distillate"]["off_under"])

    def test_a_folder_that_cannot_be_looked_at_costs_only_this_part(self) -> None:
        """Covers: B183"""
        self.curating()

        with mock.patch("m2b.hook_input.os.getcwd", side_effect=FileNotFoundError("the folder is gone")):
            answer: dict[str, Any] = self.run_json("band", "--session", SESSION)

        self.assertEqual(answer["session"], {"error": "the session's folder cannot be looked at: the folder is gone"})
        self.assertIn("candidates", answer["tasks"])
        self.assertIn("inbox", answer["status"])

    def test_a_session_named_twice_is_refused(self) -> None:
        self.curating()

        code, out, err = self.run_command("band", "--session", "../escape", "--session", SESSION)

        self.assertEqual((code, out), (cli.EXIT_USAGE, ""))
        self.assertIn("--session given twice", err)

    def test_an_id_that_is_no_session_id_is_named_and_never_becomes_a_file(self) -> None:
        """Covers: B183"""
        self.curating()
        for session_id in ("../escape", "a/b", "", "x" * 200):
            with self.subTest(session_id=session_id):
                answer: dict[str, Any] = self.run_json("band", "--session", session_id)
                self.assertEqual(answer["session"], {"error": "not a session id"})
                self.assertIn("candidates", answer["tasks"])
        self.assertFalse((self.machine.state_dir / topic_state.TOPICS_FOLDER).exists())

    def test_topics_from_before_the_counts_come_with_their_names_alone(self) -> None:
        self.curating()
        folder = self.machine.state_dir / topic_state.TOPICS_FOLDER
        folder.mkdir(parents=True)
        (folder / f"{SESSION}.json").write_text('{"shown": ["Acme Ltd"]}', encoding="utf-8")

        self.assertEqual(self.session_part()["topics"], [{"name": "Acme Ltd", "facts": None, "current": None}])
        self.assertIsNone(self.session_part()["distillate"]["at_start"])

    def test_without_a_session_named_the_answer_has_no_such_part(self) -> None:
        """Covers: B183"""
        self.curating()

        self.assertNotIn("session", self.run_json("band"))
        self.assertEqual(sorted(self.run_json("band", "--tasks-only", "--session", SESSION)), ["tasks"])

    def test_asked_for_the_session_alone_nothing_else_is_reached_or_read(self) -> None:
        """Covers: B184"""
        self.curating()
        self.start(topic_state.Given("Acme Ltd", 3, 1))
        not_read = mock.Mock(side_effect=AssertionError("asked for the session alone, the answer read something else"))

        with mock.patch.multiple(
            band,
            _tasks_part=not_read,
            status_answer=not_read,
            _proposals_part=not_read,
            configured_store=not_read,
            configured_tasks=not_read,
        ):
            answer: dict[str, Any] = self.run_json("band", "--session", SESSION, "--session-only")

        self.assertEqual(sorted(answer), ["session", "version"])
        self.assertEqual(answer["session"], self.session_part())
        self.assertEqual(answer["session"]["topics"], [{"name": "Acme Ltd", "facts": 3, "current": 1}])

    def test_the_session_alone_without_a_session_named_is_refused(self) -> None:
        """Covers: B184"""
        self.curating()

        code, out, err = self.run_command("band", "--session-only")

        self.assertEqual((code, out), (cli.EXIT_USAGE, ""))
        self.assertIn("--session-only needs --session <id>", err)

    def test_the_session_alone_does_not_go_with_the_tasks_alone(self) -> None:
        """Covers: B184"""
        self.curating()

        code, out, err = self.run_command("band", "--tasks-only", "--session", SESSION, "--session-only")

        self.assertEqual((code, out), (cli.EXIT_USAGE, ""))
        self.assertIn("--session-only does not go with --tasks-only", err)


class BandProposalsTest(test_proposals_command.ProposalsCommandTest):
    def band(self, *options: str) -> dict[str, Any]:
        result: dict[str, Any] = self.run_json("band", *options)
        return result

    def test_the_answer_names_what_waits_as_the_proposals_command_does(self) -> None:
        """Covers: B126"""
        self.proposed(DANA, LADDER)
        self.run_command("proposals", "drop", LADDER_ID)

        part = self.band()["proposals"]

        self.assertEqual(part, self.run_json("proposals"))
        self.assertEqual([waiting["id"] for waiting in part["proposals"]], [DANA_ID])
        self.assertEqual(
            {field: part["proposals"][0][field] for field in ("kind", "text", "quote", "day", "topic")},
            {
                "kind": "person",
                "text": "Dana runs IT at Northwind.",
                "quote": "Dana runs IT at Northwind",
                "day": "2026-03-04",
                "topic": "Northwind",
            },
        )
        self.assertEqual(part["answered"], 1)

    def test_it_carries_how_many_handed_in_proposals_wait_for_a_run_beside_the_proposals_and_in_the_status(
        self,
    ) -> None:
        """Covers: B240"""
        target = self.store_root / "state" / "core" / "handed-in" / "s1.a1b2c3d4e5f6.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("words no check has seen", encoding="utf-8")

        answer = self.band()

        self.assertEqual(answer["proposals"]["handed_in"], 1)
        self.assertEqual(answer["status"]["handed_in"], {"count": 1, "evicted": 0})
        self.assertNotIn("words no check has seen", json.dumps(answer))

    def test_a_folder_of_handed_in_proposals_that_cannot_be_listed_leaves_the_proposals_listed(self) -> None:
        """Covers: B240"""
        failure = StoreError("state/core/handed-in cannot be listed")

        with mock.patch("m2b.handed_in.waiting", side_effect=failure):
            answer = self.band()

        self.assertEqual(answer["proposals"], {"proposals": [], "answered": 0, "handed_in": None})
        self.assertEqual(answer["status"]["handed_in"], {"error": "state/core/handed-in cannot be listed"})

    def test_a_store_without_proposals_answers_an_empty_list(self) -> None:
        """Covers: B126"""
        self.assertEqual(self.band()["proposals"], {"proposals": [], "answered": 0, "handed_in": 0})

    def test_answers_that_are_not_downloaded_are_named_in_this_part_and_the_rest_still_answers(self) -> None:
        """Covers: B6, B126"""
        self.proposed(DANA, LADDER)
        self.run_command("proposals", "drop", LADDER_ID)

        with self.not_downloaded("proposal-answers"):
            answer = self.band()

        self.assertEqual(list(answer["proposals"]), ["error"])
        self.assertIn("m2b store fetch state/core/proposal-answers", answer["proposals"]["error"])
        self.assertEqual(answer["tasks"]["candidates"], [])
        self.assertEqual(answer["status"]["backends"]["tasks"]["state"], "reachable")

    def test_a_proposals_file_a_newer_m2b_wrote_is_named_in_this_part(self) -> None:
        """Covers: B126"""
        target = self.store_root / proposals.PROPOSALS_FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"format": proposals.FORMAT + 1, "proposals": {}}), encoding="utf-8")

        answer = self.band()

        self.assertIn("update m2b on this machine", answer["proposals"]["error"])
        self.assertIn("candidates", answer["tasks"])

    def test_a_stored_proposal_with_half_a_character_does_not_cost_the_band_its_answer(self) -> None:
        """Covers: B126"""
        self.proposed(DANA)
        target = self.store_root / proposals.PROPOSALS_FILE
        raw = json.loads(target.read_text(encoding="utf-8"))
        raw["proposals"]["aaaaaaaaaaaa"] = {**raw["proposals"][DANA_ID], "text": "Dana \ud800 runs IT"}
        target.write_text(json.dumps(raw), encoding="utf-8")

        answer = self.band()

        self.assertEqual([waiting["id"] for waiting in answer["proposals"]["proposals"]], [DANA_ID])
        self.assertIn("candidates", answer["tasks"])

    def test_tasks_only_leaves_the_proposals_out(self) -> None:
        """Covers: B126"""
        self.proposed(DANA)

        self.assertEqual(list(self.band("--tasks-only")), ["tasks"])


if __name__ == "__main__":
    import unittest

    unittest.main()


class BandReviewChangesTest(test_runner.RunnerTest):
    BEFORE = "- Sam, neighbour (garden shed) — Sam Rivers, Dana, Lee (sam.md)"
    AFTER = "- Sam, neighbour (garden shed) — Sam Rivers (carpenter), Dana, Lee (sam.md)"

    def keep_changes(self) -> None:
        from m2b.curate import machine_state, memory_guard
        from m2b.curate.report import ACTION, Finding

        change = memory_guard.FactChange(memory_guard.REWROTE, "sam.md", self.BEFORE, self.AFTER)
        machine_state.save_memory_changes(
            self.machine,
            [
                Finding("ingest", ACTION, change.described(), change.as_json()),
                Finding(
                    "ingest",
                    ACTION,
                    "memory/ as it was before this run is in /home/alex/copy; check the changes above",
                    {"kind": memory_guard.COPY, "path": "/home/alex/copy", "captures": ["a.md", "b.md"]},
                ),
            ],
        )

    def test_an_open_review_comes_with_its_changes_as_data(self) -> None:
        """Covers: B106"""
        self.curating()
        self.keep_changes()
        self.tasks().add("m2b: review", notes=self.notes())

        review = self.run_json("band")["tasks"]["review"]

        self.assertEqual(
            review["changes"],
            [
                {
                    "kind": "rewrote",
                    "file": "sam.md",
                    "topic": "Sam",
                    "before": "Sam, neighbour (garden shed) — Sam Rivers, Dana, Lee",
                    "after": "Sam, neighbour (garden shed) — Sam Rivers (carpenter), Dana, Lee",
                    "parts": [
                        {"text": "Sam, neighbour (garden shed) — Sam Rivers", "change": "same"},
                        {"text": " (carpenter)", "change": "added"},
                        {"text": ", Dana, Lee", "change": "same"},
                    ],
                }
            ],
        )
        self.assertEqual(review["copies"], [{"path": "/home/alex/copy", "captures": ["a.md", "b.md"]}])
        self.assertEqual(
            review["paragraphs"],
            [
                f'ingest: rewrote the facts line "{self.BEFORE}" as "{self.AFTER}"',
                "ingest: memory/ as it was before this run is in /home/alex/copy; check the changes above",
            ],
        )

    def notes(self, *paragraphs: str) -> str:
        from m2b.curate import machine_state
        from m2b.curate.report import one_line

        kept = [f"{f.step}: {one_line(f.text)}" for f in machine_state.load_memory_changes(self.machine)]
        return "\n\n".join([markers.marker_line(markers.REVIEW), *(paragraphs or kept)])

    def test_changes_the_open_review_no_longer_holds_are_not_named(self) -> None:
        """Covers: B106"""
        self.curating()
        self.keep_changes()
        self.tasks().add("m2b: review", notes=self.notes("lint: broken link in a.md"))

        review = self.run_json("band")["tasks"]["review"]

        self.assertEqual((review["changes"], review["copies"], review["paragraphs"]), ([], [], []))

    def test_a_review_open_over_two_runs_names_both_copies(self) -> None:
        """Covers: B106"""
        from m2b.curate import machine_state, memory_guard
        from m2b.curate.report import ACTION, Finding

        self.curating()
        copy = {"kind": memory_guard.COPY}
        machine_state.save_memory_changes(
            self.machine,
            [
                Finding(
                    "ingest",
                    ACTION,
                    "memory/ ... is in /home/alex/first",
                    {**copy, "path": "/home/alex/first", "captures": ["a.md"]},
                ),
                Finding(
                    "refresh",
                    ACTION,
                    "memory/ ... is in /home/alex/second",
                    {**copy, "path": "/home/alex/second", "captures": []},
                ),
                Finding(
                    "ingest",
                    ACTION,
                    "memory/ ... again in /home/alex/second",
                    {**copy, "path": "/home/alex/second", "captures": ["b.md"]},
                ),
            ],
        )
        self.tasks().add("m2b: review", notes=self.notes())

        self.assertEqual(
            self.run_json("band")["tasks"]["review"]["copies"],
            [{"path": "/home/alex/first", "captures": ["a.md"]}, {"path": "/home/alex/second", "captures": ["b.md"]}],
        )

    def test_without_an_open_review_no_changes_are_named(self) -> None:
        """Covers: B106"""
        self.curating()
        self.keep_changes()

        self.assertNotIn("review", self.run_json("band")["tasks"])

    def test_a_removed_word_and_a_removed_line_are_parts_too(self) -> None:
        """Covers: B106"""
        parts = band._parts("Sam Rivers, Dana, Lee", "Sam Rivers, Lee")
        self.assertEqual(
            parts,
            [
                {"text": "Sam Rivers, ", "change": "same"},
                {"text": "Dana, ", "change": "removed"},
                {"text": "Lee", "change": "same"},
            ],
        )
        self.assertEqual(band._parts("Sam Rivers", None), [{"text": "Sam Rivers", "change": "same"}])
