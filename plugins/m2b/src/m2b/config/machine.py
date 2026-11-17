"""The machine config, ``config.json``: what this machine uses and how it runs curation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
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

# The keys of the file, each list the one its parser refuses any other key with. The catalog of the
# settings (``config.catalog``) is held to them, so a key added here without an entry there fails
# the tests.
KEYS = (
    "version",
    "machine_id",
    "store",
    "calendar",
    "executables",
    "curation",
    "distillate",
    "capture",
    "band",
    "sessions",
    "addons",
)
STORE_KEYS = ("backend", "path")
CALENDAR_KEYS = ("backend", "timeout_seconds")
CURATION_KEYS = (
    "model_timeout_minutes",
    "model",
    "max_turns",
    "max_budget_usd",
    "read_sessions",
    "git_commit",
    "git_directory",
    "paused",
    "run_after_answers",
)
DISTILLATE_KEYS = ("skip_under",)
CAPTURE_KEYS = ("file_limit_mb",)
# A file captured from a session is copied into the synced store: a scan, a contract, a handbook
# fit, a film does not.
DEFAULT_FILE_LIMIT_MB = 25
BAND_KEYS = ("place", "due_tasks", "topics")
# Where the band stands: above the prompt and always there, at the end of the hint line below the
# prompt, or above the prompt only while it has something to say.
BAND_ABOVE, BAND_BELOW, BAND_WAITING = "above", "below", "waiting"
BAND_PLACES = (BAND_ABOVE, BAND_BELOW, BAND_WAITING)
# Always there: someone who installed m2b and has nothing waiting would otherwise see nothing of it.
DEFAULT_BAND_PLACE = BAND_ABOVE
# How the band shows the owner's tasks due today or overdue: not at all, how many, or the first by name.
DUE_TASKS_OFF, DUE_TASKS_COUNT, DUE_TASKS_LIST = "off", "count", "list"
DUE_TASKS_CHOICES = (DUE_TASKS_OFF, DUE_TASKS_COUNT, DUE_TASKS_LIST)
DEFAULT_DUE_TASKS = DUE_TASKS_COUNT
SESSIONS_KEYS = ("propose",)
# The sections whose keys are each a setting of its own. ``executables`` is one setting, the
# programs it names, and ``addons`` holds one per add-on.
SECTION_KEYS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "store": STORE_KEYS,
        "calendar": CALENDAR_KEYS,
        "curation": CURATION_KEYS,
        "distillate": DISTILLATE_KEYS,
        "capture": CAPTURE_KEYS,
        "band": BAND_KEYS,
        "sessions": SESSIONS_KEYS,
    }
)
ADDONS_KEY = "addons"


def setting_keys() -> tuple[str, ...]:
    """Every setting of the file by its dotted key: ``machine_id``, ``curation.paused``, ``addons.worklog``."""
    keys: list[str] = []
    for key in KEYS:
        if key in SECTION_KEYS:
            keys.extend(f"{key}.{name}" for name in SECTION_KEYS[key])
        elif key == ADDONS_KEY:
            keys.extend(f"{key}.{name}" for name in addon_names())
        else:
            keys.append(key)
    return tuple(keys)


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
    # Whether a run reads what the person typed in Claude Code on this machine and proposes from it
    # (``curate.glean_step``). Off until setup asked: the transcripts hold every project's sessions.
    read_sessions: bool = False
    # Whether a run is committed when the store folder is the top of a git work tree
    # (``curate.run_commit``). On, because the repository is the owner's own doing; this is the way
    # to keep one there and say no.
    git_commit: bool = True
    # The git directory a run commits into when the store folder's ``.git`` is a file that points
    # at one kept elsewhere, absolute after loading. The store can be written from other devices
    # and this file cannot, so the directory is named here; unset, a run commits only into a
    # ``.git`` folder of the store itself.
    git_directory: Path | None = None
    # Whether this machine starts no run by itself: none at a session start, none from a schedule.
    # A run asked for by hand (``m2b curate --force``) still runs, so the owner can pause the
    # background work and file the inbox when it suits.
    paused: bool = False
    # Whether this machine starts a run once every proposal that waited is answered and one is
    # kept (``curate.detach``), so what the owner keeps reaches the memory without a second step.
    # Such a run is started by an answer, not asked for by hand: a paused machine starts none.
    run_after_answers: bool = True


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
class CaptureSettings:
    # The largest file `m2b capture-file` copies into the inbox, in megabytes.
    file_limit_mb: int = DEFAULT_FILE_LIMIT_MB


@dataclass(frozen=True)
class BandSettings:
    # One of BAND_PLACES.
    place: str = DEFAULT_BAND_PLACE
    # One of DUE_TASKS_CHOICES. The pane lists the tasks whatever this says.
    due_tasks: str = DEFAULT_DUE_TASKS
    # Whether the band names how many topics m2b gave the session.
    topics: bool = False


@dataclass(frozen=True)
class SessionsSettings:
    # Whether a session on this machine may hand in a proposal for the memory by itself. Off until
    # the owner turns it on: with it, words from what an agent read, a mail or a document, reach
    # the store.
    propose: bool = False


@dataclass(frozen=True)
class MachineConfig:
    version: int
    machine_id: str
    store: StoreLocation
    calendar: CalendarSettings
    executables: Mapping[str, str]
    curation: CurationSettings
    distillate: DistillateSettings = field(default_factory=DistillateSettings)
    capture: CaptureSettings = field(default_factory=CaptureSettings)
    band: BandSettings = field(default_factory=BandSettings)
    sessions: SessionsSettings = field(default_factory=SessionsSettings)
    # Each add-on's settings as written, ``on`` included; ``m2b.addons.is_on`` reads them.
    addons: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)


def parse_machine_config(raw: object, home: Path) -> MachineConfig:
    """Validates a config object; ``~`` in the store path becomes ``home``."""
    fields = Fields(raw, CONFIG_FILE_NAME)
    version = fields.integer("version")
    if version > KNOWN_CONFIG_VERSION:
        raise FormatTooNewError(CONFIG_FILE_NAME, version, KNOWN_CONFIG_VERSION)
    fields.reject_unknown(KEYS)
    return MachineConfig(
        version=version,
        machine_id=fields.string("machine_id"),
        store=_store_location(fields.section("store"), home),
        calendar=_calendar(fields.section("calendar", required=False)),
        executables=_executables(fields.section("executables", required=False)),
        curation=_curation(fields.section("curation", required=False), home),
        distillate=_distillate(fields.section("distillate", required=False), home),
        capture=_capture(fields.section("capture", required=False)),
        band=_band(fields.section("band", required=False)),
        sessions=_sessions(fields.section("sessions", required=False)),
        addons=_addons(fields.section("addons", required=False)),
    )


def _store_location(fields: Fields, home: Path) -> StoreLocation:
    fields.reject_unknown(SECTION_KEYS["store"])
    written = fields.string("path")
    path = expand(written, home)
    if not path.is_absolute():
        raise fields.error("path", f"must be absolute or start with ~/, got {written!r}")
    return StoreLocation(backend=fields.choice("backend", STORE_BACKENDS), path=path)


def _calendar(fields: Fields) -> CalendarSettings:
    fields.reject_unknown(SECTION_KEYS["calendar"])
    return CalendarSettings(
        backend=fields.choice("backend", CALENDAR_BACKENDS, default="none"),
        timeout_seconds=fields.integer("timeout_seconds", default=DEFAULT_BACKEND_TIMEOUT_SECONDS),
    )


def _executables(fields: Fields) -> Mapping[str, str]:
    fields.reject_unknown(EXECUTABLES)
    return {name: fields.string(name) for name in fields.names()}


def _curation(fields: Fields, home: Path) -> CurationSettings:
    fields.reject_unknown(SECTION_KEYS["curation"])
    return CurationSettings(
        model_timeout_minutes=fields.integer("model_timeout_minutes", default=DEFAULT_MODEL_TIMEOUT_MINUTES),
        model=fields.string("model", default=DEFAULT_CURATION_MODEL),
        max_turns=fields.integer("max_turns", default=DEFAULT_MAX_TURNS),
        max_budget_usd=_budget(fields),
        read_sessions=fields.boolean("read_sessions", default=False),
        git_commit=fields.boolean("git_commit", default=True),
        git_directory=_git_directory(fields, home),
        paused=fields.boolean("paused", default=False),
        run_after_answers=fields.boolean("run_after_answers", default=True),
    )


def _git_directory(fields: Fields, home: Path) -> Path | None:
    if not fields.has("git_directory"):
        return None
    written = fields.string("git_directory")
    directory = expand(written, home)
    if not directory.is_absolute():
        raise fields.error("git_directory", f"must be absolute or start with ~/, got {written!r}")
    return directory


def _budget(fields: Fields) -> float | None:
    if not fields.has("max_budget_usd"):
        return None
    value = fields.raw("max_budget_usd")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise fields.error("max_budget_usd", "must be a number of US dollars above 0, like 0.5")
    return float(value)


def _distillate(fields: Fields, home: Path) -> DistillateSettings:
    fields.reject_unknown(SECTION_KEYS["distillate"])
    folders = []
    for written in fields.strings("skip_under"):
        folder = expand(written, home)
        if not folder.is_absolute():
            raise fields.error("skip_under", f"holds {written!r}; each folder must be absolute or start with ~/")
        folders.append(folder)
    return DistillateSettings(skip_under=tuple(folders))


def _capture(fields: Fields) -> CaptureSettings:
    fields.reject_unknown(SECTION_KEYS["capture"])
    return CaptureSettings(file_limit_mb=fields.integer("file_limit_mb", default=DEFAULT_FILE_LIMIT_MB))


def _band(fields: Fields) -> BandSettings:
    fields.reject_unknown(SECTION_KEYS["band"])
    return BandSettings(
        place=fields.choice("place", BAND_PLACES, default=DEFAULT_BAND_PLACE),
        due_tasks=_due_tasks(fields),
        topics=fields.boolean("topics", default=False),
    )


def _due_tasks(fields: Fields) -> str:
    """How the band shows the tasks due. A config written while this was on or off holds true or
    false: on drew the tasks by name, so it reads as the list."""
    if not fields.has("due_tasks"):
        return DEFAULT_DUE_TASKS
    written = fields.raw("due_tasks")
    if isinstance(written, bool):
        return DUE_TASKS_LIST if written else DUE_TASKS_OFF
    return fields.choice("due_tasks", DUE_TASKS_CHOICES)


def _sessions(fields: Fields) -> SessionsSettings:
    fields.reject_unknown(SECTION_KEYS["sessions"])
    return SessionsSettings(propose=fields.boolean("propose", default=False))


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
