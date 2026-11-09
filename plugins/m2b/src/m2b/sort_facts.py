"""The check after ``m2b curate --sort-facts`` (B51): only headings and order may have changed.

The sorting step moves facts lines of an existing distillate into topics and writes the topics'
headings. Its model may edit ``MEMORY.md``, and an edit could change a statement as well; nothing in
the fence can tell the two apart, so this code compares. Inside ``## Facts`` every line other than
a ``###`` heading or a blank line must still be there, as often as before; everything outside
``## Facts`` must be exactly as it was.
"""

from __future__ import annotations

from collections import Counter

from m2b.notes.memory_index import FACTS_HEADING, is_section_heading

_GROUP_HEADING = "### "


def sorting_problem(before: str, after: str) -> str | None:
    """Why ``after`` is more than ``before`` sorted, or None when it is only that."""
    before_facts, before_rest = _split(before)
    after_facts, after_rest = _split(after)
    if before_rest != after_rest:
        return "the sorting step changed the text outside ## Facts"
    lost = before_facts - after_facts
    added = after_facts - before_facts
    if lost or added:
        return (
            f"the sorting step changed the facts lines ({sum(lost.values())} gone, {sum(added.values())} new), "
            "though it may only move them and write topic headings"
        )
    return None


def _split(text: str) -> tuple[Counter[str], list[tuple[str, list[str]]]]:
    """The facts section's lines that must survive, and every other section line by line."""
    facts: Counter[str] = Counter()
    rest: list[tuple[str, list[str]]] = [("", [])]
    in_facts = False
    for raw_line in text.split("\n"):
        line = raw_line.removesuffix("\r")
        if is_section_heading(line):
            in_facts = line.strip() == FACTS_HEADING
            if not in_facts:
                rest.append((line, []))
            continue
        if in_facts:
            if line.strip() and not line.startswith(_GROUP_HEADING):
                facts[line.rstrip()] += 1
        else:
            rest[-1][1].append(line)
    return facts, [(heading, _trimmed(lines)) for heading, lines in rest]


def _trimmed(lines: list[str]) -> list[str]:
    """A section's lines without the blank ones at its end, which moving a block may shift."""
    end = len(lines)
    while end and not lines[end - 1].strip():
        end -= 1
    return lines[:end]
