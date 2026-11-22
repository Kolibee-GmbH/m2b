"""What the person answers to a proposal: keep, keep for every project or drop, one empty file per answer.

A client only adds to the store, and the proposals file is the curation run's. So an answer is a
new file beside it, ``state/core/proposal-answers/<id>.keep`` or ``<id>.drop``, created
exclusively: the command line and the band answer the same way, on any machine, and none of them
writes over what another one or the run wrote. The run's harvest settles the answers and removes
the files.

An answer is its file's name; the file is empty and never opened, so one that is not downloaded
still counts. An answers folder that is not downloaded cannot be listed, and then nobody can say
what is answered: that raises, it never reads as "no answer yet". Where a keep and a drop for the
same proposal meet, from two machines that did not see each other, keep stands: a fact kept by
mistake can be removed, one dropped by mistake is gone.

A lesson proposed for one project can be kept for every project, ``<id>.every-project``: a reading
sees one correction in one repository and cannot tell that the person makes it wherever they work,
the person can. It is a keep, and the widest answer: it stands where it meets a keep or a drop from
another machine. A run removes only the answer it settled and those below it, so one wider that
came in meanwhile is still there for the next run to say.

A proposal nobody answered for 14 days expires (``expire``, in every curation run) and waits no
longer. It has no answer, so a keep by its id is still taken while the store remembers it.
"""

from __future__ import annotations

import contextlib
import datetime
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from m2b import lessons, proposals
from m2b.notes.layout import STATE
from m2b.proposals import Entry
from m2b.store.base import EvictedFileError, Store

FOLDER = f"{STATE}/core/proposal-answers"
KEEP = "keep"
EVERY_PROJECT = "every-project"
DROP = "drop"
ANSWERS = (KEEP, EVERY_PROJECT, DROP)
# The answers that keep a proposal.
KEEPS = (KEEP, EVERY_PROJECT)
# Where two answers for one proposal meet, the one that comes first here stands.
_RANK = (EVERY_PROJECT, KEEP, DROP)

_FILE = re.compile(rf"([0-9a-f]{{{proposals.ID_LENGTH}}})\.({KEEP}|{EVERY_PROJECT}|{DROP})")
# What a settled proposal was answered with.
_SETTLED = {proposals.KEPT: KEEP, proposals.DROPPED: DROP}


class UnknownProposalError(Exception):
    """An answer names a proposal the store does not hold."""


class NotForOneProjectError(Exception):
    """Keep for every project names a proposal that is no lesson for one project."""


@dataclass(frozen=True)
class Waiting:
    """The open proposals without an answer, the earliest said first, and how many answers wait for a run.

    A keep for an expired proposal is such an answer; a drop of one is not, since the run does nothing with it.
    ``kept`` are the keeps among them: what the run files, where a drop changes nothing a session sees.
    """

    proposals: tuple[tuple[str, Entry], ...]
    answered: int
    kept: int = 0


@dataclass(frozen=True)
class Given:
    """The proposals that got the answer now, and those that had one: the answer that stands, per id."""

    given: tuple[str, ...]
    already: Mapping[str, str]


def file_name(proposal_id: str, answer: str) -> str:
    return f"{FOLDER}/{proposal_id}.{answer}"


def read(store: Store) -> dict[str, str]:
    """The answer per proposal id, from the names of the files alone."""
    scan = store.scan(FOLDER)
    if FOLDER in scan.evicted:
        raise EvictedFileError(FOLDER)
    answers: dict[str, str] = {}
    for path in (*scan.files, *scan.evicted):
        name = PurePosixPath(path)
        named = _FILE.fullmatch(name.name)
        if named is None or str(name.parent) != FOLDER:
            continue
        proposal_id, answer = named.groups()
        standing = answers.get(proposal_id)
        if standing is None or _RANK.index(answer) < _RANK.index(standing):
            answers[proposal_id] = answer
    return answers


def waiting(store: Store) -> Waiting:
    answers = read(store)
    entries = proposals.load(store).entries
    unanswered = [
        (key, entry) for key, entry in entries.items() if entry.state == proposals.OPEN and key not in answers
    ]
    unanswered.sort(key=lambda item: (item[1].day, item[0]))
    awaiting = awaiting_a_run(entries, answers)
    return Waiting(tuple(unanswered), len(awaiting), sum(answers[key] in KEEPS for key in awaiting))


def awaiting_a_run(entries: Mapping[str, Entry], answers: Mapping[str, str]) -> frozenset[str]:
    """The ids whose answer the next run settles: an open proposal with an answer, and an expired
    one with a keep. A drop of an expired one is not among them, since the run does nothing with it."""
    return frozenset(
        key
        for key, entry in entries.items()
        if (entry.state == proposals.OPEN and key in answers)
        or (entry.state == proposals.EXPIRED and answers.get(key) in KEEPS)
    )


def expire(store: Store, now: datetime.datetime) -> proposals.Aged:
    """Lets time pass for the proposals (``proposals.aged``) and says how many expired and were forgotten.

    The answers are looked at first: when they cannot be, this raises and no proposal expires.
    A store in which nothing is due is not written.
    """
    answers = read(store)
    aged = proposals.aged(proposals.load(store), answers.keys(), now)
    if aged.expired or aged.forgotten:
        proposals.save(store, aged.proposals)
    return aged


def give(store: Store, proposal_ids: Sequence[str], answer: str) -> Given:
    """Adds the answer for each proposal that has none; one unknown id and nothing is written."""
    entries = proposals.load(store).entries
    # A key of the proposals file that is no id is no entry, so what is known here is safe as a file name.
    unknown = [key for key in proposal_ids if key not in entries]
    if unknown:
        raise UnknownProposalError(
            f"no proposal has the id {', '.join(unknown)}; m2b proposals lists those that wait"
            if len(unknown) == 1
            else f"no proposals have the ids {', '.join(unknown)}; m2b proposals lists those that wait"
        )
    if answer == EVERY_PROJECT:
        _require_for_one_project(entries, proposal_ids)
    answers = read(store)
    given: list[str] = []
    already: dict[str, str] = {}
    for key in dict.fromkeys(proposal_ids):
        stands = answers.get(key) or _SETTLED.get(entries[key].state)
        if stands is None:
            try:
                store.create_exclusive(file_name(key, answer), b"")
            except FileExistsError:
                # Another client gave the same answer between the look and the write.
                stands = answer
        if stands is None:
            given.append(key)
        else:
            already[key] = stands
    return Given(tuple(given), already)


def _require_for_one_project(entries: Mapping[str, Entry], proposal_ids: Sequence[str]) -> None:
    others = [key for key in proposal_ids if not for_one_project(entries[key])]
    if others:
        raise NotForOneProjectError(
            f"only a lesson for one project can be kept for every project, not {', '.join(others)}; keep it with: "
            "m2b proposals keep <id>"
        )


def for_one_project(entry: Entry) -> bool:
    """Whether the proposal is a lesson for one project, which can be kept for every project."""
    return entry.lesson is not None and entry.lesson.target != lessons.EVERY_PROJECT


def remove(store: Store, proposal_id: str, settled: str = EVERY_PROJECT) -> None:
    """Removes the answer files of a proposal the run has settled with ``settled``, and those of answers
    below it; a file already gone is no error. A wider answer than the one the run read came in
    after it read them, so it stays."""
    for answer in _RANK[_RANK.index(settled) :]:
        with contextlib.suppress(FileNotFoundError):
            store.delete(file_name(proposal_id, answer))
