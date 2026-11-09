"""Search: full text over inbox, corpus and memory, read by this process under the guard.

Check and read happen in one process, so nothing can be evicted between "checked local" and "read".

Reading goes through ``store.reading``: evicted files are listed apart with the command that
fetches them and never read (B6). Only text notes are read (``.md``, ``.txt``); a binary capture
is found through its sidecar note.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from m2b.notes.layout import CORPUS, INBOX, MEMORY
from m2b.store.base import Store, fetch_command
from m2b.store.reading import Unreadable, read_text_files

# In the direction ingest moves files, so a note filed during a search is seen at least once
# (twice when it moves after its inbox copy was read).
SEARCHED_FOLDERS = (INBOX, CORPUS, MEMORY)


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
        for file in read.files
        for hit in _hits_in(file.path, file.text, lambda line: any(matches(line) for matches in matchers))
    ]
    return SearchResult(tuple(term.strip() for term in terms), whole_words, hits, read.evicted, read.unreadable)


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
