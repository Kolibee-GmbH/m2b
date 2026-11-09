"""The runner's machine state: the lock, the run log, the backoff and the temp folder."""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from m2b.curate import machine_state
from m2b.curate.machine_state import (
    MAX_LOG_BYTES,
    RunLock,
    clear_leftovers,
    last_attempt,
    last_event,
    load_backoff,
    log_event,
    record_attempt,
    record_failure,
    reset_backoff,
)
from m2b.paths import MachinePaths

NOW = datetime.datetime(2026, 11, 7, 9, 0, tzinfo=datetime.timezone.utc)

HOLD_INHERITED = """
import os, sys, time
descriptor = int(sys.argv[1])
os.write(1, b"ready\\n")
time.sleep(30)
"""


class LockTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.machine = MachinePaths(Path(temp.name) / "home")

    def test_a_second_lock_is_refused_while_the_first_is_held_and_granted_after(self) -> None:
        first = RunLock(self.machine)
        self.assertTrue(first.acquire())
        self.addCleanup(first.release)

        self.assertFalse(RunLock(self.machine).acquire())
        self.assertTrue(machine_state.lock_is_held(self.machine))

        first.release()
        self.assertFalse(machine_state.lock_is_held(self.machine))
        second = RunLock(self.machine)
        self.assertTrue(second.acquire())
        second.release()

    def test_a_child_that_inherited_the_lock_keeps_it_after_the_holder_let_go(self) -> None:
        """The lock dies with the last process of the run. Covers: B63"""
        lock = RunLock(self.machine)
        self.assertTrue(lock.acquire())
        child = subprocess.Popen(
            [sys.executable, "-c", HOLD_INHERITED, str(lock.descriptor)],
            stdout=subprocess.PIPE,
            pass_fds=lock.pass_fds,
        )
        assert child.stdout is not None
        self.addCleanup(child.stdout.close)
        self.addCleanup(child.wait)
        self.addCleanup(child.kill)
        self.assertEqual(child.stdout.readline(), b"ready\n")

        lock.release()
        self.assertTrue(machine_state.lock_is_held(self.machine))

        child.kill()
        child.wait()
        self.assertFalse(machine_state.lock_is_held(self.machine))

    def test_the_lock_descriptor_is_not_passed_to_children_unless_asked(self) -> None:
        lock = RunLock(self.machine)
        self.assertTrue(lock.acquire())
        self.addCleanup(lock.release)

        self.assertFalse(os.get_inheritable(lock.descriptor))


class RunLogTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.machine = MachinePaths(Path(temp.name) / "home")

    def test_events_are_json_lines_and_the_last_one_reads_back(self) -> None:
        log_event(self.machine, "refused", "this machine is not the curating machine", NOW)
        log_event(self.machine, "unrecorded", "the run record could not be written: disk full", NOW)

        event = last_event(self.machine)

        assert event is not None
        self.assertEqual(
            (event.kind, event.message, event.time),
            ("unrecorded", "the run record could not be written: disk full", NOW),
        )
        lines = machine_state.run_log(self.machine).read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(line)["kind"] for line in lines], ["refused", "unrecorded"])

    def test_an_attempt_is_overwritten_and_never_written_to_the_run_log(self) -> None:
        log_event(self.machine, "unrecorded", "the run record could not be written: disk full", NOW)
        later = NOW + datetime.timedelta(hours=1)
        record_attempt(self.machine, machine_state.NOT_DUE, "first", later)
        record_attempt(self.machine, machine_state.NOT_DUE, "second", later + datetime.timedelta(hours=1))

        event = last_event(self.machine)
        attempt = last_attempt(self.machine)

        assert event is not None and attempt is not None
        self.assertEqual(event.kind, "unrecorded")
        self.assertEqual((attempt.kind, attempt.message), (machine_state.NOT_DUE, "second"))
        self.assertEqual(len(machine_state.run_log(self.machine).read_text(encoding="utf-8").splitlines()), 1)

    def test_no_attempt_or_an_unreadable_one_is_none(self) -> None:
        self.assertIsNone(last_attempt(self.machine))
        machine_state.attempt_file(self.machine).parent.mkdir(parents=True, exist_ok=True)
        machine_state.attempt_file(self.machine).write_text("not json", encoding="utf-8")

        self.assertIsNone(last_attempt(self.machine))

    def test_no_log_is_no_event_and_an_unreadable_last_line_is_none(self) -> None:
        self.assertIsNone(last_event(self.machine))
        path = machine_state.run_log(self.machine)
        path.parent.mkdir(parents=True)
        path.write_bytes(b'{"kind": "succeeded"}\n\xff garbage\n')

        self.assertIsNone(last_event(self.machine))

    def test_a_time_without_an_offset_reads_as_unknown(self) -> None:
        path = machine_state.run_log(self.machine)
        path.parent.mkdir(parents=True)
        path.write_text('{"time": "2026-11-07T09:00:00", "kind": "unrecorded", "message": "x"}\n', encoding="utf-8")

        event = last_event(self.machine)

        assert event is not None
        self.assertIsNone(event.time)

    def test_the_log_is_rotated_at_one_megabyte(self) -> None:
        path = machine_state.run_log(self.machine)
        path.parent.mkdir(parents=True)
        path.write_bytes(b"x" * MAX_LOG_BYTES + b"\n")

        log_event(self.machine, "succeeded", "", NOW)

        self.assertEqual(path.with_name("run.log.1").stat().st_size, MAX_LOG_BYTES + 1)
        self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 1)


class BackoffTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.machine = MachinePaths(Path(temp.name) / "home")

    def test_each_failure_waits_longer_one_four_then_twenty_hours(self) -> None:
        self.assertIsNone(load_backoff(self.machine))
        waits = []
        for _ in range(4):
            backoff = record_failure(self.machine, NOW)
            waits.append(backoff.retry_at - NOW)
        hours = [wait / datetime.timedelta(hours=1) for wait in waits]
        self.assertEqual(hours, [1, 4, 20, 20])
        loaded = load_backoff(self.machine)
        assert loaded is not None
        self.assertEqual(loaded.failures, 4)

    def test_a_success_resets_it(self) -> None:
        record_failure(self.machine, NOW)
        reset_backoff(self.machine)
        reset_backoff(self.machine)

        self.assertIsNone(load_backoff(self.machine))

    def test_an_unreadable_backoff_file_counts_as_one_failure_at_its_modification_time(self) -> None:
        path = machine_state.backoff_file(self.machine)
        path.parent.mkdir(parents=True)
        path.write_text("{broken", encoding="utf-8")
        modified = NOW.timestamp()
        os.utime(path, (modified, modified))

        backoff = load_backoff(self.machine)

        assert backoff is not None
        self.assertEqual((backoff.failures, backoff.retry_at), (1, NOW + datetime.timedelta(hours=1)))


class LeftoversTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.machine = MachinePaths(Path(temp.name) / "home")

    def _make(self, path: Path, age: datetime.timedelta, folder: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if folder:
            path.mkdir()
            (path / "inside").write_text("x", encoding="utf-8")
        else:
            path.write_text("x", encoding="utf-8")
        moment = (NOW - age).timestamp()
        os.utime(path, (moment, moment))

    def test_old_temp_files_and_findings_files_go_and_recent_ones_stay(self) -> None:
        temp = self.machine.temp_dir
        runs = self.machine.state_dir / "runs"
        self._make(temp / "old-file", datetime.timedelta(hours=2))
        self._make(temp / "model-old", datetime.timedelta(hours=2), folder=True)
        self._make(temp / "being-written", datetime.timedelta(minutes=5))
        self._make(runs / ("a" * 32 + ".jsonl"), datetime.timedelta(days=2))
        self._make(runs / ("b" * 32 + ".jsonl"), datetime.timedelta(hours=2))

        removed = clear_leftovers(self.machine, NOW)

        self.assertEqual(sorted(path.name for path in removed), ["a" * 32 + ".jsonl", "model-old", "old-file"])
        self.assertEqual(sorted(path.name for path in temp.iterdir()), ["being-written"])
        self.assertEqual([path.name for path in runs.iterdir()], ["b" * 32 + ".jsonl"])

    def test_no_state_folder_yet_removes_nothing(self) -> None:
        self.assertEqual(clear_leftovers(self.machine, NOW), [])


if __name__ == "__main__":
    unittest.main()
