"""``addons list / on / off``: which add-ons of m2b run on this machine.

``off`` with the name of an add-on m2b no longer has removes what an older version left in
``config.json``, so the owner can tidy it up without editing the file.
"""

from __future__ import annotations

import argparse
import json

from m2b.addons import (
    ADDONS,
    REMOVED_ADDONS,
    RemovedAddonError,
    UnknownAddonError,
    addon_named,
    is_on,
    removed_addon_notice,
)
from m2b.commands import Context, UsageError
from m2b.config.machine import load_machine_config, remove_addon_entry, set_addon_on


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
    if name in REMOVED_ADDONS and not on:
        return _remove_entry(name, context)
    try:
        addon_named(name)
    except (UnknownAddonError, RemovedAddonError) as error:
        raise UsageError(str(error)) from error
    word = "on" if on else "off"
    if set_addon_on(context.machine, name, on):
        print(f"{name} is {word}")
    else:
        print(f"{name} was {word} already")
    return 0


def _remove_entry(name: str, context: Context) -> int:
    if remove_addon_entry(context.machine, name):
        print(f"{removed_addon_notice(name)}; its entry in config.json is removed")
    else:
        print(f"{removed_addon_notice(name)}; config.json has nothing to remove for it")
    return 0
