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
- Transcript files under ``~/.claude/projects/``, one JSON Lines file per session: ``sessions``
  reads what the person typed, and relies on the mark Claude Code puts on every prompt of who sent
  it (``origin``, ``promptSource``); the worklog add-on reads prompts, answers and times for the
  facts of a period (``m2b_worklog/sources/transcripts.py``) and leaves out a prompt the mark gives
  to another sender. Both read the mark through ``sender_of`` and take out the blocks Claude Code
  writes into a prompt beside what was typed (``PROMPT_BLOCK``, the one list of their tags).
  ``sessions`` reports a transcript that cannot be opened or no longer names its folder as not
  read, the worklog one that cannot be opened. When the mark goes, ``sessions`` counts every
  prompt but a slash command as unmarked and gives none of them, and the worklog takes every
  prompt as the owner's again; a record that changed in another way is not recognised and reads
  as no prompt.
- The mod API (``hooks/register.tsx``): the band, early-access API; when it changes, the band
  shows nothing and everything else works.

``CLAUDE_CONFIG_DIR`` moves the folder, as it does for Claude Code; ``M2B_INSTALLED_PLUGINS``
points at another ``installed_plugins.json`` (tests).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

MARKETPLACE = "m2b"
CORE_PLUGIN = "m2b"
INSTALLED_PLUGINS_VARIABLE = "M2B_INSTALLED_PLUGINS"

# The blocks Claude Code puts into a prompt beside what the person typed: its own reminders, the
# output of hooks and local commands, notices of finished tasks.
PROMPT_BLOCK_TAGS = (
    "system-reminder",
    "local-command-caveat",
    "local-command-stdout",
    "local-command-stderr",
    "command-message",
    "user-prompt-submit-hook",
    "task-notification",
)
PROMPT_BLOCK = re.compile(r"<(" + "|".join(PROMPT_BLOCK_TAGS) + r")\b[^>]*>.*?</\1>", re.S)

# The sender Claude Code names for what the person sent: typed in the terminal or in the desktop
# app, also while Claude was busy, or a suggested prompt they accepted.
HUMAN = "human"


def sender_of(record: Mapping[str, Any]) -> str | None:
    """Who sent the prompt of a transcript record, by Claude Code's mark; None for a record without it.

    Other senders are a plugin, a finished task and another session. A kind that is no text is
    some other sender too, never the person and never a missing mark.
    """
    origin = record.get("origin")
    if not isinstance(origin, dict):
        return None
    kind = origin.get("kind")
    return kind if kind is None or isinstance(kind, str) else repr(kind)


def installed_plugins_file(environ: Mapping[str, str]) -> Path:
    override = environ.get(INSTALLED_PLUGINS_VARIABLE)
    if override:
        return Path(override)
    return _claude_folder(environ) / "plugins" / "installed_plugins.json"


def transcripts_folder(environ: Mapping[str, str]) -> Path:
    """Where Claude Code keeps a folder of transcripts per project folder."""
    return _claude_folder(environ) / "projects"


def _claude_folder(environ: Mapping[str, str]) -> Path:
    return Path(environ.get("CLAUDE_CONFIG_DIR") or Path(environ.get("HOME") or Path.home()) / ".claude")


def resolve_install_path(plugin: str, environ: Mapping[str, str]) -> Path | None:
    """The user-scope install path of ``plugin`` from this product's marketplace, None when not installed."""
    try:
        with installed_plugins_file(environ).open(encoding="utf-8") as handle:
            entries = json.load(handle)["plugins"].get(f"{plugin}@{MARKETPLACE}", [])
        user_entry = next(entry for entry in entries if entry.get("scope") == "user")
        return Path(user_entry["installPath"])
    except (OSError, ValueError, KeyError, StopIteration, TypeError, AttributeError):
        return None
