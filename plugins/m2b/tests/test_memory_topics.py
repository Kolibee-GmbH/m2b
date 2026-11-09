"""Topics in the distillate: groups inside the facts section whose facts come in only when named."""

from __future__ import annotations

import unittest

from m2b.notes.memory_index import FactLine, MemoryIndex, Topic, parse_topic_heading, split_topics

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

    def test_a_subheading_under_current_is_reported(self) -> None:
        index = MemoryIndex.parse("## Current\n\n### Acme (Acme, Kim Lee)\n- Building the export\n")

        self.assertEqual(index.current, ["Building the export"])
        self.assertEqual(index.current_subheadings, ["### Acme (Acme, Kim Lee)"])


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

    def test_a_topic_heading_outside_the_facts_section_is_not_taken_out(self) -> None:
        text = "## Current\n\n### Acme (Acme, Kim Lee)\n- Building the export\n"

        self.assertEqual(split_topics(text).general, text)

    def test_windows_line_ends_are_kept(self) -> None:
        split = split_topics(DISTILLATE.replace("\n", "\r\n"))

        self.assertTrue(split.general.startswith("# Memory\r\n"))
        self.assertEqual(split.blocks[1].topic, Topic("Riverside Choir", ("Riverside Choir", "Petra Lang")))


if __name__ == "__main__":
    unittest.main()
