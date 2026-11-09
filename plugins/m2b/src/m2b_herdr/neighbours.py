"""Neighbour sessions: the other agent sessions herdr has open, one line each (B10).

The hook runs only while the herdr add-on is on, only inside herdr (``HERDR_PANE_ID`` set) and never
inside a curation run: hooks fire in ``claude -p`` too, and a model step has no use for neighbours.
It reads ``herdr api snapshot`` with a 2 second limit; when that fails, it says so in one line
instead of printing nothing, so "herdr could not be read" never looks like "no other sessions".
Idle and finished sessions stay listed: an open task is exactly what a new one can overlap with.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

PANE_VARIABLE = "HERDR_PANE_ID"
CURATION_RUN_VARIABLE = "M2B_CURATION_RUN"
COMMAND_VARIABLE = "M2B_HERDR"
SNAPSHOT_ARGUMENTS = ("api", "snapshot")
TIMEOUT_SECONDS = 2.0
MAX_BLOCK_BYTES = 3072
# The core of the same plugin, so its answer matches this version; the launcher is for outside callers.
CORE_COMMAND = Path(__file__).resolve().parents[2] / "bin" / "m2b"
ADDON = "herdr"
# With the 2 second snapshot after it, this stays inside the hook's 10 seconds in hooks.json.
ADDON_TIMEOUT_SECONDS = 5.0

HEADER = (
    "m2b neighbours (other agent sessions open in herdr right now; each: workspace · task · state · "
    "place). If your task overlaps with one of them, say so briefly before you start; otherwise do "
    "not mention them."
)
NO_TASK = "no title"
STATES = {
    "working": "working",
    "blocked": "waiting for approval",
    "idle": "idle",
    "done": "done, not looked at yet",
}
UNKNOWN_STATE = "state unknown"

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class HerdrError(Exception):
    """herdr did not answer with a session snapshot."""


@dataclass(frozen=True)
class Neighbour:
    workspace: str
    task: str
    state: str
    place: str

    def line(self) -> str:
        parts = [self.workspace, self.task or NO_TASK, self.state]
        if self.place:
            parts.append(self.place)
        return "- " + " · ".join(parts)


def herdr_command(environ: Mapping[str, str]) -> str:
    return environ.get(COMMAND_VARIABLE) or "herdr"


def read_snapshot(command: str, run: Runner = subprocess.run) -> dict[str, Any]:
    """The ``snapshot`` object of ``herdr api snapshot``; HerdrError says why there is none."""
    try:
        result = run(
            [command, *SNAPSHOT_ARGUMENTS],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError as error:
        raise HerdrError(f"{command} was not found") from error
    except subprocess.TimeoutExpired as error:
        raise HerdrError(f"herdr did not answer within {TIMEOUT_SECONDS:g} seconds") from error
    except (OSError, UnicodeDecodeError) as error:
        raise HerdrError(f"herdr could not be run: {error}") from error
    if result.returncode != 0:
        reason = result.stderr.strip().splitlines()[:1]
        raise HerdrError(
            f"herdr api snapshot ended with exit {result.returncode}" + (f": {reason[0]}" if reason else "")
        )
    try:
        reply = json.loads(result.stdout)
    except ValueError as error:
        raise HerdrError("herdr answered something that is not JSON") from error
    result_part = reply.get("result") if isinstance(reply, dict) else None
    snapshot = result_part.get("snapshot") if isinstance(result_part, dict) else None
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("agents"), list):
        raise HerdrError("herdr answered without a session snapshot")
    return snapshot


def neighbours(snapshot: Mapping[str, Any], own_pane: str | None) -> list[Neighbour]:
    """Every agent in the snapshot but the one in ``own_pane``, in the snapshot's order."""
    labels = {
        workspace["workspace_id"]: workspace["label"]
        for workspace in snapshot.get("workspaces", [])
        if isinstance(workspace, dict) and _is_text(workspace.get("workspace_id")) and _is_text(workspace.get("label"))
    }
    found = []
    for agent in snapshot["agents"]:
        if not isinstance(agent, dict) or not _is_text(agent.get("pane_id")) or agent["pane_id"] == own_pane:
            continue
        workspace_id = agent.get("workspace_id")
        workspace = (
            labels.get(workspace_id, workspace_id) if isinstance(workspace_id, str) and workspace_id else "session"
        )
        status = agent.get("agent_status")
        found.append(
            Neighbour(
                workspace=workspace,
                task=task_of(agent.get("terminal_title_stripped")),
                state=STATES.get(status, UNKNOWN_STATE) if isinstance(status, str) else UNKNOWN_STATE,
                place=place_of(agent.get("cwd")),
            )
        )
    return found


def task_of(title: object) -> str:
    """The terminal title without the agent's glyph and a spinner in front: single-character words."""
    if not isinstance(title, str):
        return ""
    words = title.split()
    while words and len(words[0]) == 1 and not words[0].isascii():
        words.pop(0)
    while words and len(words[0]) == 1 and not words[0].isalnum():
        words.pop(0)
    return " ".join(words)


def place_of(cwd: object) -> str:
    if not isinstance(cwd, str):
        return ""
    parts = [part for part in cwd.split("/") if part]
    return "/".join(parts[-2:])


def render(found: Sequence[Neighbour]) -> str:
    """The block for the session's context, at most MAX_BLOCK_BYTES, or nothing without neighbours."""
    if not found:
        return ""
    entries = [neighbour.line() for neighbour in found]
    for shown in range(len(entries), 0, -1):
        hidden = len(entries) - shown
        lines = [HEADER, *entries[:shown], *([_more(hidden)] if hidden else [])]
        if _size(lines) <= MAX_BLOCK_BYTES:
            return "\n".join(lines) + "\n"
    return f"{HEADER}\n{_more(len(entries))}\n"


def hook_output(environ: Mapping[str, str], run: Runner = subprocess.run) -> str:
    """What the session-start hook prints: nothing outside herdr or in a curation run."""
    own_pane = environ.get(PANE_VARIABLE)
    if not own_pane or environ.get(CURATION_RUN_VARIABLE) == "1":
        return ""
    try:
        snapshot = read_snapshot(herdr_command(environ), run)
    except HerdrError as error:
        return f"m2b neighbours: herdr could not be read ({error}).\n"
    return render(neighbours(snapshot, own_pane))


def addon_on(environ: Mapping[str, str], run: Runner = subprocess.run) -> bool:
    """Whether ``m2b addons list`` says the herdr add-on is on; m2b not set up, or no answer, is off."""
    try:
        result = run(
            [str(CORE_COMMAND), "addons", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=ADDON_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
            env=dict(environ),
        )
        rows = json.loads(result.stdout) if result.returncode == 0 else []
    except (OSError, subprocess.SubprocessError, ValueError):
        return False
    return isinstance(rows, list) and any(
        isinstance(row, dict) and row.get("name") == ADDON and row.get("on") is True for row in rows
    )


def _more(hidden: int) -> str:
    return f"and {hidden} more"


def _size(lines: Sequence[str]) -> int:
    return len(("\n".join(lines) + "\n").encode("utf-8"))


def _is_text(value: object) -> bool:
    return isinstance(value, str) and value != ""
