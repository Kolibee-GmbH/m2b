"""``config get / set``, ``profile get / set / merge`` and ``settings``: the settings, read and written by key.

``config`` and ``profile`` each read and write one file by any of its keys, for someone who knows
the key. ``settings`` lists every setting of the three files from the catalog (``config.catalog``):
as text under its file, for someone who edits one, and as JSON also with the group a view shows it
in. ``settings set`` changes a switch and nothing else, so a caller that offers a few switches to
press cannot write a path, a program or a time limit through it, whatever key it sends.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from m2b import handed_in
from m2b.addons import REMOVED_ADDONS, RemovedAddonError
from m2b.commands import Context, UsageError
from m2b.commands.backends import configured_store
from m2b.commands.output import as_json, lookup, parse_value, print_json, print_value
from m2b.config import catalog, store_path
from m2b.config.errors import ConfigError, InvalidConfigError, StoreUnreachableError
from m2b.config.json_file import read_store_json_object
from m2b.config.machine import MachineConfig, StoreLocation, load_machine_config, set_machine_config_value
from m2b.config.profile import (
    PROFILE_FILE_NAME,
    Profile,
    merge_into_profile,
    parse_profile,
    require_profile,
    set_profile_value,
)
from m2b.config.store_settings import STORE_SETTINGS_FILE_NAME, StoreSettings, load_store_settings
from m2b.notes.characters import with_unseen_written_out
from m2b.paths import expand
from m2b.store.base import StoreError
from m2b.store.factory import open_store

# Set in every command Claude Code starts, the shell line a person types into a session among them.
CLAUDE_CODE_VARIABLE = "CLAUDECODE"
STORE_KEY = "store"
STORE_PATH_KEY = "store.path"


def config_get(arguments: argparse.Namespace, context: Context) -> int:
    config = load_machine_config(context.machine)
    print_value(lookup(as_json(config), arguments.key, "config.json"), arguments.json)
    return 0


def config_set(arguments: argparse.Namespace, context: Context) -> int:
    value = parse_value(arguments.value)
    refuse_forbidden_machine_config_change(context, arguments.key, value)
    set_machine_config_value(context.machine, arguments.key, value)
    return 0


def refuse_forbidden_machine_config_change(context: Context, key: str, value: object) -> None:
    """The rules of a change of the machine config, for every command that writes a key of it.

    They stand here once, because a rule two commands each hold is a rule one of them forgets:
    no setting of an add-on m2b no longer has, no store path a curating machine cannot use, and
    handing in turned on by no session.
    """
    removed = _removed_addon_written(key)
    if removed is not None:
        raise UsageError(str(RemovedAddonError(removed)))
    written = _store_path_written(key, value)
    if written is not None:
        path = expand(written, context.machine.home)
        unusable = store_path.problem(path)
        if unusable is not None and _curates_at(context, path, value):
            raise UsageError(unusable)
    if _lets_sessions_hand_in(key, value) and context.environ.get(CLAUDE_CODE_VARIABLE):
        raise UsageError(
            f"{handed_in.SWITCH} is turned on in a terminal of your own, outside Claude Code: with it a session "
            "hands in proposals with words from what its agent read, and no session turns that on"
        )


def _lets_sessions_hand_in(key: str, value: object) -> bool:
    """Whether this call turns handing in on, under the key itself or with the whole section."""
    section, _, setting = handed_in.SWITCH.partition(".")
    if key == handed_in.SWITCH:
        return value is True
    return key == section and isinstance(value, dict) and value.get(setting) is True


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


_NOT_READABLE = (ConfigError, StoreUnreachableError, StoreError, OSError)
# The command that names what is wrong in a file that does not follow its format.
_SAYS_WHERE = {STORE_SETTINGS_FILE_NAME: "m2b status", PROFILE_FILE_NAME: "m2b profile get"}
GROUP_HEADINGS = {
    catalog.MACHINE: "This machine",
    catalog.STORE: "The store, for every machine",
    catalog.OWNER: "The owner, for every machine",
}
NOT_READ = "not read"


def settings_command(arguments: argparse.Namespace, context: Context) -> int:
    """Every setting of the three files; what a file holds is listed also when another cannot be read."""
    config = load_machine_config(context.machine)
    store, profile, not_read = _read_the_store(config, context)
    entries = catalog.entries(catalog.values(config, store, profile))
    if arguments.json:
        curates = None if store is None else store.curating_machine == config.machine_id
        answer = {"curates": curates, "not_read": not_read, "groups": catalog.group_entries(), "settings": entries}
        print_json(answer)
    else:
        _print_settings(entries, not_read)
    return 0


def _read_the_store(
    config: MachineConfig, context: Context
) -> tuple[StoreSettings | None, Profile | None, dict[str, str]]:
    """The store's settings and the profile, each None with its reason under the file's name."""
    not_read: dict[str, str] = {}
    store_settings: StoreSettings | None = None
    profile: Profile | None = None
    try:
        store = configured_store(config, context.machine)
    except _NOT_READABLE as error:
        return None, None, {name: _why_not_read(name, error) for name in (STORE_SETTINGS_FILE_NAME, PROFILE_FILE_NAME)}
    try:
        store_settings = load_store_settings(store)
    except _NOT_READABLE as error:
        not_read[STORE_SETTINGS_FILE_NAME] = _why_not_read(STORE_SETTINGS_FILE_NAME, error)
    try:
        raw = read_store_json_object(store, PROFILE_FILE_NAME)
        if raw is None:
            not_read[PROFILE_FILE_NAME] = f"no {PROFILE_FILE_NAME} in the store yet"
        else:
            profile = _with_the_language_as_written(raw, parse_profile(raw, for_writing=False))
    except _NOT_READABLE as error:
        not_read[PROFILE_FILE_NAME] = _why_not_read(PROFILE_FILE_NAME, error)
    return store_settings, profile, not_read


def _why_not_read(file_name: str, error: Exception) -> str:
    """Why a file was not read, on one line and without a word of the file.

    The error of a file that does not follow its format quotes the value it stumbled over, and that
    can be what a named setting holds, a customer's name or a folder. So this list names the kind
    of trouble and the command that says where.
    """
    if isinstance(error, InvalidConfigError):
        return f"{file_name} in the store does not follow its format; {_SAYS_WHERE[file_name]} says where"
    return with_unseen_written_out(str(error))


def _with_the_language_as_written(raw: Mapping[str, Any], profile: Profile) -> Profile:
    """The profile with the language its file, read as ``raw``, names.

    A profile from a newer m2b can name a language this one has no texts for; it reads as English
    (``config.profile``). The list shows the one the file names, as it shows a model the switch
    does not offer, so that nobody changes the language without seeing which one was set.
    """
    written = raw.get("language")
    if isinstance(written, str) and written and written != profile.language:
        return dataclasses.replace(profile, language=written)
    return profile


def _print_settings(entries: list[dict[str, Any]], not_read: Mapping[str, str]) -> None:
    for position, (scope, heading) in enumerate(GROUP_HEADINGS.items()):
        file_name = catalog.FILES[scope]
        if position:
            print()
        print(f"{heading} ({file_name})")
        if file_name in not_read:
            print(f"  {NOT_READ}: {not_read[file_name]}")
        for entry in entries:
            if entry["scope"] == scope:
                _print_setting(entry)


def _print_setting(entry: dict[str, Any]) -> None:
    shows = entry["shows"] if entry["read"] else NOT_READ
    default = entry["default"]
    differs = entry["read"] and default is not None and entry["value"] != default
    print(f"  {entry['key']}: {shows}{f' (default {catalog.in_words(default)})' if differs else ''}")
    print(f"      {entry['does']}")
    print(f"      {_how_it_changes(entry['kind'], entry['changed_by'], entry['change'])}")


def _how_it_changes(kind: str, how: str, change: str | None) -> str:
    if how == catalog.NEVER or change is None:
        return "kept by m2b, never changed by hand"
    if how == catalog.SETUP:
        return f"set up with {change}"
    if how == catalog.HAND:
        return f"by hand: {change}"
    return f"{'switch' if kind == catalog.SWITCH else 'change'}: {change}"


def settings_set(arguments: argparse.Namespace, context: Context) -> int:
    """Changes a switch to one of its values; every other key and value is refused with one line."""
    key = arguments.key
    named = catalog.named(key)
    if not named:
        raise UsageError(f"no setting is named {_as_typed(key)}; m2b settings lists them")
    switch = next((setting for setting in named if setting.kind == catalog.SWITCH), None)
    if switch is None:
        raise UsageError(f"{key} is no switch, and m2b settings set changes a switch only: {_way_to_change(named[0])}")
    value = parse_value(arguments.value)
    if not any(value == choice and type(value) is type(choice) for choice in switch.choices):
        raise UsageError(_not_a_value_of(switch, _as_typed(arguments.value)))
    SWITCH_WRITERS[switch.scope](context, key, value)
    return 0


def _way_to_change(setting: catalog.Setting) -> str:
    if setting.change is None:
        return "m2b keeps it, and it is never changed by hand"
    if setting.how == catalog.SETUP:
        return f"{setting.change} changes it"
    if setting.how == catalog.HAND:
        return f"no command writes it; {setting.change}"
    return f"change it with {setting.change}"


def _as_typed(text: str) -> str:
    """What was typed, on one line: a line break and a character that draws nothing are written out."""
    return with_unseen_written_out(text) or "''"


def _not_a_value_of(switch: catalog.Setting, given: str) -> str:
    if switch.choices == catalog.ON_OFF:
        return f"{switch.key} is true or false, not {given}"
    values = " or ".join(catalog.as_argument(choice) for choice in switch.choices)
    if switch.file_takes_more:
        return f"{switch.key} is {values} here, not {given}; any other value: m2b config set {switch.key} <value>"
    return f"{switch.key} is {values}, not {given}"


def _write_machine_switch(context: Context, key: str, value: object) -> None:
    refuse_forbidden_machine_config_change(context, key, value)
    set_machine_config_value(context.machine, key, value)


def _write_owner_switch(context: Context, key: str, value: object) -> None:
    store = configured_store(load_machine_config(context.machine), context.machine)
    try:
        set_profile_value(store, key, value)
    except InvalidConfigError as error:
        # The whole file is checked before it is written, and its error quotes the file.
        raise UsageError(_why_not_read(PROFILE_FILE_NAME, error)) from error


# The file a switch is written into, by the scope of its setting; the store's settings have no switch.
SWITCH_WRITERS: Mapping[str, Callable[[Context, str, object], None]] = {
    catalog.MACHINE: _write_machine_switch,
    catalog.OWNER: _write_owner_switch,
}
