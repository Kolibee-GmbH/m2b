"""How often the owner corrected Claude again on a lesson they kept."""

from __future__ import annotations

import datetime
import json
import tempfile
import unittest
from pathlib import Path

from m2b import lesson_counts
from m2b.glean import Correction
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard

AGAIN = Correction("quick.md", "again only the quick round", "shed")
KEPT = {"quick.md": "2026-11-20"}


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

        self.assertEqual(lesson_counts.add(self.store, [AGAIN, gone], KEPT, datetime.date(2026, 11, 22)), 1)
        self.assertEqual(lesson_counts.add(self.store, [AGAIN, other], KEPT, datetime.date(2026, 11, 22)), 1)

        self.assertEqual(lesson_counts.corrected_again(self.store, KEPT), {"quick.md": 2})

    def test_a_new_lesson_under_a_freed_name_starts_at_zero_and_the_old_count_is_dropped(self) -> None:
        """Covers: B280"""
        lesson_counts.add(self.store, [AGAIN], KEPT, datetime.date(2026, 11, 22))
        kept_again = {"quick.md": "2026-12-02"}

        self.assertEqual(lesson_counts.corrected_again(self.store, kept_again), {})
        self.assertEqual(
            lesson_counts.add(
                self.store,
                [Correction("quick.md", "the quick round again", "pier")],
                kept_again,
                datetime.date(2026, 11, 22),
            ),
            1,
        )

        self.assertEqual(lesson_counts.corrected_again(self.store, kept_again), {"quick.md": 1})
        written = json.loads((self.root / lesson_counts.COUNTS_FILE).read_text(encoding="utf-8"))
        self.assertEqual(list(written["lessons"]), ["quick.md"])
        self.assertEqual(written["lessons"]["quick.md"]["kept"], "2026-12-02")
        self.assertEqual(len(written["lessons"]["quick.md"]["corrected_again"]), 1)

    def test_the_day_of_the_last_run_that_counted_a_correction_is_kept_per_lesson(self) -> None:
        """Covers: B292"""
        other = Correction("quick.md", "only the fast checks again", "trip")
        lesson_counts.add(self.store, [AGAIN], KEPT, datetime.date(2026, 11, 25))
        # A run that counts nothing new leaves the day.
        lesson_counts.add(self.store, [AGAIN], KEPT, datetime.date(2026, 12, 1))
        self.assertEqual(lesson_counts.last_corrected(self.store, KEPT), {"quick.md": "2026-11-25"})
        lesson_counts.add(self.store, [other], KEPT, datetime.date(2026, 12, 3))
        self.assertEqual(lesson_counts.last_corrected(self.store, KEPT), {"quick.md": "2026-12-03"})
        self.assertEqual(lesson_counts.last_corrected(self.store, {"quick.md": "2026-11-21"}), {})

    def test_a_file_a_newer_m2b_wrote_is_not_read(self) -> None:
        """Covers: B280"""
        target = self.root / lesson_counts.COUNTS_FILE
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({"format": lesson_counts.FORMAT + 1, "lessons": {}}), encoding="utf-8")

        with self.assertRaises(lesson_counts.LessonCountsError):
            lesson_counts.corrected_again(self.store, KEPT)
        with self.assertRaises(lesson_counts.LessonCountsError):
            lesson_counts.add(self.store, [AGAIN], KEPT, datetime.date(2026, 11, 22))


if __name__ == "__main__":
    unittest.main()
