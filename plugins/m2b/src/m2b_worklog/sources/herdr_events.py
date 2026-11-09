"""What the recorder wrote: the events of every workspace and the workspace cache."""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from pathlib import Path

from m2b_worklog.periods import Event, load_events
from m2b_worklog.sources import SourceState

CACHE_FILE = "workspaces.json"


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


def read_recordings(folder: Path) -> Recordings:
    if not folder.is_dir():
        return Recordings([], [], SourceState.failed(f"no recordings in {folder}; is the recorder installed?"))
    try:
        events = load_events(folder)
        workspaces = _workspaces(folder / CACHE_FILE)
    except OSError as error:
        return Recordings([], [], SourceState.failed(str(error)))
    return Recordings(events, workspaces, SourceState.read())


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
