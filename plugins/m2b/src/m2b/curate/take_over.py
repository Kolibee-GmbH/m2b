"""``m2b curate take-over``: this machine becomes the one that curates the store.

One curating machine per store, because the run's lock is local and iCloud gives no reliable shared
lock; moving curation is this explicit step.

It writes this machine's id into ``store.json``; the old machine stops at its next preflight,
because it is no longer named. The parts that were on in the old machine's last run come from the
run record, so the owner can set those parts up here. While the run record says a run is in progress on another
machine and that run is not past its deadline, the take-over is refused: that run passed its
preflight already and would curate alongside the first run here.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from m2b.config import store_path
from m2b.config.errors import InvalidConfigError
from m2b.config.json_file import read_store_json_object
from m2b.config.machine import load_machine_config
from m2b.config.store_settings import STORE_SETTINGS_FILE_NAME, load_store_settings, save_store_settings
from m2b.paths import MachinePaths
from m2b.run_record import RUN_RECORD, RUNNING, RunRecordError, is_interrupted, load_run_record
from m2b.store.base import DEFAULT_FETCH_TIMEOUT_SECONDS
from m2b.store.factory import open_store


class RunInProgressError(Exception):
    """Another machine is curating right now."""


@dataclass(frozen=True)
class TakeOver:
    machine_id: str
    previous: str | None
    parts: tuple[str, ...]
    # Why the parts of the last run are not known, when the run record could not be read.
    record_problem: str | None = None


def take_over(
    machine: MachinePaths, now: datetime.datetime, fetch_timeout_seconds: float = DEFAULT_FETCH_TIMEOUT_SECONDS
) -> TakeOver:
    """``previous`` is None when this machine curated already; then nothing is written."""
    config = load_machine_config(machine)
    unusable = store_path.problem(config.store.path)
    if unusable is not None:
        raise InvalidConfigError(unusable)
    store = open_store(config.store, machine.temp_dir)
    store.fetch([STORE_SETTINGS_FILE_NAME, RUN_RECORD], fetch_timeout_seconds)
    settings = load_store_settings(store, for_writing=True)
    problem = None
    try:
        record = load_run_record(store)
    except RunRecordError as error:
        # The next run's preflight rewrites it; an unreadable record must not keep curation where it is.
        record, problem = None, str(error)
    parts = record.parts if record else ()
    if settings.curating_machine == config.machine_id:
        return TakeOver(config.machine_id, None, parts, problem)
    if (
        record
        and record.state == RUNNING
        and record.machine_id != config.machine_id
        and not is_interrupted(record, now)
    ):
        since = f"{record.started_at.astimezone():%Y-%m-%d %H:%M}"
        raise RunInProgressError(
            f"a curation run on {record.machine_id} is in progress since {since}; take over when it has finished"
        )
    raw = read_store_json_object(store, STORE_SETTINGS_FILE_NAME) or {}
    save_store_settings(store, {**raw, "curating_machine": config.machine_id})
    return TakeOver(config.machine_id, settings.curating_machine, parts, problem)
