"""Claude Code transcripts: prompts, message times and the last answer per working folder.

Only transcripts changed since the period's start are opened. A transcript that holds any record
of a headless run (``entrypoint: sdk-cli``) is left out entirely, so curation runs never report
themselves. A transcript's folder is the one its session started in. Prompts lose the blocks
Claude Code wraps around them and the summaries it writes after a context cut, keep pasted text,
are redacted and cut short. The last answer is the end of the last reply, where a question to the
owner stands.

Redaction works on patterns: a value after a word such as password or token, a credential after
``Bearer`` or ``Basic``, and long tokens of mixed letters and digits. It misses what matches none
of them, so a prompt can still carry a secret in words of its own.
"""

from __future__ import annotations

import datetime
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from m2b_worklog.sources import SourceState

HEADLESS = "sdk-cli"
PROMPT_LENGTH = 240
ANSWER_LENGTH = 500

_PASTED = re.compile(r"</?pasted_content[^>]*>")
_COMMAND = re.compile(r"<command-name>/?([^<]+)</command-name>(?:\s*<command-args>([^<]*)</command-args>)?")
_WRAPPED = re.compile(r"^\s*<([a-zA-Z][\w-]*)[^>]*>.*</\1>\s*$", re.S)
# The blocks Claude Code puts into a prompt beside what the owner typed.
_SYSTEM_TAGS = (
    "system-reminder",
    "local-command-caveat",
    "local-command-stdout",
    "local-command-stderr",
    "command-message",
    "user-prompt-submit-hook",
    "task-notification",
)
_SYSTEM_BLOCK = re.compile(r"<(" + "|".join(_SYSTEM_TAGS) + r")\b[^>]*>.*?</\1>", re.S)
# What Claude Code writes as the first user message after a context cut, when the record has no flag.
_SUMMARY_OPENING = "This session is being continued from a previous conversation"
# Not \b before the keyword: DB_PASSWORD and client_secret have a letter or "_" in front.
_KEYWORD = r"(?i)(?<![a-z])(secret|client[ _-]?id|password|passwort|kennwort|passwd|pwd|pw|token|api[ _-]?key)"
# Up to four words between the keyword and its value: "the password for the db is hunter2".
_BETWEEN = r"((?:\s+[\w.-]+){0,4}?[\"']?\s*(?:[:=]|\b(?:is|ist|lautet)\b\s*[:=]?)\s*)"
_SECRET = re.compile(_KEYWORD + r"\b" + _BETWEEN + r"(\S+)")
# The scheme as HTTP writes it, followed by a value shaped like a credential, not by a word.
_SCHEME = re.compile(r"\b(Bearer|Basic)\s+(?=[\w.~+/=-]*[\d+/=])[\w.~+/=-]{6,}")
_LONG_TOKEN = re.compile(r"\b(?=[A-Za-z0-9_\-]*[A-Za-z])(?=[A-Za-z0-9_\-]*\d)[A-Za-z0-9_\-]{24,}\b")
# A base64 key holds "/" and "+" too, and upper and lower case letters and digits. It never starts
# inside a path or a word and never ends before a file extension; one with "/" whose parts include
# a word in lower case only is a relative path (`apps/Web3Portal/src`), not a key.
_BASE64_CANDIDATE = re.compile(
    r"(?<![\w/.~+-])(?=[\w+/=-]*[A-Z])(?=[\w+/=-]*[a-z])(?=[\w+/=-]*\d)[A-Za-z0-9][\w+/=-]{23,}(?![\w/+]|\.\w)"
)
_LOWER_WORD = re.compile(r"[a-z]+")
# Redaction runs before the cut; this much more than the cut keeps its patterns fast on long text.
_REDACT_MARGIN = 200
REDACTED = "[removed]"


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
        text = _SYSTEM_BLOCK.sub("", _PASTED.sub("", content))
        if _WRAPPED.match(text) or text.lstrip().startswith(_SUMMARY_OPENING):
            return None
    text = " ".join(redact(text[: limit + _REDACT_MARGIN]).split())
    return text[:limit] or None


def answer_text(content: object, limit: int = ANSWER_LENGTH) -> str | None:
    """The end of a reply, redacted: a question to the owner stands last."""
    content = _text_of(content)
    if content is None:
        return None
    text = " ".join(redact(content[-(limit + _REDACT_MARGIN) :]).split())
    return text[-limit:] or None


def _text_of(content: object) -> str | None:
    if isinstance(content, list):
        parts = [p.get("text") for p in content if isinstance(p, dict) and p.get("type") == "text"]
        content = "\n".join(part for part in parts if isinstance(part, str))
    return content if isinstance(content, str) and content.strip() else None


def redact(text: str) -> str:
    """Credentials pasted into a prompt never reach the worklog, as far as a pattern finds them."""
    text = _SCHEME.sub(lambda m: f"{m.group(1)} {REDACTED}", text)
    text = _SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
    return _LONG_TOKEN.sub(REDACTED, _BASE64_CANDIDATE.sub(_base64_key, text))


def _base64_key(match: re.Match[str]) -> str:
    token = match.group(0)
    is_path = "/" in token and any(_LOWER_WORD.fullmatch(part) for part in token.split("/"))
    return token if is_path else REDACTED


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
            if record["type"] == "user" and not record.get("isMeta") and not record.get("isCompactSummary"):
                text = prompt_text(message.get("content"))
                if text is not None:
                    prompts.append(Prompt(moment, text))
            elif record["type"] == "assistant":
                answer = answer_text(message.get("content")) or answer
    if cwd is None or not (stamps or earlier):
        return None
    return Transcript(session_id, cwd, prompts, stamps, answer, earlier)


def _time(value: object) -> datetime.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None
