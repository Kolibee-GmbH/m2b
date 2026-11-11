"""Shared test setup: a temporary home, a fake herdr and timer, a fake installed_plugins.json, the recorder module."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
RECORDER_DIR = PLUGIN_ROOT / "recorder"
COMMAND = PLUGIN_ROOT / "bin" / "m2b-worklog"
FAKES = Path(__file__).resolve().parent / "fakes"


def load_recorder() -> ModuleType:
    """The recorder script as a module: it lives outside any package, as its installed copy does."""
    spec = importlib.util.spec_from_file_location("worklog_record", RECORDER_DIR / "record.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def executable(path: Path, script: Path, name: str = "") -> Path:
    named = f"FAKE_COMMAND_NAME={name} " if name else ""
    path.write_text(f'#!/bin/sh\n{named}exec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
    path.chmod(0o755)
    return path


def snapshot_reply(workspaces: list[dict[str, Any]], panes: list[dict[str, Any]]) -> str:
    snapshot = {"version": "0.9.3", "protocol": 22, "workspaces": workspaces, "tabs": [], "panes": panes}
    snapshot.update({"layouts": [], "agents": []})
    return json.dumps({"id": "r1", "result": {"type": "session_snapshot", "snapshot": snapshot}})


class WorklogFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.base = Path(self._temp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.state = self.home / ".local" / "state" / "m2b" / "worklog"
        self.installed = self.base / "installed_plugins.json"
        self.herdr_state = self.base / "herdr-state.json"
        self.herdr_calls = self.base / "herdr-calls.txt"
        self.herdr_reply = self.base / "snapshot.json"
        self.herdr = executable(self.base / "herdr", FAKES / "fake_herdr.py")
        self.timer_calls = self.base / "timer-calls.txt"
        self.launchctl = executable(self.base / "launchctl", FAKES / "fake_timer.py", name="launchctl")
        self.systemctl = executable(self.base / "systemctl", FAKES / "fake_timer.py", name="systemctl")
        self.environ = {
            "HOME": str(self.base / "not-the-home"),
            "M2B_HOME": str(self.home),
            "M2B_INSTALLED_PLUGINS": str(self.installed),
            "M2B_HERDR": str(self.herdr),
            "FAKE_HERDR_STATE": str(self.herdr_state),
            "FAKE_HERDR_CALLS": str(self.herdr_calls),
            "FAKE_HERDR_REPLY": str(self.herdr_reply),
            "CLAUDE_CONFIG_DIR": str(self.base / "claude-config"),
            "M2B_MANAGED_SETTINGS": str(self.base / "no-managed-settings.json"),
            "M2B_LAUNCHCTL": str(self.launchctl),
            "M2B_SYSTEMCTL": str(self.systemctl),
            "FAKE_TIMER_CALLS": str(self.timer_calls),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "M2B_TIMER_PLATFORM": "darwin",
        }

    def install_plugins(self, *keys: str) -> None:
        plugins = {key: [{"scope": "user", "installPath": f"/plugins/{key}", "version": "0.1.0"}] for key in keys}
        self.installed.write_text(json.dumps({"version": 2, "plugins": plugins}), encoding="utf-8")

    def claude_settings(self, settings: dict[str, Any], managed: bool = False) -> None:
        path = self.base / ("managed-settings.json" if managed else "claude-config/settings.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings), encoding="utf-8")
        if managed:
            self.environ["M2B_MANAGED_SETTINGS"] = str(path)

    def switch(self, value: str) -> None:
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / "recording").write_text(value + "\n", encoding="utf-8")

    def linked(self) -> dict[str, str]:
        if not self.herdr_state.exists():
            return {}
        linked: dict[str, str] = json.loads(self.herdr_state.read_text(encoding="utf-8"))["linked"]
        return linked

    def herdr_holds_version(self, version: str) -> None:
        """As herdr does for a recorder linked by an older m2b: the registration from back then."""
        state = json.loads(self.herdr_state.read_text(encoding="utf-8"))
        state["versions"] = {key: version for key in state["linked"]}
        self.herdr_state.write_text(json.dumps(state), encoding="utf-8")

    def timer_calls_made(self) -> list[str]:
        return self.timer_calls.read_text(encoding="utf-8").splitlines() if self.timer_calls.exists() else []

    def herdr_calls_made(self) -> list[str]:
        return self.herdr_calls.read_text(encoding="utf-8").splitlines() if self.herdr_calls.exists() else []
