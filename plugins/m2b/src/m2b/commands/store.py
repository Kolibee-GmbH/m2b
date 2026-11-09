"""``store check-local / fetch``: which files are evicted, and downloading them."""

from __future__ import annotations

import argparse

from m2b.commands import Context, UsageError
from m2b.commands.backends import configured_store
from m2b.commands.output import print_json
from m2b.config.machine import load_machine_config
from m2b.store.base import DEFAULT_FETCH_TIMEOUT_SECONDS, PathOutsideStoreError, Store

__all__ = ["DEFAULT_FETCH_TIMEOUT_SECONDS", "store_check_local", "store_fetch"]


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
