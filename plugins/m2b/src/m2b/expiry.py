"""Memory lines that are due: facts past their day, current items nothing has touched for a month.

The distillate only changes when ingest files a capture that touches a line, so a fact true until
a day stays in every session after it, and a current item that ended without a capture stays for
good. Ingest dates both when it writes them (``until`` in a fact file, ``(since ...)`` on a current
item); this module does the arithmetic, in code, so a run calls the model only for facts that are
actually due and asks the owner only about current items that went quiet (B41).

A fact is due the day after its ``until``. A current item is quiet once its ``since`` lies more than
``QUIET_AFTER`` back. Lines without a date, or with one that is no day, are never due; lint reports
the latter. Reading goes through ``store.reading``: an evicted fact file is listed, never read.

Lines written before ingest dated them have neither date; ``undated`` lists them once for
``m2b curate --refresh-all``, whose refresh step dates those the evidence shows a day for (B43). It
works through them in ``batches``: one model step for all of a memory moved over from another tool
would run out of turns, and fail the same way at every retry, since lasting facts stay undated.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from pathlib import PurePosixPath

from m2b.notes import frontmatter as keys
from m2b.notes.frontmatter import Note, NoteFormatError
from m2b.notes.layout import MEMORY, MEMORY_INDEX
from m2b.notes.memory_index import MemoryIndex, is_day
from m2b.store.base import Store
from m2b.store.reading import Unreadable, read_text_files

QUIET_AFTER = datetime.timedelta(days=30)
_INDEX_PATH = f"{MEMORY}/{MEMORY_INDEX}"


@dataclass(frozen=True)
class DueFact:
    path: str
    until: str


@dataclass(frozen=True)
class QuietCurrent:
    text: str
    since: str


@dataclass(frozen=True)
class Due:
    facts: list[DueFact]
    current: list[QuietCurrent]
    evicted: list[str]
    unreadable: list[Unreadable]


@dataclass(frozen=True)
class Undated:
    facts: list[str]
    current: list[str]
    evicted: list[str]
    unreadable: list[Unreadable]


@dataclass(frozen=True)
class Batch:
    """One model step's share of the backfill: fact files and current items."""

    facts: list[str]
    current: list[str]

    def to_json(self) -> str:
        return json.dumps({"facts": self.facts, "current": self.current})

    @classmethod
    def from_json(cls, text: str) -> Batch:
        """Raises ``ValueError`` when the text is no batch."""
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("not a backfill batch")
        facts, current = data.get("facts"), data.get("current")
        if not isinstance(facts, list) or not isinstance(current, list) or not _strings([*facts, *current]):
            raise ValueError("not a backfill batch")
        return cls([str(path) for path in facts], [str(item) for item in current])


def batches(found: Undated, size: int) -> list[Batch]:
    """The undated lines in batches of at most ``size``, fact files first."""
    items = [(True, path) for path in found.facts] + [(False, text) for text in found.current]
    chunks = [items[start : start + size] for start in range(0, len(items), size)]
    return [Batch([v for fact, v in chunk if fact], [v for fact, v in chunk if not fact]) for chunk in chunks]


def due(store: Store, today: datetime.date) -> Due:
    """What is due on ``today``. Raises ``StoreError`` when ``memory/`` cannot be listed."""
    read = read_text_files(store, [MEMORY], suffixes={".md"})
    facts: list[DueFact] = []
    current: list[QuietCurrent] = []
    for file in read.files:
        if PurePosixPath(file.path).parent.as_posix() != MEMORY:
            continue
        if file.path == _INDEX_PATH:
            current = _quiet(MemoryIndex.parse(file.text), today)
            continue
        until = _until(file.text)
        if until is not None and datetime.date.fromisoformat(until) < today:
            facts.append(DueFact(file.path, until))
    return Due(sorted(facts, key=lambda fact: fact.path), current, sorted(read.evicted), read.unreadable)


def undated(store: Store) -> Undated:
    """Fact files without ``until`` and current items without ``(since ...)``; a wrong date is lint's.

    Raises ``StoreError`` when ``memory/`` cannot be listed.
    """
    read = read_text_files(store, [MEMORY], suffixes={".md"})
    facts: list[str] = []
    current: list[str] = []
    for file in read.files:
        if PurePosixPath(file.path).parent.as_posix() != MEMORY:
            continue
        if file.path == _INDEX_PATH:
            index = MemoryIndex.parse(file.text)
            wrong = {line[2:].strip() for line in index.invalid_since}
            current = [line.text for line in index.current_lines if line.since is None and line.text not in wrong]
            continue
        if _has_no_until(file.text):
            facts.append(file.path)
    evicted = sorted(path for path in read.evicted if PurePosixPath(path).parent.as_posix() == MEMORY)
    return Undated(sorted(facts), current, evicted, read.unreadable)


def _strings(values: list[object]) -> bool:
    return all(isinstance(value, str) for value in values)


def _has_no_until(text: str) -> bool:
    try:
        frontmatter = Note.parse(text).frontmatter
    except NoteFormatError:
        return False
    return frontmatter is None or frontmatter.get(keys.UNTIL) is None


def _until(text: str) -> str | None:
    try:
        frontmatter = Note.parse(text).frontmatter
    except NoteFormatError:
        return None
    value = frontmatter.get(keys.UNTIL) if frontmatter is not None else None
    return str(value) if value is not None and is_day(str(value)) else None


def _quiet(index: MemoryIndex, today: datetime.date) -> list[QuietCurrent]:
    return [
        QuietCurrent(line.text, line.since)
        for line in index.current_lines
        if line.since is not None and today - datetime.date.fromisoformat(line.since) > QUIET_AFTER
    ]
