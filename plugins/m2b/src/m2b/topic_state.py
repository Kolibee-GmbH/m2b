"""Which topics of the distillate a session has been shown, one small file per session.

A topic comes into a session once: the session start notes what it printed, the prompt hook adds
what it brings in later. ``/clear`` and compaction leave a context that no longer holds what was
shown, so the list starts over; a resumed session still has it. Lists are machine state, never in
the store, and go after seven days. The session id comes from Claude Code's hook input and
becomes a file name only when it is letters, digits and dashes.
"""

from __future__ import annotations

import datetime
import json
import re
from collections.abc import Iterable
from pathlib import Path

from m2b.atomic_file import write_text_atomically
from m2b.paths import MachinePaths

TOPICS_FOLDER = "topics"
KEEP_FOR = datetime.timedelta(days=7)
RESUME = "resume"

_SESSION_ID = re.compile(r"[A-Za-z0-9-]{1,128}\Z")


def start_session(
    machine: MachinePaths, session_id: str | None, source: str | None, shown: Iterable[str], now: datetime.datetime
) -> None:
    path = _path(machine, session_id)
    if path is None:
        return
    _prune(path.parent, now)
    names = set(shown)
    if source == RESUME:
        names |= _read(path)
    _write(machine, path, names)


def shown_topics(machine: MachinePaths, session_id: str | None) -> set[str]:
    path = _path(machine, session_id)
    return _read(path) if path is not None else set()


def add_shown(machine: MachinePaths, session_id: str | None, names: Iterable[str]) -> None:
    path = _path(machine, session_id)
    if path is None:
        return
    _write(machine, path, _read(path) | set(names))


def _path(machine: MachinePaths, session_id: str | None) -> Path | None:
    if session_id is None or _SESSION_ID.match(session_id) is None:
        return None
    return machine.state_dir / TOPICS_FOLDER / f"{session_id}.json"


def _read(path: Path) -> set[str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    shown = raw.get("shown") if isinstance(raw, dict) else None
    return {name for name in shown if isinstance(name, str)} if isinstance(shown, list) else set()


def _write(machine: MachinePaths, path: Path, names: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    machine.temp_dir.mkdir(parents=True, exist_ok=True)
    write_text_atomically(path, json.dumps({"shown": sorted(names)}, ensure_ascii=False) + "\n", machine.temp_dir)


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
