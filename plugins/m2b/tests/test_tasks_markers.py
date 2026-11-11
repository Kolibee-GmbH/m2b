from __future__ import annotations

import unittest

from m2b.tasks import markers


class MarkerTest(unittest.TestCase):
    def test_a_marker_line_with_arguments_reads_back(self) -> None:
        notes = markers.with_marker(markers.CAPTURE, "see the capture", "20260329T003000Z-claude-3f9a.md", "t1")

        self.assertEqual(notes, "m2b:capture 20260329T003000Z-claude-3f9a.md t1\nsee the capture")
        self.assertEqual(markers.marker_of(notes), ("capture", ("20260329T003000Z-claude-3f9a.md", "t1")))

    def test_notes_without_a_known_marker_have_none(self) -> None:
        for notes in ("", "buy milk", "m2b:", "m2b:   ", "m2b:unknown x", " m2b"):
            with self.subTest(notes=notes):
                self.assertIsNone(markers.marker_of(notes))

    def test_the_task_for_waiting_proposals_is_one_of_the_curators_own(self) -> None:
        notes = markers.with_marker(markers.PROPOSALS, "2 proposals wait")

        self.assertEqual(markers.marker_of(notes), ("proposals", ()))
        self.assertIn(markers.PROPOSALS, markers.CURATOR)

    def test_a_marker_counts_only_on_the_first_line(self) -> None:
        self.assertIsNone(markers.marker_of("buy milk\nm2b:review"))

    def test_unknown_kinds_and_spaced_arguments_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            markers.marker_line("reminder")
        with self.assertRaises(ValueError):
            markers.marker_line(markers.CAPTURE, "two words.md")


if __name__ == "__main__":
    unittest.main()
