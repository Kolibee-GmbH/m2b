"""The action lessons as the tool hook reads them: a list in machine state, and a count of firings.

A Bash call runs often, so the tool hook reads no file of the store: the session start writes the
action lessons it read from ``memory/lessons/`` into this machine's state, and the hook reads only
that list. Each time a lesson fires, one line is appended to a log beside it; appending a short
line is one write, so calls that run side by side do not lose each other's count. Each Bash call
the hook sees while there are action lessons adds one byte to the day's file, so a lesson's firings
can be told as a share of the calls since it was kept.

Standard library and m2b's leaf modules only: the tool hook imports this before every Bash call.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from m2b.atomic_file import write_text_atomically
from m2b.lessons import ACTION, EVERY_PROJECT, Lesson
from m2b.notes.characters import without_hidden
from m2b.paths import MachinePaths

_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
FILE = "action-lessons.json"
FIRED = "action-lessons-fired.log"
# One file per day, one byte per Bash call the hook saw while there were action lessons: its size is
# the count, and appending a byte is one write, as a firing's line is.
CALLS_FOLDER = "bash-calls"


@dataclass(frozen=True)
class ActionLesson:
    name: str
    text: str
    target: str
    words: tuple[str, ...]
    unless: tuple[str, ...]
    ask: bool

    def fires_on(self, command: str, addresses: Collection[str]) -> bool:
        """All its words are in the command and none of the words that silence it, in a repository it is for."""
        if self.target != EVERY_PROJECT and self.target not in addresses:
            return False
        return all(holds_word(command, word) for word in self.words) and not any(
            holds_word(command, word) for word in self.unless
        )


def holds_word(command: str, word: str) -> bool:
    """The word stands in the command as a word of its own: ``scripts/check`` in ``./scripts/check`` and
    ``scripts/check.sh``, not in ``myscripts/checker``; ``--quick`` not in ``--quickly``."""
    return re.search(r"(?<![\w-])" + re.escape(word) + r"(?![\w-])", command) is not None


def note(machine: MachinePaths, found: Sequence[Lesson]) -> None:
    """Writes the action lessons for the tool hook, in place of the list before."""
    listed = [
        {
            "name": lesson.name,
            "text": without_hidden(lesson.text),
            "target": lesson.target,
            "words": list(lesson.words),
            "unless": list(lesson.unless),
            "ask": lesson.ask,
        }
        for lesson in found
        if lesson.kind == ACTION and lesson.words
    ]
    machine.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    machine.temp_dir.mkdir(parents=True, exist_ok=True)
    write_text_atomically(machine.state_dir / FILE, json.dumps(listed, ensure_ascii=False) + "\n", machine.temp_dir)


def read(machine: MachinePaths) -> list[ActionLesson]:
    """The list the session start wrote; raises ``OSError`` or ``ValueError`` where it cannot be read."""
    raw = json.loads((machine.state_dir / FILE).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("the action lessons are no list")
    return [
        ActionLesson(
            str(item["name"]),
            str(item["text"]),
            str(item["target"]),
            tuple(str(word) for word in item["words"]),
            tuple(str(word) for word in item.get("unless", ())),
            item.get("ask") is True,
        )
        for item in raw
    ]


def count_fired(machine: MachinePaths, names: Sequence[str], now: datetime.datetime) -> None:
    lines = "".join(f"{now.isoformat(timespec='seconds')}\t{name}\n" for name in names)
    with contextlib.suppress(OSError):
        descriptor = os.open(machine.state_dir / FIRED, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(descriptor, lines.encode("utf-8"))
        finally:
            os.close(descriptor)


def fired(machine: MachinePaths, since: datetime.date | None = None) -> dict[str, int]:
    """How often each lesson fired on this machine, on ``since`` or later where it is given; none
    where nothing is logged."""
    counts: dict[str, int] = {}
    try:
        text = (machine.state_dir / FIRED).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return counts
    for line in text.splitlines():
        moment, _, name = line.partition("\t")
        if not name or (since is not None and _local_day(moment) < since.isoformat()):
            continue
        counts[name] = counts.get(name, 0) + 1
    return counts


def _local_day(moment: str) -> str:
    """The day of a logged moment where the owner is, as a lesson's ``kept`` day is; empty when it cannot be read."""
    try:
        return datetime.datetime.fromisoformat(moment).astimezone().date().isoformat()
    except ValueError:
        return ""


def count_call(machine: MachinePaths, now: datetime.datetime) -> None:
    """Adds the call to the file of its day where the owner is, the zone a lesson's ``kept`` day is in."""
    folder = machine.state_dir / CALLS_FOLDER
    with contextlib.suppress(OSError):
        folder.mkdir(mode=0o700, exist_ok=True)
        descriptor = os.open(
            folder / now.astimezone().date().isoformat(), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600
        )
        try:
            os.write(descriptor, b".")
        finally:
            os.close(descriptor)


def calls(machine: MachinePaths, since: datetime.date) -> int:
    """How many Bash calls the hook saw on this machine on ``since`` or later while there were action lessons."""
    total = 0
    with contextlib.suppress(OSError):
        for path in (machine.state_dir / CALLS_FOLDER).iterdir():
            if _DAY.fullmatch(path.name) and path.name >= since.isoformat():
                with contextlib.suppress(OSError):
                    total += path.stat().st_size
    return total
