"""Writing a file whole by the core's rules: into the store through the machine's temp folder, on
the machine through a hidden file beside the target; and the evicted check, which the core's guard answers."""

from __future__ import annotations

import os
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from m2b import atomic_file
from m2b.store.guard import SF_DATALESS, DatalessGuard
from m2b_worklog import files


class Interrupted(Exception):
    """Stands for the process dying at the last step of a write."""


class FilesFixture(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = Path(temp.name) / "sb-test-store"
        self.store.mkdir()
        self.temp_dir = Path(temp.name) / "machine" / "tmp"
        self.machine = Path(temp.name) / "machine" / "state"
        self.machine.mkdir(parents=True)

    def names_in(self, folder: Path) -> list[str]:
        return sorted(path.name for path in folder.iterdir())

    @contextmanager
    def last_steps(self, step: str, folder: Path, break_off: bool = False) -> Iterator[list[tuple[Path, list[str]]]]:
        """Each last step of a write (``os.replace`` or ``os.link``): its temporary file, the folder at that moment."""
        seen: list[tuple[Path, list[str]]] = []
        real = getattr(os, step)

        def recording(source: Any, target: Any) -> None:
            seen.append((Path(source), self.names_in(folder)))
            if break_off:
                raise Interrupted(step)
            real(source, target)

        with mock.patch.object(atomic_file.os, step, recording):
            yield seen


class StoreFileTest(FilesFixture):
    def test_a_file_in_the_store_is_replaced_from_the_machines_temp_folder(self) -> None:
        """Covers: B135"""
        target = self.store / "ledger.json"
        target.write_bytes(b"old")

        with self.last_steps("replace", self.store) as seen:
            files.replace_in_store(target, b"new", self.temp_dir)

        [(temporary, store_at_that_moment)] = seen
        self.assertEqual(temporary.parent, self.temp_dir)
        self.assertEqual(store_at_that_moment, ["ledger.json"])
        self.assertEqual(target.read_bytes(), b"new")
        self.assertEqual(self.names_in(self.temp_dir), [])

    def test_a_new_file_in_the_store_is_created_from_the_machines_temp_folder(self) -> None:
        """Covers: B135"""
        with self.last_steps("link", self.store) as seen:
            created = files.create_in_store(self.store / "note.md", b"first", self.temp_dir)

        [(temporary, store_at_that_moment)] = seen
        self.assertTrue(created)
        self.assertEqual(temporary.parent, self.temp_dir)
        self.assertEqual(store_at_that_moment, [])
        self.assertEqual(self.names_in(self.store), ["note.md"])
        self.assertEqual(self.names_in(self.temp_dir), [])

    def test_a_write_broken_off_at_its_last_step_leaves_the_store_as_it_was(self) -> None:
        """Covers: B135"""
        target = self.store / "ledger.json"
        target.write_bytes(b"old")

        with self.last_steps("replace", self.store, break_off=True), self.assertRaises(Interrupted):
            files.replace_in_store(target, b"new", self.temp_dir)
        with self.last_steps("link", self.store, break_off=True), self.assertRaises(Interrupted):
            files.create_in_store(self.store / "note.md", b"first", self.temp_dir)

        self.assertEqual(self.names_in(self.store), ["ledger.json"])
        self.assertEqual(target.read_bytes(), b"old")

    def test_a_taken_name_is_left_alone(self) -> None:
        target = self.store / "note.md"

        self.assertTrue(files.create_in_store(target, b"first", self.temp_dir))
        self.assertFalse(files.create_in_store(target, b"second", self.temp_dir))

        self.assertEqual(target.read_bytes(), b"first")
        self.assertEqual(self.names_in(self.store), ["note.md"])
        self.assertEqual(self.names_in(self.temp_dir), [])


class MachineFileTest(FilesFixture):
    def test_a_file_on_the_machine_is_replaced_from_a_hidden_file_beside_it(self) -> None:
        target = self.machine / "recording"
        target.write_bytes(b"off\n")

        with self.last_steps("replace", self.machine) as seen:
            files.replace_file(target, b"on\n")

        [(temporary, _)] = seen
        self.assertEqual(temporary.parent, self.machine)
        self.assertTrue(temporary.name.startswith(atomic_file.HIDDEN_TEMP_PREFIX))
        self.assertEqual(target.read_bytes(), b"on\n")
        self.assertEqual(self.names_in(self.machine), ["recording"])
        self.assertFalse(self.temp_dir.exists())


class EvictedTest(FilesFixture):
    def test_whether_a_file_is_evicted_is_the_cores_guard_to_say(self) -> None:
        """Covers: B135"""
        evicted, local = self.store / "evicted.md", self.store / "local.md"
        flags = {evicted: SF_DATALESS, local: 0}
        guard = DatalessGuard(True, lstat=lambda path: SimpleNamespace(st_flags=flags[Path(path)]))

        with mock.patch.object(files, "guard_for_platform", return_value=guard):
            self.assertTrue(files.is_evicted(evicted))
            self.assertFalse(files.is_evicted(local))

    def test_a_file_that_is_here_is_not_evicted(self) -> None:
        local = self.store / "local.md"
        local.write_bytes(b"here")

        self.assertFalse(files.is_evicted(local))


if __name__ == "__main__":
    unittest.main()
