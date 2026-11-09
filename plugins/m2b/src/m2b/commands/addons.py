"""``addons list / on / off``: which add-ons of m2b run on this machine."""

from __future__ import annotations

import argparse
import json

from m2b.addons import ADDONS, UnknownAddonError, addon_named, is_on
from m2b.commands import Context, UsageError
from m2b.config.machine import load_machine_config, set_addon_on


def addons_list(arguments: argparse.Namespace, context: Context) -> int:
    addons = load_machine_config(context.machine).addons
    rows = [{"name": addon.name, "on": is_on(addons, addon.name), "summary": addon.summary} for addon in ADDONS]
    if arguments.json:
        print(json.dumps(rows, indent=2))
        return 0
    width = max(len(addon.name) for addon in ADDONS)
    for row in rows:
        print(f"{row['name']:<{width}}  {'on ' if row['on'] else 'off'}  {row['summary']}")
    return 0


def addons_on(arguments: argparse.Namespace, context: Context) -> int:
    return _switch(arguments.addon, True, context)


def addons_off(arguments: argparse.Namespace, context: Context) -> int:
    return _switch(arguments.addon, False, context)


def _switch(name: str, on: bool, context: Context) -> int:
    try:
        addon_named(name)
    except UnknownAddonError as error:
        raise UsageError(str(error)) from error
    word = "on" if on else "off"
    if set_addon_on(context.machine, name, on):
        print(f"{name} is {word}")
    else:
        print(f"{name} was {word} already")
    return 0
