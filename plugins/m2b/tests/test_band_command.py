"""``m2b band``: what the band above the prompt shows, with the status line, in one answer."""

from __future__ import annotations

import datetime
import json
from typing import Any
from unittest import mock

import test_runner
from m2b import launcher
from m2b.commands import band, doctor
from m2b.tasks import markers


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


if __name__ == "__main__":
    import unittest

    unittest.main()
