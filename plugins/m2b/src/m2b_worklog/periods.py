"""Work periods derived from the recorder's events.

Four kinds: **agent** (an agent works), **blocked** (an agent waits for an approval), **focus**
(the workspace has focus) and **human** (focused while no agent in that workspace works, the
closest herdr gets to typing). Agent and blocked periods belong to a pane: one opens at its first
start and closes at the first matching stop of the same pane; blocked closes an agent period and
working closes a blocked one, and a closed workspace stops all of its panes. A period still open
ends at "now" while its pane's last event is recent, else at that last event, because a herdr
that quit sends no stop. Focus and human periods are split at every event, whatever its
workspace, and each piece ends at most a fixed time after its event, because herdr reports no
idle keyboard. Activity blocks are the periods merged across gaps up to a limit.
"""

from __future__ import annotations

import datetime
import json
from collections.abc import Iterable, Sequence
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

    open_period_grace: datetime.timedelta = datetime.timedelta(minutes=5)
    piece_cap: datetime.timedelta = datetime.timedelta(minutes=10)
    block_gap: datetime.timedelta = datetime.timedelta(minutes=15)


RULES = Rules()


@dataclass(frozen=True)
class Event:
    time: datetime.datetime
    kind: str
    workspace: str
    pane: str | None


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
    kind, workspace, pane = raw.get("kind"), raw.get("workspace"), raw.get("pane")
    if kind not in EVENT_KINDS or not isinstance(workspace, str) or time.tzinfo is None:
        return None
    return Event(time, kind, workspace, pane if isinstance(pane, str) else None)


def load_events(folder: Path) -> list[Event]:
    """Every event of every workspace file in the recorder's folder, oldest first."""
    events: list[Event] = []
    for path in sorted(folder.glob("*.jsonl")):
        with path.open(encoding="utf-8", errors="replace") as handle:
            events.extend(event for event in map(parse_event, handle) if event is not None)
    return sorted(events, key=lambda event: event.time)


def derive_periods(events: Sequence[Event], now: datetime.datetime, rules: Rules = RULES) -> list[Period]:
    ordered = sorted(events, key=lambda event: event.time)
    pane_periods = _pane_periods(ordered, now, rules)
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


def _pane_periods(events: Sequence[Event], now: datetime.datetime, rules: Rules) -> list[Period]:
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
        recent = now - state.last_event < rules.open_period_grace
        close(pane_id, state, now if recent else state.last_event, (AGENT, BLOCKED))
    return found


def _focus_periods(
    events: Sequence[Event], agents: Sequence[Period], now: datetime.datetime, rules: Rules
) -> list[Period]:
    """Focus pieces, and the human ones among them: no agent period of that workspace covers the piece's start.

    Whether an agent works is read from the agent periods, so an agent left "working" by a herdr
    that quit stops counting where its period ended.
    """
    found: list[Period] = []
    focused: str | None = None
    for index, event in enumerate(events):
        if event.kind == FOCUS_EVENT:
            focused = event.workspace
        elif event.kind == WORKSPACE_CLOSED and focused == event.workspace:
            focused = None
        if focused is None:
            continue
        following = events[index + 1].time if index + 1 < len(events) else now
        end = min(following, event.time + rules.piece_cap)
        if end <= event.time:
            continue
        found.append(Period(FOCUS, focused, None, event.time, end))
        if not any(a.workspace == focused and a.start <= event.time < a.end for a in agents):
            found.append(Period(HUMAN, focused, None, event.time, end))
    return found
