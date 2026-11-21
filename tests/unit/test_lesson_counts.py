"""How often the owner corrected Claude again on a lesson they kept."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from m2b import lesson_counts
from m2b.glean import Correction
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard

AGAIN = Correction("quick.md", "again only the quick round", "shed")


class LessonCountsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="sb-test-lesson-counts-")
        self.addCleanup(self._temp.cleanup)
        base = Path(self._temp.name)
        self.root = base / "sb-test-store"
        self.root.mkdir()
        self.store = FolderStore(self.root, base / "machine-tmp", DatalessGuard(False))

    def test_a_correction_counts_once_under_its_lesson_and_one_of_a_lesson_that_is_gone_not_at_all(self) -> None:
        """Covers: B280"""
        other = Correction("quick.md", "only the fast checks again", "trip")
        gone = Correction("old.md", "again only the quick round", "shed")

        self.assertEqual(lesson_counts.add(self.store, [AGAIN, gone], {"quick.md"}), 1)
        self.assertEqual(lesson_counts.add(self.store, [AGAIN, other], {"quick.md"}), 1)

        self.assertEqual(lesson_counts.corrected_again(self.store), {"quick.md": 2})

    def test_a_file_a_newer_m2b_wrote_is_not_read(self) -> None:
        """Covers: B280"""
        target = self.root / lesson_counts.COUNTS_FILE
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({"format": lesson_counts.FORMAT + 1, "lessons": {}}), encoding="utf-8")

        with self.assertRaises(lesson_counts.LessonCountsError):
            lesson_counts.corrected_again(self.store)
        with self.assertRaises(lesson_counts.LessonCountsError):
            lesson_counts.add(self.store, [AGAIN], {"quick.md"})


if __name__ == "__main__":
    unittest.main()
