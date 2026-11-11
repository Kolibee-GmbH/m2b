"""Every path on the machine, derived from one root.

The root is the user's home folder, or ``M2B_HOME`` when set; tests point it
at a temporary folder, and then nothing reads or writes the user's own setup. A ``~`` in
a configured path means this root as well.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

HOME_VARIABLE = "M2B_HOME"
PRODUCT_FOLDER = "m2b"


@dataclass(frozen=True)
class MachinePaths:
    home: Path

    @property
    def config_file(self) -> Path:
        return self.home / ".config" / PRODUCT_FOLDER / "config.json"

    @property
    def state_dir(self) -> Path:
        return self.home / ".local" / "state" / PRODUCT_FOLDER

    @property
    def session_seen_file(self) -> Path:
        """When a session last ran m2b's own hooks; the launcher hook writes it."""
        return self.state_dir / "session-seen.json"

    @property
    def band_seen_file(self) -> Path:
        """When a session last started the band; the band, a mod in TypeScript, writes it."""
        return self.state_dir / "band-seen.json"

    @property
    def temp_dir(self) -> Path:
        return self.state_dir / "tmp"

    @property
    def share_dir(self) -> Path:
        return self.home / ".local" / "share" / PRODUCT_FOLDER

    @property
    def launcher(self) -> Path:
        return self.home / ".local" / "bin" / PRODUCT_FOLDER


def machine_paths(environ: Mapping[str, str] | None = None) -> MachinePaths:
    environ = os.environ if environ is None else environ
    user_home = Path(environ["HOME"]) if environ.get("HOME") else Path.home()
    override = environ.get(HOME_VARIABLE)
    return MachinePaths(expand(override, user_home) if override else user_home)


def expand(path: str, home: Path) -> Path:
    """Expands a leading ``~`` to the given machine home; anything else stays as written."""
    if path == "~":
        return home
    if path.startswith("~/"):
        return home / path[2:]
    return Path(path)
