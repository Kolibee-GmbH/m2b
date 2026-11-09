"""What Claude Code hands a hook on stdin, read the same way by every hook.

Standard library only and nothing else of m2b, so a hook that runs before every prompt can
import it without loading the rest of the core.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TextIO


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
