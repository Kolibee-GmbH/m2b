"""How often the owner corrected Claude again on a lesson they kept, in ``state/core/lesson-counts.json``.

A reading of the sessions asks, beside its proposals, which prompts of the period correct Claude
again on a kept lesson (``glean.Correction``); code keeps a correction only where its words stand in
what was typed after the day the lesson was kept. Each is kept here under its lesson by an id
drawn from its session and its words, so a period read a second time counts nothing twice. A lesson
corrected again since it was kept is one that does not work yet: the overview says so, and what then
becomes of it is the owner's.

Only the curation run writes the file. Each lesson's entry holds the day it was kept beside its ids:
a lesson is known by its file's name, and a name is free again once its lesson is gone, so a count
belongs to the lesson only while that day is the same. An entry of another day counts nothing and,
like one of a lesson that is gone, is left out when the file is written again.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence

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
    return {name: len(ids) for name, ids in _load(store, kept).items()}


def add(store: Store, corrections: Sequence[Correction], kept: Mapping[str, str]) -> int:
    """Counts the corrections of the lessons that still stand, each once; how many were new."""
    counted = _load(store, kept)
    new = 0
    for correction in corrections:
        if correction.lesson not in kept:
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
                "lessons": {
                    name: {"kept": kept[name], "corrected_again": sorted(ids)}
                    for name, ids in sorted(counted.items())
                    if ids
                },
            },
        )
    return new


def _load(store: Store, kept: Mapping[str, str]) -> dict[str, set[str]]:
    """The ids of the standing lessons whose entry holds the day they were kept."""
    raw = read_store_json_object(store, COUNTS_FILE)
    if raw is None:
        return {}
    written_as = raw.get("format")
    if isinstance(written_as, int) and not isinstance(written_as, bool) and written_as > FORMAT:
        raise LessonCountsError(f"{COUNTS_FILE} has format {written_as} and this m2b knows {FORMAT}: update m2b")
    given = raw.get("lessons")
    counted: dict[str, set[str]] = {}
    for name, value in (given if isinstance(given, dict) else {}).items():
        if not isinstance(name, str) or not isinstance(value, dict) or name not in kept:
            continue
        ids = value.get("corrected_again")
        if value.get("kept") == kept[name] and isinstance(ids, list):
            counted[name] = {each for each in ids if isinstance(each, str)}
    return counted


def _id_of(correction: Correction) -> str:
    said = f"{correction.session}\n{' '.join(correction.quote.split())}"
    return hashlib.sha256(said.encode("utf-8", errors="replace")).hexdigest()[:_ID_LENGTH]
