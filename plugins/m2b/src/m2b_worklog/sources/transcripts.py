"""Claude Code transcripts: prompts, message times and the last answer per working folder.

Only transcripts changed since the period's start are opened. A transcript that holds any record
of a headless run (``entrypoint: sdk-cli``) is left out entirely, so curation runs never report
themselves. A transcript's folder is the one its session started in. Prompts lose system
wrappers, keep pasted text, are redacted and cut short.
"""

from __future__ import annotations

import datetime
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from m2b_worklog.sources import SourceState

HEADLESS = "sdk-cli"
PROMPT_LENGTH = 240
ANSWER_LENGTH = 500

_PASTED = re.compile(r"</?pasted_content[^>]*>")
_COMMAND = re.compile(r"<command-name>/?([^<]+)</command-name>(?:\s*<command-args>([^<]*)</command-args>)?")
_WRAPPED = re.compile(r"^\s*<([a-zA-Z][\w-]*)[^>]*>.*</\1>\s*$", re.S)
# Not \b before the keyword: DB_PASSWORD and client_secret have a letter or "_" in front.
_KEYWORD = r"(?i)(?<![a-z])(secret|client[ _-]?id|password|passwort|kennwort|token|api[ _-]?key)"
_SECRET = re.compile(_KEYWORD + r"([\"']?\s*(?:[:=]|\bis\b|\bist\b|\blautet\b)\s*)(\S+)")
_LONG_TOKEN = re.compile(r"\b(?=[A-Za-z0-9_\-]*[A-Za-z])(?=[A-Za-z0-9_\-]*\d)[A-Za-z0-9_\-]{24,}\b")
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


@dataclass(frozen=True)
class Transcripts:
    transcripts: list[Transcript]
    state: SourceState


def projects_folder(environ: Mapping[str, str], home: Path) -> Path:
    claude_dir = environ.get("CLAUDE_CONFIG_DIR")
    return (Path(claude_dir) if claude_dir else home / ".claude") / "projects"


def read_transcripts(folder: Path, start: datetime.datetime, end: datetime.datetime) -> Transcripts:
    if not folder.is_dir():
        return Transcripts([], SourceState.failed(f"no Claude Code transcripts in {folder}"))
    found = []
    try:
        paths = sorted(folder.glob("*/*.jsonl"))
        for path in paths:
            if datetime.datetime.fromtimestamp(path.stat().st_mtime, datetime.timezone.utc) < start:
                continue
            transcript = _read(path, start, end)
            if transcript is not None:
                found.append(transcript)
    except OSError as error:
        return Transcripts(found, SourceState.failed(str(error)))
    return Transcripts(found, SourceState.read())


def prompt_text(content: object, limit: int = PROMPT_LENGTH) -> str | None:
    """What the owner typed, redacted and cut at ``limit``; None for system content and tool results."""
    if isinstance(content, list):
        parts = [p.get("text") for p in content if isinstance(p, dict) and p.get("type") == "text"]
        content = "\n".join(part for part in parts if isinstance(part, str))
    if not isinstance(content, str) or not content.strip():
        return None
    command = _COMMAND.search(content)
    if command:
        text = f"{command.group(1).strip()} {(command.group(2) or '').strip()}".strip()
    else:
        text = _PASTED.sub("", content)
        if _WRAPPED.match(text):
            return None
    text = " ".join(redact(text).split())
    return text[:limit] or None


def redact(text: str) -> str:
    """Credentials pasted into a prompt never reach the worklog: the value after a keyword, long mixed tokens."""
    return _LONG_TOKEN.sub(REDACTED, _SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text))


def _read(path: Path, start: datetime.datetime, end: datetime.datetime) -> Transcript | None:
    session_id, cwd, answer = path.stem, None, None
    prompts: list[Prompt] = []
    stamps: list[datetime.datetime] = []
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
            if moment is None or not start <= moment < end or record.get("type") not in ("user", "assistant"):
                continue
            stamps.append(moment)
            message: dict[str, Any] = record["message"] if isinstance(record.get("message"), dict) else {}
            if record["type"] == "user" and not record.get("isMeta"):
                text = prompt_text(message.get("content"))
                if text is not None:
                    prompts.append(Prompt(moment, text))
            elif record["type"] == "assistant":
                answer = prompt_text(message.get("content"), ANSWER_LENGTH) or answer
    if cwd is None or not stamps:
        return None
    return Transcript(session_id, cwd, prompts, stamps, answer)


def _time(value: object) -> datetime.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None
