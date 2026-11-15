"""``distillate off / on``: projects whose sessions get no distillate, for work the owner keeps apart.

``distillate topic <name>`` prints one topic's facts and current items as the distillate holds them
at the call: the owner asks what stands behind a topic a session was given, and what the session
got at its moment of giving is kept nowhere. A name the distillate holds no topic of is said, also
where there is no distillate yet; a distillate that cannot be read ends the command like any store
that cannot be reached, never as a topic without lines. No line is printed with a character that
draws nothing (``notes.characters``); the name is the caller's own and is answered as given.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from m2b.commands import Context
from m2b.commands.backends import configured_store
from m2b.commands.output import print_json
from m2b.config.machine import DistillateSettings, load_machine_config, set_machine_config_value
from m2b.notes.characters import without_hidden
from m2b.notes.layout import MEMORY, MEMORY_INDEX
from m2b.notes.memory_index import split_topics, topic_items
from m2b.paths import expand
from m2b.store.base import Store

KEY = "distillate.skip_under"


def distillate_off(arguments: argparse.Namespace, context: Context) -> int:
    folder = _folder(arguments, context)
    config = load_machine_config(context.machine)
    if config.distillate.covering(folder) is not None:
        print(f"sessions in {folder} get no distillate already")
        return 0
    written = [str(path) for path in config.distillate.skip_under]
    set_machine_config_value(context.machine, KEY, [*written, str(folder)])
    print(f"sessions in {folder} and below get no distillate from now on")
    return 0


def distillate_on(arguments: argparse.Namespace, context: Context) -> int:
    folder = _folder(arguments, context)
    config = load_machine_config(context.machine)
    kept = tuple(path for path in config.distillate.skip_under if path.resolve() != folder)
    if len(kept) != len(config.distillate.skip_under):
        set_machine_config_value(context.machine, KEY, [str(path) for path in kept])
    covering = DistillateSettings(kept).covering(folder)
    if covering is not None:
        print(f"sessions in {folder} still get no distillate: {covering} is turned off; m2b distillate on {covering}")
        return 0
    print(f"sessions in {folder} get the distillate")
    return 0


def distillate_topic(arguments: argparse.Namespace, context: Context) -> int:
    name: str = arguments.name
    text = _distillate(configured_store(load_machine_config(context.machine), context.machine))
    block = next((block for block in split_topics(text).blocks if block.topic.name == name), None)
    facts, current = topic_items(block) if block is not None else ([], [])
    if arguments.json:
        print_json({"name": name, "found": block is not None, "facts": facts, "current": current})
        return 0
    if block is None:
        print(f"the distillate holds no topic named {name} now")
        return 0
    print(f"{name}, as the distillate holds it now")
    for fact in facts:
        print(f"- {fact}")
    if current:
        print("Current")
    for item in current:
        print(f"- {item}")
    return 0


def _distillate(store: Store) -> str:
    """The distillate as a session's hooks read it, or nothing where the store has none yet."""
    try:
        return without_hidden(store.read_bytes(f"{MEMORY}/{MEMORY_INDEX}").decode("utf-8", errors="replace"))
    except FileNotFoundError:
        return ""


def _folder(arguments: argparse.Namespace, context: Context) -> Path:
    written = arguments.folder or context.environ.get("PWD") or os.getcwd()
    return expand(written, context.machine.home).resolve()
