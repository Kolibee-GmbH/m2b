"""What Claude Code hands a hook on stdin, read the same way by every hook.

Standard library only and nothing else of m2b, so a hook that runs before every prompt can
import it without loading the rest of the core.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

PROJECT_DIR_VARIABLE = "CLAUDE_PROJECT_DIR"


@dataclass(frozen=True)
class HookInput:
    """Every field may be missing; one that is not a string counts as missing."""

    session_id: str | None = None
    source: str | None = None
    cwd: str | None = None
    prompt: str | None = None


def read_hook_input(stream: TextIO | None) -> HookInput:
    """The hook input, or an empty one when there is none or it is no JSON object.

    A terminal is never read: a hook run by hand would otherwise wait for input.
    """
    if stream is None or stream.isatty():
        return HookInput()
    try:
        raw = json.loads(stream.read())
    except (OSError, ValueError):
        return HookInput()
    if not isinstance(raw, dict):
        return HookInput()
    fields = {name: raw.get(name) for name in ("session_id", "source", "cwd", "prompt")}
    return HookInput(**{name: value if isinstance(value, str) else None for name, value in fields.items()})


def project_folder(environ: Mapping[str, str], hook_input: HookInput | None = None) -> Path:
    """The folder a session counts as its project: the one Claude Code names, else the hook input's
    working directory, else this process's."""
    return Path(environ.get(PROJECT_DIR_VARIABLE) or (hook_input.cwd if hook_input else None) or os.getcwd())
