from __future__ import annotations

import errno
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from m2b import atomic_file


class WriteTextAtomicallyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        root = Path(self._temp.name)
        self.target_dir = root / "store"
        self.target_dir.mkdir()
        self.temp_dir = root / "machine" / "tmp"
        self.target = self.target_dir / "profile.json"

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_writes_the_text_and_leaves_no_temp_file(self) -> None:
        self.target.write_text("old", encoding="utf-8")

        atomic_file.write_text_atomically(self.target, "new\n", self.temp_dir)

        self.assertEqual(self.target.read_text(encoding="utf-8"), "new\n")
        self.assertEqual(list(self.temp_dir.iterdir()), [])
        self.assertEqual([p.name for p in self.target_dir.iterdir()], ["profile.json"])

    def test_an_existing_file_keeps_its_mode(self) -> None:
        self.target.write_text("old", encoding="utf-8")
        self.target.chmod(0o644)

        atomic_file.write_text_atomically(self.target, "new", self.temp_dir)

        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o644)

    def test_a_new_file_gets_the_mode_the_umask_allows(self) -> None:
        previous = os.umask(0o027)
        try:
            atomic_file.write_text_atomically(self.target, "new", self.temp_dir)
        finally:
            os.umask(previous)

        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o640)

    def test_the_temp_file_is_written_in_the_machine_temp_folder(self) -> None:
        seen: list[Path] = []
        real_replace = os.replace

        def recording_replace(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
            seen.append(Path(source))
            real_replace(source, target)

        with mock.patch.object(atomic_file.os, "replace", recording_replace):
            atomic_file.write_text_atomically(self.target, "x", self.temp_dir)

        self.assertEqual(seen[0].parent, self.temp_dir)

    def test_across_volumes_a_hidden_temp_file_next_to_the_target_is_used(self) -> None:
        real_replace = os.replace
        sources: list[Path] = []

        def replace_failing_across_volumes(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
            sources.append(Path(source))
            if Path(source).parent == self.temp_dir:
                raise OSError(errno.EXDEV, "Invalid cross-device link")
            real_replace(source, target)

        with mock.patch.object(atomic_file.os, "replace", replace_failing_across_volumes):
            atomic_file.write_text_atomically(self.target, "moved\n", self.temp_dir)

        self.assertEqual(self.target.read_text(encoding="utf-8"), "moved\n")
        self.assertEqual(sources[1].parent, self.target_dir)
        self.assertTrue(sources[1].name.startswith("."))
        self.assertEqual([p.name for p in self.target_dir.iterdir()], ["profile.json"])
        self.assertEqual(list(self.temp_dir.iterdir()), [])

    def test_another_rename_failure_is_raised_and_the_target_is_unchanged(self) -> None:
        self.target.write_text("old", encoding="utf-8")

        failing = mock.patch.object(atomic_file.os, "replace", side_effect=OSError(errno.EACCES, "denied"))
        with failing, self.assertRaises(OSError):
            atomic_file.write_text_atomically(self.target, "new", self.temp_dir)

        self.assertEqual(self.target.read_text(encoding="utf-8"), "old")
        self.assertEqual(list(self.temp_dir.iterdir()), [])


class CreateExclusivelyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        root = Path(self._temp.name)
        self.folder = root / "store" / "inbox"
        self.folder.mkdir(parents=True)
        self.temp_dir = root / "machine" / "tmp"
        self.target = self.folder / "note.md"

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_creates_the_file_with_its_content_and_leaves_no_temp_file(self) -> None:
        atomic_file.create_exclusively(self.target, b"Dana likes maps.\n", self.temp_dir)

        self.assertEqual(self.target.read_bytes(), b"Dana likes maps.\n")
        self.assertEqual([p.name for p in self.folder.iterdir()], ["note.md"])
        self.assertEqual(list(self.temp_dir.iterdir()), [])

    def test_an_existing_file_is_never_overwritten(self) -> None:
        self.target.write_bytes(b"first")

        with self.assertRaises(FileExistsError):
            atomic_file.create_exclusively(self.target, b"second", self.temp_dir)

        self.assertEqual(self.target.read_bytes(), b"first")
        self.assertEqual(list(self.temp_dir.iterdir()), [])

    def test_across_volumes_the_hidden_temp_file_sits_next_to_the_target(self) -> None:
        real_link = os.link
        sources: list[Path] = []

        def link_failing_across_volumes(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
            sources.append(Path(source))
            if Path(source).parent == self.temp_dir:
                raise OSError(errno.EXDEV, "Invalid cross-device link")
            real_link(source, target)

        with mock.patch.object(atomic_file.os, "link", link_failing_across_volumes):
            atomic_file.create_exclusively(self.target, b"moved", self.temp_dir)

        self.assertEqual(self.target.read_bytes(), b"moved")
        self.assertEqual(sources[1].parent, self.folder)
        self.assertEqual([p.name for p in self.folder.iterdir()], ["note.md"])

    def test_a_crash_before_the_link_leaves_no_file_a_reader_takes_for_content(self) -> None:
        """Covers: X22"""
        interrupted = mock.patch.object(atomic_file.os, "link", side_effect=KeyboardInterrupt)
        with interrupted, self.assertRaises(KeyboardInterrupt):
            atomic_file.create_exclusively(self.target, b"half", self.temp_dir)

        self.assertEqual(list(self.folder.iterdir()), [])

    def test_temp_files_are_written_outside_the_synced_folder(self) -> None:
        """Covers: X22"""
        seen: list[Path] = []
        real_link = os.link

        def recording_link(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
            seen.append(Path(source))
            real_link(source, target)

        with mock.patch.object(atomic_file.os, "link", recording_link):
            atomic_file.create_exclusively(self.target, b"x", self.temp_dir)

        self.assertEqual(seen[0].parent, self.temp_dir)


class CreateWithoutHardLinksTest(unittest.TestCase):
    """Volumes such as FAT, exFAT or SMB shares have no hard links; an exclusive rename stands in."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        root = Path(self._temp.name)
        self.folder = root / "store"
        self.folder.mkdir()
        self.temp_dir = root / "machine-tmp"
        self.target = self.folder / "note.md"
        self.no_links = mock.patch.object(atomic_file.os, "link", side_effect=OSError(errno.EPERM, "no hard links"))

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_the_file_is_created_by_an_exclusive_rename(self) -> None:
        with self.no_links:
            atomic_file.create_exclusively(self.target, b"Dana likes maps.\n", self.temp_dir)

        self.assertEqual(self.target.read_bytes(), b"Dana likes maps.\n")
        self.assertEqual(list(self.temp_dir.iterdir()), [])

    def test_an_existing_file_is_still_never_overwritten(self) -> None:
        self.target.write_bytes(b"first")

        with self.no_links, self.assertRaises(FileExistsError):
            atomic_file.create_exclusively(self.target, b"second", self.temp_dir)

        self.assertEqual(self.target.read_bytes(), b"first")
        self.assertEqual(list(self.temp_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
