"""What a model may propose for the memory from what the person typed and Claude answered, and what code checks of it.

A step that reads a period's sessions (``sessions``) can find what belongs in the second brain
although nobody said "remember this": a person, an agreement with its day, a commitment, something
about the person's own life. This module is the part of such a step that is code: the input the
model gets, the form its answer must have, and two checks no instruction can replace.

The input is one JSON document: the distillate, so the model can leave out what is known already,
the proposals of earlier readings the person kept and those they dropped (``Examples``), those
that still wait for an answer (``waiting``), and per
session its folder, its day and every prompt whole, what was pasted into one apart from what was
typed, and beside it what Claude answered, marked as Claude's (``claude_answers``). A session is
named by a small number, its
place in the sequence the caller passes; the model repeats a number more reliably than an id, and
``parse_answer`` turns it back with the same sequence. JSON keeps a prompt one string whatever it
holds, so no typed text can pass as another session or as the memory, and no example as a session.

What this person keeps and drops says more about what to propose to them than a rule written for
everybody, so the model is shown it. An example is words of another period and no session: a
proposal that quotes one stands in no prompt, and ``check`` refuses it like any other.

A proposal carries the words it stands on, its ``quote``. ``check`` keeps a proposal only when the
quote stands, white space aside, in one prompt of the session it names or in one of Claude's
answers there, with at least ``QUOTE_WORDS`` words: fewer show nothing. The quote stands in what the
person typed, in one text they pasted into the prompt or in one answer; ``check`` says which
(``Proposal.source``), looking at what was typed first and at the answers last, so pasted words and
Claude's are never shown as said. A proposal that fails is the model's wording and not
the person's; it is returned apart, so a caller can count it. The second check takes away what the
person captured themselves in the same period: the quote stands in a capture, or a capture of at
least ``QUOTE_WORDS`` words stands in the quote, case and the punctuation at the ends aside.

A capture often words its prompt anew: "remember that I would rather sit at the window" is noted
as "I would rather sit at the window.", in another order where the language asks for it, with what
the sentence leaves open added in square brackets. Such a capture is recognised by its words: it
has at least ``QUOTE_WORDS`` different ones, all of them stand in the prompt the quote is from (so
it came from that prompt), and it shares at least ``SAME_STATEMENT`` of the shorter one's words
with the quote (so it is about what the quote says, not about the prompt's other sentence). Order,
case, punctuation and the additions in brackets do not count. A capture made elsewhere in words of
its own is not recognised; the person sees that proposal and drops it.

Claude's answers make a day's sessions ten to twenty times what was typed, more than one model
call reads well. ``in_parts`` parts a period by time, between prompts, so that the prompts of a
part and their answers take up at most ``PART_LENGTH`` characters of the input; each part is asked
on its own, with the memory and the examples. A prompt whose answers alone are longer is a part by
itself, with as many of its first answers as fit: a session a plugin drives all day after one
prompt of the person's hangs every answer on that prompt, and a part larger than the model reads
would fail every reading that comes after.

The instruction the model is asked with is ``glean_instruction.md`` beside this module. It is the
prompt of a run without tools (``curate.model.text_step``), not a skill: no session can call it.

An answer that cannot be read is an error (``GleanError``), never an answer without proposals. A
single proposal that is not in the form is left out and counted.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from m2b.notes.characters import can_be_written, unsafe_characters
from m2b.notes.memory_index import MAX_TOPIC_NAME
from m2b.sessions import Prompt, Session

PERSON = "person"
AGREEMENT = "agreement"
COMMITMENT = "commitment"
PERSONAL = "personal"
KINDS = (PERSON, AGREEMENT, COMMITMENT, PERSONAL)
# Where in a session a proposal's quote stands. What was pasted may be anyone's words, and so may
# what Claude answered, which often says what a mail or a file holds. A reading finds a quote in a
# prompt or an answer; a session that hands a proposal in can also stand on what a tool returned.
TYPED = "typed"
PASTED = "pasted"
TOOL = "tool"
AGENT = "agent"
# A proposal is one fact or one task; a longer text is a summary, which nobody asked for.
TEXT_LENGTH = 300
QUOTE_WORDS = 3
# The share of the shorter one's words a capture and a quote have in common when they say the same.
SAME_STATEMENT = 0.8
# The characters of sessions one model call reads at most: a day of answers is two or three parts.
PART_LENGTH = 150_000
INSTRUCTION = Path(__file__).with_name("glean_instruction.md")

_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_ENDS = " .,;:!?\"'()"
_WORD = re.compile(r"\w+")
# What a note adds to a sentence that leans on its conversation: "He [Sam] brings the plywood."
# No bracket inside, so a long run of brackets that never close costs one pass, not one per bracket.
_ADDITION = re.compile(r"\[[^\[\]]*\]")


class GleanError(Exception):
    """The model's answer could not be read; that is not an answer without proposals."""


@dataclass(frozen=True)
class Proposal:
    kind: str
    text: str
    # The stretch of one prompt the proposal stands on.
    quote: str
    # The id of the session the quote is from.
    session: str
    topic: str | None = None
    due: datetime.date | None = None
    # Where the quote stands in that session; ``check`` finds it, the model is never asked.
    source: str = TYPED


@dataclass(frozen=True)
class Example:
    """A proposal of an earlier reading the person answered: what it said and the words it stood on."""

    kind: str
    text: str
    quote: str


@dataclass(frozen=True)
class Examples:
    """The earlier proposals the person kept and those they dropped, the last answered first."""

    kept: tuple[Example, ...] = ()
    dropped: tuple[Example, ...] = ()


NO_EXAMPLES = Examples()


@dataclass(frozen=True)
class Part:
    """The sessions one model call reads: their prompts from ``since`` on, up to the next part's."""

    since: datetime.datetime
    sessions: tuple[Session, ...]


@dataclass(frozen=True)
class Answer:
    proposals: tuple[Proposal, ...]
    # How many entries of the answer were not a proposal in the form.
    malformed: int


@dataclass(frozen=True)
class Checked:
    kept: tuple[Proposal, ...]
    not_quoted: tuple[Proposal, ...]
    already_captured: tuple[Proposal, ...]
    # When the first prompt that holds its quote was typed, for each kept proposal in their order.
    kept_at: tuple[datetime.datetime, ...] = ()


def instruction() -> str:
    """What the model is asked to do with ``step_input``."""
    return INSTRUCTION.read_text(encoding="utf-8")


def step_input(
    sessions: Sequence[Session],
    distillate: str,
    zone: datetime.tzinfo = datetime.timezone.utc,
    examples: Examples = NO_EXAMPLES,
    waiting: Sequence[Example] = (),
) -> str:
    """The JSON document the model reads; ``zone`` is where the person is, for the day of a session.

    ``answered`` and ``waiting`` are in it also while they are empty: the instruction describes one
    form, and a model that sees empty lists knows that nothing was answered or waits yet.
    """
    given = [
        {
            "session": number,
            "folder": session.folder,
            "day": session.prompts[0].time.astimezone(zone).strftime("%A %Y-%m-%d"),
            "prompts": [_as_shown(prompt) for prompt in session.prompts],
        }
        for number, session in enumerate(sessions, start=1)
        if session.prompts
    ]
    answered = {
        "kept": [_as_given(example) for example in examples.kept],
        "dropped": [_as_given(example) for example in examples.dropped],
    }
    document = {
        "memory": distillate,
        "answered": answered,
        "waiting": [_as_given(example) for example in waiting],
        "sessions": given,
    }
    return json.dumps(document, ensure_ascii=False, indent=1)


def in_parts(sessions: Sequence[Session], length: int) -> tuple[Part, ...]:
    """The sessions parted by time, so that a part's prompts take up at most ``length`` characters of the input.

    A part holds the prompts of every session from its start up to the next part's, each session
    with its folder and in the order of its first prompt there; a prompt whose answers alone are
    longer than ``length`` is a part by itself, with as many of its first answers as fit. A session
    without a prompt is in no part.
    """
    said = sorted(
        ((prompt.time, number, prompt) for number, session in enumerate(sessions) for prompt in session.prompts),
        key=lambda each: (each[0], each[1]),
    )
    windows: list[list[tuple[int, Prompt]]] = []
    used = 0
    for _, number, whole in said:
        prompt = _fitting(whole, length)
        size = _size(prompt)
        if not windows or used + size > length:
            windows.append([])
            used = 0
        windows[-1].append((number, prompt))
        used += size
    return tuple(_part(sessions, window) for window in windows)


def _size(prompt: Prompt) -> int:
    return len(json.dumps(_as_shown(prompt), ensure_ascii=False))


def _fitting(prompt: Prompt, length: int) -> Prompt:
    """The prompt with as many of its first answers as fit in ``length`` characters of the input."""
    if _size(prompt) <= length:
        return prompt
    kept: list[str] = []
    for answer in prompt.answers:
        if _size(dataclasses.replace(prompt, answers=(*kept, answer))) > length:
            break
        kept.append(answer)
    return dataclasses.replace(prompt, answers=tuple(kept))


def _part(sessions: Sequence[Session], window: Sequence[tuple[int, Prompt]]) -> Part:
    prompts: dict[int, list[Prompt]] = {}
    for number, prompt in window:
        prompts.setdefault(number, []).append(prompt)
    parted = tuple(dataclasses.replace(sessions[number], prompts=tuple(own)) for number, own in prompts.items())
    return Part(window[0][1].time, parted)


def parse_answer(answer: str, sessions: Sequence[Session]) -> Answer:
    """The proposals in the model's answer; ``sessions`` is the sequence its input was built from."""
    proposals: list[Proposal] = []
    malformed = 0
    for entry in _entries(answer):
        proposal = _proposal(entry, sessions)
        if proposal is None:
            malformed += 1
        else:
            proposals.append(proposal)
    return Answer(tuple(proposals), malformed)


def check(proposals: Sequence[Proposal], sessions: Sequence[Session], captures: Sequence[str]) -> Checked:
    """Sorts the proposals by the two checks; ``captures`` are the texts captured in the period.

    A kept proposal says where its quote stands (``Proposal.source``): in what was typed, or else
    in what was pasted, or else in what Claude answered.
    """
    said = {
        session.session_id: [
            _Said(
                prompt.time,
                _collapsed(prompt.text),
                tuple(_collapsed(text) for text in prompt.pasted),
                tuple(_collapsed(text) for text in prompt.answers),
            )
            for prompt in session.prompts
        ]
        for session in sessions
    }
    # Only a capture adds in brackets; what the person typed in brackets are words of their prompt.
    captured = [(_bare(capture), _words(_ADDITION.sub(" ", capture))) for capture in captures]
    kept: list[Proposal] = []
    kept_at: list[datetime.datetime] = []
    not_quoted: list[Proposal] = []
    already_captured: list[Proposal] = []
    for proposal in proposals:
        quote = _collapsed(proposal.quote)
        stands_in = _where_it_stands(quote, said.get(proposal.session, ()))
        if len(quote.split()) < QUOTE_WORDS or stands_in is None:
            not_quoted.append(proposal)
        elif _is_captured(quote, stands_in.texts, captured):
            already_captured.append(proposal)
        else:
            kept.append(dataclasses.replace(proposal, source=stands_in.source))
            kept_at.append(stands_in.first_at)
    return Checked(tuple(kept), tuple(not_quoted), tuple(already_captured), tuple(kept_at))


@dataclass(frozen=True)
class _Said:
    """A prompt as ``check`` looks at it: when it was sent, what was typed, pasted and answered."""

    time: datetime.datetime
    typed: str
    pasted: tuple[str, ...]
    answers: tuple[str, ...]


@dataclass(frozen=True)
class _StandsIn:
    """Where a quote stands in a session: the texts that hold it and when the first was sent."""

    source: str
    texts: tuple[str, ...]
    first_at: datetime.datetime


def _where_it_stands(quote: str, prompts: Sequence[_Said]) -> _StandsIn | None:
    """In what was typed, else in what was pasted, else in an answer; None when the session holds the quote nowhere.

    An answer's time is that of the prompt it follows.
    """
    for source, texts_of in (
        (TYPED, lambda said: (said.typed,)),
        (PASTED, lambda said: said.pasted),
        (AGENT, lambda said: said.answers),
    ):
        found = [(text, said.time) for said in prompts for text in texts_of(said) if quote in text]
        if found:
            return _StandsIn(source, tuple(text for text, _ in found), found[0][1])
    return None


def _as_shown(prompt: Prompt) -> str | dict[str, Any]:
    """A prompt as the model reads it: its text, or what was typed, pasted and answered, kept apart."""
    if not prompt.pasted and not prompt.answers:
        return prompt.text
    shown: dict[str, Any] = {"typed": prompt.text}
    if prompt.pasted:
        shown["pasted"] = list(prompt.pasted)
    if prompt.answers:
        shown["claude_answers"] = list(prompt.answers)
    return shown


def _as_given(example: Example) -> dict[str, str]:
    return {"kind": example.kind, "text": example.text, "quote": example.quote}


def _entries(answer: str) -> list[Any]:
    """The list under ``proposals`` of the first JSON object in the answer that has one."""
    decoder = json.JSONDecoder()
    for start in (match.start() for match in re.finditer(r"\{", answer)):
        try:
            found, _ = decoder.raw_decode(answer, start)
        except ValueError:
            continue
        if isinstance(found, dict) and isinstance(found.get("proposals"), list):
            entries: list[Any] = found["proposals"]
            return entries
    raise GleanError("the answer holds no JSON object with a list of proposals")


def _proposal(entry: object, sessions: Sequence[Session]) -> Proposal | None:
    if not isinstance(entry, dict):
        return None
    kind, quote = entry.get("kind"), entry.get("quote")
    text, topic = _one_line(entry.get("text")), _one_line(entry.get("topic", ""))
    number = _session_number(entry.get("session"))
    try:
        due = _due(entry.get("due"))
    except ValueError:
        return None
    if kind not in KINDS or not isinstance(quote, str) or not quote.strip():
        return None
    if not text or len(text) > TEXT_LENGTH:
        return None
    # The topic is the name of a heading the model was shown, so one longer than a name may be
    # is the model's own text; cut short it would name no heading either.
    if topic is None or len(topic) > MAX_TOPIC_NAME:
        return None
    if number is None or not 1 <= number <= len(sessions):
        return None
    if unsafe_characters(text + quote + topic) or not can_be_written(text + quote + topic):
        return None
    return Proposal(kind, text, quote, sessions[number - 1].session_id, topic or None, due)


def _one_line(value: object) -> str | None:
    """The text with its white space collapsed; None when the value is neither a text nor nothing."""
    if value is None:
        return ""
    return _collapsed(value) if isinstance(value, str) else None


def _session_number(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return int(value) if isinstance(value, str) and value.isascii() and value.isdigit() else None


def _due(value: object) -> datetime.date | None:
    """The day, None for no day; a ValueError for a value that is neither."""
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not _DAY.fullmatch(value):
        raise ValueError(value)
    return datetime.date.fromisoformat(value)


def _collapsed(text: str) -> str:
    return " ".join(text.split())


def _bare(text: str) -> str:
    """Without case, extra white space and the punctuation at its ends, for comparing wordings."""
    return _collapsed(text).casefold().strip(_ENDS)


def captured_already(statements: Sequence[str], captures: Sequence[str]) -> bool:
    """Whether one of the captures says what one of the statements says, by the second check.

    For a proposal that comes without the prompt its quote stands in: each statement, the quote
    and the text, is compared with each capture as a quote is, and taken as the text a capture of
    it was worded from.
    """
    captured = [(_bare(capture), _words(_ADDITION.sub(" ", capture))) for capture in captures]
    return any(_is_captured(_collapsed(statement), (statement,), captured) for statement in statements)


def _is_captured(quote: str, quoted_from: Sequence[str], captured: Sequence[tuple[str, frozenset[str]]]) -> bool:
    """Whether one of the captures, each as its bare text and its words, says what the quote says."""
    bare = _bare(quote)
    return any(_same_words(bare, text) or _worded_anew(words, quote, quoted_from) for text, words in captured)


def _same_words(quote: str, capture: str) -> bool:
    return bool(capture) and (quote in capture or (len(capture.split()) >= QUOTE_WORDS and capture in quote))


def _words(text: str) -> frozenset[str]:
    """The different words of a text, without case."""
    return frozenset(_WORD.findall(text.casefold()))


def _worded_anew(capture: frozenset[str], quote: str, quoted_from: Sequence[str]) -> bool:
    """Whether the capture is the quote's statement, noted from the prompt the quote stands in."""
    if len(capture) < QUOTE_WORDS or not any(capture <= _words(prompt) for prompt in quoted_from):
        return False
    quoted = _words(quote)
    return len(capture & quoted) >= SAME_STATEMENT * min(len(capture), len(quoted))
