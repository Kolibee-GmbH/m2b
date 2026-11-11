"""Sessions: the work of one workspace or one folder in the period, cut into blocks.

A session's work is the union of its agent, human and focus periods and the spans of its
transcripts (messages at most 15 minutes apart); waiting for an approval is not work. Everything is
clipped to the period, so a period crossing the watermark is counted once (B28). A session with
less than 2 minutes of work is left out (B33), and one without a prompt, a commit or an agent still
at work at the end needs 15 minutes, because a workspace looked at or an agent left running is
noise below that. Blocks are the work merged across gaps of up to 15 minutes; a block with less
than a minute of work is dropped, and a block's minutes are the work inside it, never its gaps.

The same minutes never land in two sessions. Workspaces on one folder are one session, so a
workspace closed and opened again, which herdr gives a new id, continues the same session. A
transcript belongs to a workspace whose folder, or one of whose panes' folders, holds its working
folder, preferring one that was open while the transcript was written and then the closest folder;
otherwise it is a session of its own. Its stamps also tell the periods that the workspace's agent
was still at work.
"""

from __future__ import annotations

import bisect
import datetime
from collections.abc import Mapping, Sequence
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
    present: float = 0.0
    """Seconds inside the block with the workspace in focus: the owner was there."""

    @property
    def minutes(self) -> int:
        return round(self.worked / 60)

    @property
    def minutes_present(self) -> int:
        return round(self.present / 60)


@dataclass
class SessionDraft:
    key: str
    workspace: Workspace | None
    folder: str | None
    series: dict[str, list[Interval]] = field(default_factory=dict)
    transcripts: list[Transcript] = field(default_factory=list)
    events: list[periods.Event] = field(default_factory=list)
    agent_state: str | None = None
    # Every herdr workspace id this session stands for: one per time the folder was opened.
    workspace_ids: set[str] = field(default_factory=set)

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
    by_workspace: dict[str, list[periods.Event]] = {}
    for event in sorted(events, key=lambda e: e.time):
        by_workspace.setdefault(event.workspace, []).append(event)
    recorded = {workspace_id: _Recorded.of(own) for workspace_id, own in by_workspace.items()}
    homes = {id(transcript): _home_of(transcript, workspaces, recorded) for transcript in transcripts}
    evidence: dict[str, list[datetime.datetime]] = {}
    for transcript in transcripts:
        home = homes[id(transcript)]
        if home is None:
            continue
        # Every workspace on the home's folder at the time: herdr may have recorded the agent under any of them.
        first = min([*transcript.earlier_stamps, *transcript.stamps])
        twins = {
            w.workspace_id
            for w in workspaces
            if (entry := workspace_at(workspaces, w.workspace_id, first)) is not None
            and entry.folder == home.holding_folder
        }
        for workspace_id in {home.workspace_id, *twins}:
            evidence.setdefault(workspace_id, []).extend([*transcript.earlier_stamps, *transcript.stamps])
    drafts: dict[str, SessionDraft] = {}
    derived = periods.derive_periods(events, now=end, evidence=evidence)
    for period in derived:
        clipped = clip((period.start, period.end), start, end)
        if clipped is None or period.kind not in (AGENT, HUMAN, FOCUS):
            continue
        draft = _workspace_draft(drafts, workspaces, period)
        draft.add(period.kind, clipped)
    for event in events:
        for draft in drafts.values():
            if event.workspace in draft.workspace_ids:
                draft.events.append(event)
    _agent_states(drafts, derived, end)
    for transcript in transcripts:
        draft = _transcript_draft(drafts, transcript, homes[id(transcript)])
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
    focused = merge(draft.series.get(FOCUS, []))
    for start, end in merge(work, gap=BLOCK_GAP):
        worked = length([piece for piece in work if start <= piece[0] and piece[1] <= end])
        if worked < MINIMUM_BLOCK.total_seconds():
            continue
        present = length([piece for piece in focused if start <= piece[0] and piece[1] <= end])
        inside = [p.text for p in prompts if start - BLOCK_GAP <= p.time <= end][-PROMPTS_PER_BLOCK:]
        found.append(SessionBlock(f"b{len(found) + 1}", start, end, inside, worked, present))
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
    folder = workspace.folder if workspace is not None else None
    same_folder = [d for d in drafts.values() if folder is not None and d.workspace is not None and d.folder == folder]
    if same_folder:
        draft = same_folder[0]
    else:
        since = workspace.since.isoformat() if workspace is not None and workspace.since is not None else ""
        key = f"workspace:{period.workspace}:{since}"
        draft = drafts.setdefault(key, SessionDraft(key, workspace, folder))
    draft.workspace_ids.add(period.workspace)
    return draft


@dataclass(frozen=True)
class _Recorded:
    """One workspace's events in time order, with what routing a transcript asks of them."""

    events: Sequence[periods.Event]
    times: Sequence[datetime.datetime]
    pane_folders: frozenset[str]

    @classmethod
    def of(cls, events: Sequence[periods.Event]) -> _Recorded:
        return cls(events, [e.time for e in events], frozenset(e.cwd for e in events if e.cwd is not None))


@dataclass(frozen=True)
class _Home:
    workspace_id: str
    # The workspace's folder when the transcript began; it tells apart two uses of a reused id.
    workspace_folder: str | None
    # The closest folder that holds the transcript: the workspace's own, else one of its panes'.
    holding_folder: str


def _home_of(transcript: Transcript, workspaces: list[Workspace], recorded: Mapping[str, _Recorded]) -> _Home | None:
    """The workspace a transcript was written in, or None when no workspace's folder holds it.

    A workspace holds it when its folder, or the folder of one of its panes, holds the transcript's
    working folder. One that was open while the transcript was written comes first, then one whose
    own folder holds it (a pane can wander into another workspace's folder), then the closest
    folder, then the one opened last.
    """
    stamps = [*transcript.earlier_stamps, *transcript.stamps]
    if not stamps:
        return None
    first, last = min(stamps), max(stamps)
    candidates: list[tuple[tuple[bool, bool, int, datetime.datetime, str], _Home]] = []
    nothing = _Recorded.of(())
    for workspace_id in set(recorded) | {w.workspace_id for w in workspaces}:
        own = recorded.get(workspace_id, nothing)
        entry = workspace_at(workspaces, workspace_id, first)
        folder = entry.folder if entry is not None else None
        roots = own.pane_folders | ({folder} if folder is not None else set())
        holding = [root for root in roots if _holds(root, transcript.cwd)]
        if not holding:
            continue
        by_own_folder = folder is not None and _holds(folder, transcript.cwd)
        closest = max(holding, key=len)
        since = entry.since if entry is not None and entry.since is not None else first
        rank = (_open_during(own, first, last), by_own_folder, len(closest), since, workspace_id)
        candidates.append(
            (rank, _Home(workspace_id, folder, folder if folder is not None and by_own_folder else closest))
        )
    return max(candidates, key=lambda candidate: candidate[0])[1] if candidates else None


def _open_during(recorded: _Recorded, first: datetime.datetime, last: datetime.datetime) -> bool:
    """The workspace was open at some moment between ``first`` and ``last``."""
    count = bisect.bisect_right(recorded.times, last)
    if count == 0:
        return False
    latest = recorded.events[count - 1]
    return latest.time >= first or latest.kind != periods.WORKSPACE_CLOSED


def _transcript_draft(drafts: dict[str, SessionDraft], transcript: Transcript, home: _Home | None) -> SessionDraft:
    """The home's session on the home's folder, else any workspace session on a folder holding it.

    Only when no workspace session holds it is it a session of its own: folder sessions joining each
    other would depend on file order.
    """
    workspace_drafts = [d for d in drafts.values() if d.workspace_ids]
    if home is not None:
        of_home = [d for d in workspace_drafts if home.workspace_id in d.workspace_ids]
        for draft in of_home:
            # The cache entry's folder, which stays put when a folderless session takes a transcript's.
            original = draft.workspace.folder if draft.workspace is not None else None
            if original == home.workspace_folder:
                if draft.folder is None and transcript.stamps:
                    draft.folder = home.holding_folder
                return draft
    holders = [d for d in workspace_drafts if d.folder is not None and _holds(d.folder, transcript.cwd)]
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
    end, however long ago it asked within the events read (three days before the period): a block
    older than that, often left by a crash, is no longer reported. Else idle when the workspace had an
    agent at all. A closed workspace and an agent herdr never stopped have no period running to the end.
    """
    for draft in drafts.values():
        if draft.workspace is None:
            continue
        own = [p for p in derived if p.workspace in draft.workspace_ids and p.kind in (AGENT, BLOCKED)]
        if any(p.kind == AGENT and p.end >= end for p in own):
            draft.agent_state = WORKING
        elif any(p.kind == BLOCKED and p.end >= end for p in own) or _waits_at(draft.events, end):
            draft.agent_state = BLOCKED_STATE
        elif own or any(e.kind.startswith("agent_") for e in draft.events):
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
