"""Starting a curation run in the background: the session-start nudge and ``m2b curate --detach``.

The start returns at once (B11), so it can only say what it checked before: this machine curates,
no run holds the lock, and a run is due unless forced. It reads ``store.json`` only when it is on
this machine; downloading it is the run's preflight, which a session start must not wait for. The
background run is started with ``--force``, because the due check was just made here, in a new
session with nothing open to the session that started it, from the machine state folder.
"""

from __future__ import annotations

import datetime
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass

from m2b import launcher
from m2b.config.machine import load_machine_config
from m2b.config.store_settings import STORE_SETTINGS_FILE_NAME, load_store_settings
from m2b.curate import machine_state
from m2b.curate.due import check_due
from m2b.paths import MachinePaths
from m2b.store.base import EvictedFileError, fetch_command
from m2b.store.factory import open_store

STARTED = "started"
NOT_CURATING = "not-curating"
RUNNING = "running"
NOT_DUE = "not-due"
NOT_DOWNLOADED = "not-downloaded"


@dataclass(frozen=True)
class Start:
    kind: str
    message: str


def start_detached(
    machine: MachinePaths,
    environ: Mapping[str, str],
    force: bool,
    now: datetime.datetime,
    refresh_all: bool = False,
    sort_facts: bool = False,
) -> Start:
    config = load_machine_config(machine)
    store = open_store(config.store, machine.temp_dir)
    try:
        settings = load_store_settings(store)
    except EvictedFileError:
        return Start(
            NOT_DOWNLOADED,
            f"{STORE_SETTINGS_FILE_NAME} is not downloaded; run: {fetch_command(STORE_SETTINGS_FILE_NAME)}",
        )
    if settings.curating_machine != config.machine_id:
        return Start(NOT_CURATING, f"this machine is not the curating machine; {settings.curating_machine} is")
    if machine_state.lock_is_held(machine):
        return Start(RUNNING, "a curation run is already running on this machine")
    if not force and not refresh_all and not sort_facts:
        due = check_due(store, machine, now)
        if not due.due:
            return Start(NOT_DUE, f"no curation run is due: {due.reason}")
    machine.state_dir.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        launcher.core_command(
            [
                "curate",
                "--force",
                *(["--refresh-all"] if refresh_all else []),
                *(["--sort-facts"] if sort_facts else []),
            ]
        ),
        cwd=machine.state_dir,
        env=dict(environ),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return Start(
        STARTED, f"a curation run started in the background (process {process.pid}); m2b status shows how it goes"
    )
