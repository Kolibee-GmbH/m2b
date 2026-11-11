"""Harvest, run step 1: what the person answered becomes captures, what they dropped is remembered.

Two things wait for an answer: a candidate, a task the person ticks or drops, and a proposal from
their sessions, answered with keep or drop (``proposal_answers``). Both are settled here.

The capture is written before the task is deleted, and a rerun recognizes its own earlier capture
by ``from_candidate``, so a crash between the two neither loses nor doubles a candidate (B34). A
task whose capture exists is deleted in whatever state it is: Apple Reminders reopens a completed
reminder to delete it, so a failed delete can leave it open. A candidate gone from the task list
counts as dropped, unless its capture exists: then the crash came after the delete.

A kept proposal goes the same way: the capture first, marked ``from_proposal``, then the
proposals file, then the answer file. A commitment that names its day gets its follow-up task with
the capture; any other proposal is a plain capture, and the filing decides what it becomes. Kept or
dropped, the proposal stays known to the proposals file, so the next reading does not bring it
back.

Only captures named with the source in question and named no earlier than the oldest candidate or
proposal still in question are opened; such a capture that is evicted or unreadable means harvest
cannot tell, so it captures nothing of that kind and drops no candidate this run and says why.
"""

from __future__ import annotations

import dataclasses
import datetime
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from m2b import candidates, proposal_answers, proposals
from m2b.capture import capture
from m2b.config.errors import ConfigError
from m2b.glean import COMMITMENT
from m2b.notes import frontmatter as keys
from m2b.notes.frontmatter import Note, NoteFormatError
from m2b.notes.layout import CORPUS, INBOX
from m2b.notes.names import NoteName
from m2b.store.base import Store, StoreError
from m2b.tasks import markers
from m2b.tasks.base import Task, Tasks, TasksError, UnconfirmedTaskError

__all__ = ["HarvestReport", "TasksError", "harvest"]

SOURCE = "candidate"
PROPOSAL_SOURCE = "proposal"
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
    """What earlier harvests left: the ids they captured, and what could not be checked."""

    ids: set[str] = field(default_factory=set)
    evicted: list[str] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)

    @property
    def certain(self) -> bool:
        return not self.evicted and not self.unreadable


def harvest(
    store: Store,
    tasks: Tasks,
    prefix: str,
    now: datetime.datetime | None = None,
    report: HarvestReport | None = None,
) -> HarvestReport:
    """Settles the candidates, then the answers to proposals.

    The answers hardly need the task list, so they are settled also when the candidates fail, for
    example over a task list that is out of reach. That failure stays the one raised; what stops
    the answers beside it is a problem in the report. A caller that hands in ``report`` has its
    problems also when this raises.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    report = report if report is not None else HarvestReport()
    try:
        _harvest_candidates(store, tasks, prefix, now, report)
    except Exception:
        try:
            _settle_proposals(store, tasks, now, report)
        except Exception as error:
            report.problems.append(f"the answers to proposals were not settled ({error}); the next run settles them")
        raise
    _settle_proposals(store, tasks, now, report)
    return report


def _harvest_candidates(store: Store, tasks: Tasks, prefix: str, now: datetime.datetime, report: HarvestReport) -> None:
    entries = candidates.load(store)
    items = tasks.items(marker=markers.CANDIDATE, include_completed=True)
    seen = {task.id for task in items}
    # A candidate the list leaves out because its task cannot be read is not gone; it waits.
    open_ids = [task_id for task_id, entry in entries.items() if entry.state == candidates.OPEN]
    gone = [task_id for task_id in open_ids if task_id not in seen] if tasks.lists_every_task() else []
    earlier = _earlier(store, _oldest(items, gone, entries), SOURCE, keys.FROM_CANDIDATE)
    report.problems += _uncertain(earlier, "candidate", "ticked and vanished candidates")
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


def _settle_proposals(store: Store, tasks: Tasks, now: datetime.datetime, report: HarvestReport) -> None:
    """Settles the answers to proposals; what stops it is a problem for the review, and the answers wait."""
    try:
        answers = proposal_answers.read(store)
        # Without an answer nothing is in question, and the proposals file is not even read.
        kept = proposals.load(store) if answers else None
    except (StoreError, proposals.ProposalsError, ConfigError) as error:
        report.problems.append(f"the answers to proposals wait for the next run: {error}")
        return
    if kept is None:
        return
    entries = dict(kept.entries)
    to_keep = [
        key
        for key, answer in answers.items()
        if answer == proposal_answers.KEEP and key in entries and entries[key].state == proposals.OPEN
    ]
    since = min((entries[key].since for key in to_keep), default=None)
    earlier = _earlier(store, since - CLOCK_MARGIN if since else None, PROPOSAL_SOURCE, keys.FROM_PROPOSAL)
    report.problems += _uncertain(earlier, "proposal", "kept proposals")
    settled: list[str] = []
    try:
        for key, answer in sorted(answers.items()):
            entry = entries.get(key)
            if entry is None or entry.state != proposals.OPEN:
                # Settled by an earlier run that could not remove the file, or never known: only the file goes.
                settled.append(key)
            elif answer == proposal_answers.DROP:
                entries[key] = dataclasses.replace(entry, state=proposals.DROPPED, since=now)
                report.dropped.append(entry.text)
                settled.append(key)
            elif key in earlier.ids or earlier.certain:
                if key not in earlier.ids:
                    _capture_proposal(store, tasks, key, entry, now, report)
                entries[key] = dataclasses.replace(entry, state=proposals.KEPT, since=now)
                settled.append(key)
    finally:
        if entries != kept.entries:
            proposals.save(store, dataclasses.replace(kept, entries=entries))
    for key in settled:
        proposal_answers.remove(store, key)


def _capture_proposal(
    store: Store, tasks: Tasks, key: str, entry: proposals.Entry, now: datetime.datetime, report: HarvestReport
) -> None:
    """Writes the capture of a kept proposal; a task that could not be confirmed is a problem, the capture stands."""
    follow_up = entry.due if entry.kind == COMMITMENT else None
    try:
        result = capture(
            store, entry.text, PROPOSAL_SOURCE, follow_up=follow_up, tasks=tasks, now=now, from_proposal=key
        )
    except UnconfirmedTaskError as error:
        report.problems.append(str(error))
        return
    report.captured.append(result.path)
    if result.notice:
        report.problems.append(f"{result.path}: {result.notice}")


def _uncertain(earlier: _Earlier, what: str, waiting: str) -> list[str]:
    """Why harvest cannot tell which captures of this kind it wrote before, for the review."""
    problems = []
    if earlier.evicted:
        problems.append(
            f"{what} captures not downloaded ({', '.join(earlier.evicted)}); {waiting} wait for the next run"
        )
    if earlier.unreadable:
        problems.append(
            f"{what} captures cannot be read ({', '.join(earlier.unreadable)}); {waiting} wait until they are fixed"
        )
    return problems


def _earlier(store: Store, since: datetime.datetime | None, source: str, key: str) -> _Earlier:
    """The ids under ``key`` in the captures of ``source`` named since then; nothing is read for no time."""
    earlier = _Earlier()
    if since is None:
        return earlier
    for folder in (INBOX, CORPUS):
        scan = store.scan(folder)
        earlier.evicted += [relative for relative in scan.evicted if _may_hold_capture(relative, since, source)]
        for relative in scan.files:
            if not _is_capture_since(relative, since, source):
                continue
            try:
                frontmatter = Note.parse(store.read_text(relative)).frontmatter
            except (UnicodeDecodeError, NoteFormatError, StoreError):
                earlier.unreadable.append(relative)
                continue
            found = frontmatter.get(key) if frontmatter is not None else None
            if found:
                earlier.ids.add(found)
    return earlier


def _is_capture_since(relative: str, since: datetime.datetime, source: str) -> bool:
    parsed = NoteName.parse(PurePosixPath(relative).name)
    return parsed is not None and parsed.source == source and relative.endswith(".md") and parsed.time >= since


def _may_hold_capture(relative: str, since: datetime.datetime, source: str) -> bool:
    """An evicted capture of the source new enough, or an evicted folder that could hold one."""
    name = PurePosixPath(relative).name
    if NoteName.parse(name) is not None:
        return _is_capture_since(relative, since, source)
    parts = PurePosixPath(relative).parts
    if parts[:1] == (CORPUS,) and len(parts) in (2, 3) and all(part.isdigit() for part in parts[1:]):
        year, month = int(parts[1]), int(parts[2]) if len(parts) == 3 else 12
        return (year, month) >= (since.year, since.month)
    return "." not in name
