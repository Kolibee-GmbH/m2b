"""The curation step ``glean``: what the person typed since the last reading, and what a model proposes from it.

The step is in a run only while ``curation.read_sessions`` is true in the machine config: the
transcripts are this machine's, and reading them is the person's decision. It runs after harvest
and before ingest, so what the person captured themselves is in the inbox or the archive by then.

A reading covers the time from the last one's end (``read_until`` in ``proposals.json``) to the
run's start: the last ``FIRST_PERIOD`` at the first reading, never more than ``LONGEST_PERIOD``,
and what lies before that is named as not read. Sessions that started in or below a folder that is
left out do not reach the model: the folders the profile's ``worklog_leave_out`` names, compared
as written with no look at the disk, and those with ``m2b distillate off``. One list for "sessions
m2b never reads" cannot be forgotten in one of two places. A session whose folder is not an
absolute path cannot be compared with either and is left out too.

The model is asked once, with nothing to call (``model.text_step``), and only when a session left
has a typed prompt. With the prompts it gets the distillate and what the person kept and dropped of
earlier proposals (``proposals.examples``); harvest has settled the answers by then, so the last
ones are among them. Code checks its answer (``glean.check``) against the prompts and against the
captures of the period, and ``proposals`` keeps what is new and counts, per kind, what was added
and what stood on no words of the person. The counts go to the run as
information, never into the review: nothing here asks the person to act. What the reader left out
of the sessions it read is among them, so a day's reading shows what it did not take.

When anything fails, the transcripts that cannot be looked at, a model without an answer, an
answer that cannot be read, nothing is saved and ``read_until`` stays, so the next run reads the
period again. A period in which nothing carries Claude Code's mark of who sent it fails the same
way: the reader then gives no prompt at all, and that must not pass for a day on which nothing
was typed; ids that depend only on session and quote keep a second reading from doubling
anything. The runner reports the failure in the review and lets the run succeed: this step reads a
file format Claude Code does not promise, and its failure must not hold back the filing of the
inbox.
"""

from __future__ import annotations

import dataclasses
import datetime
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from m2b import claude_code, glean, proposals, sessions
from m2b.config.machine import MachineConfig
from m2b.config.profile import require_profile
from m2b.curate import model
from m2b.ingest import TEXT_EXTENSIONS
from m2b.notes.frontmatter import Note
from m2b.notes.layout import CORPUS, INBOX, MEMORY, MEMORY_INDEX
from m2b.notes.names import NoteName
from m2b.paths import MachinePaths
from m2b.store.base import Store, StoreError

FIRST_PERIOD = datetime.timedelta(hours=24)
LONGEST_PERIOD = datetime.timedelta(days=7)

_MOMENT = "%Y-%m-%d %H:%M"
# A slash command as the reader gives it: only its name.
_COMMAND_NAME = re.compile(r"/\S+")


class GleanStepError(Exception):
    """The model gave no answer; the text says why."""


@dataclass(frozen=True)
class Reading:
    """How a reading ended: why no model was asked, or None when one was, and what the run reports of it."""

    skipped: str | None
    notes: tuple[str, ...]


@dataclass(frozen=True)
class _Captures:
    """The texts captured in a period, and how many of its captures could not be read."""

    texts: tuple[str, ...]
    not_downloaded: int
    unreadable: int


def propose(
    store: Store,
    config: MachineConfig,
    machine: MachinePaths,
    environ: Mapping[str, str],
    started: datetime.datetime,
    pass_fds: Sequence[int] = (),
) -> Reading:
    """Reads the sessions up to ``started``, the run's start, and keeps what is proposed from them."""
    kept = proposals.load(store)
    zone = started.tzinfo or datetime.timezone.utc
    earliest = started - LONGEST_PERIOD
    start = (kept.read_until or started - FIRST_PERIOD).astimezone(zone)
    if start >= started:
        return Reading(f"the sessions are read up to {start.strftime(_MOMENT)}", ())
    notes: list[str] = []
    if start < earliest:
        start = earliest
        notes.append(
            f"what was typed before {start.strftime(_MOMENT)} was not read: "
            f"a reading goes back {LONGEST_PERIOD.days} days at most"
        )
    found = sessions.read_sessions(claude_code.transcripts_folder(environ), start, started)
    without_mark = _nothing_marked(found.sessions)
    if without_mark:
        raise GleanStepError(
            f"nothing typed since {start.strftime(_MOMENT)} carries Claude Code's mark of who sent it, "
            f"{_count(without_mark, 'text')} {'is' if without_mark == 1 else 'are'} without it: "
            "Claude Code may write its transcripts in a way this m2b does not read"
        )
    is_left_out = _folders_left_out(store, config, machine.home)
    considered = [session for session in found.sessions if not is_left_out(session.folder)]
    left_out = len(found.sessions) - len(considered)
    read = [session for session in considered if session.prompts]
    if left_out:
        notes.append(f"{_count(left_out, 'session')} in a folder that is left out {_were(left_out)} not read")
    if found.unreadable:
        notes.append(f"{_count(len(found.unreadable), 'transcript')} could not be read")
    notes += _left_out_of(considered)
    if not read:
        proposals.save(store, dataclasses.replace(kept, read_until=started))
        return Reading(f"no session since {start.strftime(_MOMENT)} has a typed prompt", tuple(notes))
    captures = _captures(store, start, started)
    examples = proposals.examples(kept, started)
    if examples != glean.NO_EXAMPLES:
        notes.append(
            f"the model was shown {len(examples.kept)} kept and "
            f"{_count(len(examples.dropped), 'dropped proposal')} as examples"
        )
    given = glean.step_input(read, _distillate(store), zone, examples)
    run = model.text_step(config, machine, environ, glean.instruction(), given, pass_fds)
    if run.answer is None:
        raise GleanStepError(run.failure())
    answer = glean.parse_answer(run.answer, read)
    checked = glean.check(answer.proposals, read, captures.texts)
    said = [
        proposals.Said(proposal, typed_at.astimezone(zone).date())
        for proposal, typed_at in zip(checked.kept, checked.kept_at)
    ]
    added = proposals.add(kept, said, started)
    counted = added.proposals
    for refused in checked.not_quoted:
        counted = proposals.counted(counted, refused.kind, "not_quoted")
    proposals.save(store, dataclasses.replace(counted, read_until=started))
    typed = sum(len(session.prompts) for session in read)
    summary = (
        f"read {_count(len(read), 'session')} with {_count(typed, 'typed prompt')} since {start.strftime(_MOMENT)}: "
        f"{_count(added.added, 'proposal')} added, "
        f"{added.added_before} like one that waits, is answered or expired, "
        f"{len(checked.not_quoted)} without the person's words, "
        f"{len(checked.already_captured)} captured already, {answer.malformed} not in the form"
    )
    return Reading(None, (summary, *notes, *_capture_notes(captures)))


def _nothing_marked(found: Sequence[sessions.Session]) -> int:
    """How many texts have no mark of who sent them when nothing of the period has one, else 0.

    A text without the mark beside marked ones is a record the reader does not recognise, such as
    the output of a shell line that came in two blocks. When no prompt, no pasted block and
    nothing another sender sent shows the mark, the reader cannot tell what was typed; a slash
    command proves nothing, since it is taken by its form. The reading then fails at every run
    until the period holds a marked text or has moved past the unmarked ones.
    """
    marked = any(
        session.left_out.sent_by_others
        or session.left_out.suggested
        or session.left_out.pasted_blocks
        or any(not _COMMAND_NAME.fullmatch(prompt.text) for prompt in session.prompts)
        for session in found
    )
    return 0 if marked else sum(session.left_out.unmarked for session in found)


def _left_out_of(read: Sequence[sessions.Session]) -> list[str]:
    """What the reader left out of these sessions, as one note, or none when that is nothing."""
    others = sum(session.left_out.sent_by_others for session in read)
    suggested = sum(session.left_out.suggested for session in read)
    pasted = sum(session.left_out.pasted_blocks for session in read)
    unmarked = sum(session.left_out.unmarked for session in read)
    counted = (
        (others, f"{_count(others, 'prompt')} that a plugin, a task or another agent sent"),
        (suggested, f"{_count(suggested, 'suggestion')} that {_were(suggested)} only accepted"),
        (pasted, _count(pasted, "pasted block")),
        (
            unmarked,
            f"{_count(unmarked, 'text')} without Claude Code's mark of who sent {'it' if unmarked == 1 else 'them'}",
        ),
    )
    named = [text for number, text in counted if number]
    return [f"left out of these sessions: {', '.join(named)}"] if named else []


def _folders_left_out(store: Store, config: MachineConfig, home: Path) -> Callable[[str], bool]:
    named = require_profile(store).worklog_leave_out.folders(home)

    def is_left_out(folder: str) -> bool:
        path = Path(folder)
        # A folder that cannot be compared with the list is not shown to be outside it.
        if not path.is_absolute() or any(path == root or root in path.parents for root in named):
            return True
        return config.distillate.covering(path) is not None

    return is_left_out


def _distillate(store: Store) -> str:
    try:
        return store.read_text(f"{MEMORY}/{MEMORY_INDEX}")
    except FileNotFoundError:
        return ""


def _captures(store: Store, start: datetime.datetime, end: datetime.datetime) -> _Captures:
    """What was captured since ``start``, from the inbox and the archive, by the time in each name.

    A capture that is not downloaded is counted and not read (a read would download it or hang),
    and so is a folder that is not: what it holds cannot be listed. A text file the person dropped
    into the inbox under a name of its own is a capture too: ingest names it only after this step.
    """
    texts: list[str] = []
    not_downloaded = unreadable = 0
    for folder in (INBOX, *_month_folders(start, end)):
        scan = store.scan(folder)
        dropped = folder == INBOX
        not_downloaded += sum(1 for path in scan.evicted if _may_be_of_the_period(path, start, dropped))
        for path in scan.files:
            if not _is_capture_since(path, start, dropped):
                continue
            try:
                texts.append(Note.parse(store.read_text(path)).body)
            except (OSError, StoreError, UnicodeDecodeError):
                unreadable += 1
    return _Captures(tuple(texts), not_downloaded, unreadable)


def _month_folders(start: datetime.datetime, end: datetime.datetime) -> Iterator[str]:
    """The archive's folders for the months of the period; a capture is filed by its name's UTC time."""
    month = start.astimezone(datetime.timezone.utc).date().replace(day=1)
    last = end.astimezone(datetime.timezone.utc).date()
    while month <= last:
        yield f"{CORPUS}/{month:%Y}/{month:%m}"
        month = (month + datetime.timedelta(days=32)).replace(day=1)


def _is_capture_since(path: str, start: datetime.datetime, dropped: bool) -> bool:
    """A capture by its name and the time in it; with ``dropped`` also a text file under any other name."""
    name = NoteName.parse(PurePosixPath(path).name)
    if name is not None:
        return name.extension == "md" and name.time >= start
    return dropped and PurePosixPath(path).suffix.lower() in TEXT_EXTENSIONS


def _may_be_of_the_period(evicted: str, start: datetime.datetime, dropped: bool) -> bool:
    """A capture of the period by its name, or a folder, which may hold one."""
    return _is_capture_since(evicted, start, dropped) or not PurePosixPath(evicted).suffix


def _capture_notes(captures: _Captures) -> list[str]:
    notes = []
    if captures.not_downloaded:
        one = captures.not_downloaded == 1
        notes.append(
            f"{_count(captures.not_downloaded, 'capture')} of the period {'is' if one else 'are'} not downloaded, "
            f"so a proposal may repeat {'it' if one else 'one'}"
        )
    if captures.unreadable:
        one = captures.unreadable == 1
        notes.append(
            f"{_count(captures.unreadable, 'capture')} of the period could not be read, "
            f"so a proposal may repeat {'it' if one else 'one'}"
        )
    return notes


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _were(number: int) -> str:
    return "was" if number == 1 else "were"
