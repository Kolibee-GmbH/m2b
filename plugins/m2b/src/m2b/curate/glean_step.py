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
absolute path cannot be compared with either and is left out too. The same setting names work by
its repository's git remotes: a session is left out when a remote noted for its folder at a
session start, or one git names there now, holds a part the profile names, and also when neither
says anything of the folder, since it is then not shown to be other work (``session_remotes``).

The model is asked once, with nothing to call (``model.text_step``), and only when a session left
has a prompt of the person's, typed or pasted. With the prompts it gets the distillate and what the
person kept and dropped of earlier proposals (``proposals.examples``); harvest has settled the
answers by then, so the last ones are among them. Code checks its answer (``glean.check``) against
the prompts and against the captures of the period, and ``proposals`` keeps what is new and counts,
per kind, what was added and what stood on no words of the person. The counts go to the run as
information, never into the review: nothing here asks the person to act. What the reader left out of
the sessions it read is among them, so a day's reading shows what it did not take.

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
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from m2b import claude_code, folders_left_out, glean, proposals, sessions
from m2b.config.machine import MachineConfig
from m2b.curate import model, period_captures
from m2b.notes.layout import MEMORY, MEMORY_INDEX
from m2b.paths import MachinePaths
from m2b.store.base import Store

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
    left_out = folders_left_out.rule(store, config, machine, environ, started)
    reasons = {session.session_id: left_out.reason(session.folder) for session in found.sessions}
    considered = [session for session in found.sessions if reasons[session.session_id] is None]
    read = [session for session in considered if session.prompts]
    notes += _left_out_notes(Counter(reason for reason in reasons.values() if reason is not None))
    if found.unreadable:
        notes.append(f"{_count(len(found.unreadable), 'transcript')} could not be read")
    notes += _left_out_of(considered)
    if not read:
        proposals.save(store, dataclasses.replace(kept, read_until=started))
        return Reading(f"no session since {start.strftime(_MOMENT)} has a prompt of yours", tuple(notes))
    captures = period_captures.captures_since(store, start, started)
    examples = proposals.examples(kept, started)
    if examples != glean.NO_EXAMPLES:
        notes.append(
            f"the model was shown {len(examples.kept)} kept and "
            f"{_count(len(examples.dropped), 'dropped proposal')} as examples"
        )
    pasted = sum(len(prompt.pasted) for session in read for prompt in session.prompts)
    if pasted:
        notes.append(f"{_count(pasted, 'pasted text')} {_were(pasted)} read with the prompts they stand in")
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
    sent = sum(len(session.prompts) for session in read)
    summary = (
        f"read {_count(len(read), 'session')} with {_count(sent, 'prompt')} since {start.strftime(_MOMENT)}: "
        f"{_count(added.added, 'proposal')} added, "
        f"{added.added_before} like one that waits, is answered or expired, "
        f"{len(checked.not_quoted)} without the person's words, "
        f"{len(checked.already_captured)} captured already, {answer.malformed} not in the form"
    )
    return Reading(None, (summary, *notes, *period_captures.capture_notes(captures)))


def _nothing_marked(found: Sequence[sessions.Session]) -> int:
    """How many texts have no mark of who sent them when nothing of the period has one, else 0.

    A text without the mark beside marked ones is a record the reader does not recognise, such as
    the output of a shell line that came in two blocks. When no prompt and nothing another
    sender sent shows the mark, the reader cannot tell what was typed; a slash
    command proves nothing, since it is taken by its form. The reading then fails at every run
    until the period holds a marked text or has moved past the unmarked ones.
    """
    marked = any(
        session.left_out.sent_by_others
        or session.left_out.suggested
        or any(prompt.pasted or not _COMMAND_NAME.fullmatch(prompt.text) for prompt in session.prompts)
        for session in found
    )
    return 0 if marked else sum(session.left_out.unmarked for session in found)


def _left_out_of(read: Sequence[sessions.Session]) -> list[str]:
    """What the reader left out of these sessions, as one note, or none when that is nothing."""
    others = sum(session.left_out.sent_by_others for session in read)
    suggested = sum(session.left_out.suggested for session in read)
    unmarked = sum(session.left_out.unmarked for session in read)
    counted = (
        (others, f"{_count(others, 'prompt')} that a plugin, a task or another agent sent"),
        (suggested, f"{_count(suggested, 'suggestion')} that {_were(suggested)} only accepted"),
        (
            unmarked,
            f"{_count(unmarked, 'text')} without Claude Code's mark of who sent {'it' if unmarked == 1 else 'them'}",
        ),
    )
    named = [text for number, text in counted if number]
    return [f"left out of these sessions: {', '.join(named)}"] if named else []


def _left_out_notes(reasons: Mapping[str, int]) -> list[str]:
    """How many sessions were not read for each reason: folder, repository, no known repository."""
    notes = []
    in_folder = reasons.get(folders_left_out.IN_A_FOLDER_LEFT_OUT, 0)
    of_repository = reasons.get(folders_left_out.OF_A_REPOSITORY_LEFT_OUT, 0)
    unknown = reasons.get(folders_left_out.OF_NO_KNOWN_REPOSITORY, 0)
    if in_folder:
        notes.append(f"{_count(in_folder, 'session')} in a folder that is left out {_were(in_folder)} not read")
    if of_repository:
        notes.append(
            f"{_count(of_repository, 'session')} of a repository that is left out {_were(of_repository)} not read"
        )
    if unknown:
        notes.append(
            f"{_count(unknown, 'session')} {_were(unknown)} not read, because no git remote is known for "
            f"{'its folder' if unknown == 1 else 'their folders'} "
            f"({'the folder is' if unknown == 1 else 'the folders are'} gone or git did not answer) "
            "and the profile leaves work out by git remote"
        )
    return notes


def _distillate(store: Store) -> str:
    try:
        return store.read_text(f"{MEMORY}/{MEMORY_INDEX}")
    except FileNotFoundError:
        return ""


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _were(number: int) -> str:
    return "was" if number == 1 else "were"
