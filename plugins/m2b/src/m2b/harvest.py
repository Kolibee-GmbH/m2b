"""Harvest, run step 1: what the person answered becomes captures, what they dropped is remembered.

Two things wait for an answer: a candidate, a task the person ticks or drops, and a proposal from
their sessions, answered with keep or drop (``proposal_answers``). Both are settled here.

The capture is written before the task is deleted, and a rerun recognizes its own earlier capture
by ``from_candidate``, so a crash between the two neither loses nor doubles a candidate (B34). A
task whose capture exists is deleted in whatever state it is: Apple Reminders reopens a completed
reminder to delete it, so a failed delete can leave it open. A candidate gone from the task list
counts as dropped, unless its capture exists: then the crash came after the delete.

A lesson the owner kept by hand (``kept_lessons``) is written into ``memory/lessons/`` here, in
code, before anything else: no model step may write there.

A kept proposal goes the same way: the capture first, marked ``from_proposal``, then the
proposals file, then the answer file. A commitment that names its day gets its follow-up task with
the capture; a project is the capture the owner's "keep this project" makes (``project_capture``),
a pointer a capture of its line with its repository;
any other proposal is a plain capture, and the filing decides what it becomes. Kept or
dropped, the proposal stays known to the proposals file, so the next reading does not bring it
back.

Only captures named with the source in question and named no earlier than the oldest candidate or
proposal still in question are opened; such a capture that is evicted or unreadable means harvest
cannot tell, so it captures nothing of that kind and drops no candidate this run and says why.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from m2b import candidates, fixes, kept_lessons, project_capture, project_proposals, proposal_answers, proposals
from m2b.capture import capture
from m2b.config.errors import ConfigError
from m2b.glean import COMMITMENT, FIX, POINTER, PROJECT, AtSource
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
    lessons: list[str] = field(default_factory=list)
    # Where the fixes kept from proposed lessons are for, as ``Fix.place`` names them.
    fixes: list[str] = field(default_factory=list)


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
    machine_id: str | None = None,
) -> HarvestReport:
    """Settles the candidates, then the answers to proposals.

    The answers hardly need the task list, so they are settled also when the candidates fail, for
    example over a task list that is out of reach. That failure stays the one raised; what stops
    the answers beside it is a problem in the report. A caller that hands in ``report`` has its
    problems also when this raises.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    report = report if report is not None else HarvestReport()
    # Lessons kept by hand need no task list, so they are filed first, whatever the candidates do.
    filed = kept_lessons.file_kept(store)
    report.lessons += filed.lessons
    report.problems += filed.problems
    try:
        _harvest_candidates(store, tasks, prefix, now, report)
    except Exception:
        try:
            _settle_proposals(store, tasks, now, report, machine_id)
        except Exception as error:
            report.problems.append(f"the answers to proposals were not settled ({error}); the next run settles them")
        raise
    _settle_proposals(store, tasks, now, report, machine_id)
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


def _settle_proposals(
    store: Store, tasks: Tasks, now: datetime.datetime, report: HarvestReport, machine_id: str | None = None
) -> None:
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
    current = kept
    to_keep = [
        key
        for key, answer in answers.items()
        if answer == proposal_answers.KEEP
        and key in current.entries
        and _takes(current.entries[key], answer)
        # A lesson writes no capture, so none is looked for.
        and current.entries[key].lesson is None
    ]
    since = min((current.entries[key].since for key in to_keep), default=None)
    earlier = _earlier(store, since - CLOCK_MARGIN if since else None, PROPOSAL_SOURCE, keys.FROM_PROPOSAL)
    report.problems += _uncertain(earlier, "proposal", "kept proposals")
    settled: list[str] = []
    lessons_kept = False
    try:
        for key, answer in sorted(answers.items()):
            entry = current.entries.get(key)
            if entry is None or not _takes(entry, answer):
                # Settled by an earlier run that could not remove the file, or never known: only the file goes.
                settled.append(key)
            elif answer == proposal_answers.DROP:
                current = proposals.settled(current, key, proposals.DROPPED, now)
                report.dropped.append(entry.text)
                settled.append(key)
            elif entry.lesson is not None:
                if _keep_lesson(store, entry, report, machine_id):
                    current = proposals.settled(current, key, proposals.KEPT, now)
                    settled.append(key)
                    lessons_kept = True
            elif key in earlier.ids or earlier.certain:
                if key not in earlier.ids:
                    _capture_proposal(store, tasks, key, entry, now, report)
                current = proposals.settled(current, key, proposals.KEPT, now)
                settled.append(key)
    finally:
        if current != kept:
            proposals.save(store, current)
    for key in settled:
        proposal_answers.remove(store, key)
    if lessons_kept:
        # Filed in this run too; a file the first filing could not take is named once.
        filed = kept_lessons.file_kept(store)
        report.lessons += filed.lessons
        report.problems += [problem for problem in filed.problems if problem not in report.problems]


def _pointer_to(at_source: AtSource) -> str:
    if at_source.path is None:
        return at_source.file
    return f"{at_source.path} in {', '.join(at_source.repositories)}" if at_source.repositories else at_source.path


def _keep_fix(
    store: Store, entry: proposals.Entry, at_source: AtSource, machine_id: str | None, report: HarvestReport
) -> bool:
    """Keeps a lesson that is a fix of its source as a fix (``fixes``), which a session applies where
    the file lies; one for a file under ``~/.claude/`` is this machine's, where the sessions were read."""
    lesson = entry.lesson
    assert lesson is not None
    why = f'you said "{entry.quote}" and again "{lesson.quote}"'
    try:
        fix = fixes.new_fix(
            at_source.path or "",
            at_source.repositories,
            machine_id,
            at_source.line,
            at_source.wording or "",
            " ".join(why.split()),
            entry.day.isoformat(),
        )
        is_new = fixes.keep(store, fix)
    except fixes.FixRefusedError as error:
        report.problems.append(f"the lesson you kept waits: {entry.text} ({error})")
        return False
    # The same fix kept before and done or dropped since stays so: a mark is never taken back.
    state = fixes.WAITING if is_new else fixes.find(store, fix.name).state
    if state == fixes.WAITING:
        report.fixes.append(fix.place)
    else:
        report.problems.append(
            f"the lesson you kept is a fix of {fix.place} you marked {state} before; it stays {state}"
        )
    return True


def _keep_lesson(store: Store, entry: proposals.Entry, report: HarvestReport, machine_id: str | None = None) -> bool:
    """Hands a kept lesson to the way a lesson kept by hand goes, in code (B261), never to a capture
    the filing model would read; False, with the reason for the review, where it cannot go there yet.

    Keeping is safe to repeat: the same lesson waiting or filed already is not added twice.
    """
    lesson = entry.lesson
    assert lesson is not None
    at_source = lesson.at_source
    if at_source is not None and at_source.verdict == FIX:
        return _keep_fix(store, entry, at_source, machine_id, report)
    # A lesson a source states already is kept as a pointer to it: it counts, and no second text comes
    # in. The file is named as a fix names it, the same on every machine; only one no session could
    # fix, outside a repository and ~/.claude/, keeps the name this machine reads it by.
    kept_at = None if at_source is None else _pointer_to(at_source)
    given = kept_lessons.KeptLesson(
        entry.text[:60], entry.text, lesson.kind, lesson.target, entry.day.isoformat(), lesson.words, kept_at=kept_at
    )
    try:
        kept_lessons.keep(store, given)
    except kept_lessons.LessonRefusedError as error:
        report.problems.append(f"the lesson you kept waits: {entry.text} ({error})")
        return False
    return True


def _takes(entry: proposals.Entry, answer: str) -> bool:
    """An open proposal takes either answer. An expired one can still be kept: it never had an
    answer, and a keep that reached the store late, from a machine that had not seen it expire,
    must not be lost. A drop of it changes nothing."""
    if entry.state == proposals.EXPIRED:
        return answer == proposal_answers.KEEP
    return entry.state == proposals.OPEN


def _capture_proposal(
    store: Store, tasks: Tasks, key: str, entry: proposals.Entry, now: datetime.datetime, report: HarvestReport
) -> None:
    """Writes the capture of a kept proposal; a task that could not be confirmed is a problem, the capture stands."""
    follow_up = entry.due if entry.kind == COMMITMENT else None
    # A project is captured as the owner's own "keep this project" is, so the filing makes it a topic;
    # a pointer names its repository, so the filing finds the topic by its ``Repository:`` line.
    if entry.kind == PROJECT:
        text = project_capture.capture_text(project_proposals.addresses_in(entry), "")
    elif entry.kind == POINTER and entry.pointer is not None:
        text = project_capture.pointer_capture_text(entry.pointer.repositories, entry.text)
    else:
        text = entry.text
    try:
        result = capture(store, text, PROPOSAL_SOURCE, follow_up=follow_up, tasks=tasks, now=now, from_proposal=key)
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
