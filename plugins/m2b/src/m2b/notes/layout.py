"""Folder and special file names of the store format; they are a contract and never localized."""

from __future__ import annotations

import re

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


def is_journal_name(name: str) -> bool:
    return _JOURNAL_NAME.match(name) is not None
