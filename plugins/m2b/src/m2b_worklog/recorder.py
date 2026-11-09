"""Installing, refreshing and removing the recorder: a copy of ``recorder/`` that herdr links.

herdr keeps the absolute path of a linked plugin's manifest, so it links the copy in
``~/.local/share/m2b/worklog-recorder/``, never this plugin's versioned folder. Install and remove
each run twice without harm: herdr is asked whether the recorder is linked before linking or
unlinking it, so a second run makes no call that changes herdr.
"""

from __future__ import annotations

import filecmp
import json
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Callable

from m2b_worklog.files import replace_file
from m2b_worklog.paths import RECORDER_ID, RECORDER_SOURCE, WorklogPaths
from m2b_worklog.sources import SourceState

HERDR_TIMEOUT_SECONDS = 10.0
RECORDER_FILES = ("herdr-plugin.toml", "record.py")

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class HerdrError(Exception):
    """herdr could not be run or refused the request."""


def herdr_command(environ: Mapping[str, str]) -> str:
    return environ.get("M2B_HERDR") or "herdr"


def copy_recorder(paths: WorklogPaths, source: Path = RECORDER_SOURCE) -> bool:
    """Writes the recorder's files into the copy; True when any file changed."""
    target = paths.recorder_copy
    target.mkdir(parents=True, exist_ok=True)
    changed = False
    for name in RECORDER_FILES:
        if (target / name).is_file() and filecmp.cmp(source / name, target / name, shallow=False):
            continue
        replace_file(target / name, (source / name).read_bytes())
        changed = True
    return changed


def is_linked(command: str, run: Runner = subprocess.run) -> bool:
    """herdr answers an unknown id with an empty list and exit 0 (herdr 0.9.3)."""
    result = _herdr(command, ["plugin", "list", "--plugin", RECORDER_ID, "--json"], run)
    try:
        plugins = json.loads(result.stdout)["result"]["plugins"]
    except (ValueError, KeyError, TypeError) as error:
        raise HerdrError("herdr plugin list answered something that is not a plugin list") from error
    return isinstance(plugins, list) and any(
        isinstance(plugin, dict) and plugin.get("plugin_id") == RECORDER_ID for plugin in plugins
    )


def herdr_state(environ: Mapping[str, str], run: Runner = subprocess.run) -> SourceState:
    """Whether herdr answers with the recorder linked: without either, the period's activity is missing."""
    try:
        linked = is_linked(herdr_command(environ), run)
    except HerdrError as error:
        return SourceState.failed(f"herdr did not answer ({error}); activity while herdr was not running is missing")
    if not linked:
        return SourceState.failed("the recorder is not linked in herdr; m2b-worklog recorder install links it")
    return SourceState.read()


def install(paths: WorklogPaths, environ: Mapping[str, str], run: Runner = subprocess.run) -> str:
    copy_recorder(paths)
    command = herdr_command(environ)
    if is_linked(command, run):
        return f"recorder up to date in {paths.recorder_copy}, already linked in herdr"
    _herdr(command, ["plugin", "link", str(paths.recorder_copy)], run)
    return f"recorder copied to {paths.recorder_copy} and linked in herdr"


def remove(paths: WorklogPaths, environ: Mapping[str, str], run: Runner = subprocess.run) -> str:
    """Unlinks the recorder and deletes its copy; what it recorded stays."""
    command = herdr_command(environ)
    was_linked = is_linked(command, run)
    if was_linked:
        _herdr(command, ["plugin", "unlink", RECORDER_ID], run)
    shutil.rmtree(paths.recorder_copy, ignore_errors=True)
    return "recorder unlinked from herdr and its copy deleted" if was_linked else "recorder was not linked in herdr"


def is_installed(paths: WorklogPaths) -> bool:
    """Whether setup copied the recorder here; only then may recording be on."""
    return (paths.recorder_copy / RECORDER_FILES[0]).is_file()


def refresh(paths: WorklogPaths, source: Path = RECORDER_SOURCE) -> bool:
    """Brings an installed copy to this plugin version's files; a copy nobody installed stays absent."""
    if not is_installed(paths):
        return False
    return copy_recorder(paths, source)


def _herdr(command: str, arguments: Sequence[str], run: Runner, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        result = run(
            [command, *arguments],
            capture_output=True,
            text=True,
            timeout=HERDR_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError as error:
        raise HerdrError(f"{command} was not found") from error
    except subprocess.TimeoutExpired as error:
        raise HerdrError(f"herdr did not answer within {HERDR_TIMEOUT_SECONDS:g} seconds") from error
    except OSError as error:
        raise HerdrError(f"herdr could not be run: {error}") from error
    if check and result.returncode != 0:
        reason = result.stderr.strip().splitlines()[:1]
        detail = f": {reason[0]}" if reason else ""
        raise HerdrError(f"herdr {' '.join(arguments[:2])} ended with exit {result.returncode}{detail}")
    return result
