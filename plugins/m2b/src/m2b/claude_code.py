"""What m2b reads of Claude Code's own files, in one place, so a change in Claude Code
breaks one module and ``m2b doctor`` can name it.

Claude Code documents plugins, hooks, skills and settings; these are the parts m2b relies on
beyond that, each with what breaks when it changes:

- ``~/.claude/plugins/installed_plugins.json``: the launcher finds the core's install path there
  (user scope, key ``m2b@m2b``). Read here, in ``launcher.RESOLVER`` (a copy that runs before any
  m2b code is found) and in the worklog recorder's ``m2b_installed`` (``recorder/record.py``, which
  runs from its own copy). When it changes, ``m2b doctor`` says the launcher cannot find m2b,
  callers outside Claude Code (Shortcuts, integrations) stop, and the recorder records nothing (B38).
- ``enabledPlugins`` in Claude Code's managed settings (``MANAGED_SETTINGS`` in the recorder,
  ``M2B_MANAGED_SETTINGS`` in tests) and in the user's: only the worklog recorder reads them, to
  stop recording when m2b is turned off.
- Transcript files under ``~/.claude/projects/``: only the worklog part reads them, for the facts
  of a period (``m2b_worklog/sources/transcripts.py``); a source it cannot read is reported as such.
- The mod API (``hooks/register.tsx``): the band, early-access API; when it changes, the band
  shows nothing and everything else works.

``CLAUDE_CONFIG_DIR`` moves the folder, as it does for Claude Code; ``M2B_INSTALLED_PLUGINS``
points at another ``installed_plugins.json`` (tests).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

MARKETPLACE = "m2b"
CORE_PLUGIN = "m2b"
INSTALLED_PLUGINS_VARIABLE = "M2B_INSTALLED_PLUGINS"


def installed_plugins_file(environ: Mapping[str, str]) -> Path:
    override = environ.get(INSTALLED_PLUGINS_VARIABLE)
    if override:
        return Path(override)
    claude_dir = environ.get("CLAUDE_CONFIG_DIR") or str(Path(environ.get("HOME") or Path.home()) / ".claude")
    return Path(claude_dir) / "plugins" / "installed_plugins.json"


def resolve_install_path(plugin: str, environ: Mapping[str, str]) -> Path | None:
    """The user-scope install path of ``plugin`` from this product's marketplace, None when not installed."""
    try:
        with installed_plugins_file(environ).open(encoding="utf-8") as handle:
            entries = json.load(handle)["plugins"].get(f"{plugin}@{MARKETPLACE}", [])
        user_entry = next(entry for entry in entries if entry.get("scope") == "user")
        return Path(user_entry["installPath"])
    except (OSError, ValueError, KeyError, StopIteration, TypeError, AttributeError):
        return None
