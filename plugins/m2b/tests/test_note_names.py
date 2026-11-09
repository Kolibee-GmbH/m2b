from __future__ import annotations

import datetime
import unittest
from zoneinfo import ZoneInfo

from m2b.notes import layout
from m2b.notes.names import NoteName

ZURICH = ZoneInfo("Europe/Zurich")


class CaptureNameTest(unittest.TestCase):
    def test_a_capture_in_zurich_is_named_in_utc(self) -> None:
        """Covers: X9"""
        created = datetime.datetime(2026, 3, 29, 1, 30, tzinfo=ZURICH)

        name = NoteName.for_capture(created, "claude", suffix="3f9a")

        self.assertEqual(str(name), "20260329T003000Z-claude-3f9a.md")

    def test_a_name_on_both_sides_of_the_daylight_saving_change_sorts_in_capture_order(self) -> None:
        """Covers: X9"""
        before = datetime.datetime(2026, 10, 25, 2, 30, tzinfo=ZURICH, fold=0)
        after = datetime.datetime(2026, 10, 25, 2, 10, tzinfo=ZURICH, fold=1)

        names = [str(NoteName.for_capture(t, "cli", suffix="0000")) for t in (before, after)]

        self.assertEqual(names, sorted(names))

    def test_the_suffix_is_four_random_hex_characters_when_not_given(self) -> None:
        created = datetime.datetime(2026, 3, 29, 1, 30, tzinfo=ZURICH)

        suffixes = {NoteName.for_capture(created, "claude").suffix for _ in range(20)}

        self.assertTrue(all(len(s) == 4 and int(s, 16) >= 0 for s in suffixes))
        self.assertGreater(len(suffixes), 1)

    def test_a_capture_time_without_offset_is_refused(self) -> None:
        """Covers: X5"""
        with self.assertRaises(ValueError):
            NoteName.for_capture(datetime.datetime(2026, 3, 29, 1, 30), "claude")

    def test_an_extension_the_name_pattern_cannot_hold_is_refused(self) -> None:
        created = datetime.datetime(2026, 3, 29, 1, 30, tzinfo=ZURICH)
        for extension in ("", "tar.gz", "m d"):
            with self.subTest(extension=extension), self.assertRaises(ValueError):
                NoteName.for_capture(created, "cli", extension=extension)

    def test_a_suffix_that_is_not_four_lowercase_hex_characters_is_refused(self) -> None:
        created = datetime.datetime(2026, 3, 29, 1, 30, tzinfo=ZURICH)
        for suffix in ("XYZ", "3F9A", "3f9", "3f9a0"):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                NoteName.for_capture(created, "cli", suffix=suffix)

    def test_every_name_made_for_a_capture_parses_back(self) -> None:
        created = datetime.datetime(2026, 3, 29, 1, 30, tzinfo=ZURICH)
        for extension in ("md", "HEIC", "jpg"):
            name = NoteName.for_capture(created, "my-app", extension=extension)
            with self.subTest(extension=extension):
                self.assertEqual(NoteName.parse(str(name)), name)

    def test_a_source_that_is_not_a_lowercase_token_is_refused(self) -> None:
        created = datetime.datetime(2026, 3, 29, 1, 30, tzinfo=ZURICH)
        for source in ("Claude", "2phone", "my app", "", "phone_app"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                NoteName.for_capture(created, source)


class ParseNameTest(unittest.TestCase):
    def test_a_conforming_name_parses_into_its_parts(self) -> None:
        name = NoteName.parse("20260329T003000Z-my-app-3f9a.heic")

        assert name is not None
        self.assertEqual(name.time, datetime.datetime(2026, 3, 29, 0, 30, tzinfo=datetime.timezone.utc))
        self.assertEqual((name.source, name.suffix, name.extension), ("my-app", "3f9a", "heic"))
        self.assertEqual(str(name), "20260329T003000Z-my-app-3f9a.heic")

    def test_the_old_device_source_mac_stays_valid(self) -> None:
        self.assertIsNotNone(NoteName.parse("20260329T003000Z-mac-3f9a.md"))

    def test_other_names_do_not_parse(self) -> None:
        for name in (
            "20260329-013000-mac-3f9a.md",
            "20260329T003000Z-claude-3f9.md",
            "20260329T003000Z-claude-3F9A.md",
            "20261399T003000Z-claude-3f9a.md",
            "notes from the meeting.md",
            "20260329T003000Z-claude-3f9a",
        ):
            with self.subTest(name=name):
                self.assertIsNone(NoteName.parse(name))


class LayoutTest(unittest.TestCase):
    def test_folder_names_of_the_store_format(self) -> None:
        self.assertEqual(
            (layout.INBOX, layout.CORPUS, layout.MEMORY, layout.TASKS, layout.STATE),
            ("inbox", "corpus", "memory", "tasks", "state"),
        )
        self.assertEqual((layout.MEMORY_INDEX, layout.STORE_CONTRACT), ("MEMORY.md", "STORE.md"))

    def test_the_journal_of_a_month_is_named_after_year_and_month(self) -> None:
        self.assertEqual(layout.journal_name(2026, 3), "202603-done.md")

    def test_a_journal_name_is_recognised(self) -> None:
        self.assertTrue(layout.is_journal_name("202603-done.md"))
        self.assertFalse(layout.is_journal_name("202613-done.md"))
        self.assertFalse(layout.is_journal_name("202603-done.md.bak"))


if __name__ == "__main__":
    unittest.main()
