from __future__ import annotations

import errno
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from m2b.config.errors import StoreUnreachableError
from m2b.config.machine import StoreLocation
from m2b.store.base import EvictedFileError, FetchError, Store, StoreReadError, UnsupportedStoreError
from m2b.store.factory import open_store
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard
from m2b.store.icloud import ICloudStore
from store_contract import Contracts, FakeEviction


class FolderStoreContractTest(Contracts.StoreContract):
    make_store = staticmethod(FolderStore)


class ICloudStoreContractTest(Contracts.StoreContract):
    make_store = staticmethod(ICloudStore)


class _StoreFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        base = Path(self._temp.name)
        self.root = base / "sb-test-store"
        (self.root / "inbox").mkdir(parents=True)
        self.temp_dir = base / "machine-tmp"
        self.eviction = FakeEviction()
        self.clock = [0.0]

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _write(self, relative: str, data: bytes) -> None:
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def _store(self, backend: type[Store]) -> Any:
        def advance(seconds: float) -> None:
            self.clock[0] += seconds

        return backend(
            self.root,
            self.temp_dir,
            DatalessGuard(True, lstat=self.eviction.lstat),
            clock=lambda: self.clock[0],
            sleep=advance,
        )


class FetchTest(_StoreFixture):
    def test_icloud_asks_brctl_and_waits_until_the_file_is_local(self) -> None:
        self._write("inbox/far.md", b"x")
        self.eviction.evicted.add(self.root / "inbox" / "far.md")
        store = self._store(ICloudStore)
        calls: list[list[str]] = []

        def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[bytes]:
            calls.append(command)
            self.eviction.evicted.clear()
            return subprocess.CompletedProcess(command, 0)

        with mock.patch("m2b.store.icloud.subprocess.run", fake_run):
            store.fetch(["inbox"], timeout_seconds=5)

        self.assertEqual(calls, [["brctl", "download", str(self.root / "inbox" / "far.md")]])

    def test_a_download_that_does_not_finish_in_time_fails(self) -> None:
        self._write("inbox/far.md", b"x")
        self.eviction.evicted.add(self.root / "inbox" / "far.md")
        store = self._store(ICloudStore)

        with mock.patch("m2b.store.icloud.subprocess.run"), self.assertRaises(FetchError) as caught:
            store.fetch(["inbox/far.md"], timeout_seconds=2)

        self.assertIn("inbox/far.md", str(caught.exception))

    def test_folder_reads_the_file_in_a_child_that_turns_materialization_on(self) -> None:
        self._write("inbox/far.md", b"x")
        self.eviction.evicted.add(self.root / "inbox" / "far.md")
        store = self._store(FolderStore)
        calls: list[list[str]] = []

        def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[bytes]:
            calls.append(command)
            self.eviction.evicted.clear()
            return subprocess.CompletedProcess(command, 0)

        with mock.patch("m2b.store.folder.subprocess.run", fake_run):
            store.fetch(["inbox/far.md"], timeout_seconds=5)

        self.assertEqual(calls[0][0], sys.executable)
        self.assertTrue(calls[0][1].endswith("materialize.py"))

    def test_fetching_an_evicted_folder_then_fetches_the_files_that_appear_evicted_in_it(self) -> None:
        self._write("corpus/2025/a.md", b"x")
        folder, inner = self.root / "corpus" / "2025", self.root / "corpus" / "2025" / "a.md"
        self.eviction.evicted.update({folder, inner})
        store = self._store(ICloudStore)
        calls: list[str] = []

        def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[bytes]:
            calls.append(command[-1])
            self.eviction.evicted.discard(Path(command[-1]))
            return subprocess.CompletedProcess(command, 0)

        with mock.patch("m2b.store.icloud.subprocess.run", fake_run):
            store.fetch(["corpus"], timeout_seconds=5)

        self.assertEqual(calls, [str(folder), str(inner)])

    def test_a_file_that_never_downloads_leaves_time_for_the_ones_after_it(self) -> None:
        """Covers: B79"""
        self._write("inbox/a.md", b"x")
        self._write("inbox/b.md", b"x")
        self.eviction.evicted.update({self.root / "inbox" / "a.md", self.root / "inbox" / "b.md"})
        store = self._store(FolderStore)
        given: dict[str, float] = {}

        def fake_run(command: list[str], timeout: float, **_: Any) -> subprocess.CompletedProcess[bytes]:
            given[Path(command[-1]).name] = timeout
            if command[-1].endswith("a.md"):
                raise subprocess.TimeoutExpired(command, timeout)
            self.eviction.evicted.discard(Path(command[-1]))
            return subprocess.CompletedProcess(command, 0)

        with mock.patch("m2b.store.folder.subprocess.run", fake_run), self.assertRaises(FetchError):
            store.fetch(["inbox"], timeout_seconds=10)

        self.assertEqual(sorted(given), ["a.md", "b.md"], "b.md is asked for although a.md never came")
        self.assertLessEqual(given["a.md"], 5.0)
        self.assertNotIn(self.root / "inbox" / "b.md", self.eviction.evicted)

    def test_nothing_to_fetch_runs_nothing(self) -> None:
        self._write("inbox/near.md", b"x")
        store = self._store(ICloudStore)

        with mock.patch("m2b.store.icloud.subprocess.run") as run:
            store.fetch(["inbox"], timeout_seconds=5)

        run.assert_not_called()

    def test_a_hanging_download_command_hits_the_timeout(self) -> None:
        self._write("inbox/far.md", b"x")
        self.eviction.evicted.add(self.root / "inbox" / "far.md")
        store = self._store(FolderStore)
        hanging = mock.patch("m2b.store.folder.subprocess.run", side_effect=subprocess.TimeoutExpired("python3", 1))

        with hanging, self.assertRaises(FetchError):
            store.fetch(["inbox/far.md"], timeout_seconds=1)


class EvictedFileErrorTest(unittest.TestCase):
    def test_the_message_names_a_fetch_command_that_can_be_pasted_for_a_path_with_spaces(self) -> None:
        error = EvictedFileError("inbox/plan for Acme.md")

        self.assertIn("run: m2b store fetch 'inbox/plan for Acme.md'", str(error))


class ScanTest(_StoreFixture):
    """``scan``: local files and, apart, what is evicted, in one walk, never reading a file."""

    def test_local_files_and_evicted_files_and_folders_come_apart(self) -> None:
        """Covers: B6"""
        for relative in ("corpus/2026/08/a.md", "corpus/2026/09/b.md", "corpus/2026/09/c.md", "corpus/top.md"):
            self._write(relative, b"x")
        self.eviction.evicted.update({self.root / "corpus/2026/08", self.root / "corpus/2026/09/c.md"})

        scan = self._store(FolderStore).scan("corpus")

        self.assertEqual(scan.files, ["corpus/2026/09/b.md", "corpus/top.md"])
        self.assertEqual(scan.evicted, ["corpus/2026/08", "corpus/2026/09/c.md"])

    def test_an_evicted_folder_asked_for_is_listed_as_itself(self) -> None:
        self._write("corpus/a.md", b"x")
        self.eviction.evicted.add(self.root / "corpus")

        scan = self._store(FolderStore).scan("corpus")

        self.assertEqual((scan.files, scan.evicted), ([], ["corpus"]))

    def test_a_folder_that_answers_like_an_evicted_one_when_listed_is_listed_as_evicted(self) -> None:
        self._write("corpus/2026/a.md", b"x")
        self._write("corpus/b.md", b"x")
        store = self._store(FolderStore)
        real_iterdir = Path.iterdir

        def iterdir(folder: Path) -> Any:
            if folder == self.root / "corpus" / "2026":
                raise OSError(errno.EDEADLK, "Resource deadlock avoided")
            return real_iterdir(folder)

        with mock.patch.object(Path, "iterdir", iterdir):
            scan = store.scan("corpus")

        self.assertEqual((scan.files, scan.evicted), (["corpus/b.md"], ["corpus/2026"]))

    def test_hidden_files_folder_symlinks_and_a_missing_folder_give_nothing(self) -> None:
        self._write("inbox/.tmp-x.md", b"x")
        self._write("elsewhere/a.md", b"x")
        (self.root / "inbox" / "linked").symlink_to(self.root / "elsewhere")
        store = self._store(FolderStore)

        self.assertEqual((store.scan("inbox").files, store.scan("inbox").evicted), ([], []))
        self.assertEqual((store.scan("memory").files, store.scan("memory").evicted), ([], []))


class ConflictCopiesTest(_StoreFixture):
    def test_icloud_copies_are_removable_only_when_identical(self) -> None:
        """Covers: X8"""
        self._write("inbox/plan.md", b"draft")
        self._write("inbox/plan 2.md", b"draft")
        self._write("inbox/plan 2026.md", b"the plan for 2026")
        self._write("corpus/x.md", b"same")
        self._write("corpus/x 10.md", b"same")
        self._write("corpus/x 1.md", b"same")
        self._write("corpus/lonely 2.md", b"no original")

        copies = {c.path: (c.original, c.removable) for c in self._store(ICloudStore).conflict_copies()}

        self.assertEqual(
            copies,
            {
                "inbox/plan 2.md": ("inbox/plan.md", True),
                "inbox/plan 2026.md": ("inbox/plan.md", False),
                "corpus/x 10.md": ("corpus/x.md", True),
            },
        )

    def test_an_evicted_copy_or_original_is_never_compared(self) -> None:
        """Covers: X8, B6"""
        self._write("inbox/plan.md", b"draft")
        self._write("inbox/plan 2.md", b"draft")
        self.eviction.evicted.add(self.root / "inbox" / "plan.md")

        (copy,) = self._store(ICloudStore).conflict_copies("inbox")

        self.assertIsNone(copy.identical)
        self.assertFalse(copy.removable)

    def test_the_folder_backend_recognizes_no_conflict_copies(self) -> None:
        self._write("inbox/plan.md", b"draft")
        self._write("inbox/plan 2.md", b"draft")

        self.assertEqual(self._store(FolderStore).conflict_copies(), [])


class OldStubFilesTest(_StoreFixture):
    def test_icloud_refuses_a_store_with_old_style_stub_files_at_its_top(self) -> None:
        self._write("inbox/.note.md.icloud", b"")

        with self.assertRaises(UnsupportedStoreError) as caught:
            self._store(ICloudStore)

        self.assertIn("macOS 14", str(caught.exception))

    def test_icloud_refuses_a_macos_before_14(self) -> None:
        with self.assertRaises(UnsupportedStoreError) as caught:
            ICloudStore(self.root, self.temp_dir, DatalessGuard(False), macos_release="13.6.1")

        self.assertIn("macOS 14", str(caught.exception))

    def test_icloud_accepts_macos_14_and_newer(self) -> None:
        for release in ("14.0", "15.2", "26.1"):
            with self.subTest(release=release):
                ICloudStore(self.root, self.temp_dir, DatalessGuard(False), macos_release=release)

    def test_the_full_scan_finds_stub_files_deep_in_the_store(self) -> None:
        store = self._store(ICloudStore)
        self._write("corpus/2025/01/.note.md.icloud", b"")

        self.assertEqual(store.old_stub_files(), ["corpus/2025/01/.note.md.icloud"])

    def test_an_evicted_top_folder_does_not_stop_the_store_from_opening(self) -> None:
        (self.root / "corpus").mkdir()
        self.eviction.evicted.add(self.root / "corpus")
        real_iterdir = Path.iterdir

        def iterdir(path: Path) -> Any:
            if path == self.root / "corpus":
                raise OSError(errno.EDEADLK, "Resource deadlock avoided")
            return real_iterdir(path)

        with mock.patch.object(Path, "iterdir", iterdir):
            self._store(ICloudStore)

    def test_a_top_folder_that_cannot_be_read_is_a_store_error(self) -> None:
        (self.root / "corpus").mkdir()
        real_iterdir = Path.iterdir

        def iterdir(path: Path) -> Any:
            if path == self.root / "corpus":
                raise PermissionError(errno.EPERM, "Operation not permitted")
            return real_iterdir(path)

        with mock.patch.object(Path, "iterdir", iterdir), self.assertRaises(StoreReadError):
            self._store(ICloudStore)

    def test_the_folder_backend_does_not_care(self) -> None:
        self._write("inbox/.note.md.icloud", b"")

        self._store(FolderStore)


class OpenStoreTest(_StoreFixture):
    def test_the_backend_follows_the_config(self) -> None:
        store = open_store(StoreLocation("folder", self.root), self.temp_dir, platform="linux")

        self.assertIsInstance(store, FolderStore)
        self.assertFalse(store.guard.active)

    def test_a_missing_store_folder_is_unreachable(self) -> None:
        with self.assertRaises(StoreUnreachableError):
            open_store(StoreLocation("folder", self.root / "unmounted"), self.temp_dir, platform="linux")

    def test_icloud_is_refused_outside_macos(self) -> None:
        with self.assertRaises(UnsupportedStoreError):
            open_store(StoreLocation("icloud", self.root), self.temp_dir, platform="linux")

    @unittest.skipUnless(sys.platform == "darwin", "the process guard exists on macOS only")
    def test_on_macos_both_backends_run_with_the_guard(self) -> None:
        """Covers: B39"""
        for backend, expected in (("folder", FolderStore), ("icloud", ICloudStore)):
            with self.subTest(backend=backend):
                store = open_store(StoreLocation(backend, self.root), self.temp_dir)

                self.assertIsInstance(store, expected)
                self.assertTrue(store.guard.active)


if __name__ == "__main__":
    unittest.main()
