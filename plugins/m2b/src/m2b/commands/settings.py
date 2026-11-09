"""``config get / set`` and ``profile get / set / merge``: the only writers besides setup."""

from __future__ import annotations

import argparse
import json
import sys

from m2b.commands import Context, UsageError
from m2b.commands.backends import configured_store
from m2b.commands.output import as_json, lookup, parse_value, print_value
from m2b.config import store_path
from m2b.config.errors import ConfigError, StoreUnreachableError
from m2b.config.machine import load_machine_config, set_machine_config_value
from m2b.config.profile import merge_into_profile, require_profile, set_profile_value
from m2b.config.store_settings import load_store_settings
from m2b.paths import expand
from m2b.store.base import StoreError

STORE_PATH_KEY = "store.path"


def config_get(arguments: argparse.Namespace, context: Context) -> int:
    config = load_machine_config(context.machine)
    print_value(lookup(as_json(config), arguments.key, "config.json"), arguments.json)
    return 0


def config_set(arguments: argparse.Namespace, context: Context) -> int:
    value = parse_value(arguments.value)
    if arguments.key == STORE_PATH_KEY and isinstance(value, str) and _curates_here(context):
        unusable = store_path.problem(expand(value, context.machine.home))
        if unusable is not None:
            raise UsageError(unusable)
    set_machine_config_value(context.machine, arguments.key, value)
    return 0


def _curates_here(context: Context) -> bool:
    """Whether the store as configured now names this machine; one that cannot be read says no,
    and doctor names a store path curation cannot use once it can."""
    try:
        config = load_machine_config(context.machine)
        return load_store_settings(configured_store(config, context.machine)).curating_machine == config.machine_id
    except (ConfigError, StoreUnreachableError, StoreError, OSError):
        return False


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
