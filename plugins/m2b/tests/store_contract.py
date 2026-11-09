"""The contract every store backend passes; each backend's test module runs it with its own store."""

from __future__ import annotations

import errno
import os
import tempfile
import types
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest import mock

from m2b.store.base import EvictedFileError, PathOutsideStoreError, Store, StoreReadError
from m2b.store.guard import SF_DATALESS, DatalessGuard


class FakeEviction:
    """Answers ``lstat`` like macOS does for evicted files, for the paths it was told about."""

    def __init__(self) -> None:
        self.evicted: set[Path] = set()

    def lstat(self, path: str | os.PathLike[str]) -> Any:
        info = os.lstat(path)
        if Path(path) not in self.evicted:
            return info
        return types.SimpleNamespace(st_flags=SF_DATALESS, st_size=info.st_size, st_mode=info.st_mode)


class Contracts:
    """Holds the contract so that test discovery does not run it without a backend."""

    class StoreContract(unittest.TestCase):
        """Subclass it and set ``make_store`` to a backend constructor (root, temp folder, guard)."""

        make_store: Callable[[Path, Path, DatalessGuard], Store]

        def setUp(self) -> None:
            self._temp = tempfile.TemporaryDirectory()
            base = Path(self._temp.name)
            self.root = base / "sb-test-store"
            (self.root / "inbox").mkdir(parents=True)
            self.temp_dir = base / "machine-tmp"
            self.eviction = FakeEviction()
            self.store = type(self).make_store(self.root, self.temp_dir, DatalessGuard(True, lstat=self.eviction.lstat))

        def tearDown(self) -> None:
            self._temp.cleanup()

        def _evict(self, relative: str) -> None:
            self.eviction.evicted.add(self.root / relative)

        def test_a_created_file_reads_back(self) -> None:
            self.store.create_exclusive("inbox/a.md", b"Dana likes maps.\n")

            self.assertEqual(self.store.read_bytes("inbox/a.md"), b"Dana likes maps.\n")
            self.assertEqual(self.store.read_text("inbox/a.md"), "Dana likes maps.\n")

        def test_two_creates_of_one_name_leave_the_first(self) -> None:
            self.store.create_exclusive("inbox/a.md", b"first")

            with self.assertRaises(FileExistsError):
                self.store.create_exclusive("inbox/a.md", b"second")

            self.assertEqual(self.store.read_bytes("inbox/a.md"), b"first")

        def test_create_makes_missing_folders(self) -> None:
            self.store.create_exclusive("corpus/2026/03/a.md", b"x")

            self.assertTrue((self.root / "corpus" / "2026" / "03" / "a.md").is_file())

        def test_replace_writes_the_new_content(self) -> None:
            self.store.create_exclusive("memory/MEMORY.md", b"old")

            self.store.replace("memory/MEMORY.md", b"new")

            self.assertEqual(self.store.read_bytes("memory/MEMORY.md"), b"new")

        def test_writes_leave_no_temp_file_in_the_store(self) -> None:
            """Covers: X22"""
            self.store.create_exclusive("inbox/a.md", b"x")
            self.store.replace("inbox/a.md", b"y")

            self.assertEqual(sorted(p.name for p in self.root.rglob("*") if p.is_file()), ["a.md"])

        def test_listing_shows_visible_files_only(self) -> None:
            """Covers: X22"""
            for name in ("inbox/b.md", "inbox/a.md", "inbox/.sb-tmp-0011", "inbox/.DS_Store", "inbox/sub/c.md"):
                (self.root / name).parent.mkdir(parents=True, exist_ok=True)
                (self.root / name).write_bytes(b"x")

            self.assertEqual(self.store.list_files("inbox"), ["inbox/a.md", "inbox/b.md"])
            self.assertEqual(
                self.store.list_files("inbox", recursive=True), ["inbox/a.md", "inbox/b.md", "inbox/sub/c.md"]
            )
            self.assertEqual(self.store.list_files("missing"), [])

        def test_paths_outside_the_store_are_refused(self) -> None:
            for relative in ("../escape.md", "/etc/hosts", "inbox/../../escape.md", ""):
                with self.subTest(relative=relative), self.assertRaises(PathOutsideStoreError):
                    self.store.read_bytes(relative)

        def test_an_evicted_file_is_listed_and_never_read(self) -> None:
            """Covers: B6, B39"""
            (self.root / "inbox" / "far.md").write_bytes(b"not here")
            (self.root / "inbox" / "near.md").write_bytes(b"here")
            self._evict("inbox/far.md")

            self.assertEqual(self.store.check_local(["inbox"]), ["inbox/far.md"])
            self.assertEqual(self.store.check_local(["inbox/near.md", "inbox/far.md"]), ["inbox/far.md"])
            with self.assertRaises(EvictedFileError) as caught:
                self.store.read_bytes("inbox/far.md")
            self.assertIn("m2b store fetch inbox/far.md", str(caught.exception))

        def test_a_replace_into_an_evicted_file_is_refused(self) -> None:
            (self.root / "inbox" / "far.md").write_bytes(b"not here")
            self._evict("inbox/far.md")

            with self.assertRaises(EvictedFileError):
                self.store.replace("inbox/far.md", b"new")

            self.assertEqual((self.root / "inbox" / "far.md").read_bytes(), b"not here")

        def test_an_evicted_folder_is_listed_as_the_folder(self) -> None:
            """Covers: B6"""
            (self.root / "corpus" / "2025" / "01").mkdir(parents=True)
            (self.root / "corpus" / "2025" / "01" / "a.md").write_bytes(b"x")
            (self.root / "corpus" / "2026").mkdir()
            (self.root / "corpus" / "2026" / "b.md").write_bytes(b"y")
            self._evict("corpus/2025")

            self.assertEqual(self.store.check_local(["corpus"]), ["corpus/2025"])

        def test_a_read_that_fails_for_another_reason_is_a_store_error(self) -> None:
            (self.root / "inbox" / "a.md").mkdir()

            with self.assertRaises(StoreReadError):
                self.store.read_bytes("inbox/a.md")

        def test_a_subfolder_that_cannot_be_listed_is_never_shown_as_empty(self) -> None:
            """Covers: B6"""
            (self.root / "inbox" / "sub").mkdir()
            (self.root / "inbox" / "a.md").write_bytes(b"x")
            blocked = self.root / "inbox" / "sub"
            real_iterdir = Path.iterdir

            def iterdir(path: Path) -> Any:
                if path == blocked:
                    raise OSError(errno.EDEADLK, "Resource deadlock avoided")
                return real_iterdir(path)

            with mock.patch.object(Path, "iterdir", iterdir), self.assertRaises(EvictedFileError):
                self.store.list_files("inbox", recursive=True)

        def test_folder_symlinks_are_not_followed(self) -> None:
            outside = self.root.parent / "outside"
            outside.mkdir()
            (outside / "far.md").write_bytes(b"x")
            (self.root / "inbox" / "link").symlink_to(outside, target_is_directory=True)
            (self.root / "inbox" / "loop").symlink_to(self.root / "inbox", target_is_directory=True)
            self.eviction.evicted.update({outside / "far.md", self.root / "inbox" / "link" / "far.md"})

            self.assertEqual(self.store.check_local(["inbox"]), [])
            self.assertEqual(self.store.list_files("inbox", recursive=True), [])

        def test_delete_removes_a_file_and_refuses_a_missing_one(self) -> None:
            self.store.create_exclusive("tasks/a1b2c3d4e5f6.md", b"x")

            self.store.delete("tasks/a1b2c3d4e5f6.md")

            self.assertFalse(self.store.exists("tasks/a1b2c3d4e5f6.md"))
            with self.assertRaises(FileNotFoundError):
                self.store.delete("tasks/a1b2c3d4e5f6.md")

        def test_an_inactive_guard_reads_every_file(self) -> None:
            """Covers: B39"""
            (self.root / "inbox" / "a.md").write_bytes(b"local")
            store = type(self).make_store(self.root, self.temp_dir, DatalessGuard(False, lstat=self.eviction.lstat))
            self._evict("inbox/a.md")

            self.assertEqual(store.check_local(["inbox"]), [])
            self.assertEqual(store.read_bytes("inbox/a.md"), b"local")
