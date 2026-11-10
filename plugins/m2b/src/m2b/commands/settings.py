"""``config get / set`` and ``profile get / set / merge``: the only writers besides setup."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from m2b.addons import REMOVED_ADDONS, RemovedAddonError
from m2b.commands import Context, UsageError
from m2b.commands.backends import configured_store
from m2b.commands.output import as_json, lookup, parse_value, print_value
from m2b.config import store_path
from m2b.config.errors import ConfigError, StoreUnreachableError
from m2b.config.machine import StoreLocation, load_machine_config, set_machine_config_value
from m2b.config.profile import merge_into_profile, require_profile, set_profile_value
from m2b.config.store_settings import load_store_settings
from m2b.paths import expand
from m2b.store.base import StoreError
from m2b.store.factory import open_store

STORE_KEY = "store"
STORE_PATH_KEY = "store.path"


def config_get(arguments: argparse.Namespace, context: Context) -> int:
    config = load_machine_config(context.machine)
    print_value(lookup(as_json(config), arguments.key, "config.json"), arguments.json)
    return 0


def config_set(arguments: argparse.Namespace, context: Context) -> int:
    value = parse_value(arguments.value)
    removed = _removed_addon_written(arguments.key)
    if removed is not None:
        raise UsageError(str(RemovedAddonError(removed)))
    written = _store_path_written(arguments.key, value)
    if written is not None:
        path = expand(written, context.machine.home)
        unusable = store_path.problem(path)
        if unusable is not None and _curates_at(context, path, value):
            raise UsageError(unusable)
    set_machine_config_value(context.machine, arguments.key, value)
    return 0


def _removed_addon_written(key: str) -> str | None:
    """The add-on m2b no longer has whose settings this call writes; the loader would ignore them."""
    parts = key.split(".")
    if len(parts) >= 2 and parts[0] == "addons" and parts[1] in REMOVED_ADDONS:
        return parts[1]
    return None


def _store_path_written(key: str, value: object) -> str | None:
    """The store path this call writes: as ``store.path``, or inside a whole ``store`` section."""
    if key == STORE_PATH_KEY and isinstance(value, str):
        return value
    if key == STORE_KEY and isinstance(value, dict) and isinstance(value.get("path"), str):
        return str(value["path"])
    return None


def _curates_at(context: Context, path: Path, value: object) -> bool:
    """Whether this machine curates the store at ``path``, the one the config will name.

    The owner moves a store and then sets its new path, so the store is read there first; only
    when it cannot be read there (a folder not made yet) does the store configured now decide. A
    store that cannot be read at all says no, and doctor names the path once it can.
    """
    try:
        config = load_machine_config(context.machine)
    except ConfigError:
        return False
    backend = value.get("backend") if isinstance(value, dict) else None
    target = StoreLocation(backend if isinstance(backend, str) else config.store.backend, path)
    for location in (target, config.store):
        try:
            settings = load_store_settings(open_store(location, context.machine.temp_dir))
        except (ConfigError, StoreUnreachableError, StoreError, OSError):
            continue
        return settings.curating_machine == config.machine_id
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
