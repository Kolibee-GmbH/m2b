"""Writing a file whole: replacing one, and creating one only when its name is free."""

from __future__ import annotations

import errno
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from m2b_worklog import files


class CreateFileTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)

    def test_a_new_name_is_created_and_a_taken_one_left_alone(self) -> None:
        target = self.folder / "note.md"

        self.assertTrue(files.create_file(target, b"first"))
        self.assertFalse(files.create_file(target, b"second"))

        self.assertEqual(target.read_bytes(), b"first")
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ["note.md"])

    def test_a_volume_without_hard_links_still_gets_the_file(self) -> None:
        """FAT, exFAT and SMB volumes refuse os.link; a folder store may live on one."""
        target = self.folder / "note.md"
        for code in (errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP):
            with self.subTest(errno=code), mock.patch.object(files.os, "link", side_effect=OSError(code, "no")):
                target.unlink(missing_ok=True)

                self.assertTrue(files.create_file(target, b"first"))
                self.assertFalse(files.create_file(target, b"second"))

                self.assertEqual(target.read_bytes(), b"first")
                self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ["note.md"])

    def test_another_link_error_is_raised(self) -> None:
        with mock.patch.object(files.os, "link", side_effect=OSError(errno.EIO, "io")), self.assertRaises(OSError):
            files.create_file(self.folder / "note.md", b"first")

        self.assertEqual(list(self.folder.iterdir()), [])
