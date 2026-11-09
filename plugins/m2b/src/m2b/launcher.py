"""The launcher ``~/.local/bin/m2b`` and plugin install paths.

Callers outside Claude Code (Shortcuts, other plugins' hooks, integrations) cannot rely on a path
into the plugin cache: it dies some days after an update. The launcher is a small shell script
that reads the core's current user-scope ``installPath`` from Claude Code's
``installed_plugins.json`` at every call, so an update needs no step. ``M2B_CORE_ROOT``
points it at a checkout instead, and ``M2B_INSTALLED_PLUGINS`` at another
``installed_plugins.json`` (tests). The resolver runs inside the launcher, before any core code
can be found, so it exists twice: in ``RESOLVER`` for the launcher and in ``resolve_install_path``.
"""

from __future__ import annotations

import json
import shlex
import sys
from collections.abc import Sequence
from pathlib import Path

from m2b.atomic_file import write_text_atomically

# Re-exported: the launcher's callers and tests name them here.
from m2b.claude_code import CORE_PLUGIN as CORE_PLUGIN
from m2b.claude_code import INSTALLED_PLUGINS_VARIABLE as INSTALLED_PLUGINS_VARIABLE
from m2b.claude_code import MARKETPLACE as MARKETPLACE
from m2b.claude_code import installed_plugins_file as installed_plugins_file
from m2b.claude_code import resolve_install_path as resolve_install_path
from m2b.paths import MachinePaths

CORE_ROOT_VARIABLE = "M2B_CORE_ROOT"
VERSION_LINE_PREFIX = "# m2b-launcher-version: "
PLUGIN_ROOT = Path(__file__).resolve().parents[2]

# Runs with python3 -I in the launcher; it must not contain a single quote.
RESOLVER = f"""
import json, os, sys
key = "{CORE_PLUGIN}@{MARKETPLACE}"
path = os.environ.get("{INSTALLED_PLUGINS_VARIABLE}") or os.path.join(
    os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude"),
    "plugins", "installed_plugins.json")
try:
    with open(path, encoding="utf-8") as handle:
        entries = json.load(handle)["plugins"].get(key, [])
    print([entry for entry in entries if entry.get("scope") == "user"][0]["installPath"])
except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError):
    print("m2b: the core plugin " + key + " is not installed for this user (" + path + ")", file=sys.stderr)
    sys.exit(3)
"""


class LauncherError(Exception):
    """The launcher cannot be written."""


def core_command(arguments: Sequence[str]) -> list[str]:
    """``m2b <arguments>`` from this core with this interpreter, isolated as ``bin/m2b`` runs it."""
    bootstrap = "import sys; sys.path.insert(0, sys.argv.pop(1)); from m2b.cli import main; sys.exit(main())"
    return [sys.executable, "-I", "-c", bootstrap, str(PLUGIN_ROOT / "src"), *arguments]


def core_version() -> str:
    manifest = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    return str(manifest["version"])


def launcher_script(python: str, version: str) -> str:
    if "'" in RESOLVER:
        raise LauncherError("the resolver must not contain a single quote")
    quoted_python = shlex.quote(python)
    return f"""#!/bin/sh
# Written by `m2b launcher install`; the session-start hook rewrites it when outdated.
{VERSION_LINE_PREFIX}{version}
set -eu
if [ -n "${{{CORE_ROOT_VARIABLE}:-}}" ]; then
    core_root=${{{CORE_ROOT_VARIABLE}}}
else
    core_root=$({quoted_python} -I -c '{RESOLVER}')
fi
M2B_PYTHON=${{M2B_PYTHON:-{quoted_python}}}
export M2B_PYTHON
exec "$core_root/bin/m2b" "$@"
"""


def install_launcher(machine: MachinePaths, python: str) -> Path:
    machine.launcher.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomically(machine.launcher, launcher_script(python, core_version()), machine.temp_dir)
    machine.launcher.chmod(0o755)
    return machine.launcher


def installed_launcher_version(machine: MachinePaths) -> str | None:
    """The version line of the installed launcher, None without a launcher or a version line."""
    try:
        return launcher_version_in(machine.launcher.read_bytes())
    except OSError:
        return None


def launcher_version_in(data: bytes) -> str | None:
    """The version a launcher's bytes name; None for any other file, a binary included."""
    lines = data.decode("utf-8", errors="replace").split("\n")
    return next((line[len(VERSION_LINE_PREFIX) :] for line in lines if line.startswith(VERSION_LINE_PREFIX)), None)
