"""A current item above the topics that names exactly one topic moves under that topic, at every run."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from m2b.current_topics import place, placed
from m2b.store.base import EvictedFileError
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard

FACTS = """# Memory

## Facts

- Dana's birthday is on 3 March (dana.md)

### Acme Ltd (Acme Ltd, Acme, Kim Lee)
- Kim Lee leads Acme's IT (kim-lee.md)

### Mill Lane choir (Mill Lane, choir)
- The choir rehearses on Tuesdays (choir.md)
"""


class PlacedTest(unittest.TestCase):
    def test_an_item_naming_one_topic_moves_to_the_end_of_its_current_items(self) -> None:
        """Covers: B290"""
        text = (
            FACTS
            + "\n## Current\n\n- Planning the trip to Porto (since 2026-10-02)\n"
            + "- Status mail to Kim Lee moved to Thursdays [[20261101T090000Z-cli-a1b2.md]] (since 2026-11-01)\n"
            + "\n### Acme Ltd (Acme Ltd, Acme, Kim Lee)\n- Building the export for Acme (since 2026-11-02)\n"
        )
        result = placed(text)
        self.assertEqual(
            FACTS
            + "\n## Current\n\n- Planning the trip to Porto (since 2026-10-02)\n"
            + "\n### Acme Ltd (Acme Ltd, Acme, Kim Lee)\n- Building the export for Acme (since 2026-11-02)\n"
            + "- Status mail to Kim Lee moved to Thursdays [[20261101T090000Z-cli-a1b2.md]] (since 2026-11-01)\n",
            result.text,
        )
        self.assertEqual(("Status mail to Kim Lee moved to Thursdays [[20261101T090000Z-cli-a1b2.md]]",), result.moved)

    def test_a_topic_without_a_current_heading_gets_its_facts_heading_at_the_end_of_current(self) -> None:
        """Covers: B290"""
        concert = "- Choir concert at Mill Lane on 12 December (since 2026-11-10)\n"
        text = FACTS + "\n## Current\n\n" + concert + "- Planning the trip to Porto\n"
        self.assertEqual(
            FACTS
            + "\n## Current\n\n- Planning the trip to Porto\n"
            + "\n### Mill Lane choir (Mill Lane, choir)\n"
            + concert,
            placed(text).text,
        )

    def test_the_new_heading_goes_before_the_next_section(self) -> None:
        """Covers: B290"""
        text = (
            "# Memory\n\n## Current\n\n- Export for Acme is late (since 2026-11-02)\n\n## Facts\n\n"
            "### Acme Ltd (Acme Ltd, Acme)\n- Kim Lee leads Acme's IT (kim-lee.md)\n"
        )
        self.assertEqual(
            "# Memory\n\n## Current\n\n### Acme Ltd (Acme Ltd, Acme)\n- Export for Acme is late (since 2026-11-02)\n\n"
            "## Facts\n\n### Acme Ltd (Acme Ltd, Acme)\n- Kim Lee leads Acme's IT (kim-lee.md)\n",
            placed(text).text,
        )

    def test_the_words_of_all_headings_of_a_topic_count(self) -> None:
        """Covers: B290"""
        text = (
            FACTS
            + "\n## Current\n\n- Invoice to Globex sent (since 2026-11-03)\n"
            + "\n### Acme Ltd (Globex)\n- Building the export for Acme (since 2026-11-02)\n"
        )
        self.assertEqual(("Invoice to Globex sent",), placed(text).moved)

    def test_an_item_naming_two_topics_or_none_stays(self) -> None:
        """Covers: B290"""
        text = (
            FACTS
            + "\n## Current\n\n- Acme sponsors the Mill Lane choir (since 2026-11-01)\n"
            + "- Acmes of the world (since 2026-11-01)\n- Planning the trip to Porto (since 2026-10-02)\n"
        )
        result = placed(text)
        self.assertEqual(text, result.text)
        self.assertEqual((), result.moved)

    def test_a_word_only_in_a_link_names_no_topic(self) -> None:
        """Covers: B290"""
        text = FACTS + "\n## Current\n\n- Sorting the photos [[acme.md]] (since 2026-11-01)\n"
        self.assertEqual(text, placed(text).text)

    def test_an_item_under_a_topic_or_below_a_heading_that_is_no_topic_stays(self) -> None:
        """Covers: B290"""
        text = (
            FACTS
            + "\n## Current\n\n### Mill Lane choir (Mill Lane, choir)\n"
            + "- Kim Lee sings in the choir now (since 2026-11-01)\n"
        )
        self.assertEqual(text, placed(text).text)
        no_topic = FACTS + "\n## Current\n\n### Later\n- Export for Acme (since 2026-11-02)\n"
        self.assertEqual(no_topic, placed(no_topic).text)

    def test_a_distillate_without_topics_or_current_is_left_as_it_is(self) -> None:
        """Covers: B290"""
        for text in ("# Memory\n\n## Current\n\n- Export for Acme\n", FACTS, ""):
            with self.subTest(text=text):
                self.assertEqual(text, placed(text).text)

    def test_line_ends_of_the_file_are_kept(self) -> None:
        """Covers: B290"""
        text = (FACTS + "\n## Current\n\n- Export for Acme is late\n").replace("\n", "\r\n")
        result = placed(text)
        self.assertIn("### Acme Ltd (Acme Ltd, Acme, Kim Lee)\r\n- Export for Acme is late\r\n", result.text)
        self.assertNotIn("\n- Export for Acme is late\r\n\r\n###", result.text)


class PlaceTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.root = base / "sb-test-store"
        self.store = FolderStore(self.root, base / "machine-tmp", DatalessGuard(False))
        (self.root / "memory").mkdir(parents=True)

    def index(self) -> Path:
        return self.root / "memory" / "MEMORY.md"

    def test_writes_the_distillate_only_when_an_item_moved(self) -> None:
        """Covers: B290"""
        unmoved = FACTS + "\n## Current\n\n- Planning the trip to Porto\n"
        self.index().write_text(unmoved, encoding="utf-8")
        before = self.index().stat().st_mtime_ns
        self.assertEqual([], place(self.store))
        self.assertEqual(before, self.index().stat().st_mtime_ns)
        self.index().write_text(FACTS + "\n## Current\n\n- Export for Acme is late\n", encoding="utf-8")
        self.assertEqual(["Export for Acme is late"], place(self.store))
        self.assertTrue(
            self.index()
            .read_text(encoding="utf-8")
            .endswith("### Acme Ltd (Acme Ltd, Acme, Kim Lee)\n- Export for Acme is late\n")
        )

    def test_a_distillate_that_is_missing_or_not_downloaded_moves_nothing(self) -> None:
        """Covers: B290"""
        self.assertEqual([], place(self.store))
        self.index().write_text(FACTS + "\n## Current\n\n- Export for Acme is late\n", encoding="utf-8")
        original = self.store.read_text

        def evicted(relative: str) -> str:
            raise EvictedFileError(relative)

        self.store.read_text = evicted  # type: ignore[method-assign]
        try:
            self.assertEqual([], place(self.store))
        finally:
            self.store.read_text = original  # type: ignore[method-assign]


if __name__ == "__main__":
    unittest.main()
