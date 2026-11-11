"""Installing, refreshing and removing the recorder: a copy of ``recorder/`` that herdr links, and its timer.

herdr keeps the absolute path of a linked plugin's manifest, so it links the copy in
``~/.local/share/m2b/worklog-recorder/``, never this plugin's versioned folder. herdr also takes the
manifest's events and startup commands when it links the plugin, so a copy with a new version is
linked again. Install and remove each run twice without harm: herdr is asked what it has linked
before linking or unlinking, so a second run makes no call that changes herdr. The timer that runs
the recorder's tick (``timer``) is set up and taken out with it. ``check`` is what setup asks before
anything else: whether herdr is there, at least ``MIN_HERDR_VERSION`` and running.
"""

from __future__ import annotations

import contextlib
import filecmp
import json
import re
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Callable, TypedDict

from m2b_worklog import timer
from m2b_worklog.files import replace_file
from m2b_worklog.paths import RECORDER_ID, RECORDER_SOURCE, WorklogPaths
from m2b_worklog.sources import SourceState

HERDR_TIMEOUT_SECONDS = 10.0
RECORDER_FILES = ("herdr-plugin.toml", "record.py")
# Beside the copy: the manifest version herdr was last linked with.
LINKED_VERSION_FILE = "linked-version"
ALIVE_FOLDER = "alive"
FIRST_TICK_FILE = "first-tick"
# The recorder's manifest asks for the same version; 0.9 brought the events and the status it reads.
MIN_HERDR_VERSION = "0.9.0"
HERDR_HOME_PAGE = "https://herdr.dev"
_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")
_MANIFEST_VERSION = re.compile(r'^version = "([^"]+)"', re.MULTILINE)

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class HerdrCheck(TypedDict):
    herdr: str | None
    running: bool
    ready: bool
    problem: str | None


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


def linked_recorder(environ: Mapping[str, str], run: Runner = subprocess.run) -> dict[str, object] | None:
    """What herdr lists for the recorder, or None; herdr answers an unknown id with an empty list (0.9.3)."""
    result = _herdr(environ, ["plugin", "list", "--plugin", RECORDER_ID, "--json"], run)
    try:
        plugins = json.loads(result.stdout)["result"]["plugins"]
    except (ValueError, KeyError, TypeError) as error:
        raise HerdrError("herdr plugin list answered something that is not a plugin list") from error
    listed = (
        [p for p in plugins if isinstance(p, dict) and p.get("plugin_id") == RECORDER_ID]
        if isinstance(plugins, list)
        else []
    )
    return listed[0] if listed else None


def is_linked(environ: Mapping[str, str], run: Runner = subprocess.run) -> bool:
    return linked_recorder(environ, run) is not None


def herdr_state(environ: Mapping[str, str], run: Runner = subprocess.run) -> SourceState:
    """Whether herdr answers with the recorder linked and on: without that, the period's activity is missing."""
    try:
        linked = linked_recorder(environ, run)
    except HerdrError as error:
        return SourceState.failed(f"herdr did not answer ({error}); activity while herdr was not running is missing")
    if linked is None:
        return SourceState.failed("the recorder is not linked in herdr; m2b-worklog recorder install links it")
    if linked.get("enabled") is False:
        return SourceState.failed(f"the recorder is turned off in herdr; herdr plugin enable {RECORDER_ID} turns it on")
    return SourceState.read()


def check(environ: Mapping[str, str], run: Runner = subprocess.run) -> HerdrCheck:
    """Whether herdr is installed, new enough and running, with the one thing to do when it is not."""
    try:
        found = _VERSION.search(_herdr(environ, ["--version"], run).stdout)
    except HerdrError as error:
        missing = f"herdr was not found; the worklog needs herdr {MIN_HERDR_VERSION} or later, from {HERDR_HOME_PAGE}"
        return _not_ready(missing if "was not found" in str(error) else f"herdr did not answer: {error}")
    if found is None:
        return _not_ready(
            "herdr --version printed no version; is the herdr on the PATH the terminal workspace manager?"
        )
    version = found.group(0)
    running = _server_running(environ, run)
    problem: str | None = None
    if _numbers(version) < _numbers(MIN_HERDR_VERSION):
        problem = f"herdr {version} is older than {MIN_HERDR_VERSION}; herdr update installs the latest version"
    elif not running:
        problem = "herdr is installed but not running; start herdr, then run the worklog setup again"
    return {"herdr": version, "running": running, "ready": problem is None, "problem": problem}


def _not_ready(problem: str) -> HerdrCheck:
    return {"herdr": None, "running": False, "ready": False, "problem": problem}


def _server_running(environ: Mapping[str, str], run: Runner) -> bool:
    try:
        status = json.loads(_herdr(environ, ["status", "server", "--json"], run).stdout)
    except (HerdrError, ValueError):
        return False
    return isinstance(status, dict) and status.get("running") is True


def _numbers(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def install(paths: WorklogPaths, environ: Mapping[str, str], run: Runner = subprocess.run) -> str:
    """Copies and links the recorder, then sets up its timer; a timer that fails is said, not fatal."""
    copy_recorder(paths)
    linked = _link(paths, environ, run)
    try:
        started = timer.install(timer.place_for(paths, environ), run, verify=True)
    except (timer.TimerError, OSError) as error:
        started = f"the timer could not be set up ({error}); the worklog names no stretch as not recorded"
    return f"{linked}; {started}"


def remove(paths: WorklogPaths, environ: Mapping[str, str], run: Runner = subprocess.run) -> str:
    """Takes out the timer and the copy, then unlinks the recorder; what it recorded stays.

    The timer goes first, so a herdr that is gone already does not leave it running. The first
    tick is forgotten, so a later setup whose timer fails claims no silence.
    """
    try:
        stopped = timer.remove(timer.place_for(paths, environ), run)
    except (timer.TimerError, OSError) as error:
        stopped = f"the timer could not be taken out ({error})"
    shutil.rmtree(paths.recorder_copy, ignore_errors=True)
    with contextlib.suppress(OSError):
        (paths.state_dir / ALIVE_FOLDER / FIRST_TICK_FILE).unlink()
    was_linked = is_linked(environ, run)
    if was_linked:
        _herdr(environ, ["plugin", "unlink", RECORDER_ID], run)
    unlinked = "recorder unlinked from herdr and its copy deleted" if was_linked else "recorder was not linked in herdr"
    return f"{unlinked}; {stopped}"


def _link(paths: WorklogPaths, environ: Mapping[str, str], run: Runner) -> str:
    """Links the copy, again when herdr holds another version, since herdr reads events and startup at link.

    The version linked is noted beside the copy, so a refresh knows without asking herdr.
    """
    version = manifest_version(paths.recorder_copy)
    linked = linked_recorder(environ, run)
    if linked is not None and linked.get("version") == version:
        message = f"recorder up to date in {paths.recorder_copy}, already linked in herdr"
    else:
        _herdr(environ, ["plugin", "link", str(paths.recorder_copy)], run)
        message = (
            f"recorder in {paths.recorder_copy} linked again in herdr, now version {version}"
            if linked is not None
            else f"recorder copied to {paths.recorder_copy} and linked in herdr"
        )
    replace_file(paths.recorder_copy / LINKED_VERSION_FILE, f"{version}\n".encode())
    return message


def manifest_version(folder: Path) -> str | None:
    found = _MANIFEST_VERSION.search((folder / RECORDER_FILES[0]).read_text(encoding="utf-8"))
    return found.group(1) if found else None


def is_installed(paths: WorklogPaths) -> bool:
    """Whether setup copied the recorder here; only then may recording be on."""
    return (paths.recorder_copy / RECORDER_FILES[0]).is_file()


def refresh(
    paths: WorklogPaths,
    environ: Mapping[str, str],
    recording: bool = True,
    run: Runner = subprocess.run,
    source: Path = RECORDER_SOURCE,
) -> bool:
    """Brings an installed copy to this plugin version's files, links it again while herdr may hold
    another version, and puts the timer in place while this machine records; a copy nobody installed
    stays absent. herdr is asked only until a link of the copy's version succeeded."""
    if not is_installed(paths):
        return False
    changed = copy_recorder(paths, source)
    failure: Exception | None = None
    if _linked_version(paths) != manifest_version(paths.recorder_copy):
        try:
            _link(paths, environ, run)
        except HerdrError as error:
            failure = error
    if recording:
        timer.install(timer.place_for(paths, environ), run)
    if failure is not None:
        raise failure
    return changed


def _linked_version(paths: WorklogPaths) -> str | None:
    try:
        return (paths.recorder_copy / LINKED_VERSION_FILE).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _herdr(
    environ: Mapping[str, str], arguments: Sequence[str], run: Runner, check: bool = True
) -> subprocess.CompletedProcess[str]:
    command = herdr_command(environ)
    try:
        result = run(
            [command, *arguments],
            capture_output=True,
            text=True,
            timeout=HERDR_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
            env=dict(environ),
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
