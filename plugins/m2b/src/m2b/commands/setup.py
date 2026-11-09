"""``setup inspect / apply``: what the setup skill reads before it asks, and what writes the answers."""

from __future__ import annotations

import argparse
import datetime
import sys

from m2b import setup
from m2b.commands import Context, UsageError
from m2b.commands.output import print_json
from m2b.config.machine import STORE_BACKENDS, StoreLocation
from m2b.paths import expand


def setup_inspect(arguments: argparse.Namespace, context: Context) -> int:
    if (arguments.store_backend is None) != (arguments.store_path is None):
        raise UsageError("give --store-backend and --store-path together, or neither for the configured store")
    location = None
    if arguments.store_path is not None:
        location = StoreLocation(arguments.store_backend, expand(arguments.store_path, context.machine.home))
    found = setup.inspect(context.machine, location)
    if arguments.json:
        print_json(found)
    else:
        named = found["store"]
        print(f"store: {named['path']} ({named['backend']})" if named is not None else "store: none named")
        if named is not None and not found["store_exists"]:
            print("store folder: does not exist yet")
        for key, label in (("store_settings", "store.json"), ("profile", "profile.json")):
            print(f"{label}: {'present' if found[key] is not None else 'missing'}")
        print(f"memory/MEMORY.md: {'present' if found['distillate'] else 'missing'}")
        print(f"machine config: {'present' if found['machine_config'] is not None else 'missing'}")
    return 0


def setup_apply(arguments: argparse.Namespace, context: Context) -> int:
    text = sys.stdin.read() if arguments.answers == "-" else arguments.answers
    answers = setup.answers_from_text(text, context.machine.home)
    result = setup.apply(context.machine, answers, context.environ, datetime.date.today())
    if arguments.json:
        print_json(result.__dict__)
    else:
        for path in result.written:
            print(f"wrote {path}")
        if not result.written:
            print("nothing changed")
        for line in [result.take_over, *result.problems]:
            if line:
                print(line)
        for name in result.missing_executables:
            print(f"{name} was not found on PATH; record it with m2b config set executables.{name} <path>")
    # The rest was written; what is left in problems needs the owner, so the exit says so.
    return 1 if result.problems else 0


__all__ = ["STORE_BACKENDS", "setup_apply", "setup_inspect"]
