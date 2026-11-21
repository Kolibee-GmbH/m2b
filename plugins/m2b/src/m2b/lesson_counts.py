"""How often the owner corrected Claude again on a lesson they kept, in ``state/core/lesson-counts.json``.

A reading of the sessions asks, beside its proposals, which prompts of the period correct Claude
again on a kept lesson (``glean.Correction``); code keeps a correction only where its words stand in
what was typed after the day the lesson was kept. Each is kept here under its lesson by an id
drawn from its session and its words, so a period read a second time counts nothing twice. A lesson
corrected again since it was kept is one that does not work yet: the overview says so, and what then
becomes of it is the owner's.

Only the curation run writes the file. A lesson that is gone keeps its count until the file is
written again without it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Collection, Sequence

from m2b.config.json_file import read_store_json_object, write_store_json_object
from m2b.glean import Correction
from m2b.notes.layout import STATE
from m2b.store.base import Store

COUNTS_FILE = f"{STATE}/core/lesson-counts.json"
FORMAT = 1
_ID_LENGTH = 12


class LessonCountsError(Exception):
    """The file is there and this m2b cannot use it."""


def corrected_again(store: Store) -> dict[str, int]:
    """Per lesson how often it was corrected again since it was kept."""
    return {name: len(ids) for name, ids in _load(store).items()}


def add(store: Store, corrections: Sequence[Correction], lessons: Collection[str]) -> int:
    """Counts the corrections of the lessons that still stand, each once; how many were new."""
    counted = _load(store)
    new = 0
    for correction in corrections:
        if correction.lesson not in lessons:
            continue
        ids = counted.setdefault(correction.lesson, set())
        key = _id_of(correction)
        if key not in ids:
            ids.add(key)
            new += 1
    if new:
        write_store_json_object(
            store,
            COUNTS_FILE,
            {
                "format": FORMAT,
                "lessons": {name: {"corrected_again": sorted(ids)} for name, ids in sorted(counted.items()) if ids},
            },
        )
    return new


def _load(store: Store) -> dict[str, set[str]]:
    raw = read_store_json_object(store, COUNTS_FILE)
    if raw is None:
        return {}
    written_as = raw.get("format")
    if isinstance(written_as, int) and not isinstance(written_as, bool) and written_as > FORMAT:
        raise LessonCountsError(f"{COUNTS_FILE} has format {written_as} and this m2b knows {FORMAT}: update m2b")
    given = raw.get("lessons")
    counted: dict[str, set[str]] = {}
    for name, value in (given if isinstance(given, dict) else {}).items():
        ids = value.get("corrected_again") if isinstance(value, dict) else None
        if isinstance(name, str) and isinstance(ids, list):
            counted[name] = {each for each in ids if isinstance(each, str)}
    return counted


def _id_of(correction: Correction) -> str:
    said = f"{correction.session}\n{' '.join(correction.quote.split())}"
    return hashlib.sha256(said.encode("utf-8", errors="replace")).hexdigest()[:_ID_LENGTH]
