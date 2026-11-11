"""What a model may propose for the memory from what the person typed, and what code checks of it.

A step that reads a period's sessions (``sessions``) can find what belongs in the second brain
although nobody said "remember this": a person, an agreement with its day, a commitment, something
about the person's own life. This module is the part of such a step that is code: the input the
model gets, the form its answer must have, and two checks no instruction can replace.

The input is one JSON document: the distillate, so the model can leave out what is known already,
and per session its folder, its day and every prompt whole. A session is named by a small number,
its place in the sequence the caller passes; the model repeats a number more reliably than an id,
and ``parse_answer`` turns it back with the same sequence. JSON keeps a prompt one string whatever
it holds, so no typed text can pass as another session or as the memory.

A proposal carries the words it stands on, its ``quote``. ``check`` keeps a proposal only when the
quote stands, white space aside, in one prompt of the session it names, with at least
``QUOTE_WORDS`` words: fewer show nothing. A proposal that fails is the model's wording and not
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

The instruction the model is asked with is ``glean_instruction.md`` beside this module. It is the
prompt of a run without tools (``curate.model.text_step``), not a skill: no session can call it.

An answer that cannot be read is an error (``GleanError``), never an answer without proposals. A
single proposal that is not in the form is left out and counted.
"""

from __future__ import annotations

import datetime
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from m2b.notes.characters import unsafe_characters
from m2b.sessions import Session

PERSON = "person"
AGREEMENT = "agreement"
COMMITMENT = "commitment"
PERSONAL = "personal"
KINDS = (PERSON, AGREEMENT, COMMITMENT, PERSONAL)
# A proposal is one fact or one task; a longer text is a summary, which nobody asked for.
TEXT_LENGTH = 300
QUOTE_WORDS = 3
# The share of the shorter one's words a capture and a quote have in common when they say the same.
SAME_STATEMENT = 0.8
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


def instruction() -> str:
    """What the model is asked to do with ``step_input``."""
    return INSTRUCTION.read_text(encoding="utf-8")


def step_input(sessions: Sequence[Session], distillate: str, zone: datetime.tzinfo = datetime.timezone.utc) -> str:
    """The JSON document the model reads; ``zone`` is where the person is, for the day of a session."""
    given = [
        {
            "session": number,
            "folder": session.folder,
            "day": session.prompts[0].time.astimezone(zone).strftime("%A %Y-%m-%d"),
            "prompts": [prompt.text for prompt in session.prompts],
        }
        for number, session in enumerate(sessions, start=1)
        if session.prompts
    ]
    return json.dumps({"memory": distillate, "sessions": given}, ensure_ascii=False, indent=1)


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
    """Sorts the proposals by the two checks; ``captures`` are the texts captured in the period."""
    typed = {session.session_id: [_collapsed(prompt.text) for prompt in session.prompts] for session in sessions}
    # Only a capture adds in brackets; what the person typed in brackets are words of their prompt.
    captured = [(_bare(capture), _words(_ADDITION.sub(" ", capture))) for capture in captures]
    kept: list[Proposal] = []
    not_quoted: list[Proposal] = []
    already_captured: list[Proposal] = []
    for proposal in proposals:
        quote = _collapsed(proposal.quote)
        quoted_from = [prompt for prompt in typed.get(proposal.session, ()) if quote in prompt]
        if len(quote.split()) < QUOTE_WORDS or not quoted_from:
            not_quoted.append(proposal)
        elif _is_captured(quote, quoted_from, captured):
            already_captured.append(proposal)
        else:
            kept.append(proposal)
    return Checked(tuple(kept), tuple(not_quoted), tuple(already_captured))


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
    if not text or len(text) > TEXT_LENGTH or topic is None:
        return None
    if number is None or not 1 <= number <= len(sessions):
        return None
    if unsafe_characters(text + quote + topic) or not _can_be_written(text + quote + topic):
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


def _can_be_written(text: str) -> bool:
    """False for half a character (a lone surrogate), which a model's escape can leave in its answer."""
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _collapsed(text: str) -> str:
    return " ".join(text.split())


def _bare(text: str) -> str:
    """Without case, extra white space and the punctuation at its ends, for comparing wordings."""
    return _collapsed(text).casefold().strip(_ENDS)


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
