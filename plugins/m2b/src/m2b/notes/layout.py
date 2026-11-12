"""Folder and special file names of the store format; they are a contract and never localized."""

from __future__ import annotations

import re
from collections.abc import Iterable

INBOX = "inbox"
CORPUS = "corpus"
MEMORY = "memory"
TASKS = "tasks"
STATE = "state"

MEMORY_INDEX = "MEMORY.md"
STORE_CONTRACT = "STORE.md"

_JOURNAL_NAME = re.compile(r"(\d{4})(0[1-9]|1[0-2])-done\.md\Z")


def journal_name(year: int, month: int) -> str:
    """The file in ``corpus/YYYY/MM/`` that collects the month's completed tasks."""
    return f"{year:04d}{month:02d}-done.md"


def journal_month(name: str) -> tuple[int, int] | None:
    """The year and month in the name of a month's journal, or None for any other name."""
    match = _JOURNAL_NAME.match(name)
    return (int(match.group(1)), int(match.group(2))) if match else None


def is_journal_name(name: str) -> bool:
    return journal_month(name) is not None


def waiting_on_evicted(files: Iterable[str], evicted: Iterable[str]) -> set[str]:
    """The local inbox files of a bundle (a sidecar and its members share a stem) with an entry
    that is not downloaded: they wait for it, since filing the bundle reads every file in it."""
    stems = {_stem(path) for path in evicted}
    return {path for path in files if _stem(path) in stems}


def _stem(path: str) -> str:
    return path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
