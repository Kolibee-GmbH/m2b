"""Rediscover: one or a few old corpus notes back into view, each with its reason (B5).

Old means from a month before the current one. Two reasons exist: the note shares a word with
an item of the current section of ``MEMORY.md``, or it is a random pick from a past month. Asked
for a period ("what did I note last spring?"), the notes come from its months only, the current
one included, each with its month as the reason. A
note with the quiet marker is never returned (B4), and neither is a file with a ``kind``
(journal, sidecar, worklog): those are records, not notes. Reading goes through
``store.reading``, so evicted notes are listed apart and never read (B6).
"""

from __future__ import annotations

import datetime
import random
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from m2b.notes.frontmatter import KIND, Note
from m2b.notes.layout import CORPUS, MEMORY, MEMORY_INDEX, is_journal_name
from m2b.notes.memory_index import MemoryIndex
from m2b.notes.trailer import find_trailer
from m2b.store.base import EvictedFileError, Store, StoreReadError
from m2b.store.reading import Unreadable, read_text_files

RANDOM = "random"
SHARES_A_WORD = "shares a word"
FROM_PERIOD = "period"
DEFAULT_COUNT = 3
MAX_TEXT_CHARACTERS = 2000
MIN_WORD_LENGTH = 4

_MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)  # fmt: skip
# Without a period, old means any month before the current one.
_EARLIEST = (1, 1)
_MONTH_TEXT = re.compile(r"(\d{4})-(0[1-9]|1[0-2])\Z")
_MONTH_FOLDER = re.compile(rf"{CORPUS}/(\d{{4}})/(0[1-9]|1[0-2])(/|\Z)")
_WORD = re.compile(r"\w+")
# Words long enough to pass the length rule that still say nothing about a topic, English and German.
_COMMON_WORDS = frozenset(
    """
    about after again also been before being both does done each even from have here into just
    like made make many more most much must next only other over same some such than that them
    then there these they this those very want were what when where which while will with would
    your aber alle also auch dann dass denn dies diese dieser doch eine einem einen einer eines
    habe haben hier immer jetzt kann mehr mein meine mich mit nach noch nicht oder schon sehr
    sein seine sich sind und über unter viel vom von weil wenn werden wieder wird wir zum zur
    """.split()  # noqa: SIM905 - a word list is easier to keep as text than as 100 string literals
)
_MEMORY_INDEX_PATH = f"{MEMORY}/{MEMORY_INDEX}"


@dataclass(frozen=True)
class Months:
    """The months asked for, first and last included: ``YYYY-MM`` or ``YYYY-MM..YYYY-MM``."""

    first: tuple[int, int]
    last: tuple[int, int]

    @classmethod
    def parse(cls, text: str) -> Months:
        first_text, separator, last_text = text.partition("..")
        first = _parse_month(first_text)
        last = _parse_month(last_text) if separator else first
        if last < first:
            raise ValueError(f"{text!r} ends before it starts")
        return cls(first, last)

    def holds(self, month: tuple[int, int]) -> bool:
        return self.first <= month <= self.last

    def holds_year(self, year: int) -> bool:
        return self.first[0] <= year <= self.last[0]

    def label(self) -> str:
        if self.first == self.last:
            return _month_label(self.first)
        return f"{_month_label(self.first)} to {_month_label(self.last)}"


@dataclass(frozen=True)
class Pick:
    path: str
    why: str
    reason: str
    text: str
    truncated: bool
    word: str | None = None
    current_item: str | None = None


@dataclass(frozen=True)
class RediscoverResult:
    picks: list[Pick]
    evicted: list[str]
    unreadable: list[Unreadable]


@dataclass(frozen=True)
class _Candidate:
    path: str
    month: tuple[int, int]
    text: str
    words: frozenset[str]


def rediscover(
    store: Store, today: datetime.date, rng: random.Random, count: int = DEFAULT_COUNT, months: Months | None = None
) -> RediscoverResult:
    """Up to ``count`` distinct notes: those sharing a word with the current section first, at most
    ``count - 1`` of them, then random picks from past months for the rest. With ``months``, random
    picks from those months only.

    Raises ``ValueError`` for a count below one and ``StoreError`` when the corpus cannot be listed.
    """
    if count < 1:
        raise ValueError(f"the count must be at least 1, not {count}")
    read = read_text_files(store, [CORPUS], suffixes={".md"})
    current_month = (today.year, today.month)
    wanted = months if months is not None else Months(_EARLIEST, _month_before(current_month))
    candidates = [
        candidate
        for file in read.files
        if (candidate := _candidate(file.path, file.text)) is not None and wanted.holds(candidate.month)
    ]

    def could_hold_a_wanted_note(path: str) -> bool:
        return _could_hold(path, wanted) and not is_journal_name(PurePosixPath(path).name)

    evicted = [path for path in read.evicted if could_hold_a_wanted_note(path)]
    unreadable = [item for item in read.unreadable if could_hold_a_wanted_note(item.path)]
    if months is not None:
        return RediscoverResult(_random_picks(candidates, rng, count, FROM_PERIOD), sorted(evicted), unreadable)
    current_items = _current_items(store, evicted, unreadable)
    picks = _sharing_a_word(candidates, current_items, rng, count - 1)
    rest = [c for c in candidates if c.path not in {p.path for p in picks}]
    picks += _random_picks(rest, rng, count - len(picks), RANDOM)
    return RediscoverResult(picks, sorted(evicted), unreadable)


def _candidate(relative: str, text: str) -> _Candidate | None:
    month = _month_of(relative)
    if month is None:
        return None
    note = Note.parse(text)
    if note.is_quiet or (note.frontmatter is not None and note.frontmatter.get(KIND) is not None):
        return None
    trailer = find_trailer(note)
    captured = (trailer.captured if trailer is not None else note.body).strip()
    if not captured:
        return None
    return _Candidate(relative, month, captured, _words(captured))


def _current_items(store: Store, evicted: list[str], unreadable: list[Unreadable]) -> list[str]:
    try:
        text = store.read_bytes(_MEMORY_INDEX_PATH).decode("utf-8", errors="replace")
    except EvictedFileError:
        evicted.append(_MEMORY_INDEX_PATH)
        return []
    except StoreReadError as error:
        unreadable.append(Unreadable(_MEMORY_INDEX_PATH, str(error)))
        return []
    except FileNotFoundError:
        return []
    return MemoryIndex.parse(text).current


def _sharing_a_word(
    candidates: list[_Candidate], current_items: list[str], rng: random.Random, limit: int
) -> list[Pick]:
    """Round by round over the current items, one more note for each, until ``limit`` is reached."""
    matches: list[list[tuple[str, _Candidate]]] = []
    for item in current_items:
        item_words = _words(item)
        found = [(word, c) for c in candidates for word in sorted(item_words & c.words)[:1]]
        rng.shuffle(found)
        matches.append(found)
    picks: list[Pick] = []
    chosen: set[str] = set()
    while len(picks) < limit and any(matches):
        for item, found in zip(current_items, matches):
            while found and len(picks) < limit:
                word, candidate = found.pop()
                if candidate.path in chosen:
                    continue
                chosen.add(candidate.path)
                reason = f"shares {word!r} with the current item {item!r}"
                picks.append(_pick(candidate, SHARES_A_WORD, reason, word=word, current_item=item))
                break
    return picks


def _random_picks(candidates: list[_Candidate], rng: random.Random, limit: int, why: str) -> list[Pick]:
    """A random past month first, then a random note in it, so a busy month does not crowd out the rest."""
    by_month: dict[tuple[int, int], list[_Candidate]] = {}
    for candidate in sorted(candidates, key=lambda c: c.path):
        by_month.setdefault(candidate.month, []).append(candidate)
    picks: list[Pick] = []
    while len(picks) < limit and by_month:
        month = rng.choice(sorted(by_month))
        notes = by_month[month]
        candidate = notes.pop(rng.randrange(len(notes)))
        if not notes:
            del by_month[month]
        reason = f"from {_month_label(month)}" if why == FROM_PERIOD else f"random pick from {_month_label(month)}"
        picks.append(_pick(candidate, why, reason))
    return picks


def _pick(candidate: _Candidate, why: str, reason: str, **fields: str) -> Pick:
    text = candidate.text
    truncated = len(text) > MAX_TEXT_CHARACTERS
    shown = text[:MAX_TEXT_CHARACTERS].rstrip() if truncated else text
    return Pick(candidate.path, why, reason, shown, truncated, **fields)


def _month_of(relative: str) -> tuple[int, int] | None:
    match = _MONTH_FOLDER.match(relative)
    return (int(match.group(1)), int(match.group(2))) if match else None


def _could_hold(relative: str, wanted: Months) -> bool:
    """An evicted month folder or note counts when its month is wanted, a year folder when one of its
    months is, and the corpus always."""
    month = _month_of(relative)
    if month is not None:
        return wanted.holds(month)
    parts = PurePosixPath(relative).parts
    if len(parts) == 2 and parts[1].isdigit():
        return wanted.holds_year(int(parts[1]))
    return len(parts) < 3


def _month_before(month: tuple[int, int]) -> tuple[int, int]:
    year, number = month
    return (year, number - 1) if number > 1 else (year - 1, 12)


def _parse_month(text: str) -> tuple[int, int]:
    match = _MONTH_TEXT.match(text)
    if match is None:
        raise ValueError(f"{text!r} is no month; write it as YYYY-MM")
    return int(match.group(1)), int(match.group(2))


def _month_label(month: tuple[int, int]) -> str:
    year, number = month
    return f"{_MONTH_NAMES[number - 1]} {year}"


def _words(text: str) -> frozenset[str]:
    return frozenset(
        word
        for word in (match.group().casefold() for match in _WORD.finditer(text))
        if len(word) >= MIN_WORD_LENGTH and not word.isdigit() and word not in _COMMON_WORDS
    )
