"""``ingest normalize / list / task / ref / note / facts-filed / finish``: the curator's way to change captures.

A file is named by its name in the inbox (``inbox/`` in front is accepted). Each command can run
again: it finds what an earlier run did and does only the rest.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from typing import TypeVar

from m2b import ingest
from m2b.commands import Context, ProblemError, UsageError
from m2b.commands.backends import configured_store, configured_tasks
from m2b.commands.output import print_json
from m2b.commands.times import parse_day_or_moment
from m2b.config.machine import load_machine_config
from m2b.config.profile import language_for_clients, load_profile
from m2b.config.store_settings import require_store_writable
from m2b.curate.model import CURATION_RUN_VARIABLE
from m2b.notes.frontmatter import NoteFormatError
from m2b.store.base import Store
from m2b.tasks.base import Tasks

T = TypeVar("T")


def ingest_normalize(arguments: argparse.Namespace, context: Context) -> int:
    report = _guarded(lambda: ingest.normalize(_store(context), ingest.sips_converter()))
    if arguments.json:
        print_json(
            {
                "renamed": [{"from": old, "to": new} for old, new in report.renamed],
                "completed": report.completed,
                "bundles": report.bundles,
                "removed_copies": report.removed_copies,
                "kept_copies": report.kept_copies,
                "evicted": report.evicted,
                "problems": report.problems,
            }
        )
        return 1 if report.problems else 0
    for old, new in report.renamed:
        print(f"renamed {old} -> {new}")
    for relative in report.completed:
        print(f"completed the frontmatter of {relative}")
    for relative in report.bundles:
        print(f"bundle {relative}")
    for relative in report.removed_copies:
        print(f"removed the identical conflict copy {relative}")
    for relative in report.kept_copies:
        print(f"kept the conflict copy {relative}", file=sys.stderr)
    for relative in report.evicted:
        print(f"not downloaded, left for the next run: {relative}", file=sys.stderr)
    for problem in report.problems:
        print(f"m2b: {problem}", file=sys.stderr)
    return 1 if report.problems else 0


def ingest_list(arguments: argparse.Namespace, context: Context) -> int:
    """What the fenced model reads first: the store's path for its Read rules, the language for the
    titles it writes, the owner's name for what a capture says in the first person, whether it runs
    inside a curation run, and the captures waiting."""
    config = load_machine_config(context.machine)
    store = configured_store(config, context.machine)
    report = ingest.pending(store)
    owner_profile = load_profile(store)
    if arguments.json:
        print_json(
            {
                "store": str(config.store.path),
                "language": language_for_clients(owner_profile),
                "owner": owner_profile.owner if owner_profile is not None else None,
                "curation_run": context.environ.get(CURATION_RUN_VARIABLE) == "1",
                "captures": [
                    {
                        "file": capture.file,
                        "source": capture.source,
                        "kind": capture.kind,
                        "facts_filed": capture.facts_filed,
                        "quiet": capture.quiet,
                        "follow_up": capture.follow_up,
                        "members": list(capture.members),
                    }
                    for capture in report.captures
                ],
                "evicted": report.evicted,
                "problems": report.problems,
            }
        )
        return 1 if report.problems else 0
    for capture in report.captures:
        print(capture.file)
    for relative in report.evicted:
        print(f"not downloaded, left for the next run: {relative}", file=sys.stderr)
    for problem in report.problems:
        print(f"m2b: {problem}", file=sys.stderr)
    return 1 if report.problems else 0


def ingest_task(arguments: argparse.Namespace, context: Context) -> int:
    store, tasks = _store_and_tasks(context)
    if arguments.follow_up:
        if arguments.key or arguments.title or arguments.due:
            raise UsageError("--follow-up takes no --key, --title or --due: they come from the capture")
        task_id = _guarded(lambda: ingest.add_follow_up_task(store, tasks, arguments.file))
    else:
        if not arguments.key or not arguments.title:
            raise UsageError("a task needs --key and --title, or --follow-up")
        due = parse_day_or_moment(arguments.due, "--due") if arguments.due else None
        task_id = _guarded(lambda: ingest.add_task(store, tasks, arguments.file, arguments.key, arguments.title, due))
    if arguments.json:
        print_json({"task_id": task_id})
    elif task_id is not None:
        print(task_id)
    else:
        print("no follow_up in this capture")
    return 0


def ingest_ref(arguments: argparse.Namespace, context: Context) -> int:
    store = _store(context)
    _guarded(lambda: ingest.add_ref(store, arguments.file, arguments.ref))
    return 0


def ingest_note(arguments: argparse.Namespace, context: Context) -> int:
    text = sys.stdin.read() if arguments.text == "-" else arguments.text
    if not text.strip():
        raise UsageError("the note is empty")
    store = _store(context)
    _guarded(lambda: ingest.add_note(store, arguments.file, text.strip()))
    return 0


def ingest_facts_filed(arguments: argparse.Namespace, context: Context) -> int:
    store = _store(context)
    _guarded(lambda: ingest.set_facts_filed(store, arguments.file))
    return 0


def ingest_finish(arguments: argparse.Namespace, context: Context) -> int:
    store, tasks = _store_and_tasks(context)
    destinations = _guarded(lambda: ingest.finish(store, tasks, arguments.file))
    if arguments.json:
        print_json({"destinations": destinations})
    else:
        for destination in destinations:
            print(destination)
    return 0


def _store(context: Context) -> Store:
    store = configured_store(load_machine_config(context.machine), context.machine)
    require_store_writable(store)
    return store


def _store_and_tasks(context: Context) -> tuple[Store, Tasks]:
    config = load_machine_config(context.machine)
    store = configured_store(config, context.machine)
    require_store_writable(store)
    return store, configured_tasks(config, context.machine)


def _guarded(step: Callable[[], T]) -> T:
    """Runs one ingest step; a capture that cannot take it is a problem the run reports (exit 1)."""
    try:
        return step()
    except (ingest.IngestError, NoteFormatError) as error:
        raise ProblemError(str(error)) from error
