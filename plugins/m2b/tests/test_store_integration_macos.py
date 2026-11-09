"""Integration tests against real sync folders on macOS; they run only when asked to.

    M2B_IT=1 M2B_IT_ICLOUD_DIR=~/Library/Mobile\\ Documents/com~apple~CloudDocs/sb-test-store \\
        scripts/check --quick m2b

``M2B_IT_PROVIDER_DIR`` points at an ``sb-test-`` folder inside a Dropbox or OneDrive
folder for the same check through the ``folder`` backend. Each test creates one file, evicts
it, checks that it is listed and never read, downloads it again, does the same with a folder,
and deletes what it made. The folders
themselves are left in place and must be removed by hand.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

from m2b.config.machine import StoreLocation
from m2b.paths import machine_paths
from m2b.store.base import EvictedFileError, Store
from m2b.store.factory import open_store

TEST_FOLDER_PREFIX = "sb-test-"
TEST_FILE = "sb-test-evict-probe.md"
TEST_SUBFOLDER = "sb-test-evict-folder"
TEST_BYTES = b"Invented content for an eviction test.\n" * 8000
EVICT_TIMEOUT_SECONDS = 60
FETCH_TIMEOUT_SECONDS = 120


def _test_folder(variable: str) -> Path | None:
    if os.environ.get("M2B_IT") != "1" or sys.platform != "darwin" or not os.environ.get(variable):
        return None
    folder = Path(os.environ[variable]).expanduser()
    if not folder.name.startswith(TEST_FOLDER_PREFIX):
        raise RuntimeError(f"{variable} must name a folder starting with {TEST_FOLDER_PREFIX}, got {folder.name!r}")
    return folder


class _EvictionRoundTrip:
    """The checks both providers run; ``evict_command`` names the provider's own tool."""

    backend: str
    evict_command: str

    def _evict(self, store: Store, path: Path, probe: str, case: unittest.TestCase) -> None:
        """Evicts ``path`` until the file ``probe`` is evicted.

        A provider refuses to evict a file whose upload is not done, and evicting a folder
        silently skips such files, so the command is repeated until the probe shows the flag.
        """
        deadline = time.monotonic() + EVICT_TIMEOUT_SECONDS
        message = ""
        while not store.is_evicted(probe):
            if time.monotonic() > deadline:
                case.fail(f"{probe} was not evicted within {EVICT_TIMEOUT_SECONDS} seconds: {message}")
            result = subprocess.run([self.evict_command, "evict", str(path)], capture_output=True, timeout=30)
            message = result.stderr.decode(errors="replace").strip()
            time.sleep(2)

    def run_round_trip(self, case: unittest.TestCase, folder: Path) -> None:
        folder.mkdir(exist_ok=True)
        store = open_store(StoreLocation(self.backend, folder), machine_paths().temp_dir)
        target = folder / TEST_FILE
        try:
            store.create_exclusive(TEST_FILE, TEST_BYTES)
            self._evict(store, target, TEST_FILE, case)

            case.assertEqual(store.check_local([TEST_FILE]), [TEST_FILE])
            with case.assertRaises(EvictedFileError):
                store.read_bytes(TEST_FILE)
            with case.assertRaises(EvictedFileError):
                store.replace(TEST_FILE, b"must not land")
            case.assertTrue(store.is_evicted(TEST_FILE), "the refused read must not download the file")

            store.fetch([TEST_FILE], timeout_seconds=FETCH_TIMEOUT_SECONDS)
            case.assertEqual(store.read_bytes(TEST_FILE), TEST_BYTES)

            store.create_exclusive(f"{TEST_SUBFOLDER}/{TEST_FILE}", TEST_BYTES)
            inner = f"{TEST_SUBFOLDER}/{TEST_FILE}"
            self._evict(store, folder / TEST_SUBFOLDER, inner, case)
            case.assertIn(store.check_local([TEST_SUBFOLDER]), ([TEST_SUBFOLDER], [inner]))
            store.fetch([TEST_SUBFOLDER], timeout_seconds=FETCH_TIMEOUT_SECONDS)
            case.assertEqual(store.read_bytes(f"{TEST_SUBFOLDER}/{TEST_FILE}"), TEST_BYTES)
        finally:
            target.unlink(missing_ok=True)
            shutil.rmtree(folder / TEST_SUBFOLDER, ignore_errors=True)
            leftovers = [p for p in folder.iterdir() if p.name.startswith(".sb-tmp-")]
            for leftover in leftovers:
                leftover.unlink() if leftover.is_file() else shutil.rmtree(leftover)


class ICloudIntegrationTest(unittest.TestCase, _EvictionRoundTrip):
    backend = "icloud"
    evict_command = "brctl"

    def test_an_evicted_icloud_file_is_listed_never_read_and_fetched(self) -> None:
        """Covers: B6"""
        folder = _test_folder("M2B_IT_ICLOUD_DIR")
        if folder is None:
            self.skipTest("set M2B_IT=1 and M2B_IT_ICLOUD_DIR on macOS")
        self.run_round_trip(self, folder)


class FileProviderIntegrationTest(unittest.TestCase, _EvictionRoundTrip):
    backend = "folder"
    evict_command = "fileproviderctl"

    def test_an_evicted_dropbox_or_onedrive_file_is_listed_never_read_and_fetched(self) -> None:
        """Covers: B39"""
        folder = _test_folder("M2B_IT_PROVIDER_DIR")
        if folder is None:
            self.skipTest("set M2B_IT=1 and M2B_IT_PROVIDER_DIR on macOS")
        self.run_round_trip(self, folder)


if __name__ == "__main__":
    unittest.main()
