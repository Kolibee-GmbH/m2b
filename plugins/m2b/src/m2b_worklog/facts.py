"""The facts for one period: what the verdict reads, typed, and written as ``worklog-facts.schema.json`` says.

The period starts at the watermark in ``state/addons/worklog/watermark.json`` and ends now; it
reaches at most three days back, so a long pause costs one catch-up of three days, not more. A
watermark that cannot be read is an error rather than a fresh start, which would count again what
an earlier worklog counted.
"""

from __future__ import annotations

import datetime
import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from m2b_worklog import classify, periods, sessions
from m2b_worklog.sources import READ, SourceState
from m2b_worklog.sources.git import GitFacts, Runner, read_git
from m2b_worklog.sources.herdr_events import read_recordings
from m2b_worklog.sources.inbox import is_evicted, read_inbox
from m2b_worklog.sources.transcripts import read_transcripts

FACTS_VERSION = 1
WATERMARK = "state/addons/worklog/watermark.json"
# How far before the period the recorder's events are read; everything older is left unread.
EVENT_REACH = datetime.timedelta(days=3)
MAX_REACH = datetime.timedelta(days=3)
WATERMARK_ORIGIN = "watermark"
FIRST_RUN_ORIGIN = "first run"
LIMITED_ORIGIN = "watermark, limited to three days"


HERDR_NOT_CHECKED = SourceState(READ, "not checked")


class FactsError(Exception):
    """The period cannot be collected."""


@dataclass(frozen=True)
class Inputs:
    store: Path
    recordings: Path
    transcripts: Path
    home: Path
    profile: Mapping[str, Any]
    now: datetime.datetime
    git: str = "git"
    # Whether herdr runs with the recorder linked; the command asks herdr (recorder.herdr_state).
    herdr: SourceState = HERDR_NOT_CHECKED


@dataclass(frozen=True)
class Period:
    start: datetime.datetime
    end: datetime.datetime
    origin: str


def read_watermark(store: Path) -> datetime.datetime | None:
    path = store / WATERMARK
    if not path.exists():
        return None
    if is_evicted(path):
        raise FactsError(f"the watermark {WATERMARK} is not downloaded; m2b store fetch {WATERMARK} downloads it")
    try:
        moment = datetime.datetime.fromisoformat(json.loads(path.read_text(encoding="utf-8"))["end"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise FactsError(
            f"the watermark {WATERMARK} cannot be read ({error}); write the end of the last worklog into its "
            '"end" by hand: m2b-worklog state shows it as the end of the last period in the ledger'
        ) from error
    if moment.tzinfo is None:
        raise FactsError(f"the watermark {WATERMARK} has a time without an offset")
    return moment


def period_for(watermark: datetime.datetime | None, now: datetime.datetime) -> Period:
    earliest = now - MAX_REACH
    if watermark is None:
        return Period(earliest, now, FIRST_RUN_ORIGIN)
    if watermark >= now:
        raise FactsError(f"the watermark {watermark.isoformat()} is not before now; nothing to collect")
    if watermark < earliest:
        return Period(earliest, now, LIMITED_ORIGIN)
    return Period(watermark, now, WATERMARK_ORIGIN)


def collect(inputs: Inputs, run: Runner = subprocess.run) -> dict[str, Any]:
    period = period_for(read_watermark(inputs.store), inputs.now)
    # Older events add no time: an agent counts at most 30 minutes past its last sign of life (B87).
    recordings = read_recordings(inputs.recordings, since=period.start - EVENT_REACH)
    # Stamps just before the period keep an agent that was at work across the last cut counting (B84).
    signs_from = period.start - periods.RULES.agent_silence
    transcripts = read_transcripts(inputs.transcripts, period.start, period.end, signs_from)
    inbox = read_inbox(inputs.store, period.start, period.end)
    drafts = sessions.draft_sessions(
        recordings.events, recordings.workspaces, transcripts.transcripts, period.start, period.end
    )
    rules = classify.sphere_rules(inputs.profile, inputs.home)
    zone = period.end.tzinfo
    gits = {draft.key: _git_facts(draft.folder, period, inputs.git, run) for draft in drafts}
    blocks = {draft.key: sessions.blocks_of(draft) for draft in drafts}
    owners = _commit_owners(drafts, gits, blocks)
    # After ownership: a commit another worktree of the repository made keeps no session. Dropping a
    # session that owns nothing changes no owner.
    owning = set(owners.values())
    drafts = [
        draft
        for draft in drafts
        if sessions.worth_naming(
            draft,
            owns_commit=draft.key in owning,
            all_read=gits[draft.key].state.is_read and transcripts.state.is_read,
        )
    ]
    return {
        "version": FACTS_VERSION,
        "period": {"start": _iso(period.start, zone), "end": _iso(period.end, zone), "origin": period.origin},
        "sources": {
            "recorder": _state(recordings.state),
            "herdr": _state(inputs.herdr),
            "transcripts": _state(transcripts.state),
            "inbox": _state(inbox.state),
        },
        "spheres": [{"id": r.sphere_id, "label": r.label, "billable": r.billable, "default": r.default} for r in rules],
        "customers": [c for c in inputs.profile.get("customers", []) if isinstance(c, str)],
        "sessions": [_session(draft, gits[draft.key], blocks[draft.key], owners, rules, zone) for draft in drafts],
        "captures": [{"name": c.name, "created": _iso(c.created, zone), "source": c.source} for c in inbox.captures],
    }


def _commit_owners(
    drafts: list[sessions.SessionDraft], gits: Mapping[str, GitFacts], blocks: Mapping[str, list[sessions.SessionBlock]]
) -> dict[str, str]:
    """Each commit to one session: worktrees of a repository all see every branch.

    The session with a block around the commit's time wins, then the one whose checked-out branch
    carries it, then the deepest folder.
    """
    owners: dict[str, str] = {}
    seen: dict[str, list[sessions.SessionDraft]] = {}
    times: dict[str, datetime.datetime] = {}
    for draft in drafts:
        for commit in gits[draft.key].commits:
            seen.setdefault(commit.commit_hash, []).append(draft)
            times[commit.commit_hash] = commit.time
    for commit_hash, holders in seen.items():
        owners[commit_hash] = max(holders, key=lambda d: _rank(d, commit_hash, times[commit_hash], gits, blocks)).key
    return owners


def _rank(
    draft: sessions.SessionDraft,
    commit_hash: str,
    moment: datetime.datetime,
    gits: Mapping[str, GitFacts],
    blocks: Mapping[str, list[sessions.SessionBlock]],
) -> tuple[bool, bool, int]:
    """Active near the commit, then on the branch the folder has checked out, then the deepest folder."""
    near = any(b.start - sessions.BLOCK_GAP <= moment <= b.end + sessions.BLOCK_GAP for b in blocks[draft.key])
    on_head = any(c.commit_hash == commit_hash and c.on_head for c in gits[draft.key].commits)
    return near, on_head, len(draft.folder or "")


def _session(
    draft: sessions.SessionDraft,
    facts: GitFacts,
    blocks: list[sessions.SessionBlock],
    owners: Mapping[str, str],
    rules: list[classify.SphereRule],
    zone: datetime.tzinfo | None,
) -> dict[str, Any]:
    workspace = draft.workspace
    return {
        "key": draft.key,
        "workspace": workspace.workspace_id if workspace is not None else None,
        "repo": workspace.repo if workspace is not None else None,
        "label": workspace.label if workspace is not None else None,
        "folder": draft.folder,
        "sphere": classify.sphere_of(rules, draft.folder, facts.remote),
        "minutes": draft.minutes(),
        "blocks": [
            {
                "id": b.block_id,
                "start": _iso(b.start, zone),
                "end": _iso(b.end, zone),
                "minutes": b.minutes,
                "minutes_present": b.minutes_present,
                "prompts": b.prompts,
            }
            for b in blocks
        ],
        "git": _state(facts.state),
        "commits": [
            {"time": _iso(c.time, zone), "subject": c.subject}
            for c in facts.commits
            if owners.get(c.commit_hash) == draft.key
        ],
        "state": {"agent": draft.agent_state, "last_answer": draft.last_answer()},
    }


def _git_facts(folder: str | None, period: Period, git: str, run: Runner) -> GitFacts:
    if folder is None:
        return GitFacts([], None, SourceState.failed("the session has no known folder"))
    if not Path(folder).is_dir():
        return GitFacts([], None, SourceState.failed(f"the folder {folder} no longer exists"))
    return read_git(Path(folder), period.start, period.end, git, run)


def _state(state: SourceState) -> dict[str, str]:
    return {"state": state.state, "detail": state.detail}


def _iso(moment: datetime.datetime, zone: datetime.tzinfo | None) -> str:
    """Every time in one offset, the period end's: transcript stamps come in UTC."""
    return moment.astimezone(zone).isoformat(timespec="seconds")
