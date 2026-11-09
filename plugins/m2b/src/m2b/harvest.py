"""Harvest, run step 1: ticked candidates become captures, dropped ones are remembered.

The capture is written before the task is deleted, and a rerun recognizes its own earlier capture
by ``from_candidate``, so a crash between the two neither loses nor doubles a candidate (B34). A
task whose capture exists is deleted in whatever state it is: Apple Reminders reopens a completed
reminder to delete it, so a failed delete can leave it open. A candidate gone from the task list
counts as dropped, unless its capture exists: then the crash came after the delete.

Only captures named with the source ``candidate`` and named no earlier than the oldest candidate
still in question are opened; such a capture that is evicted or unreadable means harvest cannot
tell, so it captures nothing and drops nothing this run and says why.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from m2b import candidates
from m2b.capture import capture
from m2b.notes import frontmatter as keys
from m2b.notes.frontmatter import Note, NoteFormatError
from m2b.notes.layout import CORPUS, INBOX
from m2b.notes.names import NoteName
from m2b.store.base import Store, StoreError
from m2b.tasks import markers
from m2b.tasks.base import Task, Tasks, TasksError

__all__ = ["HarvestReport", "TasksError", "harvest"]

SOURCE = "candidate"
# Proposal and harvest can run on different machines; their clocks may differ a little.
CLOCK_MARGIN = datetime.timedelta(days=1)
_EVER = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)


@dataclass
class HarvestReport:
    captured: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


@dataclass
class _Earlier:
    """What earlier harvests left: the candidate ids they captured, and what could not be checked."""

    ids: set[str] = field(default_factory=set)
    evicted: list[str] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)

    @property
    def certain(self) -> bool:
        return not self.evicted and not self.unreadable


def harvest(store: Store, tasks: Tasks, prefix: str, now: datetime.datetime | None = None) -> HarvestReport:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    report = HarvestReport()
    entries = candidates.load(store)
    items = tasks.items(marker=markers.CANDIDATE, include_completed=True)
    seen = {task.id for task in items}
    # A candidate the list leaves out because its task cannot be read is not gone; it waits.
    open_ids = [task_id for task_id, entry in entries.items() if entry.state == candidates.OPEN]
    gone = [task_id for task_id in open_ids if task_id not in seen] if tasks.lists_every_task() else []
    earlier = _earlier(store, _oldest(items, gone, entries))
    if earlier.evicted:
        report.problems.append(
            f"candidate captures not downloaded ({', '.join(earlier.evicted)}); "
            "ticked and vanished candidates wait for the next run"
        )
    if earlier.unreadable:
        report.problems.append(
            f"candidate captures cannot be read ({', '.join(earlier.unreadable)}); "
            "ticked and vanished candidates wait until they are fixed"
        )
    try:
        for task in items:
            _settle(store, tasks, task, entries, earlier, prefix, now, report)
        for task_id in gone:
            if task_id in earlier.ids:
                del entries[task_id]
            elif earlier.certain:
                entries[task_id] = candidates.Entry(entries[task_id].text, candidates.DROPPED, now)
                report.dropped.append(entries[task_id].text)
        for task_id, entry in list(entries.items()):
            if entry.state == candidates.DROPPED and now - entry.since >= candidates.REMEMBER_DROPPED:
                del entries[task_id]
    finally:
        candidates.save(store, entries)
    return report


def _settle(
    store: Store,
    tasks: Tasks,
    task: Task,
    entries: dict[str, candidates.Entry],
    earlier: _Earlier,
    prefix: str,
    now: datetime.datetime,
    report: HarvestReport,
) -> None:
    entry = entries.get(task.id)
    if task.id in earlier.ids:
        tasks.delete(task.id)
        entries.pop(task.id, None)
    elif task.dropped:
        text = entry.text if entry is not None else candidates.text_of(task, prefix)
        tasks.delete(task.id)
        entries[task.id] = candidates.Entry(text, candidates.DROPPED, now)
        report.dropped.append(text)
    elif task.completed:
        if not earlier.certain:
            return
        result = capture(store, candidates.text_of(task, prefix), SOURCE, from_candidate=task.id, now=now)
        report.captured.append(result.path)
        tasks.delete(task.id)
        entries.pop(task.id, None)
    elif (entry is None or entry.state != candidates.OPEN) and earlier.certain:
        # Proposed where the file did not hear of it, or marked dropped before its task synced here.
        # Only after a full check is now a safe age: before it, an unknown age makes every capture count.
        entries[task.id] = candidates.Entry(candidates.text_of(task, prefix), candidates.OPEN, now)


def _oldest(items: list[Task], gone: list[str], entries: dict[str, candidates.Entry]) -> datetime.datetime | None:
    """The earliest time a capture of a candidate in question can be named; None when none is in question.

    A capture is never named before its candidate was proposed. A candidate the file does not know
    could be of any age.
    """
    in_question = [task.id for task in items] + gone
    if not in_question:
        return None
    times = [entries[task_id].since if task_id in entries else _EVER for task_id in in_question]
    oldest = min(times)
    return oldest - CLOCK_MARGIN if oldest > _EVER + CLOCK_MARGIN else _EVER


def _earlier(store: Store, since: datetime.datetime | None) -> _Earlier:
    earlier = _Earlier()
    if since is None:
        return earlier
    for folder in (INBOX, CORPUS):
        scan = store.scan(folder)
        earlier.evicted += [relative for relative in scan.evicted if _may_hold_capture(relative, since)]
        for relative in scan.files:
            if not _is_capture_since(relative, since):
                continue
            try:
                frontmatter = Note.parse(store.read_text(relative)).frontmatter
            except (UnicodeDecodeError, NoteFormatError, StoreError):
                earlier.unreadable.append(relative)
                continue
            found = frontmatter.get(keys.FROM_CANDIDATE) if frontmatter is not None else None
            if found:
                earlier.ids.add(found)
    return earlier


def _is_capture_since(relative: str, since: datetime.datetime) -> bool:
    parsed = NoteName.parse(PurePosixPath(relative).name)
    return parsed is not None and parsed.source == SOURCE and relative.endswith(".md") and parsed.time >= since


def _may_hold_capture(relative: str, since: datetime.datetime) -> bool:
    """An evicted candidate capture new enough, or an evicted folder that could hold one."""
    name = PurePosixPath(relative).name
    if NoteName.parse(name) is not None:
        return _is_capture_since(relative, since)
    parts = PurePosixPath(relative).parts
    if parts[:1] == (CORPUS,) and len(parts) in (2, 3) and all(part.isdigit() for part in parts[1:]):
        year, month = int(parts[1]), int(parts[2]) if len(parts) == 3 else 12
        return (year, month) >= (since.year, since.month)
    return "." not in name
