"""Work periods derived from the recorder's events.

Four kinds: **agent** (an agent works), **blocked** (an agent waits for an approval), **focus**
(the workspace has focus) and **human** (focused while no agent in that workspace works, the
closest herdr gets to typing). Agent and blocked periods belong to a pane: one opens at its first
start and closes at the first matching stop of the same pane; blocked closes an agent period and
working closes a blocked one, and a closed workspace stops all of its panes. A period still open
runs to "now".

herdr sends nothing while a machine sleeps or after herdr quit, so a stop can arrive hours late or
never. An agent therefore counts only up to a fixed time past its last sign of life: an event of
its pane, or a transcript stamp of its workspace that the caller passes as evidence. A silent
stretch longer than that counts only that long.

Focus and human periods are split at every event of the focused workspace, and each piece ends at
most a fixed time after its event, because herdr reports no idle keyboard; events of other
workspaces say nothing about whether someone still looks at this one. Activity blocks are the
periods merged across gaps up to a limit.
"""

from __future__ import annotations

import bisect
import datetime
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

AGENT_WORKING = "agent_working"
AGENT_BLOCKED = "agent_blocked"
AGENT_STOPPED = "agent_stopped"
FOCUS_EVENT = "focus"
WORKSPACE_OPENED = "workspace_opened"
WORKSPACE_CLOSED = "workspace_closed"
EVENT_KINDS = (AGENT_WORKING, AGENT_BLOCKED, AGENT_STOPPED, FOCUS_EVENT, WORKSPACE_OPENED, WORKSPACE_CLOSED)

AGENT = "agent"
BLOCKED = "blocked"
FOCUS = "focus"
HUMAN = "human"


@dataclass(frozen=True)
class Rules:
    """The three numbers the periods depend on, in one place."""

    agent_silence: datetime.timedelta = datetime.timedelta(minutes=30)
    piece_cap: datetime.timedelta = datetime.timedelta(minutes=10)
    block_gap: datetime.timedelta = datetime.timedelta(minutes=15)


RULES = Rules()


@dataclass(frozen=True)
class Event:
    time: datetime.datetime
    kind: str
    workspace: str
    pane: str | None
    # The pane's folder when the recorder could read it.
    cwd: str | None = None


@dataclass(frozen=True)
class Period:
    kind: str
    workspace: str
    pane: str | None
    start: datetime.datetime
    end: datetime.datetime


@dataclass(frozen=True)
class Block:
    start: datetime.datetime
    end: datetime.datetime


def parse_event(line: str) -> Event | None:
    """One recorder line; a line that is not one (cut by a crash, from a newer recorder) is skipped."""
    try:
        raw: Any = json.loads(line)
        time = datetime.datetime.fromisoformat(raw["time"])
    except (ValueError, KeyError, TypeError):
        return None
    kind, workspace, pane, cwd = raw.get("kind"), raw.get("workspace"), raw.get("pane"), raw.get("cwd")
    if kind not in EVENT_KINDS or not isinstance(workspace, str) or time.tzinfo is None:
        return None
    return Event(
        time, kind, workspace, pane if isinstance(pane, str) else None, cwd if isinstance(cwd, str) and cwd else None
    )


def load_events(folder: Path, written_since: datetime.datetime | None = None) -> list[Event]:
    """Every event of every workspace file in the recorder's folder, oldest first.

    With ``written_since``, a file last written before it is left unread: the recorder only appends,
    so it holds nothing newer.
    """
    events: list[Event] = []
    for path in sorted(folder.glob("*.jsonl")):
        if written_since is not None:
            changed = datetime.datetime.fromtimestamp(path.stat().st_mtime, datetime.timezone.utc)
            if changed < written_since:
                continue
        with path.open(encoding="utf-8", errors="replace") as handle:
            events.extend(event for event in map(parse_event, handle) if event is not None)
    return sorted(events, key=lambda event: event.time)


def derive_periods(
    events: Sequence[Event],
    now: datetime.datetime,
    rules: Rules = RULES,
    evidence: Mapping[str, Sequence[datetime.datetime]] | None = None,
) -> list[Period]:
    """``evidence`` holds, per workspace id, moments its agent was seen at work outside herdr."""
    ordered = sorted(events, key=lambda event: event.time)
    pane_periods = _bounded(_pane_periods(ordered, now), ordered, evidence or {}, rules)
    agents = [period for period in pane_periods if period.kind == AGENT]
    found = [*pane_periods, *_focus_periods(ordered, agents, now, rules)]
    return sorted((p for p in found if p.end > p.start), key=lambda period: (period.start, period.kind))


def activity_blocks(periods: Iterable[Period], rules: Rules = RULES) -> list[Block]:
    blocks: list[Block] = []
    for period in sorted((p for p in periods if p.end > p.start), key=lambda p: p.start):
        if blocks and period.start - blocks[-1].end <= rules.block_gap:
            blocks[-1] = Block(blocks[-1].start, max(blocks[-1].end, period.end))
        else:
            blocks.append(Block(period.start, period.end))
    return blocks


@dataclass
class _Pane:
    workspace: str
    last_event: datetime.datetime
    agent_since: datetime.datetime | None = None
    blocked_since: datetime.datetime | None = None


def _pane_periods(events: Sequence[Event], now: datetime.datetime) -> list[Period]:
    panes: dict[str, _Pane] = {}
    found: list[Period] = []

    def close(pane_id: str, state: _Pane, at: datetime.datetime, kinds: Sequence[str]) -> None:
        if AGENT in kinds and state.agent_since is not None:
            found.append(Period(AGENT, state.workspace, pane_id, state.agent_since, at))
            state.agent_since = None
        if BLOCKED in kinds and state.blocked_since is not None:
            found.append(Period(BLOCKED, state.workspace, pane_id, state.blocked_since, at))
            state.blocked_since = None

    for event in events:
        if event.kind == WORKSPACE_CLOSED:
            for pane_id, state in panes.items():
                if state.workspace == event.workspace:
                    close(pane_id, state, event.time, (AGENT, BLOCKED))
            continue
        if event.pane is None or event.kind not in (AGENT_WORKING, AGENT_BLOCKED, AGENT_STOPPED):
            continue
        state = panes.setdefault(event.pane, _Pane(event.workspace, event.time))
        state.workspace, state.last_event = event.workspace, event.time
        if event.kind == AGENT_WORKING:
            close(event.pane, state, event.time, (BLOCKED,))
            state.agent_since = state.agent_since or event.time
        elif event.kind == AGENT_BLOCKED:
            close(event.pane, state, event.time, (AGENT,))
            state.blocked_since = state.blocked_since or event.time
        else:
            close(event.pane, state, event.time, (AGENT, BLOCKED))

    for pane_id, state in panes.items():
        close(pane_id, state, now, (AGENT, BLOCKED))
    return found


def _bounded(
    found: Sequence[Period], events: Sequence[Event], evidence: Mapping[str, Sequence[datetime.datetime]], rules: Rules
) -> list[Period]:
    """Agent periods cut to the stretches within ``rules.agent_silence`` of a sign of life."""
    by_pane: dict[str | None, list[datetime.datetime]] = {}
    for event in events:
        by_pane.setdefault(event.pane, []).append(event.time)
    stamps = {workspace: sorted(moments) for workspace, moments in evidence.items()}
    bounded: list[Period] = []
    for period in found:
        if period.kind != AGENT:
            bounded.append(period)
            continue
        signs = sorted(
            {
                period.start,
                *_strictly_between(by_pane.get(period.pane, []), period.start, period.end),
                *_strictly_between(stamps.get(period.workspace, []), period.start, period.end),
            }
        )
        for start, end in _alive_stretches(signs, period.end, rules.agent_silence):
            bounded.append(Period(AGENT, period.workspace, period.pane, start, end))
    return bounded


def _strictly_between(
    moments: Sequence[datetime.datetime], start: datetime.datetime, end: datetime.datetime
) -> Sequence[datetime.datetime]:
    """The moments after ``start`` and before ``end``; ``moments`` are in time order."""
    return moments[bisect.bisect_right(moments, start) : bisect.bisect_left(moments, end)]


def _alive_stretches(
    signs: Sequence[datetime.datetime], end: datetime.datetime, silence: datetime.timedelta
) -> list[tuple[datetime.datetime, datetime.datetime]]:
    stretches: list[tuple[datetime.datetime, datetime.datetime]] = []
    for sign, following in zip(signs, [*signs[1:], end]):
        stop = min(following, sign + silence)
        if stretches and stretches[-1][1] >= sign:
            stretches[-1] = (stretches[-1][0], stop)
        else:
            stretches.append((sign, stop))
    return stretches


def _focus_periods(
    events: Sequence[Event], agents: Sequence[Period], now: datetime.datetime, rules: Rules
) -> list[Period]:
    """Focus pieces, and the human ones among them: no agent period of that workspace covers the piece's start.

    Whether an agent works is read from the agent periods, so an agent left "working" by a herdr
    that quit stops counting where its period ended.
    """
    found: list[Period] = []
    focused: str | None = None
    piece_start: datetime.datetime | None = None

    def close_piece(at: datetime.datetime) -> None:
        if focused is None or piece_start is None:
            return
        end = min(at, piece_start + rules.piece_cap)
        if end <= piece_start:
            return
        found.append(Period(FOCUS, focused, None, piece_start, end))
        if not any(a.workspace == focused and a.start <= piece_start < a.end for a in agents):
            found.append(Period(HUMAN, focused, None, piece_start, end))

    for event in events:
        moves_focus = event.kind == FOCUS_EVENT or (event.kind == WORKSPACE_CLOSED and event.workspace == focused)
        if not moves_focus and event.workspace != focused:
            continue
        close_piece(event.time)
        if event.kind == FOCUS_EVENT:
            focused = event.workspace
        elif event.kind == WORKSPACE_CLOSED:
            focused = None
        piece_start = event.time if focused is not None else None
    close_piece(now)
    return found
