"""How often the owner corrected Claude again on a lesson they kept, in ``state/core/lesson-counts.json``.

A reading of the sessions asks, beside its proposals, which prompts of the period correct Claude
again on a kept lesson (``glean.Correction``); code keeps a correction only where its words stand in
what was typed after the day the lesson was kept. Each is kept here under its lesson by an id
drawn from its session and its words, so a period read a second time counts nothing twice. A lesson
corrected again since it was kept is one that does not work yet: the overview says so, and what then
becomes of it is the owner's.

Each lesson's entry also holds ``last``, the day of the last run that counted a new correction of
it: a knowledge lesson the owner did not correct for a long time is asked about (``lesson_check``).

Only the curation run writes the file. Each lesson's entry holds the day it was kept beside its ids:
a lesson is known by its file's name, and a name is free again once its lesson is gone, so a count
belongs to the lesson only while that day is the same. An entry of another day counts nothing and,
like one of a lesson that is gone, is left out when the file is written again.
"""

from __future__ import annotations

import datetime
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from m2b.config.json_file import read_store_json_object, write_store_json_object
from m2b.glean import Correction
from m2b.notes.layout import STATE
from m2b.store.base import Store

COUNTS_FILE = f"{STATE}/core/lesson-counts.json"
FORMAT = 1
_ID_LENGTH = 12


class LessonCountsError(Exception):
    """The file is there and this m2b cannot use it."""


def corrected_again(store: Store, kept: Mapping[str, str]) -> dict[str, int]:
    """Per standing lesson (its name and the day it was kept) how often it was corrected again since."""
    return {name: len(entry.ids) for name, entry in _load(store, kept).items() if entry.ids}


def last_corrected(store: Store, kept: Mapping[str, str]) -> dict[str, str]:
    """Per standing lesson the day of the last run that counted a correction of it, where one did."""
    return {name: entry.last for name, entry in _load(store, kept).items() if entry.last}


def add(store: Store, corrections: Sequence[Correction], kept: Mapping[str, str], today: datetime.date) -> int:
    """Counts the corrections of the lessons that still stand, each once; how many were new. A lesson
    with a new one gets ``today`` as the day it was last corrected."""
    counted = _load(store, kept)
    new = 0
    for correction in corrections:
        if correction.lesson not in kept:
            continue
        entry = counted.setdefault(correction.lesson, _Entry(set(), None))
        key = _id_of(correction)
        if key not in entry.ids:
            entry.ids.add(key)
            entry.last = today.isoformat()
            new += 1
    if new:
        write_store_json_object(
            store,
            COUNTS_FILE,
            {
                "format": FORMAT,
                "lessons": {
                    name: {
                        "kept": kept[name],
                        "corrected_again": sorted(entry.ids),
                        **({"last": entry.last} if entry.last else {}),
                    }
                    for name, entry in sorted(counted.items())
                    if entry.ids
                },
            },
        )
    return new


@dataclass
class _Entry:
    ids: set[str]
    last: str | None


def _load(store: Store, kept: Mapping[str, str]) -> dict[str, _Entry]:
    """The ids and the last day of the standing lessons whose entry holds the day they were kept."""
    raw = read_store_json_object(store, COUNTS_FILE)
    if raw is None:
        return {}
    written_as = raw.get("format")
    if isinstance(written_as, int) and not isinstance(written_as, bool) and written_as > FORMAT:
        raise LessonCountsError(f"{COUNTS_FILE} has format {written_as} and this m2b knows {FORMAT}: update m2b")
    given = raw.get("lessons")
    counted: dict[str, _Entry] = {}
    for name, value in (given if isinstance(given, dict) else {}).items():
        if not isinstance(name, str) or not isinstance(value, dict) or name not in kept:
            continue
        ids = value.get("corrected_again")
        if value.get("kept") == kept[name] and isinstance(ids, list):
            last = value.get("last")
            counted[name] = _Entry(
                {each for each in ids if isinstance(each, str)},
                last if isinstance(last, str) and _is_day(last) else None,
            )
    return counted


def _is_day(text: str) -> bool:
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _id_of(correction: Correction) -> str:
    said = f"{correction.session}\n{' '.join(correction.quote.split())}"
    return hashlib.sha256(said.encode("utf-8", errors="replace")).hexdigest()[:_ID_LENGTH]
