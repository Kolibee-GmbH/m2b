"""What a curation run proposes from the person's sessions, kept in ``state/core/proposals.json``.

A run that reads the sessions (``curate.glean_step``) finds what may belong in the memory
although nobody said "remember this". Nothing of it is filed before the person said keep, so the
proposals wait here, each with the words it stands on and the day they were said. However many a
run finds, all are kept: the person answers them together, not one reminder at a time.

The person answers with keep or drop (``proposal_answers``), and the run's harvest settles the
answer here. The file also holds ``read_until``, the moment up to which the sessions were read,
``announced_until``, the newest addition the task for the waiting proposals has told the person of
(``proposals_task``), and each answered proposal for 90 days, so the same proposal does not come
back with the next reading: a dropped one because the person did not want it, a kept one because
its capture holds the proposal's text and not the person's words, so a second reading of the period
would not know it by the capture.

A proposal's id comes from its session and its quote alone. A run that reads a period a second
time, because the first reading failed after the model had answered, finds the same ids and adds
nothing. A proposal with the text of an open one, or of one answered within the 90 days, is refused
as well: the same fact said in two sessions is one proposal.

Only the curation run writes the file, as it does ``candidates.json``. A file a newer m2b wrote is
not read, so this one never writes over what it does not know.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from m2b.candidates import REMEMBER_DROPPED as REMEMBER_ANSWERED
from m2b.candidates import same_text
from m2b.config.json_file import read_store_json_object, write_store_json_object
from m2b.glean import KINDS, Proposal
from m2b.notes.layout import STATE
from m2b.store.base import Store

PROPOSALS_FILE = f"{STATE}/core/proposals.json"
FORMAT = 1
OPEN = "open"
KEPT = "kept"
DROPPED = "dropped"
STATES = (OPEN, KEPT, DROPPED)
ID_LENGTH = 12
_ID = re.compile(rf"[0-9a-f]{{{ID_LENGTH}}}")


class ProposalsError(Exception):
    """The proposals file is there and this m2b cannot use it."""


@dataclass(frozen=True)
class Entry:
    kind: str
    text: str
    # The person's own words the proposal stands on.
    quote: str
    # The day the person said them, where they are.
    day: datetime.date
    state: str
    # When the proposal was added, or when the run settled the person's answer to it.
    since: datetime.datetime
    topic: str | None = None
    due: datetime.date | None = None


@dataclass(frozen=True)
class Proposals:
    entries: Mapping[str, Entry]
    # Up to when the sessions were read; None before the first reading.
    read_until: datetime.datetime | None = None
    # When the newest proposal was added that the task for the waiting ones has told of; None before any.
    announced_until: datetime.datetime | None = None


@dataclass(frozen=True)
class Said:
    """A proposal a reading found, with the day its quote was said."""

    proposal: Proposal
    day: datetime.date


@dataclass(frozen=True)
class Added:
    proposals: Proposals
    added: int
    like_an_open_one: int
    like_a_kept_one: int
    like_a_dropped_one: int


def is_id(text: str) -> bool:
    """Whether the text has the form of an id: only then may it become a file name or be shown as one."""
    return _ID.fullmatch(text) is not None


def proposal_id(proposal: Proposal) -> str:
    """The same for the same quote of the same session, however its white space is written."""
    quoted = f"{proposal.session}\n{' '.join(proposal.quote.split())}"
    return hashlib.sha256(quoted.encode("utf-8", errors="replace")).hexdigest()[:ID_LENGTH]


def load(store: Store) -> Proposals:
    """What the store holds; an entry that is not in the form, or under a key that is no id, is left out."""
    raw = read_store_json_object(store, PROPOSALS_FILE)
    if raw is None:
        return Proposals({})
    written_as = raw.get("format")
    if isinstance(written_as, int) and not isinstance(written_as, bool) and written_as > FORMAT:
        raise ProposalsError(
            f"{PROPOSALS_FILE} has format {written_as} and this m2b knows {FORMAT}: update m2b on this machine"
        )
    given = raw.get("proposals")
    entries = {}
    for key, value in (given if isinstance(given, dict) else {}).items():
        entry = _entry(value)
        if entry is not None and is_id(str(key)):
            entries[str(key)] = entry
    return Proposals(entries, _moment(raw.get("read_until")), _moment(raw.get("announced_until")))


def save(store: Store, proposals: Proposals) -> None:
    write_store_json_object(
        store,
        PROPOSALS_FILE,
        {
            "format": FORMAT,
            "read_until": proposals.read_until.isoformat() if proposals.read_until else None,
            "announced_until": proposals.announced_until.isoformat() if proposals.announced_until else None,
            "proposals": {key: _as_json(entry) for key, entry in sorted(proposals.entries.items())},
        },
    )


def add(current: Proposals, found: Sequence[Said], now: datetime.datetime) -> Added:
    """``current`` with the proposals of ``found`` that are new, and how many were refused and why.

    A proposal kept or dropped 90 days ago or longer is forgotten here, so it may come again.
    """
    entries = {
        key: entry
        for key, entry in current.entries.items()
        if entry.state == OPEN or now - entry.since < REMEMBER_ANSWERED
    }
    counts = dict.fromkeys(STATES, 0)
    added = 0
    for said in found:
        key = proposal_id(said.proposal)
        known = entries.get(key) or next(
            (entry for entry in entries.values() if same_text(entry.text, said.proposal.text)), None
        )
        if known is not None:
            counts[known.state] += 1
            continue
        proposal = said.proposal
        entries[key] = Entry(
            proposal.kind, proposal.text, proposal.quote, said.day, OPEN, now, proposal.topic, proposal.due
        )
        added += 1
    kept = dataclasses.replace(current, entries=entries)
    return Added(kept, added, counts[OPEN], counts[KEPT], counts[DROPPED])


def _entry(value: object) -> Entry | None:
    if not isinstance(value, dict):
        return None
    kind, text, quote, state = (value.get(name) for name in ("kind", "text", "quote", "state"))
    topic = value.get("topic")
    since = _moment(value.get("since"))
    try:
        day = _day(value.get("day"))
        due = _day(value.get("due")) if value.get("due") is not None else None
    except ValueError:
        return None
    if kind not in KINDS or state not in STATES or since is None or day is None:
        return None
    if not isinstance(text, str) or not isinstance(quote, str) or not (topic is None or isinstance(topic, str)):
        return None
    if not all(_can_be_written(part) for part in (text, quote, topic or "")):
        return None
    return Entry(kind, text, quote, day, state, since, topic, due)


def _can_be_written(text: str) -> bool:
    """False for half a character (a lone surrogate), which an escape in the file can hold.

    No listing and no answer for the band could print it, and no capture could carry it: one such
    entry would otherwise end every command that reads the proposals.
    """
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _as_json(entry: Entry) -> dict[str, Any]:
    return {
        "kind": entry.kind,
        "text": entry.text,
        "quote": entry.quote,
        "topic": entry.topic,
        "due": entry.due.isoformat() if entry.due else None,
        "day": entry.day.isoformat(),
        "state": entry.state,
        "since": entry.since.isoformat(),
    }


def _day(value: object) -> datetime.date | None:
    """The day; None for no value, a ValueError for one that is no day."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(value)
    return datetime.date.fromisoformat(value)


def _moment(value: object) -> datetime.datetime | None:
    """The time, in UTC when it names no offset; None for anything that is no time."""
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=datetime.timezone.utc)
