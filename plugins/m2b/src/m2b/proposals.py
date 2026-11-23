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

A session can also hand a proposal in by itself (``handed_in``), and a run takes it in here. Such
a proposal says so (``Entry.by``), and its words may stand in what a tool returned to the session
or in what Claude answered, with the tool's name for the first. It waits and is answered like any
other. It is no example for a reading's model: its quote can be a mail's, and the examples are
shown as what this person kept and dropped of what they typed and pasted.

Only the curation run writes the file, as it does ``candidates.json``. A file a newer m2b wrote is
not read, so this one never writes over what it does not know. That is why the file carries the
lowest format that an m2b which reads it shows rightly (``_format_of``): an m2b before the source
would show a proposal from pasted text as said and write it back without the field, and one
before a session could hand in would show a handed-in proposal as said or under a source it does
not know and write it back without who proposed it and without the tool; one before a lesson or a
project could be proposed would leave such a proposal out and write the file back without it.
Fields added to a lesson since (``unless``, ``unsure``) raise no format: an m2b before them shows
the lesson and writes it back without them, which loses a hint, never a proposal.

A project is proposed by code, not by a model (``project_proposals``): a repository the person
worked in on two days that has no topic. Its quote is the repository's addresses, its source
``WORKED``; it is no example for a reading's model, which proposes no project.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import re
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from m2b import lessons
from m2b.candidates import REMEMBER_DROPPED as REMEMBER_SETTLED
from m2b.candidates import same_text
from m2b.config.json_file import read_store_json_object, write_store_json_object
from m2b.glean import (
    AGENT,
    FIX,
    KINDS,
    LESSON,
    PASTED,
    POINTER,
    PROJECT,
    READ_KINDS,
    STATED,
    TOOL,
    TYPED,
    WORKED,
    AtSource,
    Example,
    Examples,
    LessonPart,
    PointerPart,
    Proposal,
)
from m2b.notes.characters import can_be_written
from m2b.notes.layout import STATE
from m2b.store.base import Store

PROPOSALS_FILE = f"{STATE}/core/proposals.json"
FORMAT = 4
# What an m2b before a lesson could be proposed wrote and reads: no kind ``lesson``.
FORMAT_WITHOUT_LESSONS = 3
# What an m2b before a proposal had a source wrote and reads.
FORMAT_WITHOUT_SOURCE = 1
# What an m2b before a session could hand a proposal in wrote and reads: typed and pasted words.
FORMAT_OF_A_READING = 2
# Who proposed, where it was not a reading of the sessions: a session, by itself.
SESSION = "session"
# The way of every other proposal, where the ways are counted apart (``by_way_and_source``).
READING = "reading"
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
# A source is a word; one this m2b does not know is shown as written (``said_line``). So is who
# proposed.
_SOURCE = re.compile(r"[a-z][a-z-]{0,19}")
# A tool as Claude Code names it, its own or one of an MCP server: letters, digits and the signs
# such names are joined with. The name is shown to the person, so nothing else is taken for one.
_TOOL = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,127}")
_LESSON_FILE = re.compile(r"[^/\\\x00]+\.md")


class ProposalsError(Exception):
    """The proposals file is there and this m2b cannot use it."""


@dataclass(frozen=True)
class Entry:
    kind: str
    text: str
    # The words of the session the proposal stands on, typed or pasted (``source``).
    quote: str
    # The day the person said them, where they are.
    day: datetime.date
    state: str
    # When the proposal was added, or when the run settled the person's answer to it.
    since: datetime.datetime
    topic: str | None = None
    due: datetime.date | None = None
    # Where in the session the quote stands: what was typed, or something else, such as pasted text.
    source: str = TYPED
    # The tool whose result holds the quote, where the source is a tool's result.
    tool: str | None = None
    # Who proposed where it was no reading: ``SESSION`` for a proposal a session handed in.
    by: str | None = None
    # For a lesson: its kind, target, words and, where it was made in two, the same correction in a
    # second session.
    lesson: LessonPart | None = None
    # For a pointer: the file in its repository and the repository's addresses.
    pointer: PointerPart | None = None


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
    # For a proposal a session handed in: the tool whose result holds the quote, and who proposed.
    tool: str | None = None
    by: str | None = None


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


@dataclass(frozen=True)
class WayCounts:
    """Of the proposals of one way and one source: how many wait for an answer, how many have one
    that no run has settled yet, and how those settled lately ended."""

    waiting: int = 0
    answered: int = 0
    kept: int = 0
    dropped: int = 0
    expired: int = 0


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
            "format": _format_of(proposals.entries.values()),
            "read_until": proposals.read_until.isoformat() if proposals.read_until else None,
            "announced_until": proposals.announced_until.isoformat() if proposals.announced_until else None,
            "counts": {kind: dataclasses.asdict(proposals.tally(kind)) for kind in KINDS},
            "proposals": {key: _as_json(entry) for key, entry in sorted(proposals.entries.items())},
        },
    )


def is_tool_name(text: str) -> bool:
    """Whether the text has the form of a tool's name: only then is it kept and shown as one."""
    return _TOOL.fullmatch(text) is not None


def _format_of(entries: Collection[Entry]) -> int:
    """The format the file needs: 4 with a lesson, a project or a pointer; 3 with a proposal that names
    who proposed or a tool, or whose source is neither typed nor pasted; else 2 with one from pasted
    text; else 1."""
    if any(entry.kind in (LESSON, PROJECT, POINTER) for entry in entries):
        return FORMAT
    if any(entry.by is not None or entry.tool is not None or entry.source not in (TYPED, PASTED) for entry in entries):
        return FORMAT_WITHOUT_LESSONS
    return FORMAT_WITHOUT_SOURCE if all(entry.source == TYPED for entry in entries) else FORMAT_OF_A_READING


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
            proposal.kind,
            proposal.text,
            proposal.quote,
            said.day,
            OPEN,
            now,
            proposal.topic,
            proposal.due,
            proposal.source,
            said.tool,
            said.by,
            proposal.lesson,
            proposal.pointer,
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


def outcomes_since(current: Proposals, start: datetime.datetime, kind: str | None = None) -> Outcomes:
    """How the proposals settled at ``start`` or later ended, those of ``kind`` only where one is
    given; only as far back as a settled one is remembered."""
    ended = [
        entry.state
        for entry in current.entries.values()
        if entry.state != OPEN and entry.since >= start and kind in (None, entry.kind)
    ]
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
                # What a session handed in is none: its quote can be anyone's text. Nor is a
                # project: it stands on no words, and no model proposes one.
                if entry.state == state and entry.by is None and entry.kind in READ_KINDS
            ),
            key=lambda item: item[:2],
            reverse=True,
        )
        return tuple(Example(entry.kind, entry.text, entry.quote) for _, _, entry in ended[:EXAMPLES_OF_EACH])

    return Examples(settled_last(KEPT), settled_last(DROPPED))


def waiting_examples(current: Proposals) -> tuple[Example, ...]:
    """The proposals of a reading that wait for an answer, the ``EXAMPLES_OF_EACH`` added last, newest first.

    A reading shown what waits does not propose it a second time in other words, which ``add``
    takes as new. What a session handed in is none, as it is no example: its quote can be a
    tool's result, a mail's words, which must not reach the reading's model.
    """
    open_now = sorted(
        (
            (entry.since, key, entry)
            for key, entry in current.entries.items()
            if entry.state == OPEN and entry.by is None and entry.kind in READ_KINDS
        ),
        key=lambda item: item[:2],
        reverse=True,
    )
    return tuple(Example(entry.kind, entry.text, entry.quote) for _, _, entry in open_now[:EXAMPLES_OF_EACH])


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
    # Without the field the words were typed: an m2b before it read nothing else.
    source = value.get("source", TYPED)
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
    if not all(can_be_written(part) for part in (text, quote, topic or "")):
        return None
    if not isinstance(source, str) or not _SOURCE.fullmatch(source):
        return None
    tool, by = value.get("tool"), value.get("by")
    if not (tool is None or (isinstance(tool, str) and is_tool_name(tool))):
        return None
    if not (by is None or (isinstance(by, str) and _SOURCE.fullmatch(by))):
        return None
    lesson = _lesson_of(value.get("lesson"))
    if (kind == LESSON) != (lesson is not None):
        return None
    pointer = _pointer_of(value.get("pointer"))
    if (kind == POINTER) != (pointer is not None):
        return None
    return Entry(kind, text, quote, day, state, since, topic, due, source, tool, by, lesson, pointer)


def _pointer_of(value: object) -> PointerPart | None:
    """A pointer's part as the file holds it: a path in a repository and at least one address."""
    if not isinstance(value, dict):
        return None
    path, repositories = value.get("path"), value.get("repositories")
    if not isinstance(path, str) or not path or not can_be_written(path):
        return None
    if not isinstance(repositories, list) or not repositories:
        return None
    if not all(isinstance(each, str) and each and can_be_written(each) for each in repositories):
        return None
    return PointerPart(path, tuple(repositories))


def _lesson_of(value: object) -> LessonPart | None:
    """A lesson's part as the file holds it; its target there is ``every project`` or an address."""
    if not isinstance(value, dict):
        return None
    kind, target, quote, session, words = (value.get(name) for name in ("kind", "target", "quote", "session", "words"))
    if kind not in lessons.KINDS or not isinstance(target, str) or not target or target == lessons.THIS_PROJECT:
        return None
    if not isinstance(quote, str) or not isinstance(session, str) or not isinstance(words, list):
        return None
    if not all(isinstance(word, str) for word in words) or not all(
        can_be_written(part) for part in (quote, target, *words)
    ):
        return None
    at_source = value.get("at_source")
    source = None if at_source is None else _at_source_of(at_source)
    if at_source is not None and source is None:
        return None
    replaces = value.get("replaces")
    # A lesson's file name, never a path: harvest removes the file it names.
    if not (
        replaces is None
        or (isinstance(replaces, str) and _LESSON_FILE.fullmatch(replaces) and can_be_written(replaces))
    ):
        return None
    unless = value.get("unless", [])
    if not isinstance(unless, list) or not all(isinstance(word, str) and can_be_written(word) for word in unless):
        return None
    unsure = value.get("unsure", False)
    if not isinstance(unsure, bool):
        return None
    return LessonPart(kind, target, tuple(words), quote, session, source, replaces, tuple(unless), unsure)


def _at_source_of(value: object) -> AtSource | None:
    if not isinstance(value, dict):
        return None
    verdict, file, line, wording, path = (value.get(name) for name in ("verdict", "file", "line", "wording", "path"))
    repositories = value.get("repositories", [])
    texts = (file, *(part for part in (line, wording, path) if part is not None))
    if verdict not in (FIX, STATED) or not all(isinstance(part, str) and can_be_written(part) for part in texts):
        return None
    if not isinstance(file, str):
        return None
    if not isinstance(repositories, list) or not all(isinstance(each, str) for each in repositories):
        return None
    if (verdict == FIX) != (wording is not None and path is not None):
        return None
    return AtSource(verdict, file, line, wording, path, tuple(repositories))


def _as_json(entry: Entry) -> dict[str, Any]:
    written: dict[str, Any] = {
        "kind": entry.kind,
        "text": entry.text,
        "quote": entry.quote,
        "topic": entry.topic,
        "due": entry.due.isoformat() if entry.due else None,
        "day": entry.day.isoformat(),
        "state": entry.state,
        "since": entry.since.isoformat(),
    }
    # Each written only where it says something, so the file of a store without such a proposal is
    # the one an m2b before the field wrote (``_format_of``).
    if entry.source != TYPED:
        written["source"] = entry.source
    if entry.tool is not None:
        written["tool"] = entry.tool
    if entry.by is not None:
        written["by"] = entry.by
    if entry.lesson is not None:
        written["lesson"] = {
            "kind": entry.lesson.kind,
            "target": entry.lesson.target,
            "words": list(entry.lesson.words),
            "quote": entry.lesson.quote,
            "session": entry.lesson.session,
        }
        if entry.lesson.at_source is not None:
            written["lesson"]["at_source"] = dataclasses.asdict(entry.lesson.at_source)
        if entry.lesson.replaces is not None:
            written["lesson"]["replaces"] = entry.lesson.replaces
        if entry.lesson.unless:
            written["lesson"]["unless"] = list(entry.lesson.unless)
        if entry.lesson.unsure:
            written["lesson"]["unsure"] = True
    if entry.pointer is not None:
        written["pointer"] = {"path": entry.pointer.path, "repositories": list(entry.pointer.repositories)}
    return written


def said_line(entry: Entry, quote: str) -> str:
    """The line under a proposal that says whose words it stands on: ``said on <day>: "<quote>"``.

    ``quote`` is the entry's quote as the caller shows text. Typed words were said; pasted ones
    are named as pasted, words a tool returned with the tool, words of an answer as Claude's, and
    a source this m2b does not know by its name.
    """
    leads = {
        TYPED: "said on",
        PASTED: "pasted on",
        TOOL: f"in a result of {entry.tool or 'a tool'} on",
        AGENT: "Claude wrote on",
        WORKED: "sessions worked in it, the last on",
    }
    lead = leads.get(entry.source, f"from {entry.source} on")
    return f'{lead} {entry.day.isoformat()}: "{quote}"'


def lesson_heading(lesson: LessonPart, shown: Callable[[str], str]) -> str:
    """What a proposed lesson is, beside its kind in a listing: ``action for every project, on a
    command with scripts/check``; ``shown`` is how the caller shows text."""
    words = f", on a command with {' '.join(shown(word) for word in lesson.words)}" if lesson.words else ""
    replaces = f", replaces {shown(lesson.replaces)}" if lesson.replaces else ""
    return f"{lesson.kind} for {shown(lesson.target)}{words}{replaces}"


def again_line(quote: str) -> str:
    """The line that shows a lesson's second quote, as the caller shows it: what was said again. A
    lesson that stands on one correction has none, and the caller shows no such line."""
    return f'and again in another session: "{quote}"'


def source_line(at_source: AtSource, shown: Callable[[str], str]) -> str:
    """What becomes of a source a lesson is kept at: the line a fix replaces and its new wording, the
    wording a fix adds, or the line that says the lesson already."""
    if at_source.verdict == STATED:
        return f'stated already in {shown(at_source.file)}: "{shown(at_source.line or "")}"'
    if at_source.line is None:
        return f'adds to {shown(at_source.file)}: "{shown(at_source.wording or "")}"'
    return f'fixes {shown(at_source.file)}: "{shown(at_source.line)}" becomes "{shown(at_source.wording or "")}"'


def proposer_of(entry: Entry) -> str | None:
    """How the listing names who proposed where it was no reading, or None for a reading's proposal.

    Every such proposal is answered one by one and is no example for a reading, also one whose
    proposer this m2b does not know.
    """
    if entry.by is None:
        return None
    return "handed in by a session" if entry.by == SESSION else f"proposed by {entry.by}"


def by_way_and_source(
    current: Proposals, start: datetime.datetime, answered: Collection[str] = ()
) -> dict[str, dict[str, WayCounts]]:
    """Per way a proposal came (``READING``, or who proposed) and per source: what waits, and how
    what was settled at ``start`` or later ended. Derived from the entries, so it reaches only as
    far back as a settled proposal is remembered, and holds only ways and sources with something.

    ``answered`` holds the ids whose answer no run has settled yet
    (``proposal_answers.awaiting_a_run``). Such a proposal is still open in the file, or expired
    and kept late, and counted as waiting or as expired it would say the person gave no answer."""
    counted: dict[str, dict[str, WayCounts]] = {}
    for key, entry in current.entries.items():
        if key in answered:
            what = "answered"
        elif entry.state == OPEN:
            what = "waiting"
        elif entry.since < start:
            continue
        else:
            what = entry.state
        sources = counted.setdefault(entry.by or READING, {})
        counts = sources.get(entry.source, WayCounts())
        sources[entry.source] = dataclasses.replace(counts, **{what: getattr(counts, what) + 1})
    return counted


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
