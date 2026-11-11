"""The frontmatter codec: a documented subset, not YAML.

A block between ``---`` lines at the very start of a file, one ``key: value`` per line, inline
lists ``[a, b]``. Every line is kept as it was read, with its own line ending, and only lines
that change are written anew, so a file read and written unchanged comes back byte for byte.
Lines are split on ``\\n`` only; a carriage return elsewhere is content.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Union

CREATED = "created"
SOURCE = "source"
QUIET = "quiet"
FOLLOW_UP = "follow_up"
TASKS = "tasks"
REFS = "refs"
FROM_CANDIDATE = "from_candidate"
FROM_PROPOSAL = "from_proposal"
KIND = "kind"
FACTS_FILED = "facts_filed"
CURATED = "curated"
# A fact file's last day as YYYY-MM-DD, for a fact that stops being true on a known day.
UNTIL = "until"

KIND_WORKLOG = "worklog"
KIND_JOURNAL = "journal"
KIND_SIDECAR = "sidecar"

QUIET_LINE = f"{QUIET}: true"

DELIMITER = "---"
_ENTRY = re.compile(r"([a-z_][a-z0-9_]*):(?: (.*))?\Z")
_KEY = re.compile(r"[a-z_][a-z0-9_]*\Z")
_LIST_ITEM_FORBIDDEN = re.compile(r"[,\[\]\r\n]")
# The one time syntax of the format, independent of what fromisoformat accepts on this Python.
_CREATED = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})?\Z")

Value = Union[str, bool, "list[str]"]


class NoteFormatError(ValueError):
    """A value is not in the frontmatter format, or cannot be written in it."""


@dataclass(frozen=True)
class CreatedTime:
    value: datetime.datetime
    has_offset: bool


class Frontmatter:
    """The frontmatter block of one note, with its lines as read."""

    def __init__(self, opening: str, lines: list[str], closing: str) -> None:
        self._opening = opening
        self._lines = lines
        self._closing = closing

    @property
    def newline(self) -> str:
        return "\r\n" if self._opening.endswith("\r\n") else "\n"

    def render(self) -> str:
        return self._opening + "".join(self._lines) + self._closing

    def keys(self) -> list[str]:
        seen: list[str] = []
        for line in self._lines:
            key = _key_of(line)
            if key is not None and key not in seen:
                seen.append(key)
        return seen

    def contains_line(self, content: str) -> bool:
        return any(_content(line) == content for line in self._lines)

    def get(self, key: str) -> str | None:
        """The value of the first line with this key, without surrounding spaces."""
        for line in self._lines:
            match = _ENTRY.match(_content(line))
            if match and match.group(1) == key:
                return (match.group(2) or "").strip()
        return None

    def get_flag(self, key: str) -> bool:
        return self.get(key) == "true"

    def get_list(self, key: str) -> list[str]:
        value = self.get(key)
        if value is None:
            return []
        if not (value.startswith("[") and value.endswith("]")):
            raise NoteFormatError(f"{key} must be a list like [a, b], got {value!r}")
        return [item.strip() for item in value[1:-1].split(",") if item.strip()]

    def set(self, key: str, value: Value) -> None:
        """Replaces the key's line in place, or adds it at the end of the block."""
        if not _KEY.match(key):
            raise NoteFormatError(f"{key!r} is not a key; keys are lowercase names like follow_up")
        if key == CREATED:
            _require_offset(value)
        text = f"{key}: {_serialize(key, value)}"
        for index, line in enumerate(self._lines):
            if _key_of(line) == key:
                self._lines[index] = text + _ending(line)
                return
        self._lines.append(text + self.newline)

    def add_to_list(self, key: str, items: Iterable[str]) -> None:
        """Merges items into a list, keeping its order and dropping duplicates."""
        merged = self.get_list(key)
        for item in items:
            if item not in merged:
                merged.append(item)
        self.set(key, merged)

    def remove(self, key: str) -> None:
        self._lines = [line for line in self._lines if _key_of(line) != key]


@dataclass
class Note:
    """A text note: its frontmatter, if it has one, and the body after it, untouched."""

    frontmatter: Frontmatter | None
    body: str

    @classmethod
    def parse(cls, text: str) -> Note:
        lines = _split_lines(text)
        if not lines or _content(lines[0]) != DELIMITER:
            return cls(None, text)
        for index in range(1, len(lines)):
            if _content(lines[index]) == DELIMITER:
                frontmatter = Frontmatter(lines[0], lines[1:index], lines[index])
                return cls(frontmatter, "".join(lines[index + 1 :]))
        return cls(None, text)

    @classmethod
    def new(cls, fields: Mapping[str, Value], body: str, newline: str = "\n") -> Note:
        frontmatter = Frontmatter(DELIMITER + newline, [], DELIMITER + newline)
        for key, value in fields.items():
            frontmatter.set(key, value)
        return cls(frontmatter, body)

    def render(self) -> str:
        return (self.frontmatter.render() if self.frontmatter is not None else "") + self.body

    @property
    def is_quiet(self) -> bool:
        """The quiet marker counts only as this exact line in the frontmatter, never in the body."""
        return self.frontmatter is not None and self.frontmatter.contains_line(QUIET_LINE)


def set_created(frontmatter: Frontmatter, created: datetime.datetime) -> None:
    """Writes ``created`` in local time with its offset; a time without offset is refused."""
    if created.utcoffset() is None:
        raise NoteFormatError(f"created {created.isoformat()} has no offset")
    frontmatter.set(CREATED, created.isoformat(timespec="seconds"))


def read_created(frontmatter: Frontmatter) -> CreatedTime | None:
    """``created`` as read; a value without offset is tolerated here and flagged for lint."""
    text = frontmatter.get(CREATED)
    if text is None:
        return None
    value = parse_time(text)
    return CreatedTime(value, value.utcoffset() is not None)


def parse_time(text: str) -> datetime.datetime:
    """A time in the format's one syntax, ``YYYY-MM-DDTHH:MM:SS`` with ``Z``, an offset or neither."""
    if not _CREATED.match(text):
        raise NoteFormatError(f"expected a time like 2026-03-29T01:30:00+01:00, got {text!r}")
    try:
        return datetime.datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    except ValueError as error:
        raise NoteFormatError(f"created is not a valid time: {text!r}") from error


def _require_offset(value: Value) -> None:
    if not isinstance(value, str) or parse_time(value).utcoffset() is None:
        raise NoteFormatError(f"created must carry its offset, like 2026-03-29T01:30:00+01:00, got {value!r}")


def _serialize(key: str, value: Value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        for item in value:
            if not item or item != item.strip() or _LIST_ITEM_FORBIDDEN.search(item):
                raise NoteFormatError(f"{key}: {item!r} cannot be a list item (no commas, brackets or line breaks)")
        return "[" + ", ".join(value) + "]"
    if "\n" in value or "\r" in value:
        raise NoteFormatError(f"{key}: a value must fit on one line")
    return value


def _split_lines(text: str) -> list[str]:
    """Lines with their endings; only ``\\n`` ends a line."""
    parts = text.split("\n")
    lines = [part + "\n" for part in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def _ending(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    return "\n" if line.endswith("\n") else ""


def _content(line: str) -> str:
    return line[: len(line) - len(_ending(line))]


def _key_of(line: str) -> str | None:
    match = _ENTRY.match(_content(line))
    return match.group(1) if match else None
