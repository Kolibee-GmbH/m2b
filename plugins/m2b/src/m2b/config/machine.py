"""The machine config, ``config.json``: what this machine uses and how it runs curation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from m2b.addons import ON, REMOVED_ADDONS, addon_names
from m2b.config.errors import FormatTooNewError, InvalidConfigError, NotSetUpError
from m2b.config.fields import Fields
from m2b.config.json_file import read_json_object, with_value, write_json_object
from m2b.paths import MachinePaths, expand

CONFIG_FILE_NAME = "config.json"
KNOWN_CONFIG_VERSION = 1

STORE_BACKENDS = ("folder", "icloud")
CALENDAR_BACKENDS = ("none", "apple-calendar")
EXECUTABLES = ("python3", "claude", "reminders", "osascript")

DEFAULT_BACKEND_TIMEOUT_SECONDS = 20
DEFAULT_MODEL_TIMEOUT_MINUTES = 15
# A small model by default, to keep a daily run cheap; Claude Code resolves the alias to its current
# version.
DEFAULT_CURATION_MODEL = "haiku"
# What setup offers: the default, and a larger model for better filing at a higher cost.
CURATION_MODELS = (DEFAULT_CURATION_MODEL, "sonnet")
DEFAULT_MAX_TURNS = 100


@dataclass(frozen=True)
class StoreLocation:
    backend: str
    path: Path


@dataclass(frozen=True)
class CalendarSettings:
    backend: str = "none"
    timeout_seconds: int = DEFAULT_BACKEND_TIMEOUT_SECONDS


@dataclass(frozen=True)
class CurationSettings:
    model_timeout_minutes: int = DEFAULT_MODEL_TIMEOUT_MINUTES
    model: str = DEFAULT_CURATION_MODEL
    max_turns: int = DEFAULT_MAX_TURNS
    # Claude Code's own estimate of API spend per model step; unset, no cap. On a subscription the
    # estimate says little, so it is off unless the user sets it.
    max_budget_usd: float | None = None


@dataclass(frozen=True)
class DistillateSettings:
    # Folders, absolute after loading, in and under which no session gets the distillate.
    skip_under: tuple[Path, ...] = ()

    def covering(self, folder: Path) -> Path | None:
        """The first skipped folder that is ``folder`` or one above it, None when the distillate is on there."""
        resolved = folder.resolve()
        return next(
            (skipped for skipped in self.skip_under if skipped.resolve() in (resolved, *resolved.parents)), None
        )


@dataclass(frozen=True)
class MachineConfig:
    version: int
    machine_id: str
    store: StoreLocation
    calendar: CalendarSettings
    executables: Mapping[str, str]
    curation: CurationSettings
    distillate: DistillateSettings = field(default_factory=DistillateSettings)
    # Each add-on's settings as written, ``on`` included; ``m2b.addons.is_on`` reads them.
    addons: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)


def parse_machine_config(raw: object, home: Path) -> MachineConfig:
    """Validates a config object; ``~`` in the store path becomes ``home``."""
    fields = Fields(raw, CONFIG_FILE_NAME)
    version = fields.integer("version")
    if version > KNOWN_CONFIG_VERSION:
        raise FormatTooNewError(CONFIG_FILE_NAME, version, KNOWN_CONFIG_VERSION)
    fields.reject_unknown(
        ("version", "machine_id", "store", "calendar", "executables", "curation", "distillate", "addons")
    )
    return MachineConfig(
        version=version,
        machine_id=fields.string("machine_id"),
        store=_store_location(fields.section("store"), home),
        calendar=_calendar(fields.section("calendar", required=False)),
        executables=_executables(fields.section("executables", required=False)),
        curation=_curation(fields.section("curation", required=False)),
        distillate=_distillate(fields.section("distillate", required=False), home),
        addons=_addons(fields.section("addons", required=False)),
    )


def _store_location(fields: Fields, home: Path) -> StoreLocation:
    fields.reject_unknown(("backend", "path"))
    written = fields.string("path")
    path = expand(written, home)
    if not path.is_absolute():
        raise fields.error("path", f"must be absolute or start with ~/, got {written!r}")
    return StoreLocation(backend=fields.choice("backend", STORE_BACKENDS), path=path)


def _calendar(fields: Fields) -> CalendarSettings:
    fields.reject_unknown(("backend", "timeout_seconds"))
    return CalendarSettings(
        backend=fields.choice("backend", CALENDAR_BACKENDS, default="none"),
        timeout_seconds=fields.integer("timeout_seconds", default=DEFAULT_BACKEND_TIMEOUT_SECONDS),
    )


def _executables(fields: Fields) -> Mapping[str, str]:
    fields.reject_unknown(EXECUTABLES)
    return {name: fields.string(name) for name in fields.names()}


def _curation(fields: Fields) -> CurationSettings:
    fields.reject_unknown(("model_timeout_minutes", "model", "max_turns", "max_budget_usd"))
    return CurationSettings(
        model_timeout_minutes=fields.integer("model_timeout_minutes", default=DEFAULT_MODEL_TIMEOUT_MINUTES),
        model=fields.string("model", default=DEFAULT_CURATION_MODEL),
        max_turns=fields.integer("max_turns", default=DEFAULT_MAX_TURNS),
        max_budget_usd=_budget(fields),
    )


def _budget(fields: Fields) -> float | None:
    if not fields.has("max_budget_usd"):
        return None
    value = fields.raw("max_budget_usd")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise fields.error("max_budget_usd", "must be a number of US dollars above 0, like 0.5")
    return float(value)


def _distillate(fields: Fields, home: Path) -> DistillateSettings:
    fields.reject_unknown(("skip_under",))
    folders = []
    for written in fields.strings("skip_under"):
        folder = expand(written, home)
        if not folder.is_absolute():
            raise fields.error("skip_under", f"holds {written!r}; each folder must be absolute or start with ~/")
        folders.append(folder)
    return DistillateSettings(skip_under=tuple(folders))


def _addons(fields: Fields) -> Mapping[str, Mapping[str, Any]]:
    """Each known add-on's object; ``on`` must be a boolean, everything else is the add-on's own.

    The entry of an add-on m2b no longer has is left out unread, settings and all.
    """
    known = addon_names()
    addons = {}
    for name in fields.names():
        if name in REMOVED_ADDONS:
            continue
        if name not in known:
            raise fields.error(name, f"is not a known key; known here: {', '.join(known)}")
        addon = fields.section(name)
        addon.boolean(ON, default=False)
        addons[name] = fields.mapping(name)
    return addons


def load_machine_config(machine: MachinePaths) -> MachineConfig:
    raw = read_json_object(machine.config_file)
    if raw is None:
        raise NotSetUpError(f"no machine config at {machine.config_file}")
    return parse_machine_config(raw, machine.home)


def save_machine_config(machine: MachinePaths, raw: dict[str, Any]) -> None:
    """Writes the config as given, after it passed validation; nothing is written otherwise."""
    parse_machine_config(raw, machine.home)
    write_json_object(machine.config_file, raw, machine.temp_dir)


def set_machine_config_value(machine: MachinePaths, dotted_key: str, value: object) -> None:
    raw = read_json_object(machine.config_file)
    if raw is None:
        raise NotSetUpError(f"no machine config at {machine.config_file}")
    save_machine_config(machine, with_value(raw, dotted_key, value))


def set_addon_on(machine: MachinePaths, name: str, on: bool) -> bool:
    """Turns an add-on on or off and keeps its settings; False when it was so already."""
    raw = _raw_config(machine)
    addons = raw.setdefault("addons", {})
    if not isinstance(addons, dict):
        raise InvalidConfigError(f"{CONFIG_FILE_NAME}: addons is not an object")
    addon = addons.setdefault(name, {})
    if not isinstance(addon, dict):
        raise InvalidConfigError(f"{CONFIG_FILE_NAME}: addons.{name} is not an object")
    if addon.get(ON, False) is on:
        return False
    addon[ON] = on
    save_machine_config(machine, raw)
    return True


def remove_addon_entry(machine: MachinePaths, name: str) -> bool:
    """Deletes an add-on's object from ``addons``, settings and all; False when there was none."""
    raw = _raw_config(machine)
    addons = raw.get("addons")
    if not isinstance(addons, dict) or name not in addons:
        return False
    del addons[name]
    if not addons:
        del raw["addons"]
    save_machine_config(machine, raw)
    return True


def _raw_config(machine: MachinePaths) -> dict[str, Any]:
    raw = read_json_object(machine.config_file)
    if raw is None:
        raise NotSetUpError(f"no machine config at {machine.config_file}")
    parse_machine_config(raw, machine.home)
    return raw
