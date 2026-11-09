"""The worklog's activity recorder: herdr starts it once per event, it appends one line.

It runs from its own copy outside any plugin cache and imports nothing but the standard library,
so it never depends on a version of m2b. Before writing it checks three things, and records nothing
when any fails (B38): the m2b plugin is still listed in Claude Code's
``installed_plugins.json``, it is not turned off in ``enabledPlugins`` (managed settings first, then
the user's), and the switch file says ``on``. Uninstalling or turning off the plugin through
``/plugin`` therefore stops recording even while herdr still has the recorder linked.

Each event becomes ``{"time", "kind", "workspace", "pane", "cwd"}`` in
``~/.local/state/m2b/worklog/<workspace id>.jsonl``. The pane's folder and the workspace's repository,
label and folder come from herdr's snapshot; the workspace cache keeps one entry per folder a
workspace id was seen with, so an id herdr reuses for another folder starts a new entry.

Whatever goes wrong, it exits 0 and prints nothing: a herdr hook must not disturb herdr.
"""

from __future__ import annotations

import contextlib
import datetime
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

PLUGIN_KEY = "m2b@m2b"
SWITCH_FILE = "recording"
SWITCH_ON = "on"
CACHE_FILE = "workspaces.json"
CACHE_LOCK = "workspaces.lock"
SNAPSHOT_TIMEOUT_SECONDS = 2.0

AGENT_WORKING = "agent_working"
AGENT_BLOCKED = "agent_blocked"
AGENT_STOPPED = "agent_stopped"
FOCUS = "focus"
WORKSPACE_OPENED = "workspace_opened"
WORKSPACE_CLOSED = "workspace_closed"
KINDS = (AGENT_WORKING, AGENT_BLOCKED, AGENT_STOPPED, FOCUS, WORKSPACE_OPENED, WORKSPACE_CLOSED)

STATUS_KINDS = {"working": AGENT_WORKING, "blocked": AGENT_BLOCKED}
EVENT_KINDS = {
    "pane.exited": AGENT_STOPPED,
    "pane.closed": AGENT_STOPPED,
    "pane.focused": FOCUS,
    "workspace.focused": FOCUS,
    "workspace.created": WORKSPACE_OPENED,
    "worktree.opened": WORKSPACE_OPENED,
    "workspace.closed": WORKSPACE_CLOSED,
}
STATUS_EVENT = "pane.agent_status_changed"
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


def home(environ: Mapping[str, str]) -> Path:
    return Path(environ.get("M2B_HOME") or environ.get("HOME") or str(Path.home()))


def state_dir(environ: Mapping[str, str]) -> Path:
    return home(environ) / ".local" / "state" / "m2b" / "worklog"


def installed_plugins_file(environ: Mapping[str, str]) -> Path:
    override = environ.get("M2B_INSTALLED_PLUGINS")
    if override:
        return Path(override)
    claude_dir = environ.get("CLAUDE_CONFIG_DIR") or str(Path(environ.get("HOME") or str(Path.home())) / ".claude")
    return Path(claude_dir) / "plugins" / "installed_plugins.json"


def m2b_installed(environ: Mapping[str, str]) -> bool:
    try:
        with installed_plugins_file(environ).open(encoding="utf-8") as handle:
            entries = json.load(handle)["plugins"].get(PLUGIN_KEY)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False
    return isinstance(entries, list) and len(entries) > 0


MANAGED_SETTINGS = {
    "darwin": "/Library/Application Support/ClaudeCode/managed-settings.json",
    "linux": "/etc/claude-code/managed-settings.json",
}


def settings_files(environ: Mapping[str, str]) -> list[Path]:
    """Managed settings first, as they override the user's (Claude Code's settings docs)."""
    managed = environ.get("M2B_MANAGED_SETTINGS") or next(
        (path for prefix, path in MANAGED_SETTINGS.items() if sys.platform.startswith(prefix)), None
    )
    claude_dir = environ.get("CLAUDE_CONFIG_DIR") or str(Path(environ.get("HOME") or str(Path.home())) / ".claude")
    return [*([Path(managed)] if managed else []), Path(claude_dir) / "settings.json"]


def m2b_enabled(environ: Mapping[str, str]) -> bool:
    """Not turned off; a settings file that exists but cannot be read counts as off."""
    for path in settings_files(environ):
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            value = raw.get("enabledPlugins", {}).get(PLUGIN_KEY) if isinstance(raw, dict) else None
        except (OSError, ValueError, AttributeError):
            return False
        if isinstance(value, bool):
            return value
    return True


def recording_on(environ: Mapping[str, str]) -> bool:
    try:
        return (state_dir(environ) / SWITCH_FILE).read_text(encoding="utf-8").strip() == SWITCH_ON
    except (OSError, UnicodeDecodeError):
        return False


def event_data(environ: Mapping[str, str]) -> tuple[str, dict[str, Any]] | None:
    """The event's name and payload; herdr's payload may come wrapped in ``{"event", "data"}``."""
    try:
        payload = json.loads(environ.get("HERDR_PLUGIN_EVENT_JSON", ""))
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    wrapped = payload.get("data")
    data: dict[str, Any] = wrapped if isinstance(wrapped, dict) else payload
    name = environ.get("HERDR_PLUGIN_EVENT") or ""
    kind = data.get("type")
    if not name and isinstance(kind, str):
        name = kind.replace("_", ".", 1)
    return name, data


def kind_of(name: str, data: Mapping[str, Any]) -> str | None:
    if name == STATUS_EVENT:
        status = data.get("agent_status")
        return STATUS_KINDS.get(status, AGENT_STOPPED) if isinstance(status, str) else None
    return EVENT_KINDS.get(name)


def workspace_of(data: Mapping[str, Any]) -> str | None:
    workspace = data.get("workspace_id")
    if not isinstance(workspace, str) and isinstance(data.get("workspace"), dict):
        workspace = data["workspace"].get("workspace_id")
    return workspace if isinstance(workspace, str) and _SAFE_ID.match(workspace) else None


def read_snapshot(environ: Mapping[str, str]) -> dict[str, Any] | None:
    command = environ.get("HERDR_BIN_PATH") or environ.get("M2B_HERDR") or "herdr"
    try:
        result = subprocess.run(
            [command, "api", "snapshot"],
            capture_output=True,
            text=True,
            timeout=SNAPSHOT_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
            env=dict(environ),
        )
        reply = json.loads(result.stdout) if result.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    part = reply.get("result") if isinstance(reply, dict) else None
    snapshot = part.get("snapshot") if isinstance(part, dict) else None
    return snapshot if isinstance(snapshot, dict) else None


def pane_cwd(snapshot: Mapping[str, Any] | None, pane: str | None) -> str | None:
    if snapshot is None or pane is None:
        return None
    for listed in [*_objects(snapshot.get("panes")), *_objects(snapshot.get("agents"))]:
        if listed.get("pane_id") == pane and isinstance(listed.get("cwd"), str):
            return str(listed["cwd"])
    return None


def workspace_entry(
    snapshot: Mapping[str, Any] | None, data: Mapping[str, Any], workspace: str, cwd: str | None
) -> tuple[dict[str, str | None], bool]:
    """Repository, label and folder of the workspace, and whether the folder is its worktree's.

    Only a worktree's checkout path names the workspace's folder for sure; a pane's folder is a
    fallback for a workspace without one, and its panes may sit in different folders.
    """
    info: Mapping[str, Any] | None = None
    if snapshot is not None:
        info = next((w for w in _objects(snapshot.get("workspaces")) if w.get("workspace_id") == workspace), None)
    if info is None and isinstance(data.get("workspace"), dict):
        info = data["workspace"]
    worktree = info.get("worktree") if info is not None else None
    repo = worktree.get("repo_name") if isinstance(worktree, dict) else None
    checkout = worktree.get("checkout_path") if isinstance(worktree, dict) else None
    label = info.get("label") if info is not None else None
    entry = {
        "repo": repo if isinstance(repo, str) else None,
        "label": label if isinstance(label, str) else None,
        "folder": checkout if isinstance(checkout, str) else cwd,
    }
    return entry, isinstance(checkout, str)


def update_cache(folder: Path, workspace: str, entry: Mapping[str, str | None], is_worktree: bool, time: str) -> None:
    """A new entry when the workspace id comes back with another worktree; else the newest entry is updated."""
    if all(value is None for value in entry.values()):
        return
    with (folder / CACHE_LOCK).open("a", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        cache_path = folder / CACHE_FILE
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cache = {}
        if not isinstance(cache, dict):
            cache = {}
        entries = cache.get(workspace)
        entries = entries if isinstance(entries, list) else []
        last = entries[-1] if entries and isinstance(entries[-1], dict) else None
        if last is None or _another_workspace(last, entry, is_worktree):
            entries.append({**entry, "since": time})
        else:
            # Without a folder, a plain workspace's event cannot tell a rename from a reused id: the next
            # event with a folder decides, so it changes no label.
            changed = {
                key: value
                for key, value in entry.items()
                if value is not None
                and last.get(key) != value
                and (key != "folder" or is_worktree or last.get(key) is None)
                and (key != "label" or is_worktree or entry["folder"] is not None)
            }
            if not changed:
                return
            last.update(changed)
        cache[workspace] = entries
        _replace(cache_path, json.dumps(cache, ensure_ascii=False, indent=1) + "\n")


def _another_workspace(last: Mapping[str, Any], entry: Mapping[str, str | None], is_worktree: bool) -> bool:
    """The id stands for another workspace: another worktree, or for a plain one another folder and label.

    Panes of one plain workspace sit in different folders, so a folder alone does not say so.
    """
    if entry["folder"] is None or entry["folder"] == last.get("folder"):
        return False
    return is_worktree or (entry["label"] is not None and entry["label"] != last.get("label"))


def record(environ: Mapping[str, str], now: datetime.datetime) -> bool:
    """Appends the event's line; False when nothing was written."""
    if not m2b_installed(environ) or not m2b_enabled(environ) or not recording_on(environ):
        return False
    event = event_data(environ)
    if event is None:
        return False
    name, data = event
    kind = kind_of(name, data)
    workspace = workspace_of(data)
    if kind is None or workspace is None:
        return False
    pane = data.get("pane_id") if isinstance(data.get("pane_id"), str) else None
    snapshot = read_snapshot(environ)
    cwd = pane_cwd(snapshot, pane)
    # Milliseconds: the time is the only order between recorders herdr runs at once.
    time = now.isoformat(timespec="milliseconds")
    line = json.dumps({"time": time, "kind": kind, "workspace": workspace, "pane": pane, "cwd": cwd}) + "\n"
    folder = state_dir(environ)
    folder.mkdir(parents=True, exist_ok=True)
    # One write of one short line on a file opened for appending: herdr may run several recorders at once.
    descriptor = os.open(folder / f"{workspace}.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(descriptor, line.encode("utf-8"))
    finally:
        os.close(descriptor)
    entry, is_worktree = workspace_entry(snapshot, data, workspace, cwd)
    update_cache(folder, workspace, entry, is_worktree, time)
    return True


def _objects(value: object) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _replace(path: Path, text: str) -> None:
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def main() -> int:
    # A herdr hook must not disturb herdr, whatever went wrong.
    with contextlib.suppress(Exception):
        record(os.environ, datetime.datetime.now().astimezone())
    return 0


if __name__ == "__main__":
    sys.exit(main())
