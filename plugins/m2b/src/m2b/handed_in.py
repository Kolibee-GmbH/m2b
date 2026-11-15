"""A proposal a session hands in by itself: checked at the call, then one file in the store.

The agent of a session can notice what belongs in the memory in something it read for its task, a
mail or a document, and hand it in as a proposal: a kind, a text and the words it stands on.
Handing in is off until ``sessions.propose`` is true in the machine config, because with it words
from what an agent read reach the store.

The check is here, at the call, on the machine the session runs on: only there the session's
transcript is at hand, and the agent hears at once when its words do not stand in it. Whoever
calls, the tool of a session or a shell, meets the same checks, and a refusal is one line that
never repeats the quote or the text, so no refusal puts the words into the session for a second
call.

- The form: one of the kinds a reading proposes, a text of one line, a quote of at least as many
  words as a reading's, no character that hides or reorders text or steers a terminal, and no
  credential in either.
- The session: its id has the form of one and exactly one transcript on this machine has it.
- Where it worked: no working folder of the session or of its subagents, and no path one of its
  calls names, is work m2b does not read (``folders_left_out``). A session that named more paths
  than are looked at is refused too: it cannot be shown to have stayed out of such work.
- The quote stands in one text of the session (``session_places``), white space aside, as whole
  words: a piece cut out of the middle of a word is not what the text says. Where it stands in
  several texts, the place a person is surest to have meant decides: what they typed before what
  they pasted, before what a tool returned, before what Claude answered.
- What gives back the memory is no place: a result of one of m2b's own tools, of a shell command
  that runs ``m2b``, and of a call that names the store's folder. And a tool's result says
  nothing of its own where Claude wrote the words first: a quote that stands in the input of a
  call or in an answer before that result is Claude's text come back (``echo``, a file written
  and then read, a task given to a subagent), and its source is the answer. Words Claude encoded
  on the way in are not known for its own.
- No credential: wherever the quote stands, the text right before and right behind it goes
  through the redaction with it, so a value is caught whose name stands before the quote, under
  a key of JSON, or whose form shows only with what follows. A text that begins with a
  credential's value, by what stood before it, gives no quote at all: under a key that names a
  credential the whole value is one. A name further off, or only in the input of the call, is
  not seen; the redaction is a net with holes, here as everywhere.
- No more than ``WAITING_PER_SESSION`` proposals of one session wait for a run. The number is
  chosen: a document planted to make an agent propose a hundred things, each with a real quote,
  fills the list no further between two runs. Once a run took them in, the session can hand in
  as many again. Calls at the same moment can pass the limit.

What the check shows is that the words stand in the session and where. It does not show that
they carry the text: a document can lead an agent to a proposal that quotes three words the
person typed. Whoever answers a proposal reads it first.

A proposal that passes is one file, ``state/core/handed-in/<session>.<id>.json``, created
exclusively: a client only adds to the store, and ``proposals.json`` is the curation run's. The
id is the one a reading gives the same quote of the same session (``proposals.proposal_id``), so
the same call twice finds its file there, and what a reading and a session both propose has one
id. The file holds no folder: a folder's name can be a customer's.

The next curation run takes the file in (``curate.handed_in_intake``) and removes it. It has no
transcript, so it reads the file again with every check that needs none (``read``).
"""

from __future__ import annotations

import datetime
import json
import os.path
import re
import time
import unicodedata
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from m2b import claude_code, folders_left_out, glean, proposals, session_places
from m2b.candidates import same_text
from m2b.config.errors import ConfigError
from m2b.config.machine import MachineConfig
from m2b.config.store_settings import require_store_writable
from m2b.glean import AGENT, PASTED, TOOL, TYPED
from m2b.notes.characters import can_be_written, unsafe_characters, without_hidden
from m2b.notes.layout import HANDED_IN
from m2b.paths import MachinePaths
from m2b.prompt_hook import CURATION_RUN_VARIABLE
from m2b.redaction import is_removed_behind, redact
from m2b.session_places import Place
from m2b.store.base import Store, StoreError

FOLDER = HANDED_IN
FORMAT = 1
WAITING_PER_SESSION = 10
# A quote is the words a proposal stands on, a sentence or two, not the passage they are from.
QUOTE_LENGTH = 500
# How much of the text before and behind the quote is redacted with it: enough for a
# credential's name, and for the host that shows a password in an address.
CONTEXT_LENGTH = 200
# What git gets to name a folder's remotes, and what the whole look at where the session worked
# may take: a call in the middle of a session cannot wait as a curation run can.
GIT_SECONDS = 2.0
LOOK_SECONDS = 15.0
# The tools of m2b's own mod, and m2b's commands as a shell runs them: what they return is the
# memory itself.
OWN_TOOLS = "mcp__m2b__"
SHELL_TOOL = "Bash"
# ``m2b`` as a word of a command, wherever it stands: behind ``env``, in a ``sh -c``, behind a pipe.
_OWN_COMMAND = re.compile(r"""(?:^|[\s;&|()'"=])(?:[\w.~/-]*/)?m2b(?:-worklog)?(?=$|[\s;&|()'"])""")
# The selector that makes a sign an emoji draws nothing and hides nothing.
_EMOJI_SELECTOR = "\ufe0f"
_JOINERS = "\u200c\u200d"
# Where a quote found in several places is taken to stand, the first of these.
_SOURCES = (TYPED, PASTED, TOOL, AGENT)
SWITCH = "sessions.propose"
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
# The time of a call as ``as_json`` writes it: with its seconds and its offset.
_MOMENT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?[+-]\d{2}:\d{2}")
# What steers a terminal or is drawn as nothing; white space is gone by then, the text is one line.
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


class RefusedError(Exception):
    """The proposal was not handed in; the text is the one line that says why."""


class NotInFormError(Exception):
    """A file in the folder is no proposal this m2b wrote; the text names what is not in the form."""


class NewerFormatError(Exception):
    """A file in the folder was written by a newer m2b; this one does not judge it."""


@dataclass(frozen=True)
class Given:
    """What a caller hands in, in the form."""

    kind: str
    text: str
    quote: str
    session: str
    due: datetime.date | None = None


@dataclass(frozen=True)
class HandedIn:
    """A proposal as its file holds it."""

    kind: str
    text: str
    quote: str
    session: str
    # The day the quote was written in the session, where the person is.
    day: datetime.date
    # Where the quote stands in the session, and for a tool's result the tool.
    source: str
    at: datetime.datetime
    tool: str | None = None
    due: datetime.date | None = None


@dataclass(frozen=True)
class Outcome:
    proposal: HandedIn
    # False when this session handed the same proposal in before.
    is_new: bool


def require_on(config: MachineConfig, environ: Mapping[str, str]) -> None:
    """Refuses where nothing is handed in at all: the switch is off, or this is a curation run."""
    if not config.sessions.propose:
        raise RefusedError(f"nothing handed in: handing in is off on this machine ({SWITCH} in the m2b config)")
    if environ.get(CURATION_RUN_VARIABLE) == "1":
        raise RefusedError("nothing handed in: a curation run hands nothing in")


def parse(raw: object) -> Given:
    """What the caller gave, checked for its form; a ``RefusedError`` names the part that is not in it."""
    if not isinstance(raw, dict):
        raise RefusedError("nothing handed in: a proposal is a JSON object with kind, text, quote and session")
    kind, session = raw.get("kind"), raw.get("session")
    text, quote = _one_line(raw.get("text")), _one_line(raw.get("quote"))
    if kind not in glean.KINDS:
        raise RefusedError(f"nothing handed in: kind is one of {', '.join(glean.KINDS)}")
    if not text or len(text) > glean.TEXT_LENGTH:
        raise RefusedError(f"nothing handed in: text is one plain sentence of at most {glean.TEXT_LENGTH} characters")
    if not quote or len(quote.split()) < glean.QUOTE_WORDS or len(quote) > QUOTE_LENGTH:
        raise RefusedError(
            f"nothing handed in: quote is at least {glean.QUOTE_WORDS} words and at most {QUOTE_LENGTH} characters, "
            "copied as they stand"
        )
    if _hides_something(text + quote):
        raise RefusedError("nothing handed in: text or quote holds a character that hides or reorders text")
    if redact(text) != text or redact(quote) != quote:
        raise RefusedError("nothing handed in: text or quote holds what looks like a credential, which is not kept")
    if not isinstance(session, str) or not session_places.is_session_id(session):
        raise RefusedError("nothing handed in: session is the id of the session that hands in")
    return Given(kind, text, quote, session, _due(raw.get("due")))


def hand_in(
    store: Store,
    config: MachineConfig,
    machine: MachinePaths,
    environ: Mapping[str, str],
    given: Given,
    now: datetime.datetime,
) -> Outcome:
    """Checks the proposal against its session and adds its file; a ``RefusedError`` says why it did not."""
    require_on(config, environ)
    found = _session(environ, given.session)
    _refuse_work_left_out(found, store, config, machine, environ, now)
    store_folders = _spellings_of(store)
    holding = [
        index
        for index, place in enumerate(found.places)
        if not _gives_back_the_memory(place, store_folders)
        and next(_starts_of(given.quote, place.text), None) is not None
    ]
    if not holding:
        raise RefusedError(
            "nothing handed in: the words do not stand in this session as given; "
            f"copy at least {glean.QUOTE_WORDS} whole words as they stand in one text"
        )
    if any(_is_a_credential_there(given.quote, found.places[index]) for index in holding):
        raise RefusedError("nothing handed in: the quote holds what looks like a credential, which is not kept")
    sources = {index: _source_of(given.quote, found, index) for index in holding}
    chosen = min(holding, key=lambda index: _SOURCES.index(sources[index]))
    place, source = found.places[chosen], sources[chosen]
    proposal = HandedIn(
        given.kind,
        given.text,
        given.quote,
        given.session,
        place.time.astimezone(now.tzinfo or datetime.timezone.utc).date(),
        source,
        now,
        # A name that is not in the form of a tool's name is not shown as one.
        place.tool if source == TOOL and place.tool and proposals.is_tool_name(place.tool) else None,
        given.due,
    )
    return _add(store, proposal)


def read(name: str, text: str) -> HandedIn:
    """A file of the folder as the curation run takes it in: ``name`` is its file name.

    The run has no transcript, the session may have run on another machine. It checks again what
    needs none, because the file came through the store like any other: the form of the text and
    the quote, with no character that hides and nothing the redaction removes; that the name is
    the session's id and the id of that quote; a source this m2b writes; a tool's name only with
    a tool's result and only in the form of one. What does not hold is a ``NotInFormError``; a
    file of a newer format is a ``NewerFormatError`` and is left for the m2b that knows it.
    """
    stem, dot, extension = name.rpartition(".")
    session, _, proposal_id = stem.rpartition(".")
    if dot != "." or extension != "json" or not session_places.is_session_id(session):
        raise NotInFormError("its name")
    if not proposals.is_id(proposal_id):
        raise NotInFormError("its name")
    try:
        raw = json.loads(text)
    except (ValueError, RecursionError):
        raise NotInFormError("its content") from None
    if not isinstance(raw, dict):
        raise NotInFormError("its content")
    written_as = raw.get("format")
    if not isinstance(written_as, int) or isinstance(written_as, bool) or written_as < 1:
        raise NotInFormError("its format")
    if written_as > FORMAT:
        raise NewerFormatError(f"format {written_as}")
    try:
        given = parse(raw)
    except RefusedError:
        raise NotInFormError("its kind, text, quote, session or due") from None
    # A call writes text and quote as one line; a file that holds them otherwise is not a call's.
    if raw.get("text") != given.text or raw.get("quote") != given.quote:
        raise NotInFormError("its text")
    named = proposals.proposal_id(glean.Proposal(given.kind, given.text, given.quote, given.session))
    if given.session != session or named != proposal_id:
        raise NotInFormError("its name")
    source, tool = raw.get("source"), raw.get("tool")
    if source not in _SOURCES:
        raise NotInFormError("its source")
    if tool is not None and not (source == TOOL and isinstance(tool, str) and proposals.is_tool_name(tool)):
        raise NotInFormError("its tool")
    # A call never takes a result of one of m2b's own tools for a place: it gives the memory back.
    if isinstance(tool, str) and tool.startswith(OWN_TOOLS):
        raise NotInFormError("its tool")
    written_day, written_at = raw.get("day"), raw.get("at")
    # As a call writes them, whatever else the running Python would read as a day or a time.
    if not (isinstance(written_day, str) and _DAY.fullmatch(written_day)):
        raise NotInFormError("its day")
    if not (isinstance(written_at, str) and _MOMENT.fullmatch(written_at)):
        raise NotInFormError("its time")
    try:
        day = datetime.date.fromisoformat(written_day)
        at = datetime.datetime.fromisoformat(written_at)
    except ValueError:
        raise NotInFormError("its day") from None
    # The words were written before the call, a day's difference between two zones aside.
    if day > at.date() + datetime.timedelta(days=1):
        raise NotInFormError("its day")
    return HandedIn(given.kind, given.text, given.quote, given.session, day, source, at, tool, given.due)


def file_name(session: str, proposal_id: str) -> str:
    return f"{FOLDER}/{session}.{proposal_id}.json"


def as_json(proposal: HandedIn) -> dict[str, object]:
    return {
        "format": FORMAT,
        "kind": proposal.kind,
        "text": proposal.text,
        "quote": proposal.quote,
        "due": proposal.due.isoformat() if proposal.due else None,
        "session": proposal.session,
        "day": proposal.day.isoformat(),
        "source": proposal.source,
        "tool": proposal.tool,
        "at": proposal.at.isoformat(),
    }


def _session(environ: Mapping[str, str], session: str) -> session_places.SessionPlaces:
    transcripts = session_places.transcripts_of(claude_code.transcripts_folder(environ), session)
    if len(transcripts) != 1:
        raise RefusedError(
            "nothing handed in: the transcript of this session is not on this machine"
            if not transcripts
            else "nothing handed in: more than one transcript on this machine has this session's id"
        )
    try:
        return session_places.read(transcripts[0])
    except OSError as error:
        raise RefusedError("nothing handed in: the transcript of this session could not be read") from error


def _refuse_work_left_out(
    found: session_places.SessionPlaces,
    store: Store,
    config: MachineConfig,
    machine: MachinePaths,
    environ: Mapping[str, str],
    now: datetime.datetime,
) -> None:
    """Refuses a session that worked where m2b does not read, or that cannot be shown to have stayed out."""
    cannot_be_told = "nothing handed in: where this session worked cannot be told whole"
    if not found.folders or found.paths_incomplete:
        raise RefusedError(cannot_be_told)
    started = time.monotonic()
    try:
        rule = folders_left_out.rule(store, config, machine, environ, now, GIT_SECONDS)
    except (OSError, StoreError, ConfigError) as error:
        raise RefusedError(
            "nothing handed in: could not look which work m2b leaves out, the store's profile cannot be read"
        ) from error
    for path in (*found.folders, *found.paths):
        if rule.reason_for_a_path(path) is not None:
            raise RefusedError("nothing handed in: this session worked in or read from a folder m2b does not read")
        if time.monotonic() - started > LOOK_SECONDS:
            raise RefusedError(cannot_be_told)


def _hides_something(text: str) -> bool:
    """Whether the text holds what hides or reorders text, steers a terminal or cannot be written."""
    plain = text.replace(_EMOJI_SELECTOR, "")
    return bool(
        unsafe_characters(text) or _CONTROL.search(text) or without_hidden(plain) != plain or not can_be_written(text)
    )


def _starts_of(quote: str, text: str) -> Iterator[int]:
    """Where the quote stands in the text as whole words: no part of a word touches it at either end."""
    start = text.find(quote)
    while start >= 0:
        end = start + len(quote)
        if not _is_of_a_word(text[start - 1 : start] if start else "") and not _is_of_a_word(text[end : end + 1]):
            yield start
        start = text.find(quote, start + 1)


def _is_of_a_word(character: str) -> bool:
    """A letter, a digit, a mark on one, an underscore, or what joins two signs into one."""
    return bool(character) and (
        character == "_" or character in _JOINERS or unicodedata.category(character)[0] in "LNM"
    )


def _spellings_of(store: Store) -> tuple[str, ...]:
    """The store's folder as a call may name it: as configured, and where that leads."""
    root = str(store.root)
    return tuple(dict.fromkeys((root, os.path.realpath(root))))


def _gives_back_the_memory(place: Place, store_folders: Sequence[str]) -> bool:
    """A result of one of m2b's own tools, of a shell command that runs m2b, or of a call that names the store."""
    tool = place.tool or ""
    if tool.startswith(OWN_TOOLS):
        return True
    if any(folder in given for folder in store_folders for given in place.call_input):
        return True
    return tool == SHELL_TOOL and any(_OWN_COMMAND.search(given) for given in place.call_input)


def _source_of(quote: str, found: session_places.SessionPlaces, index: int) -> str:
    """The place's source; a tool's result behind an input or an answer that held the quote is Claude's own text."""
    place = found.places[index]
    if place.source != TOOL:
        return place.source
    written_before = any(
        quote in given for call in found.inputs if call.places_before <= index for given in call.texts
    ) or any(quote in earlier.text for earlier in found.places[:index] if earlier.source == AGENT)
    return AGENT if written_before else TOOL


def _is_a_credential_there(quote: str, place: Place) -> bool:
    """Whether the redaction takes the quote, whole or in part, at one of the spots it stands in this place."""
    if place.before and is_removed_behind(place.before, place.text[:CONTEXT_LENGTH]):
        return True
    for start in _starts_of(quote, place.text):
        end = start + len(quote)
        before = place.text[max(0, start - CONTEXT_LENGTH) : start]
        if start < CONTEXT_LENGTH and place.before:
            before = f"{place.before} {before}"
        behind = place.text[end : end + CONTEXT_LENGTH]
        # Asked spot by spot: the same words nearby, left whole, must not answer for this one.
        if is_removed_behind(before, quote) or not redact(f"{quote}{behind}").startswith(quote):
            return True
    return False


def _add(store: Store, proposal: HandedIn) -> Outcome:
    require_store_writable(store)
    waiting = store.scan(FOLDER)
    if FOLDER in waiting.evicted:
        raise RefusedError("nothing handed in: could not look how many proposals of this session wait")
    # A file that is not downloaded is counted by its name.
    names = (*waiting.files, *waiting.evicted)
    of_this_session = [name for name in names if PurePosixPath(name).name.startswith(f"{proposal.session}.")]
    proposal_id = proposals.proposal_id(glean.Proposal(proposal.kind, proposal.text, proposal.quote, proposal.session))
    name = file_name(proposal.session, proposal_id)
    if name not in of_this_session and len(of_this_session) >= WAITING_PER_SESSION:
        raise RefusedError(f"nothing handed in: {WAITING_PER_SESSION} proposals of this session wait already")
    data = json.dumps(as_json(proposal), ensure_ascii=False, indent=1) + "\n"
    try:
        store.create_exclusive(name, data.encode("utf-8"))
    except FileExistsError:
        _refuse_unless_the_same(store, name, proposal)
        return Outcome(proposal, is_new=False)
    return Outcome(proposal, is_new=True)


def _refuse_unless_the_same(store: Store, name: str, proposal: HandedIn) -> None:
    """Refuses where the file under the proposal's name holds another proposal or cannot be read."""
    try:
        there = json.loads(store.read_text(name))
    except (OSError, StoreError, ValueError, RecursionError):
        there = None
    kind, text = (there.get("kind"), there.get("text")) if isinstance(there, dict) else (None, None)
    if not isinstance(text, str):
        raise RefusedError("nothing handed in: could not look whether this proposal was handed in before")
    if kind != proposal.kind or not same_text(text, proposal.text):
        raise RefusedError(
            "nothing handed in: these words carry another proposal of this session already; "
            "quote the words that name this one"
        )


def _one_line(value: object) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _due(value: object) -> datetime.date | None:
    if value is None or value == "":
        return None
    try:
        if not isinstance(value, str) or not _DAY.fullmatch(value):
            raise ValueError(value)
        return datetime.date.fromisoformat(value)
    except ValueError:
        raise RefusedError("nothing handed in: due is a day as YYYY-MM-DD") from None
