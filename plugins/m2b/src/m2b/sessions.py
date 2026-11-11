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

Of a prompt goes what was typed. A pasted block is left out with what it holds: a mail or a
document is what a third party wrote, and counting it as the person's words would file it as
theirs. The blocks Claude Code writes into a prompt (``claude_code.PROMPT_BLOCK``: its reminders,
the output of hooks) go the same way. Credentials are redacted (``redaction``), white space is
collapsed, and the text ends after ``PROMPT_LENGTH`` characters, which keeps nearly every typed
prompt whole. No answer of Claude and no tool result is read: text from web pages, mails and
documents stands there.

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
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from m2b.claude_code import PROMPT_BLOCK
from m2b.redaction import redact

PROMPT_LENGTH = 2000

_HEADLESS = "sdk-cli"
_HUMAN = "human"
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
# The closing tag repeats the opening tag's id, so a closing tag inside the pasted text ends nothing.
_PASTED_BLOCK = re.compile(r"<pasted_content\b([^>]*)>.*?</pasted_content\1>", re.S)
_PASTED_UNCLOSED = re.compile(r"<pasted_content\b[^>]*>.*", re.S)
# Redaction runs on this much of the text, so its patterns stay fast on a long prompt; the word at
# the far edge, which may be cut, is dropped. White space and redaction shrink the piece before the
# cut, so it reaches well past the kept part. A piece without any white space goes whole: it is a
# blob, not a sentence.
_REDACT_WINDOW = 8 * 1024
_LAST_WORD = re.compile(r"\S*\Z")


class SessionsError(Exception):
    """The transcripts could not be looked at; that is not a period without sessions."""


@dataclass(frozen=True)
class Prompt:
    time: datetime.datetime
    text: str


@dataclass(frozen=True)
class LeftOut:
    """What of a session's period is not among its prompts, counted."""

    pasted_blocks: int
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
    pasted_blocks: int = 0
    sent_by_others: int = 0
    suggested: int = 0
    unmarked: int = 0

    def session(self) -> Session:
        left_out = LeftOut(self.pasted_blocks, self.sent_by_others, self.suggested, self.unmarked)
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


def _take(record: Mapping[str, Any], moment: datetime.datetime, reading: _Reading) -> bool:
    """Adds the record to ``reading`` as a prompt or a count; False when it is neither."""
    message = record.get("message")
    text = _text_of(message.get("content") if isinstance(message, dict) else None)
    if text is None:
        return False
    origin = record.get("origin")
    sender = origin.get("kind") if isinstance(origin, dict) else None
    source = record.get("promptSource")
    # A slash command's record names no source; a typed prompt that starts with the tags has one.
    command = _COMMAND.match(text) if source is None else None
    if sender not in (None, _HUMAN):
        reading.sent_by_others += 1
    elif command is not None:
        reading.prompts.append(Prompt(moment, f"/{command.group(1)}"))
    elif sender is None:
        if _WRAPPED.match(text) or text.lstrip().startswith(_INTERRUPTED):
            return False
        reading.unmarked += 1
    elif source == _SUGGESTION:
        reading.suggested += 1
    else:
        typed, pasted_blocks = _without_pasted_blocks(text)
        shown = _shown(PROMPT_BLOCK.sub(" ", typed))
        if not shown and not pasted_blocks:
            return False
        reading.pasted_blocks += pasted_blocks
        if shown:
            reading.prompts.append(Prompt(moment, shown))
    return True


def _without_pasted_blocks(text: str) -> tuple[str, int]:
    """``text`` without what was pasted into it, and how many blocks went."""
    text, closed = _PASTED_BLOCK.subn(" ", text)
    # A block without its end: nothing after its start can be told from the pasted text.
    text, unclosed = _PASTED_UNCLOSED.subn(" ", text)
    return text, closed + unclosed


def _shown(text: str) -> str:
    if len(text) > _REDACT_WINDOW:
        text = _LAST_WORD.sub("", text[:_REDACT_WINDOW])
    return " ".join(redact(text).split())[:PROMPT_LENGTH]


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
