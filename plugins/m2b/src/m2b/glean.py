"""What a model may propose for the memory from what the person typed, and what code checks of it.

A step that reads a period's sessions (``sessions``) can find what belongs in the second brain
although nobody said "remember this": a person, an agreement with its day, a commitment, something
about the person's own life. This module is the part of such a step that is code: the input the
model gets, the form its answer must have, and two checks no instruction can replace.

The input is one JSON document: the distillate, so the model can leave out what is known already,
the proposals of earlier readings the person kept and those they dropped (``Examples``), those
that still wait for an answer (``waiting``), and per
session its folder, its day and every prompt whole, what was pasted into one apart from what was
typed, and beside it the end of Claude's answer before it and the Bash commands of that turn, which
are Claude's and never stand for the person's words. A session is named by a small number, its
place in the sequence the caller passes; the model repeats a number more reliably than an id, and
``parse_answer`` turns it back with the same sequence. JSON keeps a prompt one string whatever it
holds, so no typed text can pass as another session or as the memory, and no example as a session.

What this person keeps and drops says more about what to propose to them than a rule written for
everybody, so the model is shown it. An example is words of another period and no session: a
proposal that quotes one stands in no prompt, and ``check`` refuses it like any other.

A proposal carries the words it stands on, its ``quote``. ``check`` keeps a proposal only when the
quote stands, white space aside, in one prompt of the session it names, with at least
``QUOTE_WORDS`` words: fewer show nothing. The quote stands in what the person typed or in one text
they pasted into the prompt; ``check`` says which (``Proposal.source``), looking at what was typed
first, so pasted words are never shown as said. A proposal that fails is the model's wording and not
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

A session's ``written`` files go in only where its repository is a project of the memory (the
reading step leaves them out elsewhere), each by its path in that repository. A ``pointer`` names one
of them in ``file``; ``check`` keeps a pointer only when its file stands among its session's
``written``, so a decision written into no file of the repository points nowhere.

An answer that cannot be read is an error (``GleanError``), never an answer without proposals. A
single proposal that is not in the form is left out and counted.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from m2b import kept_lessons, lessons, remembered_corrections, session_remotes
from m2b.action_lessons import holds_word
from m2b.lessons import EVERY_PROJECT, THIS_PROJECT
from m2b.notes.characters import can_be_written, unsafe_characters
from m2b.notes.memory_index import MAX_TOPIC_NAME
from m2b.sessions import LeftOut, Prompt, Session

PERSON = "person"
AGREEMENT = "agreement"
COMMITMENT = "commitment"
PERSONAL = "personal"
# A correction of how Claude works that holds beyond the task, made in one session or the same in
# two: kept, it becomes a lesson (``lessons``).
LESSON = "lesson"
# A decision, an agreement, a person or a deadline of a project a session wrote into a file of its
# repository: kept, it becomes a line of the project's topic that points to that file.
POINTER = "pointer"
# What a model may propose from the words of a session.
READ_KINDS = (PERSON, AGREEMENT, COMMITMENT, PERSONAL, LESSON, POINTER)
# A repository the person worked in on two days and that has no topic: code proposes it from where
# the sessions worked (``project_proposals``), on no words, so no model is asked and none is shown it.
PROJECT = "project"
KINDS = (*READ_KINDS, PROJECT)
# The kinds that become a fact or a task, and what a session may hand in by itself. A lesson is not
# among them: before it is proposed, a reading checks it against the files every session loads and
# shows it beside what the person kept and dropped, which a session handing it in cannot do.
FACT_KINDS = (PERSON, AGREEMENT, COMMITMENT, PERSONAL)
HANDED_IN_KINDS = FACT_KINDS
# Whom a proposed lesson is for: every project, or the repository its sessions worked in, which the
# reading step names by its address (``curate.glean_step``).
LESSON_TARGETS = (EVERY_PROJECT, THIS_PROJECT)
# A word of a command an action lesson fires on, such as ``scripts/check`` or ``push``.
MAX_WORD = 60
# Where in a session a proposal's quote stands. What was pasted may be anyone's words. A reading
# finds a quote in a prompt only; a session that hands a proposal in can also stand on what a tool
# returned to it or on what Claude answered.
TYPED = "typed"
PASTED = "pasted"
TOOL = "tool"
AGENT = "agent"
# Where a project's proposal stands: the sessions that worked in its repository, its quote the
# repository's addresses.
WORKED = "worked"
# A proposal is one fact or one task; a longer text is a summary, which nobody asked for.
TEXT_LENGTH = 300
# What a single correction is about, in the model's words: a matter, not a lesson's text.
MATTER_LENGTH = 200
QUOTE_WORDS = 3
# The share of the shorter one's words a capture and a quote have in common when they say the same.
SAME_STATEMENT = 0.8
INSTRUCTION = Path(__file__).with_name("glean_instruction.md")
# The id of the session a remembered correction stands in for ``check``: an id of its own, since
# that session may go on in the period read, and the two must not be one session there.
EARLIER = "earlier:"

_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_ENDS = " .,;:!?\"'()"
_WORD = re.compile(r"\w+")
# What a note adds to a sentence that leans on its conversation: "He [Sam] brings the plywood."
# No bracket inside, so a long run of brackets that never close costs one pass, not one per bracket.
_ADDITION = re.compile(r"\[[^\[\]]*\]")


class GleanError(Exception):
    """The model's answer could not be read; that is not an answer without proposals."""


# What a source a session loads says of a proposed lesson (``lesson_sources``): wrongly, so the
# lesson is a fix of it; or rightly, so the lesson is a pointer to the line that states it.
FIX = "fix"
STATED = "stated"


@dataclass(frozen=True)
class AtSource:
    """A proposed lesson's source: the file as the person reads its name, the line a fix replaces or
    that states the lesson (None for a fix that adds), a fix's new wording, and where a fix is kept:
    its path in its repository with the repository's addresses, or from ``~`` with none."""

    verdict: str
    file: str
    line: str | None
    wording: str | None = None
    path: str | None = None
    repositories: tuple[str, ...] = ()


@dataclass(frozen=True)
class LessonPart:
    """What a proposed lesson carries beside its text: its kind and target, the words of the command
    for an action, and the same correction in a second session where it was made in two."""

    kind: str
    target: str
    words: tuple[str, ...]
    quote: str
    # The id of the second session; with ``quote`` empty where the lesson stands on one correction.
    session: str
    # What a source says of it, where one does; set by the reading step, never by the model's answer.
    at_source: AtSource | None = None
    # The kept lesson it would replace, where what every session starts with is past its target;
    # set by the reading step, never by the model's answer.
    replaces: str | None = None
    # For an action, the words of a command that already does what the person asked for, so the
    # lesson stays silent there (``--quick``): without them it would also stop the very command the
    # correction asked for. Kept only where they stand in its sessions (B295).
    unless: tuple[str, ...] = ()


@dataclass(frozen=True)
class PointerPart:
    """Where a proposed pointer points: a file its session wrote, by its path in the repository, and
    the addresses of that repository, which the reading step sets (``curate.glean_step``)."""

    path: str
    repositories: tuple[str, ...] = ()


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
    # For a lesson, and only for one.
    lesson: LessonPart | None = None
    # For a pointer, and only for one.
    pointer: PointerPart | None = None


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
class Correction:
    """A prompt that corrects Claude again on a lesson the person kept: the lesson's name, the words
    and the id of the session they were typed in."""

    lesson: str
    quote: str
    session: str


@dataclass(frozen=True)
class SingleCorrection:
    """A correction of how Claude works where the model cannot tell whether it holds beyond the task
    at hand: what it is about in the model's words, the person's words, the id of their session,
    and the kind and target a lesson of it would have. No lesson is proposed from it; code
    remembers it (``remembered_corrections``)."""

    matter: str
    quote: str
    session: str
    kind: str
    target: str


@dataclass(frozen=True)
class ShownLesson:
    """A lesson the person kept, as the model is shown it: its name, its text and the day it was kept."""

    name: str
    text: str
    kept: str


@dataclass(frozen=True)
class Answer:
    proposals: tuple[Proposal, ...]
    # How many entries of the answer were not a proposal in the form.
    malformed: int
    corrections: tuple[Correction, ...] = ()
    single_corrections: tuple[SingleCorrection, ...] = ()
    # How many entries under ``single_corrections`` were not in the form.
    singles_malformed: int = 0


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
    shown_lessons: Sequence[ShownLesson] = (),
    earlier: Sequence[remembered_corrections.Correction] = (),
) -> str:
    """The JSON document the model reads; ``zone`` is where the person is, for the day of a session.

    ``earlier`` are the corrections made in one session that earlier readings remembered, each by a
    number of its own, with its matter, its words, its day and the name of its repository; one whose
    session goes on in the period carries that session's number, so that the model does not take a
    session's correction and its repeat in that session for two.

    ``answered`` and ``waiting`` are in it also while they are empty: the instruction describes one
    form, and a model that sees empty lists knows that nothing was answered or waits yet.
    """
    given = [
        {
            "session": number,
            "folder": session.folder,
            "day": session.prompts[0].time.astimezone(zone).strftime("%A %Y-%m-%d"),
            "prompts": [_as_shown(prompt) for prompt in session.prompts],
            # Only where a pointer can be kept; the reading step leaves the files out elsewhere.
            **({"written": list(session.written)} if session.written else {}),
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
        # Only where there is one, so a reading without lessons is asked as before.
        **(
            {"lessons": [{"name": each.name, "text": each.text, "kept": each.kept} for each in shown_lessons]}
            if shown_lessons
            else {}
        ),
        **({"earlier_corrections": _earlier_shown(earlier, sessions)} if earlier else {}),
        "sessions": given,
    }
    return json.dumps(document, ensure_ascii=False, indent=1)


def _earlier_shown(
    earlier: Sequence[remembered_corrections.Correction], sessions: Sequence[Session]
) -> list[dict[str, Any]]:
    numbers = {session.session_id: number for number, session in enumerate(sessions, start=1) if session.prompts}
    return [
        {
            "number": number,
            "matter": correction.matter,
            "quote": correction.quote,
            "day": correction.day.strftime("%A %Y-%m-%d"),
            **({"repository": session_remotes.name_of(correction.addresses)} if correction.addresses else {}),
            **({"session": numbers[correction.session]} if correction.session in numbers else {}),
        }
        for number, correction in enumerate(earlier, start=1)
    ]


def earlier_sessions(earlier: Sequence[remembered_corrections.Correction]) -> tuple[Session, ...]:
    """Each remembered correction as a session of one prompt, its words typed on its day, with the
    commands of the turn they answered: so ``check`` holds a lesson's second quote and an action's
    words against it as against a session of the period."""
    return tuple(
        Session(
            earlier_session_id(correction),
            "",
            (
                Prompt(
                    datetime.datetime.combine(correction.day, datetime.time(12), datetime.timezone.utc),
                    correction.quote,
                    commands=correction.commands,
                ),
            ),
            LeftOut(0, 0, 0),
        )
        for correction in earlier
    )


def earlier_session_id(correction: remembered_corrections.Correction) -> str:
    return f"{EARLIER}{correction.id}"


def parse_answer(
    answer: str, sessions: Sequence[Session], earlier: Sequence[remembered_corrections.Correction] = ()
) -> Answer:
    """The proposals in the model's answer; ``sessions`` and ``earlier`` are the sequences its input
    was built from."""
    proposals: list[Proposal] = []
    malformed = 0
    found = _answer_object(answer)
    for entry in found["proposals"]:
        proposal = _proposal(entry, sessions, earlier)
        if proposal is None:
            malformed += 1
        else:
            proposals.append(proposal)
    given = found.get("corrected_again")
    corrections = [_correction(entry, sessions) for entry in (given if isinstance(given, list) else [])]
    given = found.get("single_corrections")
    singles = [_single_correction(entry, sessions) for entry in (given if isinstance(given, list) else [])]
    return Answer(
        tuple(proposals),
        malformed,
        tuple(each for each in corrections if each is not None),
        tuple(each for each in singles if each is not None),
        sum(each is None for each in singles),
    )


def checked_single_corrections(
    singles: Sequence[SingleCorrection], used: Sequence[tuple[str, str]], sessions: Sequence[Session]
) -> tuple[list[tuple[SingleCorrection, Prompt]], int]:
    """The single corrections whose quote, at least ``QUOTE_WORDS`` words, stands in what the person
    typed in its session, each with the first prompt that holds it, and how many were refused.

    ``used`` are the session and the words of each correction a kept lesson or a counted correction
    of a kept lesson stands on. A single correction among them is left out and not counted: the
    model judged it already, so it is no unsure correction.
    """
    by_id = {session.session_id: session for session in sessions}
    kept: list[tuple[SingleCorrection, Prompt]] = []
    refused = 0
    for single in singles:
        if any(session == single.session and _overlap(quote, single.quote) for session, quote in used):
            continue
        typed = _typed_in(single.quote, by_id.get(single.session))
        if not typed or len(_collapsed(single.quote).split()) < QUOTE_WORDS:
            refused += 1
            continue
        kept.append((single, typed[0]))
    return kept, refused


def _overlap(first: str, second: str) -> bool:
    one, other = _collapsed(first), _collapsed(second)
    return bool(one and other) and (one in other or other in one)


def _single_correction(entry: object, sessions: Sequence[Session]) -> SingleCorrection | None:
    if not isinstance(entry, dict):
        return None
    matter, quote = _one_line(entry.get("matter")), entry.get("quote")
    kind, target, number = entry.get("kind"), entry.get("target"), _session_number(entry.get("session"))
    if not matter or len(matter) > MATTER_LENGTH or not isinstance(quote, str) or not quote.strip():
        return None
    if kind not in lessons.KINDS or target not in LESSON_TARGETS:
        return None
    if number is None or not 1 <= number <= len(sessions):
        return None
    if unsafe_characters(matter + quote) or not can_be_written(matter + quote):
        return None
    return SingleCorrection(matter, quote, sessions[number - 1].session_id, str(kind), str(target))


def checked_corrections(
    corrections: Sequence[Correction], sessions: Sequence[Session], kept: Sequence[ShownLesson], zone: datetime.tzinfo
) -> list[Correction]:
    """The corrections whose lesson the person kept and whose quote, at least ``QUOTE_WORDS`` words,
    stands in what they typed in its session after the day the lesson was kept. A lesson is kept by
    the day, so a prompt of that day may be the correction it was kept from."""
    by_id = {session.session_id: session for session in sessions}
    days = {lesson.name: lesson.kept for lesson in kept}
    found = []
    for correction in corrections:
        kept_on = days.get(correction.lesson)
        if kept_on is None or len(_collapsed(correction.quote).split()) < QUOTE_WORDS:
            continue
        typed = _typed_in(correction.quote, by_id.get(correction.session))
        if any(prompt.time.astimezone(zone).date().isoformat() > kept_on for prompt in typed):
            found.append(correction)
    return found


def _correction(entry: object, sessions: Sequence[Session]) -> Correction | None:
    if not isinstance(entry, dict):
        return None
    lesson, quote, number = entry.get("lesson"), entry.get("quote"), _session_number(entry.get("session"))
    if not isinstance(lesson, str) or not isinstance(quote, str) or not quote.strip():
        return None
    if number is None or not 1 <= number <= len(sessions):
        return None
    return Correction(lesson, quote, sessions[number - 1].session_id)


def check(proposals: Sequence[Proposal], sessions: Sequence[Session], captures: Sequence[str]) -> Checked:
    """Sorts the proposals by the two checks; ``captures`` are the texts captured in the period.

    A kept proposal says where its quote stands (``Proposal.source``): in what was typed, or else
    in what was pasted. A lesson is a correction of Claude, so its quote must stand in what was
    typed, and so must a second one in its own session where the lesson has one, and for an action
    every word in a command of the turn one of them answers (``Prompt.commands``); a lesson that
    fails is counted with ``not_quoted``.
    """
    said = {
        session.session_id: [
            (prompt.time, _collapsed(prompt.text), [_collapsed(text) for text in prompt.pasted])
            for prompt in session.prompts
        ]
        for session in sessions
    }
    by_id = {session.session_id: session for session in sessions}
    # Only a capture adds in brackets; what the person typed in brackets are words of their prompt.
    captured = [(_bare(capture), _words(_ADDITION.sub(" ", capture))) for capture in captures]
    kept: list[Proposal] = []
    kept_at: list[datetime.datetime] = []
    not_quoted: list[Proposal] = []
    already_captured: list[Proposal] = []
    for proposal in proposals:
        quote = _collapsed(proposal.quote)
        stands_in = _where_it_stands(quote, said.get(proposal.session, ()))
        stands = stands_in is not None and len(quote.split()) >= QUOTE_WORDS
        if stands and proposal.lesson is not None:
            stands = stands_in is not None and _lesson_stands(proposal, stands_in.source, by_id)
        if stands and proposal.pointer is not None:
            # A pointer points to what its session wrote, or it points nowhere.
            session = by_id.get(proposal.session)
            stands = session is not None and proposal.pointer.path in session.written
        if not stands or stands_in is None:
            not_quoted.append(proposal)
        elif _is_captured(quote, stands_in.texts, captured):
            already_captured.append(proposal)
        else:
            kept.append(dataclasses.replace(_with_standing_unless(proposal, by_id), source=stands_in.source))
            kept_at.append(stands_in.first_at)
    return Checked(tuple(kept), tuple(not_quoted), tuple(already_captured), tuple(kept_at))


def _lesson_stands(proposal: Proposal, source: str, sessions: Mapping[str, Session]) -> bool:
    """Whether a lesson's quotes stand typed in their sessions, the second where there is one, and an
    action's words in a command of a turn one of them answers."""
    lesson = proposal.lesson
    assert lesson is not None
    first = _typed_in(proposal.quote, sessions.get(proposal.session))
    second = _typed_in(lesson.quote, sessions.get(lesson.session)) if lesson.session else []
    if source != TYPED or not first:
        return False
    if lesson.session and (not second or len(lesson.quote.split()) < QUOTE_WORDS):
        return False
    if lesson.kind != lessons.ACTION:
        return True
    commands = [command for prompt in (*first, *second) for command in prompt.commands]
    return any(all(holds_word(command, word) for word in lesson.words) for command in commands)


def _with_standing_unless(proposal: Proposal, sessions: Mapping[str, Session]) -> Proposal:
    """The proposal with only those of its lesson's ``unless`` words that stand in what the person
    typed or in a command of either session, and not inside the lesson's own words: words the model
    made up would silence it elsewhere, and one of its own words would silence it everywhere."""
    lesson = proposal.lesson
    if lesson is None or not lesson.unless:
        return proposal
    prompts = [
        prompt for session_id in (proposal.session, lesson.session) for prompt in _prompts_of(sessions, session_id)
    ]
    texts = [prompt.text for prompt in prompts] + [command for prompt in prompts for command in prompt.commands]
    # A word inside the lesson's own words stands in every command it fires on and would silence it.
    standing = tuple(
        word
        for word in lesson.unless
        if any(holds_word(text, word) for text in texts) and not any(holds_word(own, word) for own in lesson.words)
    )
    return dataclasses.replace(proposal, lesson=dataclasses.replace(lesson, unless=standing))


def _prompts_of(sessions: Mapping[str, Session], session_id: str) -> tuple[Prompt, ...]:
    session = sessions.get(session_id)
    return session.prompts if session else ()


def _typed_in(quote: str, session: Session | None) -> list[Prompt]:
    """The prompts of the session whose typed text holds the quote, white space aside."""
    wanted = _collapsed(quote)
    return [prompt for prompt in (session.prompts if session else ()) if wanted and wanted in _collapsed(prompt.text)]


@dataclass(frozen=True)
class _StandsIn:
    """Where a quote stands in a session: the texts that hold it and when the first was sent."""

    source: str
    texts: tuple[str, ...]
    first_at: datetime.datetime


def _where_it_stands(quote: str, prompts: Sequence[tuple[datetime.datetime, str, Sequence[str]]]) -> _StandsIn | None:
    """In what was typed, or else in what was pasted; None when no prompt of the session holds the quote."""
    typed = [(text, time) for time, text, _ in prompts if quote in text]
    if typed:
        return _StandsIn(TYPED, tuple(text for text, _ in typed), typed[0][1])
    pasted = [(text, time) for time, _, texts in prompts for text in texts if quote in text]
    if pasted:
        return _StandsIn(PASTED, tuple(text for text, _ in pasted), pasted[0][1])
    return None


def _as_shown(prompt: Prompt) -> str | dict[str, Any]:
    """A prompt as the model reads it: its text, or what was typed, what was pasted and the turn it
    answers (the end of Claude's answer before it, the Bash commands of that turn), kept apart."""
    if not (prompt.pasted or prompt.answer_before or prompt.commands):
        return prompt.text
    shown: dict[str, Any] = {"typed": prompt.text}
    if prompt.pasted:
        shown["pasted"] = list(prompt.pasted)
    if prompt.answer_before:
        shown["answer_before"] = prompt.answer_before
    if prompt.commands:
        shown["commands"] = list(prompt.commands)
    return shown


def _as_given(example: Example) -> dict[str, str]:
    return {"kind": example.kind, "text": example.text, "quote": example.quote}


def _answer_object(answer: str) -> dict[str, Any]:
    """The first JSON object in the answer that has a list under ``proposals``."""
    decoder = json.JSONDecoder()
    for start in (match.start() for match in re.finditer(r"\{", answer)):
        try:
            found, _ = decoder.raw_decode(answer, start)
        except ValueError:
            continue
        if isinstance(found, dict) and isinstance(found.get("proposals"), list):
            return found
    raise GleanError("the answer holds no JSON object with a list of proposals")


def _proposal(
    entry: object, sessions: Sequence[Session], earlier: Sequence[remembered_corrections.Correction] = ()
) -> Proposal | None:
    if not isinstance(entry, dict):
        return None
    kind, quote = entry.get("kind"), entry.get("quote")
    text, topic = _one_line(entry.get("text")), _one_line(entry.get("topic", ""))
    number = _session_number(entry.get("session"))
    try:
        due = _due(entry.get("due"))
    except ValueError:
        return None
    if kind not in READ_KINDS or not isinstance(quote, str) or not quote.strip():
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
    session_id = sessions[number - 1].session_id
    if kind == POINTER:
        path = entry.get("file")
        if not isinstance(path, str) or not path.strip() or due is not None or not can_be_written(path):
            return None
        # The topic is the project's, which code knows; the model names none.
        return Proposal(kind, text, quote, session_id, pointer=PointerPart(path))
    if kind != LESSON:
        return Proposal(kind, text, quote, session_id, topic or None, due)
    lesson = _lesson_part(entry.get("lesson"), sessions, earlier)
    if lesson is None or (lesson.session and lesson.session == session_id) or due is not None:
        return None
    # A remembered correction of the session the first quote stands in is that session's own
    # correction again: no second session.
    if any(lesson.session == earlier_session_id(each) and each.session == session_id for each in earlier):
        return None
    return Proposal(kind, text, quote, session_id, topic or None, None, lesson=lesson)


def _lesson_part(
    value: object, sessions: Sequence[Session], earlier: Sequence[remembered_corrections.Correction] = ()
) -> LessonPart | None:
    """The part of a lesson's entry beside its text; None for one that is not in the form.

    A lesson stands on one correction, or on the same correction a second time: in another session
    of the period by its ``quote`` and ``session``, given together or not at all, or remembered by an
    earlier reading by its number under ``earlier``; then its words are the remembered ones, copied
    by code.
    """
    if not isinstance(value, dict):
        return None
    kind, target = value.get("kind"), value.get("target")
    words = value.get("words", [])
    if kind not in lessons.KINDS or target not in LESSON_TARGETS:
        return None
    second = ""
    # A model fills a field it does not use with null, as it does for ``topic`` and ``due``.
    if value.get("earlier") is not None:
        number = _session_number(value.get("earlier"))
        if number is None or not 1 <= number <= len(earlier):
            return None
        quote: object = earlier[number - 1].quote
        second = earlier_session_id(earlier[number - 1])
    else:
        quote, number = value.get("quote"), _session_number(value.get("session"))
        if quote in (None, "") and value.get("session") is None:
            quote = ""
        elif isinstance(quote, str) and quote.strip() and number is not None and 1 <= number <= len(sessions):
            second = sessions[number - 1].session_id
        else:
            return None
    if not isinstance(quote, str):
        return None
    if not isinstance(words, list) or not all(isinstance(word, str) for word in words):
        return None
    cleaned = tuple(dict.fromkeys(" ".join(word.split()) for word in words if word.strip()))
    if (kind == lessons.ACTION) != bool(cleaned) or len(cleaned) > kept_lessons.MAX_WORDS:
        return None
    if any(len(word) > MAX_WORD for word in cleaned):
        return None
    said = quote + "".join(cleaned)
    if unsafe_characters(said) or not can_be_written(said):
        return None
    unless = _silencing_words(value.get("unless", [])) if kind == lessons.ACTION else ()
    return LessonPart(kind, target, cleaned, quote, second, unless=unless)


def _silencing_words(value: object) -> tuple[str, ...]:
    """A lesson's ``unless`` as the model wrote it, or none where it is not in the form: they only
    narrow the lesson, so words the step cannot use leave it as it is instead of failing it."""
    if not isinstance(value, list) or not all(isinstance(word, str) for word in value):
        return ()
    cleaned = tuple(dict.fromkeys(" ".join(word.split()) for word in value if word.strip()))
    if len(cleaned) > kept_lessons.MAX_WORDS or any(len(word) > MAX_WORD for word in cleaned):
        return ()
    said = "".join(cleaned)
    # A kept lesson refuses these in its words, and the lesson the person kept would wait forever.
    if unsafe_characters(said) or not can_be_written(said) or any(mark in said for mark in ",[]"):
        return ()
    return cleaned


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
