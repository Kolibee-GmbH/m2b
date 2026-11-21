"""Still current? A current item no capture touched for a month goes to the owner as a question (B42).

Whether a trip is still being planned only the owner knows, so the run asks instead of guessing,
through the ledger every such question goes through (``question_ledger``): one task per quiet item,
``"<prefix> <item>"``, with the marker ``m2b:current <key>``, the key a short hash of the item's
text, the keys asked in ``state/core/current-questions.json``. A question the owner deleted counts
as dropped, as a deleted memory candidate does. A question whose item ingest changed or removed is
closed by ``ask``: there is nothing left to answer.

``settle`` runs at the start of the next run: a ticked question keeps the item and moves its
``since`` to today, a dropped or deleted one takes the item out of ``## Current``, on every line
that holds it, and with a topic's last item its heading there. The distillate is written first,
then the ledger forgets the answers and removes their tasks.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence

from m2b.expiry import QuietCurrent
from m2b.notes.layout import MEMORY, MEMORY_INDEX, STATE
from m2b.notes.memory_index import (
    CURRENT_HEADING,
    MemoryIndex,
    current_line_text,
    ends_topic_block,
    is_section_heading,
    parse_topic_heading,
)
from m2b.question_ledger import Ledger, Wanted, key_of
from m2b.store.base import Store, StoreError
from m2b.tasks import markers
from m2b.tasks.base import Tasks

PREFIX_KEY = "current.prefix"
QUESTIONS_FILE = f"{STATE}/core/current-questions.json"
LEDGER = Ledger(markers.CURRENT, QUESTIONS_FILE)
_INDEX_PATH = f"{MEMORY}/{MEMORY_INDEX}"


def ask(store: Store, tasks: Tasks, quiet: Sequence[QuietCurrent], prefix: str, *, task_list: str) -> list[str]:
    """Closes questions whose item is gone, then asks about each quiet item not asked yet.

    ``task_list`` names the list the tasks are in, ``<backend>:<list name>``.
    """
    items = _current_keys(store)
    wanted = [Wanted(key_of(item.text), item.text, item.text) for item in quiet]
    gone = None if items is None else (lambda key, _: key not in items)
    return LEDGER.ask(store, tasks, wanted, prefix, task_list=task_list, gone=gone)


def settle(store: Store, tasks: Tasks, today: datetime.date, *, task_list: str) -> None:
    """Applies the owner's answers to the distillate, then forgets and removes the answered questions."""
    answers = LEDGER.answers(store, tasks, task_list=task_list)
    if answers is None:
        return
    text = store.read_text(_INDEX_PATH)
    store.replace(_INDEX_PATH, _answer(text, set(answers.kept), set(answers.dropped), today).encode("utf-8"))
    LEDGER.forget(store, tasks, answers)


def _answer(text: str, keep: set[str], drop: set[str], today: datetime.date) -> str:
    """The distillate with every current line of a kept item dated ``today`` and of a dropped one removed.

    A topic heading under current that lost its last item goes too: a session start would still
    name a topic that holds nothing.
    """
    lines: list[str] = []
    section = ""
    # Where in ``lines`` the open topic heading under current stands, and the same once it lost an item.
    topic_at: int | None = None
    lost_an_item_at: int | None = None
    for line in text.split("\n"):
        if ends_topic_block(line):
            _take_out_emptied_topic(lines, lost_an_item_at)
            topic_at = lost_an_item_at = None
            if is_section_heading(line):
                section = line.strip()
            elif section == CURRENT_HEADING and parse_topic_heading(line) is not None:
                topic_at = len(lines)
        elif section == CURRENT_HEADING and line.startswith("- "):
            item = current_line_text(line)
            key = key_of(item)
            if key in drop:
                lost_an_item_at = topic_at
                continue
            if key in keep:
                line = f"- {item} (since {today.isoformat()})"
        lines.append(line)
    _take_out_emptied_topic(lines, lost_an_item_at)
    return "\n".join(lines)


def _take_out_emptied_topic(lines: list[str], heading_at: int | None) -> None:
    """Removes the topic heading at ``heading_at`` when only blank lines follow it."""
    if heading_at is None or any(line.strip() for line in lines[heading_at + 1 :]):
        return
    del lines[heading_at]
    # The blank lines that followed it would double the one before it.
    while 0 < heading_at < len(lines) and not lines[heading_at - 1].strip():
        del lines[heading_at]


def _current_keys(store: Store) -> set[str] | None:
    """The keys of the current items now, or None when the distillate cannot be read."""
    try:
        text = store.read_text(_INDEX_PATH)
    except (StoreError, FileNotFoundError, UnicodeDecodeError):
        return None
    return {key_of(item) for item in MemoryIndex.parse(text).current}


def task_list_of(backend: str, list_name: str | None) -> str:
    """How the questions file names a task list: ``<backend>:<list name>``."""
    return f"{backend}:{list_name or ''}"
