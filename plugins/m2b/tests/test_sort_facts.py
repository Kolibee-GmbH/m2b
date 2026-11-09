"""The check after sorting facts into topics: only headings and order may change."""

from __future__ import annotations

import unittest

from m2b.sort_facts import sorting_problem

BEFORE = """# Memory

## Facts

- Dana's birthday is on 3 March (dana.md)
- Kim Lee leads Acme's IT (kim-lee.md)
### People
- The choir meets on Wednesdays (choir.md)

## Current

- Building the Acme export (since 2026-10-02)
"""
SORTED = """# Memory

## Facts

- Dana's birthday is on 3 March (dana.md)

### Acme Ltd (Acme Ltd, Acme, Kim Lee)
- Kim Lee leads Acme's IT (kim-lee.md)

### Riverside Choir (Riverside Choir)
- The choir meets on Wednesdays (choir.md)

## Current

- Building the Acme export (since 2026-10-02)
"""


class SortingProblemTest(unittest.TestCase):
    def test_moving_lines_into_topics_and_writing_headings_is_fine(self) -> None:
        """Covers: B51"""
        self.assertIsNone(sorting_problem(BEFORE, SORTED))
        self.assertIsNone(sorting_problem(BEFORE, BEFORE))

    def test_a_changed_statement_is_a_problem(self) -> None:
        """Covers: B51"""
        changed = SORTED.replace("leads Acme's IT", "led Acme's IT")

        self.assertIn("facts lines", sorting_problem(BEFORE, changed) or "")

    def test_a_dropped_or_doubled_line_is_a_problem(self) -> None:
        dropped = SORTED.replace("- The choir meets on Wednesdays (choir.md)\n", "")
        doubled = SORTED.replace("(dana.md)\n", "(dana.md)\n- Dana's birthday is on 3 March (dana.md)\n")

        self.assertIsNotNone(sorting_problem(BEFORE, dropped))
        self.assertIsNotNone(sorting_problem(BEFORE, doubled))

    def test_any_change_outside_the_facts_section_is_a_problem(self) -> None:
        """Covers: B51"""
        for after in (
            SORTED.replace("(since 2026-10-02)", "(since 2026-11-08)"),
            SORTED.replace("# Memory", "# Memories"),
            SORTED + "\n## Notes\n\nnew\n",
        ):
            with self.subTest(after=after[-40:]):
                self.assertIn("outside ## Facts", sorting_problem(BEFORE, after) or "")

    def test_a_line_moved_out_of_the_facts_section_is_a_problem(self) -> None:
        moved = SORTED.replace("- Dana's birthday is on 3 March (dana.md)\n", "").replace(
            "## Current\n\n", "## Current\n\n- Dana's birthday is on 3 March (dana.md)\n"
        )

        self.assertIsNotNone(sorting_problem(BEFORE, moved))

    def test_other_text_in_the_facts_section_stays(self) -> None:
        before = BEFORE.replace("## Facts\n\n", "## Facts\n\nA note the owner wrote.\n")

        self.assertIsNotNone(sorting_problem(before, SORTED))
        self.assertIsNone(
            sorting_problem(before, SORTED.replace("## Facts\n\n", "## Facts\n\nA note the owner wrote.\n"))
        )


if __name__ == "__main__":
    unittest.main()
