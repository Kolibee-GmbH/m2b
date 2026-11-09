"""``refresh due``: the memory lines that are due, as the refresh skill's work list; ``--json`` for it.

Facts past their ``until`` go to the fenced refresh step; quiet current items go to the owner as a
question. An evicted fact file is named with its fetch command, never read, so "nothing due" is
only said about what could be looked at. In the refresh step of ``m2b curate --refresh-all`` the JSON
also names the undated lines of the step's batch, the backfill's work list.
"""

from __future__ import annotations

import argparse
import datetime
from pathlib import PurePosixPath

from m2b import expiry
from m2b.commands import Context, ProblemError
from m2b.commands.backends import configured_store
from m2b.commands.output import print_json
from m2b.commands.times import parse_day
from m2b.config.machine import load_machine_config
from m2b.curate.model import CURATION_RUN_VARIABLE, REFRESH_ALL_VARIABLE
from m2b.store.base import fetch_command


def _batch(raw: str | None) -> expiry.Batch | None:
    if not raw:
        return None
    try:
        return expiry.Batch.from_json(raw)
    except ValueError as error:
        raise ProblemError(f"{REFRESH_ALL_VARIABLE} holds no backfill batch: {error}") from error


def refresh_due(arguments: argparse.Namespace, context: Context) -> int:
    today = parse_day(arguments.today, "--today") if arguments.today else datetime.date.today()
    config = load_machine_config(context.machine)
    store = configured_store(config, context.machine)
    found = expiry.due(store, today)
    if arguments.json:
        batch = _batch(context.environ.get(REFRESH_ALL_VARIABLE))
        data: dict[str, object] = {
            "store": str(config.store.path),
            "curation_run": context.environ.get(CURATION_RUN_VARIABLE) == "1",
            "refresh_all": batch is not None,
            "today": today.isoformat(),
            "facts": [
                {"file": PurePosixPath(fact.path).name, "path": fact.path, "until": fact.until} for fact in found.facts
            ],
            "current": [{"text": item.text, "since": item.since} for item in found.current],
            "evicted": [{"path": path, "fetch": fetch_command(path)} for path in found.evicted],
            "unreadable": [{"path": item.path, "reason": item.reason} for item in found.unreadable],
        }
        if batch is not None:
            # Read again: ingest, earlier in the run, may have dated a line of the batch meanwhile.
            undated = expiry.undated(store)
            data["undated"] = {
                "facts": [
                    {"file": PurePosixPath(path).name, "path": path} for path in batch.facts if path in undated.facts
                ],
                "current": [text for text in batch.current if text in undated.current],
            }
        print_json(data)
        return 0
    if not found.facts:
        complete = not found.evicted and not found.unreadable
        print("No fact is past its day." if complete else "No fact is past its day among those read.")
    for fact in found.facts:
        print(f"{fact.path} (until {fact.until})")
    for item in found.current:
        print(f"current, quiet since {item.since}: {item.text}")
    for path in found.evicted:
        print(f"not downloaded: {fetch_command(path)}")
    for unreadable in found.unreadable:
        print(f"could not read {unreadable.path}: {unreadable.reason}")
    return 0
