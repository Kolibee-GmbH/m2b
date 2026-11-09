"""Still current? A current item no capture touched for a month goes to the owner as a question (B42).

Whether a trip is still being planned only the owner knows, so the run asks instead of guessing.
``ask`` makes one task per quiet item, ``"<prefix> <item>"``, with the marker ``m2b:current <key>``;
the key is a short hash of the item's text, because a marker argument is one word. The keys asked
are kept in ``state/core/current-questions.json``, so an item is never asked twice, and a question
the owner deleted (the only way to say no in a reminders app without a dropped state) counts as
dropped, as a deleted memory candidate does. A question whose item ingest changed or removed is
closed by ``ask``: there is nothing left to answer.

``settle`` runs at the start of the next run: a ticked question keeps the item and moves its
``since`` to today, a dropped or deleted one takes the item out of ``## Current``, on every line
that holds it. The distillate is written first, then the state, then the tasks are deleted, so a
crash in between leaves at most a question whose answer is already applied, and applying it again
changes nothing.

A question missing from the task list counts as deleted only in the list it was asked in. The file
keeps that list (backend and list name); after setup switched to another one, the questions still
waiting are forgotten instead, so ``ask`` asks them again in the new list and no item leaves
``## Current`` without an answer.
"""

from __future__ import annotations

import datetime
import hashlib
from collections.abc import Sequence

from m2b.config.json_file import read_store_json_object, write_store_json_object
from m2b.expiry import QuietCurrent
from m2b.notes.layout import MEMORY, MEMORY_INDEX, STATE
from m2b.notes.memory_index import CURRENT_HEADING, MemoryIndex, current_line_text, is_section_heading
from m2b.store.base import Store, StoreError
from m2b.tasks import markers
from m2b.tasks.base import Task, Tasks

PREFIX_KEY = "current.prefix"
QUESTIONS_FILE = f"{STATE}/core/current-questions.json"
FORMAT = 1
_INDEX_PATH = f"{MEMORY}/{MEMORY_INDEX}"


def key_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def ask(store: Store, tasks: Tasks, quiet: Sequence[QuietCurrent], prefix: str, *, task_list: str) -> list[str]:
    """Closes questions whose item is gone, then asks about each quiet item not asked yet.

    ``task_list`` names the list the tasks are in, ``<backend>:<list name>``.
    """
    loaded, asked_in = _load(store)
    # Questions asked in another list are asked again here; the old list is not read.
    asked = loaded if asked_in == task_list else {}
    questions = _questions(tasks)
    items = _current_keys(store)
    if items is not None:
        for key, task in questions.items():
            if not task.completed and key not in items:
                tasks.delete(task.id)
                asked.pop(key, None)
    new = []
    for item in quiet:
        key = key_of(item.text)
        if key in asked or key in questions:
            asked.setdefault(key, item.text)
            continue
        tasks.add(f"{prefix} {item.text}", markers.with_marker(markers.CURRENT, "", key))
        asked[key] = item.text
        new.append(item.text)
    if asked != loaded or (asked and asked_in != task_list):
        _save(store, asked, task_list)
    return new


def settle(store: Store, tasks: Tasks, today: datetime.date, *, task_list: str) -> None:
    """Applies the owner's answers to the distillate, then forgets and removes the answered questions."""
    asked, asked_in = _load(store)
    questions = _questions(tasks)
    answered = {key: task for key, task in questions.items() if task.completed}
    # Not in another list is not deleted: the owner never saw the question there. Nor is a question
    # the list could not answer for: its task may be one the backend cannot read.
    certain = asked_in == task_list and tasks.lists_every_task()
    deleted = [key for key in asked if key not in questions] if certain else []
    if not answered and not deleted:
        return
    keep = {key for key, task in answered.items() if not task.dropped}
    drop = {key for key, task in answered.items() if task.dropped} | set(deleted)
    text = store.read_text(_INDEX_PATH)
    store.replace(_INDEX_PATH, _answer(text, keep, drop, today).encode("utf-8"))
    _save(store, {key: item for key, item in asked.items() if key not in answered and key not in deleted}, asked_in)
    for task in answered.values():
        tasks.delete(task.id)


def _answer(text: str, keep: set[str], drop: set[str], today: datetime.date) -> str:
    """The distillate with every current line of a kept item dated ``today`` and of a dropped one removed."""
    lines = []
    section = ""
    for line in text.split("\n"):
        if is_section_heading(line):
            section = line.strip()
        elif section == CURRENT_HEADING and line.startswith("- "):
            item = current_line_text(line)
            key = key_of(item)
            if key in drop:
                continue
            if key in keep:
                line = f"- {item} (since {today.isoformat()})"
        lines.append(line)
    return "\n".join(lines)


def _questions(tasks: Tasks) -> dict[str, Task]:
    found: dict[str, Task] = {}
    for task in tasks.items(marker=markers.CURRENT, include_completed=True):
        marker = markers.marker_of(task.notes)
        if marker is not None and marker[1]:
            found[marker[1][0]] = task
    return found


def _current_keys(store: Store) -> set[str] | None:
    """The keys of the current items now, or None when the distillate cannot be read."""
    try:
        text = store.read_text(_INDEX_PATH)
    except (StoreError, FileNotFoundError, UnicodeDecodeError):
        return None
    return {key_of(item) for item in MemoryIndex.parse(text).current}


def _load(store: Store) -> tuple[dict[str, str], str | None]:
    """The questions asked and the list they were asked in; None for a file written before lists were kept."""
    raw = read_store_json_object(store, QUESTIONS_FILE) or {}
    asked = raw.get("asked")
    asked_in = raw.get("list")
    questions = {str(key): str(text) for key, text in asked.items()} if isinstance(asked, dict) else {}
    return questions, asked_in if isinstance(asked_in, str) else None


def _save(store: Store, asked: dict[str, str], task_list: str | None) -> None:
    data: dict[str, object] = {"format": FORMAT, "asked": dict(sorted(asked.items()))}
    if task_list is not None:
        data["list"] = task_list
    write_store_json_object(store, QUESTIONS_FILE, data)


def task_list_of(backend: str, list_name: str | None) -> str:
    """How the questions file names a task list: ``<backend>:<list name>``."""
    return f"{backend}:{list_name or ''}"
