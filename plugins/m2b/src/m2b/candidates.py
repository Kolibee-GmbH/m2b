"""Memory candidates: proposed as tasks, remembered in ``state/core/candidates.json``.

The core owns a candidate's life, so any add-on can propose one and a tick is filed even without the
worklog.

A module proposes a fact the owner may want kept; it becomes a task with the candidate marker and
the localized title prefix ("Remember? "). The file holds each open candidate's text, so one deleted
outside the product is still known, and each dropped candidate's text for 90 days, so the same
proposal does not come back daily (B35). Harvest (``harvest.py``) moves entries along; nothing keeps
a list of harvested ids (X18).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from m2b.config.json_file import read_store_json_object, write_store_json_object
from m2b.notes.layout import STATE
from m2b.store.base import Store
from m2b.tasks import markers
from m2b.tasks.base import Task, Tasks

CANDIDATES_FILE = f"{STATE}/core/candidates.json"
FORMAT = 1
OPEN = "open"
DROPPED = "dropped"
REMEMBER_DROPPED = datetime.timedelta(days=90)
# The locale key of the title prefix every candidate starts with.
PREFIX_KEY = "candidate.prefix"


@dataclass(frozen=True)
class Entry:
    text: str
    state: str
    since: datetime.datetime


@dataclass(frozen=True)
class Proposal:
    task_id: str | None
    refused: str | None = None


def same_text(first: str, second: str) -> bool:
    """Equal up to case and spacing: the same proposal in another shape is still the same."""
    return " ".join(first.split()).casefold() == " ".join(second.split()).casefold()


def text_of(task: Task, prefix: str) -> str:
    """The fact a candidate stands for: its title without the prefix; a title the owner edited wins."""
    title = task.title.strip()
    return title[len(prefix.strip()) :].strip() if title.startswith(prefix.strip()) else title


def load(store: Store) -> dict[str, Entry]:
    raw = read_store_json_object(store, CANDIDATES_FILE) or {}
    entries = {}
    for task_id, value in (raw.get("candidates") or {}).items():
        try:
            since = datetime.datetime.fromisoformat(value["since"])
            entries[str(task_id)] = Entry(
                str(value["text"]),
                str(value["state"]),
                since if since.tzinfo is not None else since.replace(tzinfo=datetime.timezone.utc),
            )
        except (KeyError, TypeError, ValueError):
            continue
    return entries


def save(store: Store, entries: dict[str, Entry]) -> None:
    write_store_json_object(
        store,
        CANDIDATES_FILE,
        {
            "format": FORMAT,
            "candidates": {
                task_id: {"text": entry.text, "state": entry.state, "since": entry.since.isoformat()}
                for task_id, entry in sorted(entries.items())
            },
        },
    )


def propose(store: Store, tasks: Tasks, text: str, prefix: str, now: datetime.datetime) -> Proposal:
    """Adds the candidate, or refuses it when an open one or one dropped within 90 days has its text."""
    text = " ".join(text.split())
    if not text:
        raise ValueError("a candidate needs a text")
    entries = load(store)
    open_tasks = tasks.items(marker=markers.CANDIDATE)
    if any(same_text(text, text_of(task, prefix)) for task in open_tasks):
        return Proposal(None, OPEN)
    for entry in entries.values():
        if not same_text(text, entry.text):
            continue
        if entry.state == OPEN:
            return Proposal(None, OPEN)
        if entry.state == DROPPED and now - entry.since < REMEMBER_DROPPED:
            return Proposal(None, DROPPED)
    task_id = tasks.add(f"{prefix.strip()} {text}", notes=markers.marker_line(markers.CANDIDATE))
    entries[task_id] = Entry(text, OPEN, now)
    save(store, entries)
    return Proposal(task_id)
