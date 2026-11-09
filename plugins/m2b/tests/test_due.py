"""When a curation run is due: 20 hours after the last success, or a visible file in the inbox (B12)."""

from __future__ import annotations

import datetime
import os
import tempfile
import unittest
from pathlib import Path

from m2b.curate import machine_state
from m2b.curate.due import check_due
from m2b.paths import MachinePaths
from m2b.run_record import FAILED, RUN_RECORD, RUNNING, SUCCEEDED, RunRecord, write_run_record
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard
from store_contract import FakeEviction

NOW = datetime.datetime(2026, 11, 7, 9, 0, tzinfo=datetime.timezone.utc)


def _local(moment: datetime.datetime) -> str:
    return f"{moment.astimezone():%Y-%m-%d %H:%M}"


class DueTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.machine = MachinePaths(base / "home")
        self.eviction = FakeEviction()
        self.store = FolderStore(
            base / "sb-test-store", self.machine.temp_dir, DatalessGuard(True, lstat=self.eviction.lstat)
        )
        (self.store.root / "inbox").mkdir(parents=True)

    def succeeded(self, hours_ago: float) -> None:
        finished = NOW - datetime.timedelta(hours=hours_ago)
        write_run_record(self.store, RunRecord(SUCCEEDED, "sb-test-m1", finished, finished))

    def test_twenty_one_hours_after_the_last_success_a_run_is_due_and_nineteen_it_is_not(self) -> None:
        """Covers: B12"""
        self.succeeded(21)
        self.assertTrue(check_due(self.store, self.machine, NOW).due)

        self.succeeded(19)
        due = check_due(self.store, self.machine, NOW)
        self.assertFalse(due.due)
        self.assertIn(_local(NOW + datetime.timedelta(hours=1)), due.reason)

    def test_one_visible_inbox_file_makes_it_due_and_hidden_files_do_not(self) -> None:
        """Covers: B12"""
        self.succeeded(1)
        (self.store.root / "inbox" / ".DS_Store").write_bytes(b"x")
        (self.store.root / "inbox" / ".sb-tmp-abc").write_bytes(b"x")
        self.assertFalse(check_due(self.store, self.machine, NOW).due)

        (self.store.root / "inbox" / "20261107T080000Z-cli-a1b2.md").write_text("x", encoding="utf-8")
        due = check_due(self.store, self.machine, NOW)
        self.assertTrue(due.due)
        self.assertIn("1 capture", due.reason)

    def test_a_file_the_last_run_could_not_ingest_makes_no_run_due_until_it_changes(self) -> None:
        """Covers: B57"""
        self.succeeded(1)
        stuck = self.store.root / "inbox" / "note.md"
        stuck.write_text("---\ncreated: 2026-01-01\n---\nexported\n", encoding="utf-8")
        machine_state.save_stuck_inbox(self.machine, {"inbox/note.md": stuck.stat().st_mtime_ns})

        self.assertFalse(check_due(self.store, self.machine, NOW).due)

        later = stuck.stat().st_mtime_ns + 2_000_000_000
        os.utime(stuck, ns=(later, later))
        self.assertTrue(check_due(self.store, self.machine, NOW).due)

    def test_a_new_capture_beside_a_stuck_file_makes_a_run_due(self) -> None:
        """Covers: B57"""
        self.succeeded(1)
        stuck = self.store.root / "inbox" / "note.md"
        stuck.write_text("x", encoding="utf-8")
        machine_state.save_stuck_inbox(self.machine, {"inbox/note.md": stuck.stat().st_mtime_ns})
        (self.store.root / "inbox" / "20261107T080000Z-cli-a1b2.md").write_text("x", encoding="utf-8")

        due = check_due(self.store, self.machine, NOW)

        self.assertTrue(due.due)
        self.assertIn("1 capture", due.reason)

    def test_an_evicted_inbox_file_counts_as_waiting(self) -> None:
        self.succeeded(1)
        evicted = self.store.root / "inbox" / "20261107T080000Z-phone-a1b2.md"
        evicted.write_bytes(b"")
        self.eviction.evicted.add(evicted)

        self.assertTrue(check_due(self.store, self.machine, NOW).due)

    def test_without_any_successful_run_it_is_due(self) -> None:
        self.assertTrue(check_due(self.store, self.machine, NOW).due)
        start = NOW - datetime.timedelta(hours=1)
        write_run_record(self.store, RunRecord(FAILED, "sb-test-m1", start, start))
        self.assertTrue(check_due(self.store, self.machine, NOW).due)

    def test_a_failed_run_carries_the_last_success_so_the_due_time_does_not_move(self) -> None:
        """Covers: B13"""
        start = NOW - datetime.timedelta(hours=2)
        last_success = NOW - datetime.timedelta(hours=10)
        write_run_record(self.store, RunRecord(FAILED, "sb-test-m1", start, start, last_succeeded_at=last_success))

        self.assertFalse(check_due(self.store, self.machine, NOW).due)

    def test_after_a_failure_the_backoff_wins_even_over_a_full_inbox(self) -> None:
        """Covers: B63"""
        (self.store.root / "inbox" / "20261107T080000Z-cli-a1b2.md").write_text("x", encoding="utf-8")
        machine_state.record_failure(self.machine, NOW - datetime.timedelta(minutes=30))

        due = check_due(self.store, self.machine, NOW)
        self.assertFalse(due.due)
        self.assertIn(_local(NOW + datetime.timedelta(minutes=30)), due.reason)

        self.assertTrue(check_due(self.store, self.machine, NOW + datetime.timedelta(hours=1)).due)

    def test_a_run_holding_the_lock_is_not_due_again(self) -> None:
        """Covers: B63"""
        lock = machine_state.RunLock(self.machine)
        self.assertTrue(lock.acquire())
        self.addCleanup(lock.release)

        due = check_due(self.store, self.machine, NOW)

        self.assertFalse(due.due)
        self.assertIn("in progress", due.reason)

    def test_a_record_that_cannot_be_read_leaves_it_to_the_run(self) -> None:
        self.store.replace(RUN_RECORD, b"{broken")
        self.assertTrue(check_due(self.store, self.machine, NOW).due)

    def test_a_running_record_without_the_lock_is_a_dead_run_and_due_by_its_last_success(self) -> None:
        start = NOW - datetime.timedelta(hours=1)
        write_run_record(
            self.store, RunRecord(RUNNING, "sb-test-m1", start, last_succeeded_at=NOW - datetime.timedelta(hours=30))
        )

        self.assertTrue(check_due(self.store, self.machine, NOW).due)


if __name__ == "__main__":
    unittest.main()
