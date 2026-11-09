"""``config get / set`` and ``profile get / set / merge``: the only writers besides setup."""

from __future__ import annotations

import argparse
import json
import sys

from m2b.commands import Context, UsageError
from m2b.commands.backends import configured_store
from m2b.commands.output import as_json, lookup, parse_value, print_value
from m2b.config.machine import load_machine_config, set_machine_config_value
from m2b.config.profile import merge_into_profile, require_profile, set_profile_value


def config_get(arguments: argparse.Namespace, context: Context) -> int:
    config = load_machine_config(context.machine)
    print_value(lookup(as_json(config), arguments.key, "config.json"), arguments.json)
    return 0


def config_set(arguments: argparse.Namespace, context: Context) -> int:
    set_machine_config_value(context.machine, arguments.key, parse_value(arguments.value))
    return 0


def profile_get(arguments: argparse.Namespace, context: Context) -> int:
    store = configured_store(load_machine_config(context.machine), context.machine)
    print_value(lookup(as_json(require_profile(store)), arguments.key, "profile.json"), arguments.json)
    return 0


def profile_set(arguments: argparse.Namespace, context: Context) -> int:
    store = configured_store(load_machine_config(context.machine), context.machine)
    set_profile_value(store, arguments.key, parse_value(arguments.value))
    return 0


def profile_merge(arguments: argparse.Namespace, context: Context) -> int:
    """Merges a JSON object, given as the argument or on standard input with ``-``."""
    text = sys.stdin.read() if arguments.patch == "-" else arguments.patch
    try:
        patch = json.loads(text)
    except ValueError as error:
        raise UsageError(f"profile merge takes a JSON object: {error}") from error
    if not isinstance(patch, dict):
        raise UsageError('profile merge takes a JSON object, such as {"language": "de"}')
    store = configured_store(load_machine_config(context.machine), context.machine)
    merge_into_profile(store, patch)
    return 0
