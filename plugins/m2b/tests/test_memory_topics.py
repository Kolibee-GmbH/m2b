"""Topics in the distillate: groups of facts and current items that come in only when named."""

from __future__ import annotations

import unittest

from m2b.notes.memory_index import (
    CurrentLine,
    FactLine,
    MemoryIndex,
    Topic,
    TopicBlock,
    parse_topic_heading,
    split_topics,
)

DISTILLATE = """# Memory

## Facts

- Dana's birthday is on 3 March (dana.md)

### Acme (Schweiz) AG (Acme, Kim Lee)
- Kim Lee leads Acme's IT (kim-lee.md)

### Riverside Choir (Riverside Choir, Petra Lang)
- The choir meets on Wednesdays (choir.md)

## Current

- Building the Acme export (since 2026-10-02)
"""
ACME_EXPORT = "- Shipping the export to Kim Lee (since 2026-11-02)\n"
CURRENT_UNDER_ACME = f"{DISTILLATE}\n### Acme (Schweiz) AG (Acme, Kim Lee)\n{ACME_EXPORT}"


class TopicHeadingTest(unittest.TestCase):
    def test_the_words_are_the_last_parenthesised_group(self) -> None:
        """Covers: B44"""
        self.assertEqual(
            parse_topic_heading("### Acme (Schweiz) AG (Acme, Kim Lee)"),
            Topic("Acme (Schweiz) AG", ("Acme", "Kim Lee")),
        )

    def test_words_are_trimmed_and_empty_ones_dropped(self) -> None:
        self.assertEqual(
            parse_topic_heading("### Lumen ( Lumen ,, Ben Ortiz )"), Topic("Lumen", ("Lumen", "Ben Ortiz"))
        )

    def test_a_heading_without_words_is_no_topic(self) -> None:
        for line in (
            "### People",
            "### Lumen ()",
            "### (Lumen)",
            "## Acme (Acme)",
            "#### Acme (Acme)",
            "### Acme (Acme) x",
        ):
            with self.subTest(line=line):
                self.assertIsNone(parse_topic_heading(line))


class TopicsInTheIndexTest(unittest.TestCase):
    def test_each_facts_line_knows_its_topic(self) -> None:
        """Covers: B44"""
        index = MemoryIndex.parse(DISTILLATE)

        self.assertEqual(
            index.facts,
            [
                FactLine("Dana's birthday is on 3 March", "dana.md"),
                FactLine("Kim Lee leads Acme's IT", "kim-lee.md", "Acme (Schweiz) AG"),
                FactLine("The choir meets on Wednesdays", "choir.md", "Riverside Choir"),
            ],
        )
        self.assertEqual([topic.name for topic in index.topics], ["Acme (Schweiz) AG", "Riverside Choir"])
        self.assertEqual(index.current, ["Building the Acme export"])

    def test_facts_under_a_heading_that_is_no_topic_hold_everywhere_and_the_heading_is_reported(self) -> None:
        index = MemoryIndex.parse("## Facts\n\n### People\n- Dana likes maps (dana.md)\n")

        self.assertEqual(index.facts, [FactLine("Dana likes maps", "dana.md")])
        self.assertEqual(index.unparsed_topic_headings, ["### People"])

    def test_each_current_item_knows_its_topic(self) -> None:
        """Covers: B136"""
        index = MemoryIndex.parse(CURRENT_UNDER_ACME)

        self.assertEqual(
            index.current_lines,
            [
                CurrentLine("Building the Acme export", "2026-10-02"),
                CurrentLine("Shipping the export to Kim Lee", "2026-11-02", "Acme (Schweiz) AG"),
            ],
        )
        self.assertEqual(index.unparsed_topic_headings, [])

    def test_items_under_a_heading_of_current_that_is_no_topic_hold_everywhere_and_the_heading_is_reported(
        self,
    ) -> None:
        index = MemoryIndex.parse("## Current\n\n### Trips\n- Planning the trip to Porto\n")

        self.assertEqual(index.current_lines, [CurrentLine("Planning the trip to Porto", None)])
        self.assertEqual(index.unparsed_topic_headings, ["### Trips"])


class SplitTopicsTest(unittest.TestCase):
    def test_the_general_view_is_the_text_without_the_topic_blocks(self) -> None:
        """Covers: B46"""
        split = split_topics(DISTILLATE)

        self.assertEqual(
            split.general,
            "# Memory\n\n## Facts\n\n- Dana's birthday is on 3 March (dana.md)\n\n"
            "## Current\n\n- Building the Acme export (since 2026-10-02)\n",
        )
        self.assertEqual([block.topic.name for block in split.blocks], ["Acme (Schweiz) AG", "Riverside Choir"])
        self.assertEqual(
            split.blocks[0].text, "### Acme (Schweiz) AG (Acme, Kim Lee)\n- Kim Lee leads Acme's IT (kim-lee.md)\n"
        )

    def test_lines_the_parser_cannot_read_stay_in_the_general_view(self) -> None:
        """Covers: B46"""
        text = (
            "# Memory\n\n## Facts\n\n- a line without its file\n### People\n- Dana likes maps (dana.md)\n\n"
            "## Notes\n\nfree text\n"
        )

        self.assertEqual(split_topics(text).general, text)
        self.assertEqual(split_topics(text).blocks, [])

    def test_a_deeper_heading_stays_inside_its_topic(self) -> None:
        text = "## Facts\n\n### Acme (Acme, Kim Lee)\n#### People\n- Kim Lee leads IT (kim-lee.md)\n"

        split = split_topics(text)

        self.assertEqual(split.general, "## Facts\n\n")
        self.assertEqual(
            split.blocks[0].text, "### Acme (Acme, Kim Lee)\n#### People\n- Kim Lee leads IT (kim-lee.md)\n"
        )

    def test_a_topics_current_items_come_out_with_it_and_stand_below_its_facts(self) -> None:
        """Covers: B136"""
        split = split_topics(CURRENT_UNDER_ACME)

        self.assertEqual(split.general, split_topics(DISTILLATE).general + "\n")
        self.assertEqual([block.topic.name for block in split.blocks], ["Acme (Schweiz) AG", "Riverside Choir"])
        self.assertEqual(
            split.blocks[0].text,
            "### Acme (Schweiz) AG (Acme, Kim Lee)\n- Kim Lee leads Acme's IT (kim-lee.md)\n"
            f"#### Current\n{ACME_EXPORT}",
        )

    def test_a_topic_may_stand_under_current_alone(self) -> None:
        """Covers: B136"""
        text = "## Facts\n\n## Current\n\n- Planning the trip\n\n### Lumen (Lumen, Ben Ortiz)\n- Auditing Lumen\n"

        split = split_topics(text)

        self.assertEqual(split.general, "## Facts\n\n## Current\n\n- Planning the trip\n\n")
        self.assertEqual(
            split.blocks,
            [_block("Lumen", ("Lumen", "Ben Ortiz"), "### Lumen (Lumen, Ben Ortiz)\n#### Current\n- Auditing Lumen\n")],
        )

    def test_headings_with_one_name_are_one_topic_with_the_words_of_each(self) -> None:
        """Covers: B136"""
        text = (
            "## Facts\n\n### Acme (Acme, Kim Lee)\n- Kim Lee leads IT (kim-lee.md)\n\n"
            "### Acme (Acme, Acme Ltd)\n- Acme pays in 30 days (acme.md)\n\n"
            "## Current\n\n### Acme (Acme export, Kim Lee)\n- Building the export\n"
        )

        split = split_topics(text)

        self.assertEqual(
            split.blocks,
            [
                _block(
                    "Acme",
                    ("Acme", "Kim Lee", "Acme Ltd", "Acme export"),
                    "### Acme (Acme, Kim Lee)\n- Kim Lee leads IT (kim-lee.md)\n- Acme pays in 30 days (acme.md)\n"
                    "#### Current\n- Building the export\n",
                )
            ],
        )

    def test_a_heading_under_current_without_items_adds_nothing_to_its_topic(self) -> None:
        acme = "### Acme (Acme, Kim Lee)\n"
        text = f"## Facts\n\n{acme}- Kim Lee leads IT (kim-lee.md)\n\n## Current\n\n{acme}"

        self.assertEqual(
            split_topics(text).blocks[0].text, "### Acme (Acme, Kim Lee)\n- Kim Lee leads IT (kim-lee.md)\n"
        )

    def test_a_topic_heading_in_another_section_is_not_taken_out(self) -> None:
        text = "## Notes\n\n### Acme (Acme, Kim Lee)\n- Building the export\n"

        self.assertEqual(split_topics(text).general, text)
        self.assertEqual(split_topics(text).blocks, [])

    def test_windows_line_ends_are_kept(self) -> None:
        split = split_topics(DISTILLATE.replace("\n", "\r\n"))

        self.assertTrue(split.general.startswith("# Memory\r\n"))
        self.assertEqual(split.blocks[1].topic, Topic("Riverside Choir", ("Riverside Choir", "Petra Lang")))


def _block(name: str, words: tuple[str, ...], text: str) -> TopicBlock:
    return TopicBlock(Topic(name, words), text)


if __name__ == "__main__":
    unittest.main()
