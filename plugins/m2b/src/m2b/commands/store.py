"""``store check-local / fetch / open / edit``: which files are evicted, downloading them, opening a
PDF or a picture of the archive in the system's viewer, and editing a copy of a fact file.

``store edit`` answers a name that is no fact file's, a path (a lesson's among them) or the
distillate or a fact file that is a symbolic link with exit 2, a fact file ``memory/`` does not hold
or one it cannot copy (not downloaded, a run under way) with exit 1; nothing is copied then.
"""

from __future__ import annotations

import argparse

from m2b import fact_edit, viewer
from m2b.commands import Context, ProblemError, UsageError
from m2b.commands.backends import configured_store
from m2b.commands.output import print_json
from m2b.config.machine import load_machine_config
from m2b.curate.machine_state import lock_is_held
from m2b.notes.characters import with_hidden_written_out
from m2b.source import SourceNotFoundError, SourceRefusedError, fact_file_named
from m2b.store.base import DEFAULT_FETCH_TIMEOUT_SECONDS, PathOutsideStoreError, Store

__all__ = ["DEFAULT_FETCH_TIMEOUT_SECONDS", "store_check_local", "store_edit", "store_fetch", "store_open"]


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


def store_edit(arguments: argparse.Namespace, context: Context) -> int:
    """Makes and opens the copy, or keeps or discards it; prints what became of it."""
    store = _store(context)
    name = arguments.name
    try:
        try:
            fact_file_named(store, name)
        except SourceNotFoundError:
            # A copy outlives a fact file removed or renamed since; dropping it touches no store.
            if not arguments.discard:
                raise
        if arguments.keep:
            kept = fact_edit.keep_copy(store, context.machine, name)
            answer: dict[str, object] = {"kept": kept}
            words = f"kept as {kept} for the next curation run" if kept else "the copy did not differ; nothing kept"
        elif arguments.discard:
            discarded = fact_edit.discard_copy(context.machine, name)
            answer = {"discarded": discarded}
            words = "the copy was removed" if discarded else "there was no copy"
        else:
            opened = fact_edit.open_copy(store, context.machine, name, context.environ, lock_is_held(context.machine))
            answer = {"copy": str(opened.copy), "opened": opened.opened, "not_opened": opened.not_opened}
            words = f"{'opened' if opened.opened else 'not opened'}: {opened.copy}"
            if opened.not_opened:
                words += f" ({opened.not_opened})"
    except SourceRefusedError as error:
        raise UsageError(with_hidden_written_out(str(error))) from error
    except (SourceNotFoundError, fact_edit.EditRefusedError) as error:
        raise ProblemError(with_hidden_written_out(str(error))) from error
    if arguments.json:
        print_json(answer)
    else:
        print(words)
    return 0
