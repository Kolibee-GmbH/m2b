"""The worklog's session-start hook: the recording switch and the installed recorder copy.

Only the curating machine records, only while the worklog add-on is on, and only after
``/m2b:worklog-setup`` installed the recorder. The hook asks the core through its launcher
(``m2b status --json``, fields ``this_machine_curates`` and ``addons``) and writes the switch ``on``
while all three hold, else ``off``, so a take-over or ``m2b addons off worklog`` turns recording off
at the next session, and installing m2b alone never turns recording on. When the
core cannot answer, the switch stays as it was and one line says so (B7). An installed recorder
copy is brought to this plugin version's files, so an update needs no step.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass

from m2b_worklog import recorder
from m2b_worklog.files import replace_file
from m2b_worklog.paths import SWITCH_OFF, SWITCH_ON, WorklogPaths

STATUS_TIMEOUT_SECONDS = 20.0
EXIT_USAGE = 2
# How the core begins its answer when setup has not run (m2b.config.errors.NotSetUpError).
NOT_SET_UP = "m2b: not set up:"


ADDONS_TIMEOUT_SECONDS = 10.0


class StatusError(Exception):
    """The core did not say whether this machine curates."""


def worklog_addon_on(paths: WorklogPaths, run: recorder.Runner = subprocess.run) -> bool | None:
    """Whether the worklog add-on is on; False before setup, None when the core gave no usable answer.

    It only reads the machine config, so it is asked first: a user who never turned the worklog on
    gets no status probe and no line at session start, whatever state the store is in.
    """
    try:
        result = run(
            [str(paths.launcher), "addons", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=ADDONS_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return False
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode == EXIT_USAGE and NOT_SET_UP in result.stderr:
        return False
    try:
        rows = json.loads(result.stdout) if result.returncode == 0 else None
    except ValueError:
        rows = None
    if not isinstance(rows, list):
        return None
    return any(isinstance(row, dict) and row.get("name") == "worklog" and row.get("on") is True for row in rows)


def this_machine_curates(paths: WorklogPaths, run: recorder.Runner = subprocess.run) -> bool | None:
    """True or False from the core; None when m2b is not set up here (nothing to record for)."""
    answer = core_status(paths, run)
    return None if answer is None else answer.curates


@dataclass(frozen=True)
class CoreStatus:
    curates: bool
    worklog_on: bool


def core_status(paths: WorklogPaths, run: recorder.Runner = subprocess.run) -> CoreStatus | None:
    """Which machine curates and whether the worklog add-on is on; None when m2b is not set up here."""
    try:
        result = run(
            [str(paths.launcher), "status", "--json"],
            capture_output=True,
            text=True,
            timeout=STATUS_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        # Setup writes the launcher, so without one m2b is not set up here.
        return None
    except subprocess.TimeoutExpired as error:
        raise StatusError(f"m2b status did not answer within {STATUS_TIMEOUT_SECONDS:g} seconds") from error
    except OSError as error:
        raise StatusError(f"m2b status could not be run: {error}") from error
    if result.returncode == EXIT_USAGE and NOT_SET_UP in result.stderr:
        return None
    try:
        answer = json.loads(result.stdout) if result.returncode == 0 else None
    except ValueError:
        answer = None
    if isinstance(answer, dict) and isinstance(answer.get("store_error"), str):
        # A store that cannot be read now says nothing about which machine curates.
        raise StatusError(f"store.json could not be read: {answer['store_error']}")
    curates = answer.get("this_machine_curates") if isinstance(answer, dict) else None
    if not isinstance(curates, bool):
        raise StatusError(f"m2b status answered without saying which machine curates (exit {result.returncode})")
    addons = answer.get("addons") if isinstance(answer, dict) else None
    return CoreStatus(curates, isinstance(addons, dict) and addons.get("worklog") is True)


def set_switch(paths: WorklogPaths, on: bool) -> bool:
    """Writes the switch when it changes; True when it did."""
    wanted = SWITCH_ON if on else SWITCH_OFF
    with contextlib.suppress(OSError, UnicodeDecodeError):
        if paths.switch.read_text(encoding="utf-8").strip() == wanted:
            return False
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    replace_file(paths.switch, f"{wanted}\n".encode())
    return True


def session_start(paths: WorklogPaths, environ: Mapping[str, str], run: recorder.Runner = subprocess.run) -> str:
    """What the hook prints: nothing unless something needs the owner."""
    if environ.get("M2B_CURATION_RUN") == "1":
        return ""
    addon_on = worklog_addon_on(paths, run)
    if addon_on is None:
        # The core's own session-start hooks report a config they cannot read; nothing changes here.
        return ""
    if not addon_on:
        with contextlib.suppress(OSError):
            if paths.switch.exists():
                set_switch(paths, False)
        return ""
    lines = []
    try:
        status = core_status(paths, run)
    except StatusError as error:
        lines.append(f"m2b worklog: could not check which machine curates ({error}); recording left as it was.")
    else:
        recording = status is not None and status.curates and status.worklog_on and recorder.is_installed(paths)
        try:
            set_switch(paths, recording)
        except OSError as error:
            lines.append(f"m2b worklog: the recording switch could not be written ({error}).")
    try:
        recorder.refresh(paths)
    except OSError as error:
        lines.append(f"m2b worklog: the installed recorder could not be updated ({error}).")
    return "".join(f"{line}\n" for line in lines)
