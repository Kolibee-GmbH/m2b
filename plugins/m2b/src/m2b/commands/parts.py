"""``parts list / on / off``: which optional parts of m2b run on this machine."""

from __future__ import annotations

import argparse
import json

from m2b.commands import Context, UsageError
from m2b.config.machine import load_machine_config, set_part_on
from m2b.parts import PARTS, UnknownPartError, is_on, part_named


def parts_list(arguments: argparse.Namespace, context: Context) -> int:
    parts = load_machine_config(context.machine).parts
    rows = [{"name": part.name, "on": is_on(parts, part.name), "summary": part.summary} for part in PARTS]
    if arguments.json:
        print(json.dumps(rows, indent=2))
        return 0
    width = max(len(part.name) for part in PARTS)
    for row in rows:
        print(f"{row['name']:<{width}}  {'on ' if row['on'] else 'off'}  {row['summary']}")
    return 0


def parts_on(arguments: argparse.Namespace, context: Context) -> int:
    return _switch(arguments.part, True, context)


def parts_off(arguments: argparse.Namespace, context: Context) -> int:
    return _switch(arguments.part, False, context)


def _switch(name: str, on: bool, context: Context) -> int:
    try:
        part_named(name)
    except UnknownPartError as error:
        raise UsageError(str(error)) from error
    word = "on" if on else "off"
    if set_part_on(context.machine, name, on):
        print(f"{name} is {word}")
    else:
        print(f"{name} was {word} already")
    return 0
