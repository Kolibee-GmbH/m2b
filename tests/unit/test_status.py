"""``m2b status``: inbox, due or running, the run record and the backends, for the status line under the prompt."""

from __future__ import annotations

import datetime
import json
from typing import Any
from unittest import mock

import test_runner
from m2b import cli, proposals
from m2b.curate import machine_state
from m2b.run_record import RUN_RECORD


def _iso(moment: datetime.datetime) -> str:
    return moment.isoformat(timespec="seconds")


class StatusTest(test_runner.RunnerTest):
    def status(self) -> dict[str, Any]:
        result: dict[str, Any] = self.run_json("status")
        return result

    def record(self, **fields: Any) -> None:
        self.write(RUN_RECORD, json.dumps({"machine_id": "sb-test-m1", **fields}))

    def test_on_the_curating_machine_it_reports_inbox_due_run_and_backends(self) -> None:
        self.curating()
        self.capture()
        self.capture("20261107T070100Z-cli-c3d4.md")
        finished = datetime.datetime.now().astimezone() - datetime.timedelta(hours=2)
        self.record(state="succeeded", started_at=_iso(finished), finished_at=_iso(finished))

        status = self.status()

        self.assertEqual(status["machine_id"], "sb-test-m1")
        self.assertTrue(status["this_machine_curates"])
        self.assertEqual(status["inbox"], {"count": 2, "evicted": 0})
        self.assertEqual(status["due"]["due"], True)
        self.assertEqual(status["run"]["state"], "succeeded")
        self.assertEqual(status["run"]["finished_at"], _iso(finished))
        self.assertEqual(status["backends"]["store"]["state"], "reachable")
        self.assertEqual(status["backends"]["tasks"]["state"], "reachable")
        self.assertEqual(status["backends"]["calendar"]["state"], "not configured")
        self.assertEqual(status["addons"], {"worklog": False})

    def test_a_run_holding_the_lock_is_running(self) -> None:
        self.curating()
        start = datetime.datetime.now().astimezone() - datetime.timedelta(minutes=2)
        self.record(state="running", started_at=_iso(start), deadline_at=_iso(start + datetime.timedelta(minutes=30)))
        lock = machine_state.RunLock(self.machine)
        self.assertTrue(lock.acquire())
        self.addCleanup(lock.release)

        status = self.status()

        self.assertEqual(status["run"]["state"], "running")
        self.assertFalse(status["due"]["due"])

    def test_a_running_record_without_its_lock_on_this_machine_is_an_interrupted_run(self) -> None:
        self.curating()
        start = datetime.datetime.now().astimezone() - datetime.timedelta(minutes=2)
        self.record(state="running", started_at=_iso(start), deadline_at=_iso(start + datetime.timedelta(minutes=30)))

        self.assertEqual(self.status()["run"]["state"], "interrupted")

    def test_another_machines_running_record_counts_as_running_until_its_deadline(self) -> None:
        self.curating()
        start = datetime.datetime.now().astimezone() - datetime.timedelta(minutes=2)
        self.record(
            machine_id="sb-test-m2",
            state="running",
            started_at=_iso(start),
            deadline_at=_iso(start + datetime.timedelta(minutes=30)),
        )
        self.set_curating("sb-test-m2")

        status = self.status()
        self.assertEqual(status["run"]["state"], "running")
        self.assertFalse(status["this_machine_curates"])
        self.assertIsNone(status["due"])

        late = start - datetime.timedelta(hours=2)
        self.record(
            machine_id="sb-test-m2",
            state="running",
            started_at=_iso(late),
            deadline_at=_iso(late + datetime.timedelta(minutes=30)),
        )
        self.assertEqual(self.status()["run"]["state"], "interrupted")

    def test_a_record_that_cannot_be_read_says_so_instead_of_nothing(self) -> None:
        self.curating()
        self.write(RUN_RECORD, "{broken")

        status = self.status()

        self.assertIn("cannot be read", status["run"]["error"])

    def test_no_run_yet_is_state_none(self) -> None:
        self.curating()
        self.assertEqual(self.status()["run"], {"state": "none"})

    def test_an_unreachable_backend_says_so(self) -> None:
        self.curating(tasks={"backend": "apple-reminders", "list": "sb-test-missing"})

        tasks = self.status()["backends"]["tasks"]

        self.assertEqual(tasks["state"], "not reachable")
        self.assertIn("sb-test-missing", tasks["detail"])

    def test_the_backend_probes_are_cached_for_five_minutes(self) -> None:
        self.curating()
        with mock.patch("m2b.commands.status.probe_backends", wraps=_counting()) as probes:
            self.status()
            self.status()
            self.assertEqual(probes.call_count, 1)
            cache = self.machine.state_dir / "status-cache.json"
            raw = json.loads(cache.read_text(encoding="utf-8"))
            old = datetime.datetime.fromisoformat(raw["checked_at"]) - datetime.timedelta(minutes=6)
            raw["checked_at"] = old.isoformat()
            cache.write_text(json.dumps(raw), encoding="utf-8")
            self.status()
            self.assertEqual(probes.call_count, 2)

    def test_a_later_attempt_that_was_not_due_is_shown_beside_the_last_run(self) -> None:
        self.curating()
        now = datetime.datetime.now().astimezone()
        finished = now - datetime.timedelta(hours=2)
        self.record(state="succeeded", started_at=_iso(finished), finished_at=_iso(finished))
        tried = now - datetime.timedelta(hours=1)
        machine_state.record_attempt(self.machine, machine_state.NOT_DUE, "the last successful run was at ...", tried)

        status = self.status()
        _, out, _ = self.run_command("status")

        self.assertEqual(
            status["last_attempt"],
            {"kind": "not_due", "at": _iso(tried), "message": "the last successful run was at ..."},
        )
        self.assertIn(f"last attempt: not due at {_iso(tried)}", out)

    def test_a_paused_machine_says_so_beside_what_is_due(self) -> None:
        """Covers: B161"""
        self.curating(curation={"paused": True})
        self.capture()

        status = self.status()
        _, out, _ = self.run_command("status")

        self.assertTrue(status["paused"])
        self.assertEqual(status["due"]["due"], True)
        self.assertIn("paused: no curation run starts by itself on this machine", out)

    def test_a_scheduled_attempt_on_a_paused_machine_shows_as_the_last_attempt(self) -> None:
        """Covers: B161"""
        self.curating(curation={"paused": True})

        self.run_command("curate")
        _, out, _ = self.run_command("status")

        self.assertIn("last attempt: paused at ", out)

    def test_a_machine_that_is_not_paused_has_no_line_about_it(self) -> None:
        self.curating()

        status = self.status()
        _, out, _ = self.run_command("status")

        self.assertFalse(status["paused"])
        self.assertNotIn("paused", out)

    def test_an_attempt_older_than_the_last_run_is_not_shown(self) -> None:
        self.curating()
        now = datetime.datetime.now().astimezone()
        machine_state.record_attempt(self.machine, machine_state.NOT_DUE, "x", now - datetime.timedelta(hours=3))
        finished = now - datetime.timedelta(hours=2)
        self.record(state="succeeded", started_at=_iso(finished), finished_at=_iso(finished))

        self.assertIsNone(self.status()["last_attempt"])

    def test_the_text_form_is_short_lines(self) -> None:
        self.curating()
        self.capture()

        code, out, _ = self.run_command("status")

        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("inbox: 1", out)
        self.assertIn("tasks: reachable", out)
        self.assertIn("add-ons on: none", out)

    def proposed(self, *ended: tuple[str, float], counts: dict[str, proposals.Tally] | None = None) -> None:
        """Proposals in the store, one per state given, settled (or added) so many days ago."""
        now = datetime.datetime.now().astimezone()
        entries = {
            f"{number:012x}": proposals.Entry(
                "person",
                f"Fact {number}.",
                f"the words of fact {number}",
                now.date(),
                state,
                now - datetime.timedelta(days=days),
            )
            for number, (state, days) in enumerate(ended)
        }
        proposals.save(self.store, proposals.Proposals(entries, counts=counts or {}))

    def test_it_shows_the_share_kept_of_what_was_answered_in_the_last_thirty_days(self) -> None:
        """Covers: B133"""
        self.curating(curation={"read_sessions": True})
        self.proposed(
            ("kept", 0),
            ("kept", 29.9),
            ("kept", 30.1),
            ("dropped", 12),
            ("expired", 3),
            ("open", 20),
            counts={"person": proposals.Tally(proposed=9, kept=5, dropped=1, expired=1, not_quoted=2)},
        )

        status = self.status()
        _, out, _ = self.run_command("status")

        nothing = {"proposed": 0, "kept": 0, "dropped": 0, "expired": 0, "not_quoted": 0}
        self.assertEqual(
            status["proposal_answers"],
            {
                "days": 30,
                "kept": 2,
                "dropped": 1,
                "expired": 1,
                "keep_rate": 0.67,
                "counts": {
                    "person": {"proposed": 9, "kept": 5, "dropped": 1, "expired": 1, "not_quoted": 2},
                    "agreement": nothing,
                    "commitment": nothing,
                    "personal": nothing,
                },
            },
        )
        self.assertIn("\nproposals: kept 2 of 3 answered in the last 30 days (67%), 1 expired without an answer\n", out)

    def test_without_an_answer_in_the_thirty_days_it_shows_no_rate_instead_of_none_kept(self) -> None:
        """Covers: B133"""
        self.curating()
        self.proposed(("kept", 31), ("open", 2))

        status = self.status()
        _, out, _ = self.run_command("status")

        answers = status["proposal_answers"]
        self.assertEqual((answers["kept"], answers["dropped"], answers["expired"]), (0, 0, 0))
        self.assertIsNone(answers["keep_rate"])
        self.assertIn("\nproposals: no answer in the last 30 days\n", out)
        self.assertNotIn("%", out)

    def test_proposals_that_only_expired_are_named_and_give_no_rate(self) -> None:
        """Covers: B133"""
        self.curating()
        self.proposed(("expired", 1), ("expired", 2))

        _, out, _ = self.run_command("status")

        self.assertIsNone(self.status()["proposal_answers"]["keep_rate"])
        self.assertIn("\nproposals: no answer in the last 30 days, 2 expired without an answer\n", out)

    def test_a_machine_that_reads_no_sessions_in_a_store_without_proposals_shows_nothing_of_it(self) -> None:
        """Covers: B133"""
        self.curating()

        _, out, _ = self.run_command("status")

        self.assertNotIn("proposal_answers", self.status())
        self.assertNotIn("proposals", out)

    def test_a_store_that_only_holds_counts_of_proposals_long_gone_still_shows_the_part(self) -> None:
        """Covers: B133"""
        self.curating()
        self.proposed(counts={"agreement": proposals.Tally(proposed=2, dropped=2)})

        answers = self.status()["proposal_answers"]

        self.assertEqual(answers["counts"]["agreement"]["dropped"], 2)
        self.assertIsNone(answers["keep_rate"])

    def test_a_machine_that_reads_the_sessions_shows_the_part_before_anything_was_proposed(self) -> None:
        """Covers: B133"""
        self.curating(curation={"read_sessions": True})

        _, out, _ = self.run_command("status")

        self.assertIsNone(self.status()["proposal_answers"]["keep_rate"])
        self.assertIn("\nproposals: no answer in the last 30 days\n", out)

    def test_a_proposals_file_that_cannot_be_used_says_so_instead_of_nothing(self) -> None:
        """Covers: B133"""
        self.curating()
        self.write(proposals.PROPOSALS_FILE, json.dumps({"format": 2, "proposals": {}}))

        _, out, _ = self.run_command("status")

        self.assertIn("format 2", self.status()["proposal_answers"]["error"])
        self.assertIn("\nproposals: could not look: ", out)

    def set_curating(self, machine_id: str) -> None:
        path = self.store_root / "store.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["curating_machine"] = machine_id
        path.write_text(json.dumps(raw), encoding="utf-8")


def _counting() -> Any:
    from m2b.commands import status

    return status.probe_backends


if __name__ == "__main__":
    import unittest

    unittest.main()
