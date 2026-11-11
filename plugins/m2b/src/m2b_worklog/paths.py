"""Where the worklog keeps its files on this machine, under ``M2B_HOME`` when set (tests)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
RECORDER_SOURCE = PLUGIN_ROOT / "recorder"
RECORDER_ID = "m2b.worklog-recorder"
SWITCH_FILE = "recording"
SWITCH_ON = "on"
SWITCH_OFF = "off"


@dataclass(frozen=True)
class WorklogPaths:
    home: Path

    @property
    def state_dir(self) -> Path:
        """What the recorder writes: one events file per workspace, the workspace cache, the switch."""
        return self.home / ".local" / "state" / "m2b" / "worklog"

    @property
    def run_dir(self) -> Path:
        """The facts and the verdict of the worklog being written, between collect and the model's verdict."""
        return self.home / ".local" / "state" / "m2b" / "worklog-run"

    @property
    def verdict_draft(self) -> Path:
        """Where the verdict's model step writes its verdict before it hands it in."""
        return self.run_dir / "verdict-draft.json"

    @property
    def switch(self) -> Path:
        return self.state_dir / SWITCH_FILE

    @property
    def recorder_copy(self) -> Path:
        """The copy herdr links: outside the plugin cache, whose folders disappear after an update."""
        return self.home / ".local" / "share" / "m2b" / "worklog-recorder"

    @property
    def launcher(self) -> Path:
        return self.home / ".local" / "bin" / "m2b"


def worklog_paths(environ: Mapping[str, str]) -> WorklogPaths:
    return WorklogPaths(Path(environ.get("M2B_HOME") or environ.get("HOME") or str(Path.home())))
