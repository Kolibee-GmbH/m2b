"""``harvest`` and ``journal``, and the localized prefix every candidate title starts with."""

from __future__ import annotations

import argparse
import datetime
import sys

from m2b import harvest, journal
from m2b.candidates import PREFIX_KEY
from m2b.commands import Context
from m2b.commands.backends import configured_store, configured_tasks
from m2b.commands.output import print_json
from m2b.config.machine import load_machine_config
from m2b.config.profile import language_for_clients, load_profile
from m2b.config.store_settings import load_store_settings, require_store_writable
from m2b.locale import load_locale
from m2b.store.base import DEFAULT_FETCH_TIMEOUT_SECONDS, Store

__all__ = ["PREFIX_KEY", "candidate_prefix", "harvest_command", "journal_command"]


def candidate_prefix(store: Store) -> str:
    return load_locale(language_for_clients(load_profile(store))).text(PREFIX_KEY)


def harvest_command(arguments: argparse.Namespace, context: Context) -> int:
    config = load_machine_config(context.machine)
    store = configured_store(config, context.machine)
    require_store_writable(store)
    report = harvest.harvest(store, configured_tasks(config, context.machine), candidate_prefix(store))
    if arguments.json:
        print_json({"captured": report.captured, "dropped": report.dropped, "problems": report.problems})
    else:
        for path in report.captured:
            print(f"captured {path}")
        for text in report.dropped:
            print(f"dropped: {text}")
        for problem in report.problems:
            print(f"m2b: {problem}", file=sys.stderr)
    return 1 if report.problems else 0


def journal_command(arguments: argparse.Namespace, context: Context) -> int:
    config = load_machine_config(context.machine)
    store = configured_store(config, context.machine)
    require_store_writable(store)
    since = load_store_settings(store).journal_since
    report = journal.write_journal(
        store,
        configured_tasks(config, context.machine),
        since,
        datetime.datetime.now(),
        fetch_timeout_seconds=DEFAULT_FETCH_TIMEOUT_SECONDS,
    )
    if arguments.json:
        print_json({"appended": report.appended, "problems": report.problems})
    else:
        for path, count in report.appended.items():
            print(f"{path}: {count} completed tasks added")
        for problem in report.problems:
            print(f"m2b: {problem}", file=sys.stderr)
    # A month left alone is could not look, not nothing to add.
    return 1 if report.problems else 0
