"""The contract every store backend passes; each backend's test module runs it with its own store."""

from __future__ import annotations

import errno
import os
import shutil
import tempfile
import types
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest import mock

from m2b.store import symlinks
from m2b.store.base import EvictedFileError, PathOutsideStoreError, Scan, Store, StoreReadError, SymlinkError
from m2b.store.guard import SF_DATALESS, DatalessGuard

SECRET = b"OUTSIDE-SECRET\n"


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
        """Subclass it and set ``make_store`` to a backend constructor (root, temp folder, guard).

        ``copy_of_plan`` is a name the backend's sync service gives a conflict copy of ``plan.md``.
        """

        make_store: Callable[[Path, Path, DatalessGuard], Store]
        copy_of_plan: str

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

        def _put(self, relative: str, data: bytes) -> None:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

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
            self.assertEqual(self.store.scan("inbox"), Scan([], [], ["inbox/link", "inbox/loop"]))

        def test_a_file_symlink_is_never_listed_and_never_read(self) -> None:
            """Covers: B166"""
            self._put("corpus/a.md", b"Dana likes maps.\n")
            (self.root / "inbox" / "note.txt").symlink_to(self._outside_file())
            (self.root / "inbox" / "inside.md").symlink_to(self.root / "corpus" / "a.md")
            (self.root / "inbox" / "nowhere.md").symlink_to(self.root.parent / "missing.md")
            links = ["inbox/inside.md", "inbox/note.txt", "inbox/nowhere.md"]

            self.assertEqual(self.store.list_files("inbox"), [])
            self.assertEqual(self.store.scan("inbox"), Scan([], [], links))
            self._evict("inbox/note.txt")
            self.assertEqual(self.store.check_local(["inbox", "inbox/note.txt"]), [])
            for relative in links:
                for read in (self.store.read_bytes, self.store.read_text):
                    with self.subTest(relative=relative, read=read.__name__):
                        with self.assertRaises(SymlinkError) as caught:
                            read(relative)
                        self.assertIn(f"{relative} is a symlink", str(caught.exception))

        def test_a_path_through_a_folder_symlink_is_never_listed_and_never_read(self) -> None:
            """Covers: B166"""
            outside = self._outside_file().parent
            (self.root / "inbox" / "scans").symlink_to(outside, target_is_directory=True)
            (self.root / "memory").symlink_to(outside, target_is_directory=True)

            for folder, behind in (("inbox/scans", "inbox/scans/secret.txt"), ("memory", "memory/secret.txt")):
                with self.subTest(folder=folder):
                    self.assertEqual(self.store.list_files(folder, recursive=True), [])
                    self.assertEqual(self.store.scan(folder), Scan([], [], [folder]))
                    self._evict(behind)
                    self.assertEqual(self.store.check_local([folder, behind]), [])
                    with self.assertRaises(SymlinkError) as caught:
                        self.store.read_bytes(behind)
                    self.assertIn(f"{folder} is a symlink", str(caught.exception))

        def test_the_read_itself_refuses_a_symlink_so_none_can_be_slipped_in_after_a_check(self) -> None:
            """Covers: B166"""
            outside = self._outside_file()
            (self.root / "inbox" / "note.txt").symlink_to(outside)
            (self.root / "inbox" / "scans").symlink_to(outside.parent, target_is_directory=True)

            for relative in ("inbox/note.txt", "inbox/scans/secret.txt"):
                # As if the symlink had come after every check: the store is told there is none.
                with (
                    self.subTest(relative=relative),
                    mock.patch.object(symlinks, "symlink_on", return_value=None),
                    self.assertRaises(StoreReadError),
                ):
                    self.store.read_bytes(relative)

        def test_nothing_is_written_or_deleted_through_a_folder_symlink(self) -> None:
            """Covers: B166"""
            outside = self._outside_file().parent
            shutil.rmtree(self.root / "inbox")
            (self.root / "inbox").symlink_to(outside, target_is_directory=True)

            with self.assertRaises(SymlinkError):
                self.store.create_exclusive("inbox/a.md", b"a capture")
            with self.assertRaises(SymlinkError):
                self.store.replace("inbox/secret.txt", b"overwritten")
            with self.assertRaises(SymlinkError):
                self.store.delete("inbox/secret.txt")

            self.assertEqual({path.name: path.read_bytes() for path in outside.iterdir()}, {"secret.txt": SECRET})

        def test_replacing_or_deleting_a_file_symlink_leaves_its_target_alone(self) -> None:
            """Covers: B166"""
            outside = self._outside_file()
            (self.root / "memory").mkdir()
            for name in ("memory/MEMORY.md", "memory/dana.md"):
                (self.root / name).symlink_to(outside)

            self.store.replace("memory/MEMORY.md", b"# Facts\n")
            self.store.delete("memory/dana.md")

            self.assertEqual(outside.read_bytes(), SECRET)
            self.assertFalse((self.root / "memory" / "MEMORY.md").is_symlink())
            self.assertEqual(self.store.read_bytes("memory/MEMORY.md"), b"# Facts\n")
            self.assertEqual(self.store.list_files("memory"), ["memory/MEMORY.md"])

        def _outside_file(self) -> Path:
            """A file beside the store that no store path may reach."""
            outside = self.root.parent / "outside" / "secret.txt"
            outside.parent.mkdir()
            outside.write_bytes(SECRET)
            return outside

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

        def test_a_conflict_copy_is_removable_only_when_it_equals_its_original(self) -> None:
            """Covers: X8"""
            self._put("inbox/plan.md", b"draft")
            self._put(f"inbox/{self.copy_of_plan}", b"draft")
            self._put("corpus/2026/11/plan.md", b"draft")
            self._put(f"corpus/2026/11/{self.copy_of_plan}", b"another draft")

            copies = {copy.path: (copy.original, copy.removable) for copy in self.store.conflict_copies()}

            self.assertEqual(
                copies,
                {
                    f"inbox/{self.copy_of_plan}": ("inbox/plan.md", True),
                    f"corpus/2026/11/{self.copy_of_plan}": ("corpus/2026/11/plan.md", False),
                },
            )

        def test_a_copy_counts_only_next_to_a_file_it_names_as_its_original(self) -> None:
            """Covers: B150"""
            self._put(f"inbox/{self.copy_of_plan}", b"draft")
            self._put("corpus/plan.md", b"draft")
            self._put(f"memory/{self.copy_of_plan}", b"draft")
            (self.root / "memory" / "plan.md").mkdir()

            self.assertEqual(self.store.conflict_copies(), [])

        def test_conflict_copies_are_looked_for_below_the_folder_asked_for(self) -> None:
            for folder in ("inbox", "corpus"):
                self._put(f"{folder}/plan.md", b"draft")
                self._put(f"{folder}/{self.copy_of_plan}", b"draft")

            self.assertEqual(
                [copy.path for copy in self.store.conflict_copies("corpus")], [f"corpus/{self.copy_of_plan}"]
            )
            self.assertEqual(self.store.conflict_copies("tasks"), [])

        def test_an_evicted_copy_or_original_is_a_copy_that_is_never_compared(self) -> None:
            """Covers: X8, B6"""
            for folder in ("inbox", "corpus"):
                self._put(f"{folder}/plan.md", b"draft")
                self._put(f"{folder}/{self.copy_of_plan}", b"draft")
            self._evict("inbox/plan.md")
            self._evict(f"corpus/{self.copy_of_plan}")

            with mock.patch.object(self.store, "read_bytes", side_effect=AssertionError("an evicted file was read")):
                copies = self.store.conflict_copies()

            self.assertEqual(
                [(copy.path, copy.identical, copy.removable) for copy in copies],
                [(f"corpus/{self.copy_of_plan}", None, False), (f"inbox/{self.copy_of_plan}", None, False)],
            )

        def test_an_evicted_folder_is_passed_over_when_looking_for_conflict_copies(self) -> None:
            self._put("corpus/2025/03/plan.md", b"draft")
            self._put(f"corpus/2025/03/{self.copy_of_plan}", b"draft")
            self._put("corpus/2026/11/plan.md", b"draft")
            self._put(f"corpus/2026/11/{self.copy_of_plan}", b"draft")
            self._put("corpus/2024/01/plan.md", b"draft")
            self._put(f"corpus/2024/01/{self.copy_of_plan}/inside.md", b"draft")
            self._evict("corpus/2025/03")
            self._evict(f"corpus/2024/01/{self.copy_of_plan}")

            self.assertEqual(
                [copy.path for copy in self.store.conflict_copies("corpus")], [f"corpus/2026/11/{self.copy_of_plan}"]
            )

        def test_a_pair_that_cannot_be_read_is_a_copy_that_is_not_compared(self) -> None:
            """Covers: B150"""
            self._put("inbox/plan.md", b"draft")
            self._put(f"inbox/{self.copy_of_plan}", b"draft")

            failures = [
                ("read_bytes", StoreReadError("inbox/plan.md could not be read")),
                ("read_bytes", FileNotFoundError("removed by the sync service since the folder was listed")),
                ("is_evicted", FileNotFoundError("removed by the sync service since the folder was listed")),
            ]
            for method, error in failures:
                with self.subTest(method=method, error=type(error).__name__):
                    with mock.patch.object(self.store, method, side_effect=error):
                        (copy,) = self.store.conflict_copies("inbox")

                    self.assertEqual((copy.identical, copy.removable), (None, False))

        def test_a_symlink_is_never_the_original_of_a_copy(self) -> None:
            """Covers: B150"""
            self._put(f"inbox/{self.copy_of_plan}", b"draft")
            (self.root / "inbox" / "plan.md").symlink_to(self.root / "inbox" / self.copy_of_plan)

            self.assertEqual(self.store.conflict_copies(), [])
