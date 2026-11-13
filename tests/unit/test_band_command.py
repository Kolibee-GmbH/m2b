"""``m2b band``: what the band above the prompt shows, with the status line, in one answer."""

from __future__ import annotations

import datetime
import json
from typing import Any
from unittest import mock

import test_proposals_command
import test_runner
from m2b import launcher, proposals
from m2b.commands import band, doctor
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

        due = self.band()["tasks"]["due"]

        self.assertEqual([task["title"] for task in due], ["Return the drill", "Call Dana"])
        self.assertEqual([task["overdue"] for task in due], [True, False])

    def test_the_due_tasks_are_left_out_when_band_due_tasks_is_off(self) -> None:
        """Covers: B102"""
        self.curating()
        self.tasks().add("Call Dana", due=datetime.date.today())
        config = json.loads(self.machine.config_file.read_text(encoding="utf-8"))
        config["band"] = {"due_tasks": False}
        self.machine.config_file.write_text(json.dumps(config), encoding="utf-8")

        self.assertNotIn("due", self.band()["tasks"])

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

    def test_a_store_without_proposals_answers_an_empty_list(self) -> None:
        """Covers: B126"""
        self.assertEqual(self.band()["proposals"], {"proposals": [], "answered": 0})

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
        target.write_text(json.dumps({"format": 2, "proposals": {}}), encoding="utf-8")

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
