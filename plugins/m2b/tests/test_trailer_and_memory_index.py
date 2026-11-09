from __future__ import annotations

import unittest

from m2b.notes.frontmatter import Note
from m2b.notes.memory_index import CurrentLine, FactLine, MemoryIndex, parse_fact_line
from m2b.notes.trailer import MARKER_LINE, find_trailer

CAPTURE = "Dana asked about the garden shed.\n"


def _note(curated: bool, body: str) -> Note:
    flag = "curated: true\n" if curated else ""
    return Note.parse(f"---\nsource: cli\n{flag}---\n{body}")


class TrailerTest(unittest.TestCase):
    def test_a_marker_without_curated_true_is_no_trailer(self) -> None:
        """Covers: X16"""
        note = _note(curated=False, body=f"{CAPTURE}{MARKER_LINE}\nfiled under garden\n")

        self.assertIsNone(find_trailer(note))

    def test_the_trailer_starts_at_the_last_marker_line(self) -> None:
        """Covers: X16"""
        body = f"{CAPTURE}{MARKER_LINE}\nquoted marker above\n{MARKER_LINE}\nfiled under garden\n"

        trailer = find_trailer(_note(curated=True, body=body))

        assert trailer is not None
        self.assertEqual(trailer.captured, f"{CAPTURE}{MARKER_LINE}\nquoted marker above\n")
        self.assertEqual(trailer.notes, "filed under garden\n")

    def test_the_marker_counts_only_as_a_whole_line(self) -> None:
        """Covers: X16"""
        body = f"{CAPTURE}see {MARKER_LINE} in the docs\n"

        self.assertIsNone(find_trailer(_note(curated=True, body=body)))

    def test_the_marker_line_counts_with_crlf_and_at_the_very_end(self) -> None:
        """Covers: X16"""
        crlf = find_trailer(_note(curated=True, body=f"{CAPTURE}{MARKER_LINE}\r\nfiled\r\n"))
        at_end = find_trailer(_note(curated=True, body=f"{CAPTURE}{MARKER_LINE}"))

        assert crlf is not None and at_end is not None
        self.assertEqual((crlf.captured, crlf.notes), (CAPTURE, "filed\r\n"))
        self.assertEqual((at_end.captured, at_end.notes), (CAPTURE, ""))

    def test_a_curated_note_without_a_marker_has_no_trailer(self) -> None:
        self.assertIsNone(find_trailer(_note(curated=True, body=CAPTURE)))


INDEX = """# Memory

## Facts

- Dana's birthday is 14 March (dana.md)
- Prefers green tea (mostly) in the morning (alex.md)
- Works with Acme on the shop (friend-alex.md)
- a line without its file
-  (empty.md)

## Current

- Plans the garden shed for spring (garden-shed.md)
- Waiting for the quote from Initech
"""


class MemoryIndexTest(unittest.TestCase):
    def test_a_facts_line_gives_statement_and_file_name(self) -> None:
        """Covers: X13"""
        self.assertEqual(
            parse_fact_line("- Dana's birthday is 14 March (dana.md)"),
            FactLine("Dana's birthday is 14 March", "dana.md"),
        )

    def test_parentheses_inside_the_statement_stay_in_the_statement(self) -> None:
        """Covers: X13"""
        self.assertEqual(
            parse_fact_line("- Prefers green tea (mostly) in the morning (alex.md)"),
            FactLine("Prefers green tea (mostly) in the morning", "alex.md"),
        )

    def test_lines_that_are_not_facts_lines_do_not_parse(self) -> None:
        for line in (
            "- a line without its file",
            "-  (empty.md)",
            "Dana (dana.md)",
            "- x (notes/dana.md)",
            "- x (dana.txt)",
        ):
            with self.subTest(line=line):
                self.assertIsNone(parse_fact_line(line))

    def test_a_file_is_indexed_only_by_its_exact_name(self) -> None:
        """Covers: X13"""
        index = MemoryIndex.parse(INDEX)

        self.assertIn("friend-alex.md", index.indexed_files())
        self.assertIn("alex.md", index.indexed_files())
        self.assertNotIn("lex.md", index.indexed_files())
        self.assertNotIn("garden-shed.md", index.indexed_files())

    def test_the_sections_are_read_separately_and_odd_lines_are_reported(self) -> None:
        index = MemoryIndex.parse(INDEX.replace("\n", "\r\n"))

        self.assertEqual([fact.file_name for fact in index.facts], ["dana.md", "alex.md", "friend-alex.md"])
        self.assertEqual(
            index.current, ["Plans the garden shed for spring (garden-shed.md)", "Waiting for the quote from Initech"]
        )
        self.assertEqual(index.unparsed_fact_lines, ["- a line without its file", "-  (empty.md)"])

    def test_a_subheading_inside_a_section_keeps_the_section(self) -> None:
        index = MemoryIndex.parse("## Facts\n\n### People\n- Dana's birthday is 14 March (dana.md)\n#tag\n- x (x.md)\n")

        self.assertEqual([fact.file_name for fact in index.facts], ["dana.md", "x.md"])

    def test_an_index_without_sections_has_no_facts(self) -> None:
        index = MemoryIndex.parse("- Dana's birthday is 14 March (dana.md)\n")

        self.assertEqual(index.facts, [])


class CurrentSinceTest(unittest.TestCase):
    """A current item says since when it is going on, so a run can ask about one that went quiet."""

    def test_since_is_read_apart_from_the_item(self) -> None:
        """Covers: B40"""
        index = MemoryIndex.parse("## Current\n\n- Planning the trip to Porto (since 2026-10-02)\n- Reading Dune\n")

        self.assertEqual(index.current, ["Planning the trip to Porto", "Reading Dune"])
        self.assertEqual(
            index.current_lines,
            [CurrentLine("Planning the trip to Porto", "2026-10-02"), CurrentLine("Reading Dune", None)],
        )
        self.assertEqual(index.invalid_since, [])

    def test_a_since_that_is_no_date_is_reported_and_the_item_kept_whole(self) -> None:
        """Covers: B40"""
        index = MemoryIndex.parse("## Current\n\n- Porto (since last week)\n- Shed (since 2026-02-30)\n")

        self.assertEqual(index.current, ["Porto (since last week)", "Shed (since 2026-02-30)"])
        self.assertEqual(index.invalid_since, ["- Porto (since last week)", "- Shed (since 2026-02-30)"])

    def test_since_in_the_middle_of_an_item_is_part_of_its_text(self) -> None:
        index = MemoryIndex.parse("## Current\n\n- Rebuilding the shed (since 2026-10-02) with Sam\n")

        self.assertEqual(index.current, ["Rebuilding the shed (since 2026-10-02) with Sam"])
        self.assertEqual(index.invalid_since, [])


if __name__ == "__main__":
    unittest.main()
