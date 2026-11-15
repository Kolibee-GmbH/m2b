"""What the person typed in Claude Code, session by session, read from its transcripts.

Claude Code writes each session as a JSON Lines file and marks on every prompt who sent it. A
prompt is the person's when its ``origin`` is ``human``: typed in the terminal or in the desktop
app, also while Claude was busy. What is not the person speaking is left out and counted per
session: what a sender other than a human sent, such as a plugin or a finished task; a suggested
prompt the person only accepted, whose wording is the model's; and text without the mark, which a
Claude Code older than the one m2b asks for writes. So a day read with such a Claude Code shows as
unmarked prompts, not as a day on which nothing was said. What Claude Code writes in the user's
place for itself is left out without a count: records it flags as its own (a skill's text, the
summary after a context cut, another agent's message), a subagent's conversation, tool results,
the output of a local command.

Of a prompt goes what was typed and, apart from it, what was pasted into it, block by block
(``Prompt.pasted``). A longer text the person wrote elsewhere arrives as a pasted block, and so
does a mail, a document, an agent's text or a command's output: what was pasted may be anyone's
words, so it never passes as typed, and whoever proposes from it says so. The blocks Claude Code
writes into a prompt (``claude_code.PROMPT_BLOCK``: its reminders, the output of hooks) are left
out. Credentials are redacted (``redaction``), white space is collapsed, and a prompt ends after
``PROMPT_LENGTH`` characters, which keeps nearly every typed prompt whole: the typed text comes
first and the pasted texts get what is left, so a paste pushes out no typed word. No answer of
Claude and no tool result is read: text from web pages, mails and documents stands there.

A slash command is only its name. Its record names no source and often no origin, so it is taken
by its form, a record that starts with the command's tags, unless its origin is another sender.

A transcript with any record of a headless run is left out whole, so a curation run or a check
never reads itself. A session's folder is the one it started in; a transcript with prompts of the
period that names no folder is reported as not read. Only transcripts written since the period
began are opened.
"""

from __future__ import annotations

import datetime
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from m2b.claude_code import HUMAN, PROMPT_BLOCK, sender_of
from m2b.redaction import REDACTED, is_removed_behind, redact

PROMPT_LENGTH = 2000

_HEADLESS = "sdk-cli"
_SUGGESTION = "suggestion_accepted"
# What Claude Code writes into the transcript when the person stops a turn.
_INTERRUPTED = "[Request interrupted"
# A command's record starts with its tags; the same tags further in are text about a command.
_COMMAND = re.compile(
    r"\A\s*(?:<command-message>[^<]*</command-message>\s*)?<command-name>\s*/?([^<\s]+)\s*</command-name>"
)
# A text that is one block from its first to its last character: a local command's output, a shell
# line typed with "!". Claude Code wrote it, nobody typed it as a prompt.
_WRAPPED = re.compile(r"^\s*<([a-zA-Z][\w-]*)[^>]*>.*</\1>\s*$", re.S)
_BLOCK_OPENS = re.compile(r"\s*<([a-zA-Z][\w-]*)[^>]*>")
_ONLY_SPACE = re.compile(r"\s*\Z")
# The closing tag repeats the opening tag's id, so a closing tag inside the pasted text ends nothing.
_PASTED_BLOCK = re.compile(r"<pasted_content\b([^>]*)>(.*?)</pasted_content\1>", re.S)
_PASTED_UNCLOSED = re.compile(r"<pasted_content\b[^>]*>(.*)", re.S)
# A paste that was taken out is marked by its number between two of one of these characters, the
# first the text does not hold. The patterns here read each as they read a space: it is no part of
# a word or of a tag's name, and not the ">" a tag ends with.
_MARK_EDGES = "\x00\x01\x02\x03\x04\x05\x06\x07\x08"
_PASTE_OPENS = "<pasted_content"
_FIRST_WORD = re.compile(r"\S+")
_WORD_AT_START = re.compile(r"\A\S*")
# How much of the typed text before a paste can hold the name of a credential the paste begins with.
_NAME_BEFORE_A_PASTE = 200
# Redaction runs on this much of the text, so its patterns stay fast on a long prompt; the word at
# the far edge, which may be cut, is dropped. White space and redaction shrink the piece before the
# cut, so it reaches well past the kept part. A piece without any white space goes whole: it is a
# blob, not a sentence.
_REDACT_WINDOW = 8 * 1024
_LAST_WORD = re.compile(r"\S*\Z")
# A paste is looked at this far, one without its end too. Finding the blocks Claude Code wrote
# costs more than a text's length when it is full of opening tags that never close, and what a
# prompt keeps of a paste stands at its start. A block that closes behind this part stays as text.
_PASTE_WINDOW = 8 * _REDACT_WINDOW


class SessionsError(Exception):
    """The transcripts could not be looked at; that is not a period without sessions."""


@dataclass(frozen=True)
class Prompt:
    time: datetime.datetime
    # What the person typed; empty for a prompt that is pasted text only.
    text: str
    # What they pasted into it, block by block: their own words written elsewhere, or anyone's.
    pasted: tuple[str, ...] = ()


@dataclass(frozen=True)
class LeftOut:
    """What of a session's period is not among its prompts, counted."""

    sent_by_others: int
    suggested: int
    unmarked: int


@dataclass(frozen=True)
class Session:
    session_id: str
    folder: str
    prompts: tuple[Prompt, ...]
    left_out: LeftOut


@dataclass(frozen=True)
class Sessions:
    sessions: tuple[Session, ...]
    # Transcripts that could not be read, as ``<project folder>/<file>``.
    unreadable: tuple[str, ...]


def read_sessions(folder: Path, start: datetime.datetime, end: datetime.datetime) -> Sessions:
    """The sessions with a prompt or a counted text in ``[start, end)``, in the order of their first one."""
    if not folder.is_dir():
        raise SessionsError(f"no Claude Code transcripts in {folder}")
    found: list[tuple[datetime.datetime, Session]] = []
    unreadable: list[str] = []
    try:
        paths = sorted(folder.glob("*/*.jsonl"))
    except OSError as error:
        raise SessionsError(f"cannot list the transcripts in {folder}: {error}") from error
    for path in paths:
        try:
            if datetime.datetime.fromtimestamp(path.stat().st_mtime, datetime.timezone.utc) < start:
                continue
            reading = _read(path, start, end)
        except (OSError, _NoFolder):
            unreadable.append(f"{path.parent.name}/{path.name}")
            continue
        if reading.first is not None:
            found.append((reading.first, reading.session()))
    found.sort(key=lambda started_and_session: started_and_session[0])
    return Sessions(tuple(session for _, session in found), tuple(unreadable))


class _NoFolder(Exception):
    """A transcript has prompts of the period and no record that names the session's folder."""


@dataclass
class _Reading:
    """One transcript while it is read; ``first`` is the time of its first prompt or counted text."""

    session_id: str
    folder: str = ""
    first: datetime.datetime | None = None
    prompts: list[Prompt] = field(default_factory=list)
    sent_by_others: int = 0
    suggested: int = 0
    unmarked: int = 0

    def session(self) -> Session:
        left_out = LeftOut(self.sent_by_others, self.suggested, self.unmarked)
        return Session(self.session_id, self.folder, tuple(self.prompts), left_out)


def _read(path: Path, start: datetime.datetime, end: datetime.datetime) -> _Reading:
    """What ``path`` holds of the period; a reading without a ``first`` when that is nothing."""
    folder: str | None = None
    reading = _Reading(path.stem)
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                record: Any = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            if record.get("entrypoint") == _HEADLESS:
                return _Reading(path.stem)
            # The first folder is where the session started; later records follow the Bash tool's `cd`.
            if folder is None and isinstance(record.get("cwd"), str):
                folder = record["cwd"]
            moment = _time(record.get("timestamp"))
            if moment is None or not start <= moment < end or not _may_be_a_prompt(record):
                continue
            if _take(record, moment, reading):
                reading.first = reading.first or moment
    if reading.first is not None and folder is None:
        raise _NoFolder(path.name)
    reading.folder = folder or ""
    return reading


def _may_be_a_prompt(record: Mapping[str, Any]) -> bool:
    """A record of the main conversation in the user's place that Claude Code did not write itself."""
    flags = ("isMeta", "isCompactSummary", "isSidechain")
    return record.get("type") == "user" and not any(record.get(flag) for flag in flags)


def _is_only_blocks(text: str) -> bool:
    """Whether the text is blocks one after another and nothing else, as the output of a shell line is.

    A shell line's output comes as its standard output and its standard error, each in a block of
    its own. Each block ends at the first closing tag of its name: a walk from the front, in one
    pass however long the text is.
    """
    position = 0
    while True:
        opening = _BLOCK_OPENS.match(text, position)
        if opening is None:
            return False
        closing = f"</{opening.group(1)}>"
        end = text.find(closing, opening.end())
        if end < 0:
            return False
        position = end + len(closing)
        if _ONLY_SPACE.match(text, position):
            return True


def _take(record: Mapping[str, Any], moment: datetime.datetime, reading: _Reading) -> bool:
    """Adds the record to ``reading`` as a prompt or a count; False when it is neither."""
    message = record.get("message")
    text = _text_of(message.get("content") if isinstance(message, dict) else None)
    if text is None:
        return False
    sender = sender_of(record)
    source = record.get("promptSource")
    # A slash command's record names no source; a typed prompt that starts with the tags has one.
    command = _COMMAND.match(text) if source is None else None
    if sender not in (None, HUMAN):
        reading.sent_by_others += 1
    elif command is not None:
        reading.prompts.append(Prompt(moment, f"/{command.group(1)}"))
    elif sender is None:
        if _WRAPPED.match(text) or _is_only_blocks(text) or text.lstrip().startswith(_INTERRUPTED):
            return False
        reading.unmarked += 1
    elif source == _SUGGESTION:
        reading.suggested += 1
    else:
        shown = _shown(_typed(text))
        pasted = _as_far_as_fits(_pasted(text), PROMPT_LENGTH - len(shown))
        if not shown and not pasted:
            return False
        reading.prompts.append(Prompt(moment, shown, pasted))
    return True


def _typed(text: str) -> str:
    """What was typed: the steps that found it before a paste was kept, so nothing pasted stands in it.

    Every paste goes, then the rest of the prompt from a paste without its end, since nothing after
    its start can be told from the pasted text, then the blocks Claude Code wrote.
    """
    text = _PASTED_BLOCK.sub(" ", text)
    text = _PASTED_UNCLOSED.sub(" ", text)
    return PROMPT_BLOCK.sub(" ", text)


def _pasted(text: str) -> list[str]:
    """What was pasted into the prompt, block by block in their order.

    The steps of ``_typed`` once more, with a mark where a paste stood; the marks that are left at
    the end name what was pasted. So a block of Claude Code's takes the pastes in it with it. A
    paste without its end holds whatever stood behind its start, later pastes too; where a block
    of Claude Code's holds that start, the block goes whole and what stood behind it is nobody's.
    A text that holds every character a mark is made with has no paste read.

    A credential whose name was typed and whose value begins the paste goes like one typed whole.
    """
    edge = next((character for character in _MARK_EDGES if character not in text), None)
    if edge is None or _PASTE_OPENS not in text:
        return []
    mark = re.compile(rf"{edge}(\d+){edge}")
    pastes: list[str] = []
    as_written: list[str] = []

    def marked_as(paste: str) -> str:
        pastes.append(paste)
        return f"{edge}{len(pastes) - 1}{edge}"

    def taken_out(paste: re.Match[str]) -> str:
        as_written.append(paste.group(0))
        return marked_as(paste.group(2))

    marked = _PASTED_BLOCK.sub(taken_out, text)
    unclosed = _PASTED_UNCLOSED.search(marked)
    if unclosed is not None:
        opens_at = unclosed.start()
        looked_at = marked[: opens_at + _PASTE_WINDOW]
        around = next(
            (block for block in PROMPT_BLOCK.finditer(looked_at) if block.start() < opens_at < block.end()), None
        )
        if around is not None:
            marked = marked[: around.end()]
        else:
            rest = mark.sub(lambda taken: as_written[int(taken.group(1))], unclosed.group(1))
            marked = marked[:opens_at] + marked_as(rest)
    marked = PROMPT_BLOCK.sub(" ", marked)
    pasted = []
    typed_from = 0
    for taken in mark.finditer(marked):
        typed_before = _end_of(marked[typed_from : taken.start()], _NAME_BEFORE_A_PASTE)
        pasted.append(_without_a_value_named_before(pastes[int(taken.group(1))], typed_before))
        typed_from = taken.end()
    return pasted


def _without_a_value_named_before(paste: str, typed_before: str) -> str:
    """``paste`` without its first word where the text typed right before it makes that a credential."""
    first = _FIRST_WORD.search(paste)
    if first is None:
        return paste
    space = paste[: first.start()]
    if not is_removed_behind(typed_before + space, first.group(0)[:_REDACT_WINDOW]):
        return paste
    return f"{space}{REDACTED}{paste[first.end() :]}"


def _as_far_as_fits(blocks: Sequence[str], room: int) -> tuple[str, ...]:
    """The pasted texts as a prompt shows them, in the room what was typed leaves of its length."""
    fitting = []
    for block in blocks:
        if room <= 0:
            break
        shown = _shown(PROMPT_BLOCK.sub(" ", _start_of(block, _PASTE_WINDOW)))[:room]
        if shown:
            fitting.append(shown)
            room -= len(shown)
    return tuple(fitting)


def _shown(text: str) -> str:
    # A transcript can hold half a character (a lone surrogate); as a question mark the text can be
    # written and sent like any other.
    text = text.encode("utf-8", errors="replace").decode("utf-8")
    return " ".join(redact(_start_of(text, _REDACT_WINDOW)).split())[:PROMPT_LENGTH]


def _start_of(text: str, length: int) -> str:
    """The first ``length`` characters of ``text``, without the word a cut there went through."""
    return text if len(text) <= length else _LAST_WORD.sub("", text[:length])


def _end_of(text: str, length: int) -> str:
    """The last ``length`` characters of ``text``, without the word a cut there went through."""
    return text if len(text) <= length else _WORD_AT_START.sub("", text[-length:])


def _text_of(content: object) -> str | None:
    if isinstance(content, list):
        parts = [part.get("text") for part in content if isinstance(part, dict) and part.get("type") == "text"]
        content = "\n".join(part for part in parts if isinstance(part, str))
    return content if isinstance(content, str) and content.strip() else None


def _time(value: object) -> datetime.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None
