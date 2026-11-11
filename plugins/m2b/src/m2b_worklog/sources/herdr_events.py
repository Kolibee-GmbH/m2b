"""What the recorder wrote: the events of every workspace, its signs of life and the workspace cache."""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from pathlib import Path

from m2b_worklog.periods import FOCUS_EVENT, WORKSPACE_CLOSED, Event, load_events
from m2b_worklog.sources import SourceState

CACHE_FILE = "workspaces.json"
ALIVE_FOLDER = "alive"
SIGN_KINDS = ("recorder_alive", "herdr_started")
FIRST_TICK_FILE = "first-tick"


@dataclass(frozen=True)
class Workspace:
    """One cache entry: what a workspace id stood for from ``since`` on."""

    workspace_id: str
    repo: str | None
    label: str | None
    folder: str | None
    since: datetime.datetime | None


@dataclass(frozen=True)
class Recordings:
    events: list[Event]
    workspaces: list[Workspace]
    state: SourceState
    # The recorder's signs of life (its ticks and herdr's starts), oldest first.
    alive: list[datetime.datetime] = field(default_factory=list)
    # The first tick of the recorder's timer; None while there was none.
    recording_since: datetime.datetime | None = None


def read_recordings(folder: Path, since: datetime.datetime | None = None) -> Recordings:
    """The recorder's events, from ``since`` on when given, and its workspace cache.

    From before ``since`` it keeps what still holds: the last focus event, and the workspace closes
    after it, so a workspace left in focus for days keeps its focus. A piece of focus starting there
    lasts at most minutes and ends long before the period, so it adds no time.
    """
    if not folder.is_dir():
        return Recordings([], [], SourceState.failed(f"no recordings in {folder}; is the recorder installed?"))
    try:
        events = _from(load_events(folder, written_since=since), since)
        workspaces = _workspaces(folder / CACHE_FILE)
        alive = _alive(folder / ALIVE_FOLDER, since)
        recording_since = _first_tick(folder / ALIVE_FOLDER / FIRST_TICK_FILE)
    except OSError as error:
        return Recordings([], [], SourceState.failed(str(error)))
    return Recordings(events, workspaces, SourceState.read(), alive, recording_since)


def _first_tick(path: Path) -> datetime.datetime | None:
    if not path.exists():
        return None
    return _time(path.read_text(encoding="utf-8").strip())


def _alive(folder: Path, since: datetime.datetime | None) -> list[datetime.datetime]:
    """Signs of life from ``since`` on; a month's file last written before it holds none."""
    if not folder.is_dir():
        return []
    found: list[datetime.datetime] = []
    for path in sorted(folder.glob("*.jsonl")):
        if since is not None and datetime.datetime.fromtimestamp(path.stat().st_mtime, datetime.timezone.utc) < since:
            continue
        with path.open(encoding="utf-8", errors="replace") as handle:
            found.extend(moment for moment in map(_alive_time, handle) if moment is not None)
    return sorted(moment for moment in found if since is None or moment >= since)


def _alive_time(line: str) -> datetime.datetime | None:
    try:
        raw = json.loads(line)
    except ValueError:
        return None
    if not isinstance(raw, dict) or raw.get("kind") not in SIGN_KINDS:
        return None
    return _time(raw.get("time"))


def _from(events: list[Event], since: datetime.datetime | None) -> list[Event]:
    if since is None:
        return events
    earlier = [event for event in events if event.time < since]
    focus = [index for index, event in enumerate(earlier) if event.kind == FOCUS_EVENT]
    still_holding = (
        [earlier[focus[-1]], *(e for e in earlier[focus[-1] + 1 :] if e.kind == WORKSPACE_CLOSED)] if focus else []
    )
    return [*still_holding, *(event for event in events if event.time >= since)]


def workspace_at(workspaces: list[Workspace], workspace_id: str, moment: datetime.datetime) -> Workspace | None:
    """The cache entry the id stood for at ``moment``: the newest one that began by then, else the oldest."""
    entries = [w for w in workspaces if w.workspace_id == workspace_id]
    begun = [w for w in entries if w.since is None or w.since <= moment]
    return begun[-1] if begun else (entries[0] if entries else None)


def _workspaces(path: Path) -> list[Workspace]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return []
    found = []
    for workspace_id, entries in raw.items() if isinstance(raw, dict) else []:
        for entry in entries if isinstance(entries, list) else []:
            if isinstance(entry, dict):
                found.append(
                    Workspace(
                        workspace_id,
                        _text(entry.get("repo")),
                        _text(entry.get("label")),
                        _text(entry.get("folder")),
                        _time(entry.get("since")),
                    )
                )
    return found


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _time(value: object) -> datetime.datetime | None:
    try:
        moment = datetime.datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None
    return moment if moment is not None and moment.tzinfo is not None else None
