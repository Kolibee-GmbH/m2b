"""What the person answers to a proposal: keep or drop, one empty file per answer.

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
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from m2b import proposals
from m2b.notes.layout import STATE
from m2b.proposals import Entry
from m2b.store.base import EvictedFileError, Store

FOLDER = f"{STATE}/core/proposal-answers"
KEEP = "keep"
DROP = "drop"
ANSWERS = (KEEP, DROP)

_FILE = re.compile(rf"([0-9a-f]{{{proposals.ID_LENGTH}}})\.({KEEP}|{DROP})")
# What a settled proposal was answered with.
_SETTLED = {proposals.KEPT: KEEP, proposals.DROPPED: DROP}


class UnknownProposalError(Exception):
    """An answer names a proposal the store does not hold."""


@dataclass(frozen=True)
class Waiting:
    """The open proposals without an answer, the earliest said first, and how many answers wait for a run."""

    proposals: tuple[tuple[str, Entry], ...]
    answered: int


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
        if answers.get(proposal_id) != KEEP:
            answers[proposal_id] = answer
    return answers


def waiting(store: Store) -> Waiting:
    answers = read(store)
    entries = proposals.load(store).entries
    still_open = {key: entry for key, entry in entries.items() if entry.state == proposals.OPEN}
    unanswered = [(key, entry) for key, entry in still_open.items() if key not in answers]
    unanswered.sort(key=lambda item: (item[1].day, item[0]))
    return Waiting(tuple(unanswered), len(still_open) - len(unanswered))


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


def remove(store: Store, proposal_id: str) -> None:
    """Removes the answer files of a proposal the run has settled; a file already gone is no error."""
    for answer in ANSWERS:
        with contextlib.suppress(FileNotFoundError):
            store.delete(file_name(proposal_id, answer))
