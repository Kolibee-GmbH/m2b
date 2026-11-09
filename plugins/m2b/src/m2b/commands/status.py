"""``status``: the state of curation in one answer, on any machine, so the band can show a
hanging or failed run at once.

Inbox count, the run record, whether a run is due (only on the curating machine, the only one
where that question has an answer), and whether the backends can be reached. The backend probes
start other programs, so their answer is kept for 5 minutes in the machine state; the rest is read
fresh. Each part that cannot be looked at says why instead of disappearing.

A ``running`` record counts as running until its deadline; on this machine, also only while a run
holds the lock, since a runner killed with nothing left holding the lock cannot finish its run.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import json
from typing import Any

from m2b.addons import ADDONS, is_on
from m2b.atomic_file import replace_atomically
from m2b.commands import Context
from m2b.commands.backends import configured_store, configured_tasks
from m2b.commands.doctor import calendar_check, probe
from m2b.commands.output import print_json
from m2b.config import store_settings
from m2b.config.errors import ConfigError
from m2b.config.machine import MachineConfig, load_machine_config
from m2b.config.store_settings import describe_format, format_state, load_store_settings
from m2b.curate import machine_state
from m2b.curate.due import check_due
from m2b.notes.layout import INBOX
from m2b.paths import MachinePaths
from m2b.run_record import RUNNING, RunRecordError, is_interrupted, load_run_record
from m2b.store.base import Store, StoreError

CACHE_FILE = "status-cache.json"
PROBE_MAX_AGE = datetime.timedelta(minutes=5)
INTERRUPTED = "interrupted"


def status_command(arguments: argparse.Namespace, context: Context) -> int:
    config = load_machine_config(context.machine)
    store = configured_store(config, context.machine)
    now = datetime.datetime.now().astimezone()
    answer: dict[str, Any] = {"machine_id": config.machine_id}
    answer["addons"] = {addon.name: is_on(config.addons, addon.name) for addon in ADDONS}
    try:
        settings = load_store_settings(store)
        curating: str | None = settings.curating_machine
        answer["store_format"] = {
            "store": settings.format,
            "known": store_settings.KNOWN_STORE_FORMAT,
            "state": format_state(settings),
            "detail": describe_format(settings),
        }
    except (ConfigError, StoreError) as error:
        curating = None
        answer["store_error"] = str(error)
    answer["curating_machine"] = curating
    answer["this_machine_curates"] = curating == config.machine_id
    answer["inbox"] = _inbox(store)
    answer["run"] = _run(store, context.machine, config.machine_id, now)
    answer["last_attempt"] = _last_attempt(context.machine, answer["run"])
    if curating == config.machine_id:
        due = check_due(store, context.machine, now)
        answer["due"] = {"due": due.due, "reason": due.reason}
    else:
        answer["due"] = None
    checked_at, backends = _backends(config, context, now)
    answer["backends"] = backends
    answer["backends_checked_at"] = checked_at
    if arguments.json:
        print_json(answer)
    else:
        _print_text(answer)
    return 0


def probe_backends(config: MachineConfig, context: Context) -> dict[str, dict[str, str]]:
    checks = [
        probe("store", lambda: _check_store(config, context.machine)),
        probe("tasks", lambda: configured_tasks(config, context.machine).check_reachable()),
        calendar_check(config),
    ]
    return {check.name: {"state": check.state, "detail": check.detail} for check in checks}


def _check_store(config: MachineConfig, machine: MachinePaths) -> None:
    load_store_settings(configured_store(config, machine))


def _inbox(store: Store) -> dict[str, Any]:
    try:
        scan = store.scan(INBOX)
    except StoreError as error:
        return {"error": str(error)}
    return {"count": len(scan.files) + len(scan.evicted), "evicted": len(scan.evicted)}


def _run(store: Store, machine: MachinePaths, this_machine: str, now: datetime.datetime) -> dict[str, Any]:
    try:
        record = load_run_record(store)
    except (RunRecordError, StoreError) as error:
        return {"error": str(error)}
    if record is None:
        return {"state": "none"}
    state = record.state
    if state == RUNNING and (
        is_interrupted(record, now) or (record.machine_id == this_machine and not machine_state.lock_is_held(machine))
    ):
        state = INTERRUPTED
    run: dict[str, Any] = {"state": state, "machine_id": record.machine_id, "started_at": _iso(record.started_at)}
    if record.finished_at:
        run["finished_at"] = _iso(record.finished_at)
    if record.last_success:
        run["last_succeeded_at"] = _iso(record.last_success)
    if record.message:
        run["message"] = record.message
    return run


def _last_attempt(machine: MachinePaths, run: dict[str, Any]) -> dict[str, str] | None:
    """A run that was not due after the last recorded run, so a scheduled attempt shows it reached m2b."""
    attempt = machine_state.last_attempt(machine)
    if attempt is None or attempt.time is None:
        return None
    last_run = run.get("finished_at") or run.get("started_at")
    if last_run is not None and attempt.time <= datetime.datetime.fromisoformat(last_run):
        return None
    return {"kind": attempt.kind, "at": _iso(attempt.time), "message": attempt.message}


def _backends(config: MachineConfig, context: Context, now: datetime.datetime) -> tuple[str, dict[str, Any]]:
    cache = context.machine.state_dir / CACHE_FILE
    try:
        raw = json.loads(cache.read_text(encoding="utf-8"))
        checked_at = datetime.datetime.fromisoformat(raw["checked_at"])
        if datetime.timedelta(0) <= now - checked_at < PROBE_MAX_AGE and isinstance(raw["backends"], dict):
            return raw["checked_at"], raw["backends"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    backends = probe_backends(config, context)
    checked = _iso(now)
    data = json.dumps({"checked_at": checked, "backends": backends}) + "\n"
    # A cache that cannot be written only means probing again next time.
    with contextlib.suppress(OSError):
        replace_atomically(cache, data.encode("utf-8"), context.machine.temp_dir)
    return checked, backends


def _print_text(answer: dict[str, Any]) -> None:
    inbox = answer["inbox"]
    if "error" in inbox:
        print(f"inbox: could not look: {inbox['error']}")
    else:
        print(f"inbox: {inbox['count']}" + (f" ({inbox['evicted']} not downloaded)" if inbox["evicted"] else ""))
    run = answer["run"]
    if "error" in run:
        print(f"run: could not look: {run['error']}")
    elif run["state"] == "none":
        print("run: no curation run yet")
    else:
        when = run.get("finished_at") or run["started_at"]
        line = f"run: {run['state']} on {run['machine_id']} at {when}"
        print(line + (f": {run['message']}" if run.get("message") else ""))
    attempt = answer["last_attempt"]
    if attempt is not None:
        print(f"last attempt: {attempt['kind'].replace('_', ' ')} at {attempt['at']}")
    curating = answer["curating_machine"] or "unknown"
    due = answer["due"]
    if due is None:
        print(f"due: asked on {curating}, the curating machine")
    else:
        print(f"due: {'yes' if due['due'] else 'no'} ({due['reason']})")
    for name, check in answer["backends"].items():
        print(f"{name}: {check['state']}" + (f" ({check['detail']})" if check.get("detail") else ""))
    store_format = answer.get("store_format")
    if store_format is not None:
        print(f"store format: {store_format['state']} ({store_format['detail']})")
    on = [name for name, is_addon_on in answer["addons"].items() if is_addon_on]
    print(f"add-ons on: {', '.join(on) if on else 'none'}")


def _iso(moment: datetime.datetime) -> str:
    return moment.isoformat(timespec="seconds")
