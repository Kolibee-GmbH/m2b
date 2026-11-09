"""The run record: written by the runner, read by every machine; unknown fields are ignored."""

from __future__ import annotations

import datetime
import json
import tempfile
import unittest
from pathlib import Path

from m2b.curate.report import ACTION, INFO, Finding
from m2b.run_record import (
    FAILED,
    RUN_RECORD,
    RUNNING,
    SUCCEEDED,
    RunRecord,
    RunRecordError,
    StepResult,
    is_interrupted,
    load_run_record,
    write_run_record,
)
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard

START = datetime.datetime(2026, 11, 7, 3, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=1)))


class RunRecordTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.store = FolderStore(base / "sb-test-store", base / "tmp", DatalessGuard(False))
        self.store.root.mkdir()

    def test_a_full_record_reads_back_as_written(self) -> None:
        record = RunRecord(
            state=FAILED,
            machine_id="sb-test-m1",
            started_at=START,
            finished_at=START + datetime.timedelta(minutes=4),
            message="ingest failed: timed out after 15 minutes",
            deadline_at=START + datetime.timedelta(minutes=30),
            last_succeeded_at=START - datetime.timedelta(days=1),
            steps=(StepResult("harvest", "succeeded"), StepResult("ingest", "failed", "timed out after 15 minutes")),
            findings=(
                Finding("lint", ACTION, "memory/dana.md links a missing note"),
                Finding("lint", INFO, "3 evicted"),
            ),
            parts=("worklog", "backup"),
        )

        write_run_record(self.store, record)

        self.assertEqual(load_run_record(self.store), record)
        raw = json.loads(self.store.read_text(RUN_RECORD))
        self.assertEqual(
            raw["steps"][1], {"name": "ingest", "result": "failed", "detail": "timed out after 15 minutes"}
        )
        self.assertEqual(raw["parts"], ["worklog", "backup"])

    def test_times_are_written_in_whole_seconds_so_they_read_back(self) -> None:
        precise = START.replace(microsecond=279691)

        write_run_record(self.store, RunRecord(RUNNING, "sb-test-m1", precise))

        record = load_run_record(self.store)
        assert record is not None
        self.assertEqual(record.started_at, START)
        self.assertIn('"2026-11-07T03:00:00+01:00"', self.store.read_text(RUN_RECORD))

    def test_a_record_from_before_the_runner_still_reads_with_empty_lists(self) -> None:
        self.store.replace(
            RUN_RECORD,
            json.dumps({"state": "succeeded", "machine_id": "sb-test-m1", "started_at": START.isoformat()}).encode(),
        )

        record = load_run_record(self.store)

        assert record is not None
        self.assertEqual((record.steps, record.findings, record.parts), ((), (), ()))
        self.assertIsNone(record.deadline_at)

    def test_malformed_list_entries_are_left_out_instead_of_failing_the_record(self) -> None:
        raw = {
            "state": "succeeded",
            "machine_id": "sb-test-m1",
            "started_at": START.isoformat(),
            "steps": [{"name": "lint", "result": "succeeded"}, "junk", {"result": "failed"}],
            "findings": [{"step": "lint", "kind": "info", "text": "fine"}, 3],
            "parts": "not a list",
        }
        self.store.replace(RUN_RECORD, json.dumps(raw).encode())

        record = load_run_record(self.store)

        assert record is not None
        self.assertEqual(record.steps, (StepResult("lint", "succeeded"),))
        self.assertEqual(record.findings, (Finding("lint", INFO, "fine"),))
        self.assertEqual(record.parts, ())

    def test_a_deadline_that_is_no_time_fails_the_record(self) -> None:
        raw = {"state": "running", "machine_id": "sb-test-m1", "started_at": START.isoformat(), "deadline_at": "soon"}
        self.store.replace(RUN_RECORD, json.dumps(raw).encode())

        with self.assertRaises(RunRecordError):
            load_run_record(self.store)

    def test_the_last_success_is_the_finish_of_a_succeeded_run_and_carried_otherwise(self) -> None:
        earlier = START - datetime.timedelta(days=2)
        finished = START + datetime.timedelta(minutes=3)

        succeeded = RunRecord(SUCCEEDED, "sb-test-m1", START, finished, last_succeeded_at=earlier)
        failed = RunRecord(FAILED, "sb-test-m1", START, finished, last_succeeded_at=earlier)
        never = RunRecord(FAILED, "sb-test-m1", START, finished)

        self.assertEqual(succeeded.last_success, finished)
        self.assertEqual(failed.last_success, earlier)
        self.assertIsNone(never.last_success)

    def test_a_running_record_past_its_deadline_is_an_interrupted_run(self) -> None:
        deadline = START + datetime.timedelta(minutes=30)
        running = RunRecord(RUNNING, "sb-test-m1", START, deadline_at=deadline)

        self.assertFalse(is_interrupted(running, deadline))
        self.assertTrue(is_interrupted(running, deadline + datetime.timedelta(seconds=1)))
        self.assertFalse(is_interrupted(RunRecord(RUNNING, "sb-test-m1", START), deadline + datetime.timedelta(days=9)))
        finished = RunRecord(SUCCEEDED, "sb-test-m1", START, START, deadline_at=deadline)
        self.assertFalse(is_interrupted(finished, deadline + datetime.timedelta(days=1)))


if __name__ == "__main__":
    unittest.main()
