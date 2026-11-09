"""The curation trailer: the curator's notes after the captured text, which is never rewritten.

The trailer starts at the last line that is exactly the marker, and it exists only when the
frontmatter says ``curated: true``; a marker a user typed into a capture is just text.
"""

from __future__ import annotations

from dataclasses import dataclass

from m2b.notes.frontmatter import CURATED, Note

MARKER_LINE = "<!-- m2b:curation -->"


@dataclass(frozen=True)
class Trailer:
    captured: str
    notes: str


def find_trailer(note: Note) -> Trailer | None:
    if note.frontmatter is None or not note.frontmatter.get_flag(CURATED):
        return None
    lines = note.body.split("\n")
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].removesuffix("\r") == MARKER_LINE:
            captured = "\n".join(lines[:index]) + ("\n" if index else "")
            notes = "\n".join(lines[index + 1 :])
            return Trailer(captured, notes)
    return None
