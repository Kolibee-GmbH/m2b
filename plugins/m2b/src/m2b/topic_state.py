"""What m2b gave a session, one small file per session.

A topic of the distillate comes into a session once: the session start notes what it printed, the
prompt hook adds what it brings in later. ``/clear`` and compaction leave a context that no longer
holds what was shown, so the list starts over; a resumed session still has it. Beside each topic's
name the file keeps how many facts lines and current items its block held when it was given, and
how the start printed the distillate, so a reader can say what this session got since its last
start and not what the distillate holds now. Lists are machine state, never in the store, and go after seven days. The
session id comes from Claude Code's hook input, or from a caller that asks about a session, and
becomes a file name only when it is letters, digits and dashes.
"""

from __future__ import annotations

import datetime
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from m2b.atomic_file import write_text_atomically
from m2b.paths import MachinePaths

TOPICS_FOLDER = "topics"
KEEP_FOR = datetime.timedelta(days=7)
RESUME = "resume"
# How a session start printed the distillate: all of it, up to the cut, or none (missing, not downloaded).
WHOLE, CUT, NONE = "whole", "cut", "none"

_SESSION_ID = re.compile(r"[A-Za-z0-9-]{1,128}\Z")


@dataclass(frozen=True)
class Given:
    """A topic a session was given, with the facts lines and current items its block held then.

    The counts are None for a topic noted by an m2b that did not keep them.
    """

    name: str
    facts: int | None = None
    current: int | None = None


@dataclass(frozen=True)
class Session:
    """The topics one session was given, by name, and how its start printed the distillate: None
    where no start noted it."""

    topics: tuple[Given, ...]
    distillate: str | None


def is_session_id(text: str) -> bool:
    return _SESSION_ID.match(text) is not None


def start_session(
    machine: MachinePaths,
    session_id: str | None,
    source: str | None,
    shown: Iterable[Given],
    now: datetime.datetime,
    distillate: str | None = None,
) -> None:
    path = _path(machine, session_id)
    if path is None:
        return
    _prune(path.parent, now)
    before = _noted(path).topics if source == RESUME else ()
    _write(machine, path, Session(_merged(before, shown), distillate))


def shown_topics(machine: MachinePaths, session_id: str | None) -> set[str]:
    path = _path(machine, session_id)
    return {topic.name for topic in _noted(path).topics} if path is not None else set()


def add_shown(machine: MachinePaths, session_id: str | None, shown: Iterable[Given]) -> None:
    path = _path(machine, session_id)
    if path is None:
        return
    before = _noted(path)
    _write(machine, path, Session(_merged(before.topics, shown), before.distillate))


def session(machine: MachinePaths, session_id: str | None) -> Session | None:
    """What this machine noted of the session; None for one it noted nothing it can read of, and for
    an id that is none."""
    path = _path(machine, session_id)
    return _read(path) if path is not None else None


def _merged(before: Iterable[Given], added: Iterable[Given]) -> tuple[Given, ...]:
    """Each topic once, by name, as it came last."""
    by_name = {topic.name: topic for topic in (*before, *added)}
    return tuple(by_name[name] for name in sorted(by_name))


def _path(machine: MachinePaths, session_id: str | None) -> Path | None:
    if session_id is None or not is_session_id(session_id):
        return None
    return machine.state_dir / TOPICS_FOLDER / f"{session_id}.json"


def _noted(path: Path) -> Session:
    """What the file holds; a session with nothing readable noted starts from nothing."""
    return _read(path) or Session((), None)


def _read(path: Path) -> Session | None:
    """None for a file that is missing, broken or without its list of names; counts and the print
    that are not in the form read as not noted."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    shown = raw.get("shown") if isinstance(raw, dict) else None
    if not isinstance(shown, list):
        return None
    names = sorted({name for name in shown if isinstance(name, str)})
    counts = raw.get("given")
    printed = raw.get("distillate")
    return Session(
        tuple(_given(name, counts.get(name) if isinstance(counts, dict) else None) for name in names),
        printed if printed in (WHOLE, CUT, NONE) else None,
    )


def _given(name: str, counts: Any) -> Given:
    facts = counts.get("facts") if isinstance(counts, dict) else None
    current = counts.get("current") if isinstance(counts, dict) else None
    return Given(name, facts, current) if _is_count(facts) and _is_count(current) else Given(name)


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _write(machine: MachinePaths, path: Path, noted: Session) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    machine.temp_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Any] = {"shown": [topic.name for topic in noted.topics]}
    counted = {
        topic.name: {"facts": topic.facts, "current": topic.current}
        for topic in noted.topics
        if topic.facts is not None and topic.current is not None
    }
    if counted:
        written["given"] = counted
    if noted.distillate is not None:
        written["distillate"] = noted.distillate
    write_text_atomically(path, json.dumps(written, ensure_ascii=False) + "\n", machine.temp_dir)


def _prune(folder: Path, now: datetime.datetime) -> None:
    if not folder.is_dir():
        return
    oldest = (now - KEEP_FOR).timestamp()
    for path in folder.glob("*.json"):
        try:
            if path.stat().st_mtime < oldest:
                path.unlink()
        except OSError:
            continue
