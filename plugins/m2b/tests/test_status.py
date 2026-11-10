"""``m2b status``: inbox, due or running, the run record and the backends, for the status line under the prompt."""

from __future__ import annotations

import datetime
import json
from typing import Any
from unittest import mock

import test_runner
from m2b import cli
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
