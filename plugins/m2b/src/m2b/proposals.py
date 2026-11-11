"""What a curation run proposes from the person's sessions, kept in ``state/core/proposals.json``.

A run that reads the sessions (``curate.glean_step``) finds what may belong in the memory
although nobody said "remember this". Nothing of it is filed before the person said keep, so the
proposals wait here, each with the words it stands on and the day they were said. However many a
run finds, all are kept: the person answers them together, not one reminder at a time.

The person answers with keep or drop (``proposal_answers``), and the run's harvest settles the
answer here. A proposal that got no answer for 14 days expires: a list that only grows is one
nobody opens, and no answer is not a drop. While it is remembered it can still be kept by its id,
since nothing is lost by a late keep. The file also holds ``read_until``, the moment up to
which the sessions were read, ``announced_until``, the newest addition the task for the waiting
proposals has told the person of (``proposals_task``), and each settled proposal for 90 days, so
the same proposal does not come back with the next reading: a dropped one because the person did
not want it, an expired one because they did not look at it, a kept one because its capture holds
the proposal's text and not the person's words, so a second reading of the period would not know
it by the capture.

``counts`` says per kind how many proposals were added and how each ended, and how many the quote
check refused. The counts outlast the proposals: they are what shows whether a kind is worth
proposing to this person. What was kept and dropped lately is read from the
settled proposals themselves (``outcomes_since``), which carry the moment.

The kept and the dropped proposals are also what the next reading shows the model (``examples``),
so it proposes what this person keeps. An expired one is not shown: the person did not look at it,
and that says nothing about the proposal.

A proposal's id comes from its session and its quote alone. A run that reads a period a second
time, because the first reading failed after the model had answered, finds the same ids and adds
nothing. A proposal with the text of an open one, or of one settled within the 90 days, is refused
as well: the same fact said in two sessions is one proposal.

Only the curation run writes the file, as it does ``candidates.json``. A file a newer m2b wrote is
not read, so this one never writes over what it does not know.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from m2b.candidates import REMEMBER_DROPPED as REMEMBER_SETTLED
from m2b.candidates import same_text
from m2b.config.json_file import read_store_json_object, write_store_json_object
from m2b.glean import KINDS, Example, Examples, Proposal
from m2b.notes.layout import STATE
from m2b.store.base import Store

PROPOSALS_FILE = f"{STATE}/core/proposals.json"
FORMAT = 1
OPEN = "open"
KEPT = "kept"
DROPPED = "dropped"
EXPIRED = "expired"
STATES = (OPEN, KEPT, DROPPED, EXPIRED)
EXPIRES_AFTER = datetime.timedelta(days=14)
# Shorter than a settled proposal is remembered, so the settled proposals alone give the rate.
KEEP_RATE_PERIOD = datetime.timedelta(days=30)
# How many kept and how many dropped proposals a reading shows the model. Chosen, not derived:
# enough to show a line the person draws, and a part of the input that stays small beside a day's prompts.
EXAMPLES_OF_EACH = 30
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
class Tally:
    """How many proposals of one kind were added, how they ended, and how many the quote check refused."""

    proposed: int = 0
    kept: int = 0
    dropped: int = 0
    expired: int = 0
    # Refused by the quote check (``glean.check``); never added, so not in ``proposed``.
    not_quoted: int = 0


@dataclass(frozen=True)
class Proposals:
    entries: Mapping[str, Entry]
    # Up to when the sessions were read; None before the first reading.
    read_until: datetime.datetime | None = None
    # When the newest proposal was added that the task for the waiting ones has told of; None before any.
    announced_until: datetime.datetime | None = None
    # Per kind, only the kinds with something counted.
    counts: Mapping[str, Tally] = dataclasses.field(default_factory=dict)

    def tally(self, kind: str) -> Tally:
        return self.counts.get(kind, Tally())


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
    like_an_expired_one: int

    @property
    def added_before(self) -> int:
        """How many were refused because the store holds them already, in whichever state."""
        return self.like_an_open_one + self.like_a_kept_one + self.like_a_dropped_one + self.like_an_expired_one


@dataclass(frozen=True)
class Aged:
    """The proposals after a run let time pass, and how many of them expired and were forgotten in it."""

    proposals: Proposals
    expired: int
    forgotten: int


@dataclass(frozen=True)
class Outcomes:
    """How the proposals settled in a period ended."""

    kept: int
    dropped: int
    expired: int

    @property
    def keep_rate(self) -> float | None:
        """The share kept of those the person answered; None without an answer, which is not a rate of 0.

        An expired proposal is not in it: the person did not look, which says nothing about the proposal.
        """
        answered = self.kept + self.dropped
        return self.kept / answered if answered else None


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
    return Proposals(
        entries, _moment(raw.get("read_until")), _moment(raw.get("announced_until")), _counts(raw.get("counts"))
    )


def save(store: Store, proposals: Proposals) -> None:
    write_store_json_object(
        store,
        PROPOSALS_FILE,
        {
            "format": FORMAT,
            "read_until": proposals.read_until.isoformat() if proposals.read_until else None,
            "announced_until": proposals.announced_until.isoformat() if proposals.announced_until else None,
            "counts": {kind: dataclasses.asdict(proposals.tally(kind)) for kind in KINDS},
            "proposals": {key: _as_json(entry) for key, entry in sorted(proposals.entries.items())},
        },
    )


def add(current: Proposals, found: Sequence[Said], now: datetime.datetime) -> Added:
    """``current`` with the proposals of ``found`` that are new, and how many were refused and why.

    A proposal settled 90 days ago or longer is forgotten here, so it may come again.
    """
    entries = _remembered(current.entries, now)
    like = dict.fromkeys(STATES, 0)
    counts = current.counts
    added = 0
    for said in found:
        key = proposal_id(said.proposal)
        known = entries.get(key) or next(
            (entry for entry in entries.values() if same_text(entry.text, said.proposal.text)), None
        )
        if known is not None:
            like[known.state] += 1
            continue
        proposal = said.proposal
        entries[key] = Entry(
            proposal.kind, proposal.text, proposal.quote, said.day, OPEN, now, proposal.topic, proposal.due
        )
        counts = _counted(counts, proposal.kind, "proposed")
        added += 1
    kept = dataclasses.replace(current, entries=entries, counts=counts)
    return Added(kept, added, like[OPEN], like[KEPT], like[DROPPED], like[EXPIRED])


def settled(current: Proposals, key: str, state: str, now: datetime.datetime) -> Proposals:
    """``current`` with the proposal ``key`` kept, dropped or expired since ``now``, counted for its kind.

    A proposal is counted under how it ended: one kept after it had expired is no longer counted as expired.
    """
    entry = current.entries[key]
    entries = {**current.entries, key: dataclasses.replace(entry, state=state, since=now)}
    counts = _counted(current.counts, entry.kind, state)
    if entry.state != OPEN:
        counts = _counted(counts, entry.kind, entry.state, -1)
    return dataclasses.replace(current, entries=entries, counts=counts)


def counted(current: Proposals, kind: str, what: str, number: int = 1) -> Proposals:
    """``current`` with ``number`` more of ``what``, a field of ``Tally``, counted for the kind."""
    return dataclasses.replace(current, counts=_counted(current.counts, kind, what, number))


def aged(current: Proposals, answered: Collection[str], now: datetime.datetime) -> Aged:
    """What time makes of ``current``; ``answered`` are the ids with an answer no run has settled yet.

    An open proposal without an answer expires 14 days after it was added, and one settled 90 days
    ago or longer is forgotten. One whose answer waits stays open however old it is: the person
    answered, and only the run is late.
    """
    late = [
        key
        for key, entry in current.entries.items()
        if entry.state == OPEN and key not in answered and now - entry.since >= EXPIRES_AFTER
    ]
    result = current
    for key in late:
        result = settled(result, key, EXPIRED, now)
    remembered = _remembered(result.entries, now)
    forgotten = len(result.entries) - len(remembered)
    if forgotten:
        result = dataclasses.replace(result, entries=remembered)
    return Aged(result, len(late), forgotten)


def outcomes_since(current: Proposals, start: datetime.datetime) -> Outcomes:
    """How the proposals settled at ``start`` or later ended; only as far back as a settled one is remembered."""
    ended = [entry.state for entry in current.entries.values() if entry.state != OPEN and entry.since >= start]
    return Outcomes(ended.count(KEPT), ended.count(DROPPED), ended.count(EXPIRED))


def examples(current: Proposals, now: datetime.datetime) -> Examples:
    """What the person kept and what they dropped, of each the ``EXAMPLES_OF_EACH`` a run settled last, newest first.

    The moment is the one a run settled the answer at, so the answers one run settled share it;
    among those the id decides, which keeps the order the same from run to run. A proposal settled
    90 days ago or longer is none, also while it is still in the file: a run removes those only
    in its last step, and what ``add`` takes as forgotten must not be shown as remembered.
    """

    def settled_last(state: str) -> tuple[Example, ...]:
        ended = sorted(
            (
                (entry.since, key, entry)
                for key, entry in _remembered(current.entries, now).items()
                if entry.state == state
            ),
            key=lambda item: item[:2],
            reverse=True,
        )
        return tuple(Example(entry.kind, entry.text, entry.quote) for _, _, entry in ended[:EXAMPLES_OF_EACH])

    return Examples(settled_last(KEPT), settled_last(DROPPED))


def _remembered(entries: Mapping[str, Entry], now: datetime.datetime) -> dict[str, Entry]:
    return {key: entry for key, entry in entries.items() if entry.state == OPEN or now - entry.since < REMEMBER_SETTLED}


def _counted(counts: Mapping[str, Tally], kind: str, what: str, number: int = 1) -> Mapping[str, Tally]:
    if number == 0:
        return counts
    tally = counts.get(kind, Tally())
    return {**counts, kind: dataclasses.replace(tally, **{what: max(getattr(tally, what) + number, 0)})}


def _counts(value: object) -> dict[str, Tally]:
    """The counts of the kinds that have any; what is no count of a kind this m2b knows reads as nothing counted."""
    counts = {}
    for kind in KINDS:
        given = value.get(kind) if isinstance(value, dict) else None
        if not isinstance(given, dict):
            continue
        tally = Tally(**{field.name: _count(given.get(field.name)) for field in dataclasses.fields(Tally)})
        if tally != Tally():
            counts[kind] = tally
    return counts


def _count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


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
