"""Claude Code transcripts: prompts, message times and the last answer per working folder.

Only transcripts changed since the period's start are opened. A transcript that holds any record
of a headless run (``entrypoint: sdk-cli``) is left out entirely, so curation runs never report
themselves. A transcript's folder is the one its session started in. Prompts lose the blocks
Claude Code wraps around them and the summaries it writes after a context cut, keep pasted text,
are redacted and cut short. The last answer is the end of the last reply, where a question to the
owner stands.

A prompt is the owner's unless Claude Code marks it as sent by someone else: a plugin that drives
the session, a finished task, another session. Such a record is no prompt, and its time still is a
sign of work. A prompt without the mark, which an older Claude Code writes, counts as the owner's:
the worklog asks what a session was about, and a prompt too many costs less there than a session
without any (B130). A suggested prompt the owner accepted counts as well, because they sent it.

How they are redacted is in the core's ``m2b.redaction``; which blocks are Claude Code's and how
it marks the sender is in its ``m2b.claude_code``.
"""

from __future__ import annotations

import datetime
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from m2b.claude_code import HUMAN, PROMPT_BLOCK, sender_of
from m2b.redaction import redact

from m2b_worklog.sources import SourceState

HEADLESS = "sdk-cli"
PROMPT_LENGTH = 240
ANSWER_LENGTH = 500

_PASTED = re.compile(r"</?pasted_content[^>]*>")
_COMMAND = re.compile(r"<command-name>/?([^<]+)</command-name>(?:\s*<command-args>([^<]*)</command-args>)?")
_WRAPPED = re.compile(r"^\s*<([a-zA-Z][\w-]*)[^>]*>.*</\1>\s*$", re.S)
# What Claude Code writes as the first user message after a context cut, when the record has no flag.
_SUMMARY_OPENING = "This session is being continued from a previous conversation"
# Redaction runs on this much of the text, from the end that is kept, so its patterns stay fast on a
# long paste. Whitespace and redaction shrink the piece before the cut, so the piece reaches well
# past the kept part, and the word at its far edge, which may be cut, is dropped.
_REDACT_WINDOW = 8 * 1024
_FIRST_WORD = re.compile(r"\A\S*")
_LAST_WORD = re.compile(r"\S*\Z")


@dataclass(frozen=True)
class Prompt:
    time: datetime.datetime
    text: str


@dataclass(frozen=True)
class Transcript:
    session_id: str
    cwd: str
    prompts: list[Prompt]
    stamps: list[datetime.datetime]
    last_answer: str | None
    # Stamps from just before the period: no work of the period, only a sign that an agent was alive.
    earlier_stamps: list[datetime.datetime] = field(default_factory=list)


@dataclass(frozen=True)
class Transcripts:
    transcripts: list[Transcript]
    state: SourceState


def projects_folder(environ: Mapping[str, str], home: Path) -> Path:
    claude_dir = environ.get("CLAUDE_CONFIG_DIR")
    return (Path(claude_dir) if claude_dir else home / ".claude") / "projects"


def read_transcripts(
    folder: Path, start: datetime.datetime, end: datetime.datetime, signs_from: datetime.datetime | None = None
) -> Transcripts:
    """The transcripts with a message in ``[start, end)``; from ``signs_from`` on, earlier stamps too."""
    earliest = start if signs_from is None else min(signs_from, start)
    if not folder.is_dir():
        return Transcripts([], SourceState.failed(f"no Claude Code transcripts in {folder}"))
    found = []
    try:
        paths = sorted(folder.glob("*/*.jsonl"))
        for path in paths:
            if datetime.datetime.fromtimestamp(path.stat().st_mtime, datetime.timezone.utc) < earliest:
                continue
            transcript = _read(path, start, end, earliest)
            if transcript is not None:
                found.append(transcript)
    except OSError as error:
        return Transcripts(found, SourceState.failed(str(error)))
    return Transcripts(found, SourceState.read())


def prompt_text(content: object, limit: int = PROMPT_LENGTH) -> str | None:
    """What the owner typed, redacted and cut at ``limit``; None for system content and tool results."""
    content = _text_of(content)
    if content is None:
        return None
    command = _COMMAND.search(content)
    if command:
        text = f"{command.group(1).strip()} {(command.group(2) or '').strip()}".strip()
    else:
        text = PROMPT_BLOCK.sub("", _PASTED.sub("", content))
        if _WRAPPED.match(text) or text.lstrip().startswith(_SUMMARY_OPENING):
            return None
    if len(text) > _REDACT_WINDOW:
        text = _LAST_WORD.sub("", text[:_REDACT_WINDOW])
    text = " ".join(redact(text).split())
    return text[:limit] or None


def answer_text(content: object, limit: int = ANSWER_LENGTH) -> str | None:
    """The end of a reply, redacted: a question to the owner stands last."""
    content = _text_of(content)
    if content is None:
        return None
    if len(content) > _REDACT_WINDOW:
        content = _FIRST_WORD.sub("", content[-_REDACT_WINDOW:])
    text = " ".join(redact(content).split())
    return text[-limit:] or None


def _text_of(content: object) -> str | None:
    if isinstance(content, list):
        parts = [p.get("text") for p in content if isinstance(p, dict) and p.get("type") == "text"]
        content = "\n".join(part for part in parts if isinstance(part, str))
    return content if isinstance(content, str) and content.strip() else None


def _read(
    path: Path, start: datetime.datetime, end: datetime.datetime, earliest: datetime.datetime
) -> Transcript | None:
    session_id, cwd, answer = path.stem, None, None
    prompts: list[Prompt] = []
    stamps: list[datetime.datetime] = []
    earlier: list[datetime.datetime] = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                record: Any = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            if record.get("entrypoint") == HEADLESS:
                return None
            # The first folder is where the session started; later records follow the Bash tool's `cd`.
            if cwd is None and isinstance(record.get("cwd"), str):
                cwd = record["cwd"]
            moment = _time(record.get("timestamp"))
            if moment is None or record.get("type") not in ("user", "assistant"):
                continue
            if earliest <= moment < start:
                earlier.append(moment)
                continue
            if not start <= moment < end:
                continue
            stamps.append(moment)
            message: dict[str, Any] = record["message"] if isinstance(record.get("message"), dict) else {}
            if record["type"] == "user" and _is_the_owners(record):
                text = prompt_text(message.get("content"))
                if text is not None:
                    prompts.append(Prompt(moment, text))
            elif record["type"] == "assistant":
                answer = answer_text(message.get("content")) or answer
    if cwd is None or not (stamps or earlier):
        return None
    return Transcript(session_id, cwd, prompts, stamps, answer, earlier)


def _is_the_owners(record: Mapping[str, Any]) -> bool:
    if record.get("isMeta") or record.get("isCompactSummary"):
        return False
    return sender_of(record) in (None, HUMAN)


def _time(value: object) -> datetime.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None
