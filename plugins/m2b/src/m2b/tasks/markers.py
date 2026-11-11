"""The marker lines that make curator tasks recognizable whatever their (localized) title.

A curator task's notes start with its marker line. A task ingest creates from a capture names
the capture's file and a key, so a rerun finds its own tasks instead of guessing by title.
"""

from __future__ import annotations

PREFIX = "m2b:"
REVIEW = "review"
CANDIDATE = "candidate"
CAPTURE = "capture"
# A question to the owner whether a current item of the distillate is still going on.
CURRENT = "current"
# The one task that says proposals from the sessions wait for an answer.
PROPOSALS = "proposals"
KINDS = (REVIEW, CANDIDATE, CAPTURE, CURRENT, PROPOSALS)
# The curator's own tasks: never listed as the owner's todos, never journaled as the owner's work.
CURATOR = frozenset({REVIEW, CANDIDATE, CURRENT, PROPOSALS})
# Where a backend has no state for it (Apple Reminders), a dropped task carries this line in its notes.
DROPPED_LINE = f"{PREFIX}dropped"


def marker_line(kind: str, *arguments: str) -> str:
    if kind not in KINDS:
        raise ValueError(f"unknown task marker {kind!r}; known: {', '.join(KINDS)}")
    if any(not argument or any(c.isspace() for c in argument) for argument in arguments):
        raise ValueError(f"marker arguments must be single words, got {arguments!r}")
    return " ".join([f"{PREFIX}{kind}", *arguments])


def with_marker(kind: str, notes: str, *arguments: str) -> str:
    """The notes with the marker line in front."""
    line = marker_line(kind, *arguments)
    return f"{line}\n{notes}" if notes else line


def marker_of(notes: str) -> tuple[str, tuple[str, ...]] | None:
    """The marker kind and its arguments, when the notes start with a marker line."""
    first_line = notes.split("\n", 1)[0].strip()
    if not first_line.startswith(PREFIX):
        return None
    words = first_line[len(PREFIX) :].split()
    if not words or words[0] not in KINDS:
        return None
    return words[0], tuple(words[1:])


def with_dropped_line(notes: str) -> str:
    return notes if is_dropped(notes) else (f"{notes}\n{DROPPED_LINE}" if notes else DROPPED_LINE)


def without_dropped_line(notes: str) -> str:
    return "\n".join(line for line in notes.split("\n") if line.strip() != DROPPED_LINE)


def is_dropped(notes: str) -> bool:
    return any(line.strip() == DROPPED_LINE for line in notes.split("\n"))
