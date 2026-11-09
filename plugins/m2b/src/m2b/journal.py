"""The journal of completed tasks, run step 6: ``corpus/YYYY/MM/YYYYMM-done.md``, one file per month (B23).

A line per completed task, by its local completion day: ``- <date> <title> <!-- m2b:done <id> <date> -->``.
The hidden comment is the key, so a task completed again on another day gets a second line and a
rerun adds nothing. A Markdown task the owner named by hand has its file name as id, spaces
included, so the key is read back up to the date; whitespace in an id is written as one space and
a ``-->`` in it is escaped, so the comment always ends where the key does. Existing bytes are
kept, lines the owner wrote included. Curator tasks (review, candidate) are left out; tasks ingest
made from captures are the owner's and stay in. Nothing completed before ``journal_since`` is asked
for. Every month file is read before any is written, so
an evicted one fails the step with nothing written (X3).
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field

from m2b.notes import frontmatter as keys
from m2b.notes.frontmatter import NoteFormatError
from m2b.notes.layout import CORPUS, journal_name
from m2b.store.base import Store, StoreError
from m2b.tasks import markers
from m2b.tasks.base import Task, Tasks

__all__ = ["JournalReport", "NoteFormatError", "StoreError", "write_journal"]

SOURCE = "journal"
CURATOR_MARKERS = markers.CURATOR
_DONE = re.compile(r"<!-- m2b:done (\S.*?) (\d{4}-\d{2}-\d{2}) -->")


@dataclass
class JournalReport:
    appended: dict[str, int] = field(default_factory=dict)


def write_journal(store: Store, tasks: Tasks, since: datetime.date, now: datetime.datetime) -> JournalReport:
    # Without the privacy grant Reminders answers an empty list: that is could not look, not nothing done (X3).
    tasks.check_reachable()
    start = datetime.datetime.combine(since, datetime.time()).astimezone()
    months: dict[str, list[tuple[datetime.date, Task]]] = {}
    for task in tasks.completed_items(start):
        if task.completed_at is None or task.marker in CURATOR_MARKERS:
            continue
        day = task.completed_at.astimezone().date()
        if day < since:
            continue
        months.setdefault(_month_file(day), []).append((day, task))
    texts = {path: _read(store, path) for path in months}
    report = JournalReport()
    for path in sorted(months):
        text = texts[path] or _header(now)
        known = set(_DONE.findall(text))
        lines = []
        for day, task in sorted(months[path], key=lambda item: (item[0], item[1].completed_at, item[1].id)):
            key = (_key_id(task.id), day.isoformat())
            if key not in known:
                known.add(key)
                lines.append(f"- {day.isoformat()} {_safe(task.title)} <!-- m2b:done {key[0]} {day.isoformat()} -->\n")
        if not lines:
            continue
        separator = "" if not text or text.endswith("\n") else "\n"
        store.replace(path, (text + separator + "".join(lines)).encode("utf-8"))
        report.appended[path] = len(lines)
    return report


def _month_file(day: datetime.date) -> str:
    return f"{CORPUS}/{day:%Y}/{day:%m}/{journal_name(day.year, day.month)}"


def _read(store: Store, path: str) -> str | None:
    """The month file as text; None when it does not exist yet. An evicted file raises."""
    try:
        data = store.read_bytes(path)
    except FileNotFoundError:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise NoteFormatError(f"{path} is not UTF-8, so nothing is appended to it: {error}") from error


def _header(now: datetime.datetime) -> str:
    created = now.astimezone().isoformat(timespec="seconds")
    return f"---\n{keys.CREATED}: {created}\n{keys.SOURCE}: {SOURCE}\n{keys.KIND}: {keys.KIND_JOURNAL}\n---\n"


def _key_id(task_id: str) -> str:
    """The id as the key writes it: on one line, and unable to end the comment early."""
    return " ".join(task_id.split()).replace("-->", "--&gt;")


def _safe(title: str) -> str:
    """One line that cannot open a comment, so no title can hide the lines after it."""
    return " ".join(title.split()).replace("<!--", "&lt;!--") or "(no title)"
