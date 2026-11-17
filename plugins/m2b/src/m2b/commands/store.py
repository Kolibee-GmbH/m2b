"""``store check-local / fetch / open``: which files are evicted, downloading them, and opening a
PDF or a picture of the archive in the system's viewer."""

from __future__ import annotations

import argparse

from m2b import viewer
from m2b.commands import Context, ProblemError, UsageError
from m2b.commands.backends import configured_store
from m2b.commands.output import print_json
from m2b.config.machine import load_machine_config
from m2b.notes.characters import with_hidden_written_out
from m2b.source import SourceNotFoundError
from m2b.store.base import DEFAULT_FETCH_TIMEOUT_SECONDS, PathOutsideStoreError, Store

__all__ = ["DEFAULT_FETCH_TIMEOUT_SECONDS", "store_check_local", "store_fetch", "store_open"]


def _store(context: Context) -> Store:
    return configured_store(load_machine_config(context.machine), context.machine)


def store_check_local(arguments: argparse.Namespace, context: Context) -> int:
    try:
        evicted = _store(context).check_local(arguments.paths)
    except PathOutsideStoreError as error:
        raise UsageError(str(error)) from error
    if arguments.json:
        print_json(evicted)
    else:
        for path in evicted:
            print(path)
    return 0


def store_fetch(arguments: argparse.Namespace, context: Context) -> int:
    try:
        _store(context).fetch(arguments.paths, timeout_seconds=arguments.timeout)
    except PathOutsideStoreError as error:
        raise UsageError(str(error)) from error
    return 0


def store_open(arguments: argparse.Namespace, context: Context) -> int:
    """A refused name ends with exit 2, a file that is not there or does not open with exit 1."""
    try:
        opened = viewer.open_original(_store(context), arguments.name, context.environ)
    except viewer.OpenRefusedError as error:
        raise UsageError(with_hidden_written_out(str(error))) from error
    except (viewer.NotOpenedError, SourceNotFoundError) as error:
        raise ProblemError(with_hidden_written_out(str(error))) from error
    print(f"opened {with_hidden_written_out(opened)} in the system's viewer")
    return 0
