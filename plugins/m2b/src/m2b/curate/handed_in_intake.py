"""What sessions handed in becomes proposals that wait: the curation run's side of ``handed_in``.

A session hands a proposal in as one file (``handed_in``), checked against its transcript on the
machine it ran on. The run takes each file in, in every run, whether or not it reads the sessions
itself: the two ways do not depend on each other. Where it reads them, it takes in afterwards, so
of a fact both ways bring in one run the reading's proposal waits.

The run reads no transcript. The session may have run on another machine, and a second look for
the quote would hold for this machine's sessions only. So for such a proposal, where its words
stand is what the machine that handed it in found. What needs no transcript the run checks again
(``handed_in.read``), because the file reached it through the store like any other, and it sets
itself that a session proposed (``proposals.SESSION``): it took the file from this folder.

- A file that is not in the form is removed and counted, a copy a sync service made in a
  conflict among them. One a newer m2b wrote stays, and the run says to update m2b here.
- Of one session's files the ``handed_in.WAITING_PER_SESSION`` earliest are taken and the rest
  removed: calls at the same moment can pass the limit at the call, and the run holds it again.
- A proposal the person captured themselves since its day is not added: they asked for a note,
  and the agent handed the same fact in too.
- ``proposals.add`` refuses what is like a proposal that waits, was answered or expired, so a
  fact a session hands in and a reading proposes too waits once, and so does one that several
  sessions hand in.
- The proposals file is written before a file is removed. A run that stops between the two finds
  the file again and takes it for one that waits already.

A file that is not downloaded, or cannot be read, stays where it is and is counted in what the
run reports. So does one no commit holds, where the run commits: it came in after the run
began, or was not downloaded when the run committed what waited, and taken in now it would be
lost with a revert of the run. A symlink in the folder is never read and is named.
"""

from __future__ import annotations

import contextlib
import datetime
import os
from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import PurePosixPath

from m2b import glean, handed_in, proposals
from m2b.config.errors import ConfigError
from m2b.curate import period_captures
from m2b.store.base import Store, StoreError

# How far back captures are read for a proposal that names an early day: a file's day is its
# writer's word, and a run does not read years of the archive for it.
CAPTURES_BACK = datetime.timedelta(days=31)
# A proposal's file is a few hundred bytes; the call takes no more than this as its input.
LARGEST_FILE = 64 * 1024
# The machine that handed in and the one that curates can be in two zones and their clocks can
# differ: a day is taken a day wide, and a call may be that far ahead of this machine's time.
CLOCK_MARGIN = datetime.timedelta(days=1)


@dataclass(frozen=True)
class Intake:
    """What the run tells of it: ``notes`` for its information, ``problems`` for what needs the person."""

    notes: tuple[str, ...] = ()
    problems: tuple[str, ...] = ()


def take_in(store: Store, now: datetime.datetime, listed: Collection[str] | None = None) -> Intake:
    """Makes the handed-in files proposals that wait and removes them; a store without one is not written.

    ``listed`` are the handed-in paths a run that commits may take in, those a commit holds: a
    file that is not among them is left for the next run and counted.
    """
    scan = store.scan(handed_in.FOLDER)
    if handed_in.FOLDER in scan.evicted:
        return Intake(notes=("what sessions handed in is not downloaded and waits for the next run",))
    links = (
        (f"{_count(len(scan.symlinks), 'symlink')} in the folder of handed-in proposals: m2b follows none",)
        if scan.symlinks
        else ()
    )
    files = [path for path in sorted(scan.files) if listed is None or path in listed]
    later = len(scan.files) - len(files)
    waiting = (
        (f"{_count(later, 'handed-in proposal')} no commit holds yet, left for the next run, which commits first",)
        if later
        else ()
    )
    if not files and not scan.evicted:
        return Intake(notes=(*waiting, *links))
    try:
        current = proposals.load(store)
    except (StoreError, proposals.ProposalsError, ConfigError) as error:
        return Intake(problems=(f"what sessions handed in waits for the next run: {error}",))
    read: list[tuple[str, handed_in.HandedIn]] = []
    not_in_form: list[str] = []
    newer = unreadable = 0
    for path in files:
        # A file in a folder below is none this m2b wrote, whatever it is named, and neither is
        # one far larger than a proposal: neither is opened.
        if str(PurePosixPath(path).parent) != handed_in.FOLDER or _size(store, path) > LARGEST_FILE:
            not_in_form.append(path)
            continue
        try:
            text = store.read_text(path)
        except UnicodeDecodeError:
            not_in_form.append(path)
            continue
        except (OSError, StoreError):
            unreadable += 1
            continue
        try:
            proposal = handed_in.read(PurePosixPath(path).name, text)
            if proposal.at > now + CLOCK_MARGIN:
                raise handed_in.NotInFormError("its time")
            read.append((path, proposal))
        except handed_in.NewerFormatError:
            newer += 1
        except handed_in.NotInFormError:
            not_in_form.append(path)
    taken, beyond = _within_the_limit(read)
    zone = now.tzinfo or datetime.timezone.utc
    notes: list[str] = []
    captured = 0
    said = []
    if taken:
        earliest = min(proposal.day for _, proposal in taken)
        day_began = datetime.datetime.combine(earliest, datetime.time.min, zone) - CLOCK_MARGIN
        start = max(day_began, now - CAPTURES_BACK)
        captures = period_captures.captures_since(store, start, now)
        notes += period_captures.capture_notes(captures)
        for _, proposal in taken:
            if glean.captured_already((proposal.quote, proposal.text), captures.texts):
                captured += 1
                continue
            found = glean.Proposal(
                proposal.kind, proposal.text, proposal.quote, proposal.session, due=proposal.due, source=proposal.source
            )
            said.append(proposals.Said(found, proposal.day, proposal.tool, proposals.SESSION))
    added = proposals.add(current, said, now)
    if added.added:
        proposals.save(store, added.proposals)
    for path in (*(path for path, _ in taken), *not_in_form, *beyond):
        # Gone already means another run took it; one that cannot be removed is taken again and
        # found to wait already.
        with contextlib.suppress(OSError, StoreError):
            store.delete(path)
    summary = (
        f"took in what sessions handed in: {_count(added.added, 'proposal')} added, "
        f"{added.added_before} like one that waits, is answered or expired, {captured} captured already, "
        f"{len(not_in_form)} not in the form, {len(beyond)} beyond {handed_in.WAITING_PER_SESSION} of one session"
    )
    if taken or not_in_form or beyond:
        notes.insert(0, summary)
    if scan.evicted:
        notes.append(f"{_count(len(scan.evicted), 'handed-in proposal')} not downloaded, left for the next run")
    if unreadable:
        notes.append(f"{_count(unreadable, 'handed-in proposal')} could not be read, left for the next run")
    problems = (
        (f"{_count(newer, 'handed-in proposal')} written by a newer m2b {_wait(newer)}: update m2b on this machine",)
        if newer
        else ()
    )
    return Intake((*notes, *waiting, *links), problems)


def _within_the_limit(
    read: list[tuple[str, handed_in.HandedIn]],
) -> tuple[list[tuple[str, handed_in.HandedIn]], list[str]]:
    """Of each session the earliest ``WAITING_PER_SESSION`` by the time of the call, and the paths beyond."""
    taken: list[tuple[str, handed_in.HandedIn]] = []
    beyond: list[str] = []
    of_session: Counter[str] = Counter()
    for path, proposal in sorted(read, key=lambda item: (item[1].at, item[0])):
        if of_session[proposal.session] >= handed_in.WAITING_PER_SESSION:
            beyond.append(path)
            continue
        of_session[proposal.session] += 1
        taken.append((path, proposal))
    return taken, beyond


def _size(store: Store, path: str) -> int:
    """The file's size without opening it; one that cannot be looked at counts as small and is read, which says why."""
    try:
        return os.lstat(store.path(path)).st_size
    except OSError:
        return 0


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _wait(number: int) -> str:
    return "waits" if number == 1 else "wait"
