"""Search: full text over inbox, corpus and memory, read by this process under the guard.

Check and read happen in one process, so nothing can be evicted between "checked local" and "read".

Reading goes through ``store.reading``: evicted files are listed apart with the command that
fetches them and never read (B6). Only text notes are read (``.md``, ``.txt``); a binary capture
is found through its sidecar note.

The hits come in the order a question wants them, not the order the files were read in: what is
curated first, and a newer note before an older one. A client shows only the first of many hits.
"""

from __future__ import annotations

import datetime
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath

from m2b.notes.layout import CORPUS, INBOX, MEMORY, MEMORY_INDEX, is_journal_name, journal_month
from m2b.notes.names import NoteName
from m2b.store.base import Store, fetch_command
from m2b.store.reading import Unreadable, read_text_files

# Read in the direction ingest moves files, so a note filed during a search is seen at least once
# (twice when it moves after its inbox copy was read).
SEARCHED_FOLDERS = (INBOX, CORPUS, MEMORY)
# Answered the other way round: what curation wrote, then what it filed, then what it has not seen.
ANSWERED_FOLDERS = (MEMORY, CORPUS, INBOX)


@dataclass(frozen=True)
class Hit:
    path: str
    line: int
    text: str


@dataclass(frozen=True)
class SearchResult:
    terms: tuple[str, ...]
    whole_words: bool
    hits: list[Hit]
    evicted: list[str]
    unreadable: list[Unreadable]

    def fetch_commands(self) -> list[str]:
        return [fetch_command(path) for path in self.evicted]


def search(store: Store, *terms: str, whole_words: bool = False) -> SearchResult:
    """Every line that holds one of ``terms``, once, ignoring case; with ``whole_words`` not inside a word.

    The hits of a file stay together in line order, the files in the order of the answer
    (``ANSWERED_FOLDERS``, in the archive and the inbox the newest note first).

    Each term is a phrase of its own. Several terms let one search find a note in either language
    its owner writes in, a word and its translation, without a second pass over the store.

    Raises ``ValueError`` for no term or an empty one and ``StoreError`` when a folder cannot be
    listed, so that a store that could not be searched never looks like one without hits.
    """
    if not terms:
        raise ValueError("no search term")
    matchers = [_matcher(term, whole_words) for term in terms]
    read = read_text_files(store, SEARCHED_FOLDERS)
    hits = [
        hit
        for file in sorted(read.files, key=lambda file: _place_in_the_answer(file.path))
        for hit in _hits_in(file.path, file.text, lambda line: any(matches(line) for matches in matchers))
    ]
    return SearchResult(tuple(term.strip() for term in terms), whole_words, hits, read.evicted, read.unreadable)


def _place_in_the_answer(path: str) -> tuple[int, float, bool]:
    """Sorts the searched files into the order of the answer.

    Memory, archive, inbox. In memory the distillate, then the fact files. In the archive and the
    inbox the newest note first, by the time in its name and never by the time of the file, which
    in a synced folder is when it arrived on this machine; a file whose name carries no time
    follows every dated one of the archive or of the inbox. Files with the same place keep the
    order they were read in, which is by path.
    """
    folder, _, below = path.partition("/")
    folder_place = ANSWERED_FOLDERS.index(folder)
    if folder == MEMORY:
        return (folder_place, 0.0 if below == MEMORY_INDEX else 1.0, False)
    name = PurePosixPath(path).name
    time = _time_in_name(name)
    if time is None:
        return (folder_place, math.inf, False)
    return (folder_place, -time.timestamp(), is_journal_name(name))


def _time_in_name(name: str) -> datetime.datetime | None:
    """When a note was captured. A month's journal counts as the start of its month, so it follows
    the notes of that month (one of that very second too, by the last part of the sort key): it
    lists the tasks ticked off, and a note says more about them."""
    note = NoteName.parse(name)
    if note is not None:
        return note.time
    month = journal_month(name)
    if month is None or month[0] < datetime.MINYEAR:
        return None
    return datetime.datetime(month[0], month[1], 1, tzinfo=datetime.timezone.utc)


def _matcher(term: str, whole_words: bool) -> Callable[[str], bool]:
    needle = term.strip().casefold()
    if not needle:
        raise ValueError("the search term is empty")
    if not whole_words:
        return lambda line: needle in line.casefold()
    pattern = re.compile(r"(?<!\w)" + re.escape(needle) + r"(?!\w)")
    return lambda line: pattern.search(line.casefold()) is not None


def _hits_in(relative: str, text: str, matches: Callable[[str], bool]) -> list[Hit]:
    return [
        Hit(relative, number, line.rstrip("\r").strip())
        for number, line in enumerate(text.split("\n"), start=1)
        if matches(line)
    ]
