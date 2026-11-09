"""Sessions: the work of one workspace or one folder in the period, cut into blocks.

A session's work is the union of its agent, human and focus periods and the spans of its
transcripts (messages at most 15 minutes apart); waiting for an approval is not work. Everything is
clipped to the period, so a period crossing the watermark is counted once (B28). A session with
less than 2 minutes of work is left out (B33), and one without a prompt, a commit or an agent still
at work at the end needs 15 minutes, because a workspace looked at or an agent left running is
noise below that. Blocks are the work merged across gaps of up to 15 minutes; a block with less
than a minute of work is dropped, and a block's minutes are the work inside it, never its gaps. A
transcript belongs to the session whose folder holds its working folder most closely; otherwise it
is a session of its own.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from dataclasses import dataclass, field

from m2b_worklog import periods
from m2b_worklog.periods import AGENT, BLOCKED, FOCUS, HUMAN, Period
from m2b_worklog.sources.herdr_events import Workspace, workspace_at
from m2b_worklog.sources.transcripts import Prompt, Transcript

MINIMUM_WORK = datetime.timedelta(minutes=2)
MINIMUM_SILENT_WORK = datetime.timedelta(minutes=15)
# An agent's state at the period's end, as the facts name it.
WORKING = "working"
BLOCKED_STATE = "blocked"
IDLE = "idle"
MINIMUM_BLOCK = datetime.timedelta(minutes=1)
BLOCK_GAP = periods.RULES.block_gap
TRANSCRIPT_GAP = datetime.timedelta(minutes=15)
PROMPTS_PER_BLOCK = 25
TRANSCRIPT = "transcript"

Interval = tuple[datetime.datetime, datetime.datetime]


@dataclass(frozen=True)
class SessionBlock:
    block_id: str
    start: datetime.datetime
    end: datetime.datetime
    prompts: list[str]
    worked: float = 0.0
    """Seconds of work inside the block, without its gaps."""

    @property
    def minutes(self) -> int:
        return round(self.worked / 60)


@dataclass
class SessionDraft:
    key: str
    workspace: Workspace | None
    folder: str | None
    series: dict[str, list[Interval]] = field(default_factory=dict)
    transcripts: list[Transcript] = field(default_factory=list)
    events: list[periods.Event] = field(default_factory=list)
    agent_state: str | None = None

    def add(self, kind: str, interval: Interval) -> None:
        self.series.setdefault(kind, []).append(interval)

    def work(self) -> list[Interval]:
        return merge([i for kind, intervals in self.series.items() for i in intervals], gap=datetime.timedelta(0))

    def minutes(self) -> dict[str, int]:
        return {
            kind: round(length(merge(self.series.get(kind, []))) / 60) for kind in (AGENT, HUMAN, FOCUS, TRANSCRIPT)
        }

    def prompts(self) -> list[Prompt]:
        return sorted((p for t in self.transcripts for p in t.prompts), key=lambda prompt: prompt.time)

    def last_answer(self) -> str | None:
        answered = [t for t in self.transcripts if t.last_answer]
        return max(answered, key=lambda t: t.stamps[-1]).last_answer if answered else None


def draft_sessions(
    events: Sequence[periods.Event],
    workspaces: list[Workspace],
    transcripts: Sequence[Transcript],
    start: datetime.datetime,
    end: datetime.datetime,
) -> list[SessionDraft]:
    drafts: dict[str, SessionDraft] = {}
    derived = periods.derive_periods(events, now=end)
    for period in derived:
        clipped = clip((period.start, period.end), start, end)
        if clipped is None or period.kind not in (AGENT, HUMAN, FOCUS):
            continue
        draft = _workspace_draft(drafts, workspaces, period)
        draft.add(period.kind, clipped)
    for event in events:
        for draft in drafts.values():
            if draft.workspace is not None and draft.workspace.workspace_id == event.workspace:
                draft.events.append(event)
    _agent_states(drafts, derived, end)
    for transcript in transcripts:
        draft = _transcript_draft(drafts, transcript)
        draft.transcripts.append(transcript)
        for span in transcript_spans(transcript.stamps):
            clipped = clip(span, start, end)
            if clipped is not None:
                draft.add(TRANSCRIPT, clipped)
    return [draft for draft in drafts.values() if length(draft.work()) >= MINIMUM_WORK.total_seconds()]


def worth_naming(draft: SessionDraft, owns_commit: bool, all_read: bool) -> bool:
    """Whether a session goes into the facts: with a prompt, a commit or an agent still working or
    waiting at the period's end, else with 15 minutes of work. A source that could not be read
    keeps it, because a missing commit or prompt must not read as none (X20)."""
    if not all_read or owns_commit or draft.prompts() or draft.agent_state in (WORKING, BLOCKED_STATE):
        return True
    return length(draft.work()) >= MINIMUM_SILENT_WORK.total_seconds()


def blocks_of(draft: SessionDraft) -> list[SessionBlock]:
    prompts = draft.prompts()
    found: list[SessionBlock] = []
    work = draft.work()
    for start, end in merge(work, gap=BLOCK_GAP):
        worked = length([piece for piece in work if start <= piece[0] and piece[1] <= end])
        if worked < MINIMUM_BLOCK.total_seconds():
            continue
        inside = [p.text for p in prompts if start - BLOCK_GAP <= p.time <= end][-PROMPTS_PER_BLOCK:]
        found.append(SessionBlock(f"b{len(found) + 1}", start, end, inside, worked))
    return found


def transcript_spans(stamps: Sequence[datetime.datetime]) -> list[Interval]:
    spans: list[Interval] = []
    for moment in sorted(stamps):
        if spans and moment - spans[-1][1] <= TRANSCRIPT_GAP:
            spans[-1] = (spans[-1][0], moment)
        else:
            spans.append((moment, moment))
    return [span for span in spans if span[1] > span[0]]


def merge(intervals: Sequence[Interval], gap: datetime.timedelta = datetime.timedelta(0)) -> list[Interval]:
    merged: list[Interval] = []
    for start, end in sorted(intervals):
        if merged and start - merged[-1][1] <= gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def clip(interval: Interval, start: datetime.datetime, end: datetime.datetime) -> Interval | None:
    clipped = (max(interval[0], start), min(interval[1], end))
    return clipped if clipped[1] > clipped[0] else None


def length(intervals: Sequence[Interval]) -> float:
    return sum((end - start).total_seconds() for start, end in intervals)


def _workspace_draft(drafts: dict[str, SessionDraft], workspaces: list[Workspace], period: Period) -> SessionDraft:
    workspace = workspace_at(workspaces, period.workspace, period.start)
    since = workspace.since.isoformat() if workspace is not None and workspace.since is not None else ""
    key = f"workspace:{period.workspace}:{since}"
    if key not in drafts:
        drafts[key] = SessionDraft(key, workspace, workspace.folder if workspace is not None else None)
    return drafts[key]


def _transcript_draft(drafts: dict[str, SessionDraft], transcript: Transcript) -> SessionDraft:
    # Only workspaces hold transcripts: folder sessions joining each other would depend on file order.
    holders = [
        d
        for d in drafts.values()
        if d.workspace is not None and d.folder is not None and _holds(d.folder, transcript.cwd)
    ]
    if holders:
        return max(holders, key=lambda d: len(d.folder or ""))
    key = f"folder:{transcript.cwd}"
    return drafts.setdefault(key, SessionDraft(key, None, transcript.cwd))


def _holds(folder: str, cwd: str) -> bool:
    root = folder.rstrip("/")
    return cwd == root or cwd.startswith(root + "/")


def _agent_states(drafts: dict[str, SessionDraft], derived: Sequence[Period], end: datetime.datetime) -> None:
    """Each session's agent state at the period's end, by the same rules as its periods.

    Working when an agent period of its workspace runs to the end. Blocked when one does, or when
    a pane's last agent event is a block the workspace did not close after: an agent waiting for
    an approval sends nothing more, so its period ends early, but it still waits at the period's
    end, however long ago it asked. Else idle when the workspace had an agent at all. A closed
    workspace and an agent herdr never stopped have no period running to the end.
    """
    for draft in drafts.values():
        if draft.workspace is None:
            continue
        own = [p for p in derived if p.workspace == draft.workspace.workspace_id and p.kind in (AGENT, BLOCKED)]
        if any(p.kind == AGENT and p.end >= end for p in own):
            draft.agent_state = WORKING
        elif any(p.kind == BLOCKED and p.end >= end for p in own) or _waits_at(draft.events, end):
            draft.agent_state = BLOCKED_STATE
        elif own or any(
            e.workspace == draft.workspace.workspace_id and e.kind.startswith("agent_") for e in draft.events
        ):
            draft.agent_state = IDLE


def _waits_at(events: Sequence[periods.Event], end: datetime.datetime) -> bool:
    """A pane whose last agent event up to ``end`` is a block, with no workspace close after it."""
    last: dict[str | None, str] = {}
    for event in sorted((e for e in events if e.time <= end), key=lambda e: e.time):
        if event.kind == periods.WORKSPACE_CLOSED:
            last.clear()
        elif event.kind in (periods.AGENT_WORKING, periods.AGENT_BLOCKED, periods.AGENT_STOPPED):
            last[event.pane] = event.kind
    return periods.AGENT_BLOCKED in last.values()
