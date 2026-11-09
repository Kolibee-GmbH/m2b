"""Setting a machine up: a new store from nothing, or joining one that exists (B37).

``inspect`` downloads what a store already holds and shows it, so the setup skill asks only what is
missing. ``apply`` takes the answers and writes, in this order: nothing until every file it needs
from the store is downloaded; then the machine config, ``store.json``, ``profile.json``, the folders,
``MEMORY.md`` with its two sections, ``STORE.md`` and the launcher. Each file is written only when
its content changes, so running setup again with the same answers changes no file, and a file
that exists is changed only when the user gave a different answer. ``MEMORY.md`` is never written
over. A machine that answers "curates" while ``store.json`` names another one is not named: moving
curation is ``m2b curate take-over``, an explicit step, so two machines never curate one store.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import secrets
import shutil
import socket
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from m2b import hooks, launcher
from m2b.addons import ADDONS, is_on
from m2b.config import store_path
from m2b.config.errors import ConfigError, InvalidConfigError
from m2b.config.json_file import read_json_object, read_store_json_object
from m2b.config.machine import (
    CALENDAR_BACKENDS,
    CURATION_MODELS,
    STORE_BACKENDS,
    StoreLocation,
    parse_machine_config,
    save_machine_config,
)
from m2b.config.profile import PROFILE_FILE_NAME, parse_profile, save_profile
from m2b.config.store_settings import (
    KNOWN_STORE_FORMAT,
    STORE_SETTINGS_FILE_NAME,
    TASKS_BACKENDS,
    StoreSettings,
    parse_store_settings,
    require_writable,
    save_store_settings,
)
from m2b.notes.layout import CORPUS, INBOX, MEMORY, MEMORY_INDEX, STATE, STORE_CONTRACT, TASKS
from m2b.notes.memory_index import CURRENT_HEADING, FACTS_HEADING
from m2b.paths import MachinePaths, expand
from m2b.store.base import DEFAULT_FETCH_TIMEOUT_SECONDS, Store
from m2b.store.factory import open_store

FETCH_TIMEOUT_SECONDS: float = DEFAULT_FETCH_TIMEOUT_SECONDS
MEMORY_INDEX_PATH = f"{MEMORY}/{MEMORY_INDEX}"
# What a joining machine must see before it decides anything. ``memory`` as the folder: an evicted
# folder stands for everything in it, so a file path below it would not be seen and not downloaded.
EXISTING = (STORE_SETTINGS_FILE_NAME, PROFILE_FILE_NAME, MEMORY, STORE_CONTRACT)
APPLE_CALENDAR = "apple-calendar"
APPLE_REMINDERS = "apple-reminders"


class SetupError(ConfigError):
    """The answers do not make a setup: a value is missing or does not fit."""


@dataclass(frozen=True)
class Answers:
    store: StoreLocation
    curates: bool
    machine_id: str | None = None
    calendar: str | None = None
    tasks: Mapping[str, Any] | None = None
    owner: str | None = None
    language: str | None = None
    executables: Mapping[str, str] = field(default_factory=dict)
    # Only for a folder store: create the folder when it is missing (the first run without
    # configuration). Without it a missing folder is refused, so a typo never becomes a store.
    create_store: bool = False
    # Only when the owner chose one; without it the recorded model, or the default, stays.
    curation_model: str | None = None


@dataclass
class SetupResult:
    written: list[str] = field(default_factory=list)
    machine_id: str = ""
    curating_machine: str = ""
    take_over: str | None = None
    missing_executables: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    # Each add-on with whether it is on here; setup offers the ones that are off.
    addons: list[dict[str, Any]] = field(default_factory=list)


def parse_answers(raw: object, home: Path) -> Answers:
    if not isinstance(raw, dict):
        raise SetupError("the answers must be a JSON object")
    store = raw.get("store")
    if (
        not isinstance(store, dict)
        or not isinstance(store.get("path"), str)
        or store.get("backend") not in STORE_BACKENDS
    ):
        raise SetupError(f'store must be {{"backend": one of {", ".join(STORE_BACKENDS)}, "path": "..."}}')
    path = expand(store["path"], home)
    if not path.is_absolute():
        raise SetupError(f"the store path must be absolute or start with ~/, got {store['path']!r}")
    create = store.get("create", False)
    if not isinstance(create, bool) or (create and store["backend"] != "folder"):
        raise SetupError("store.create is true or false, and only a folder store is created")
    if not isinstance(raw.get("curates"), bool):
        raise SetupError("curates must be true or false: does this machine curate the store?")
    unusable = store_path.problem(path) if raw["curates"] else None
    if unusable is not None:
        raise SetupError(unusable)
    calendar = raw.get("calendar")
    if calendar is not None and calendar not in CALENDAR_BACKENDS:
        raise SetupError(f"calendar must be one of {', '.join(CALENDAR_BACKENDS)}")
    tasks = raw.get("tasks")
    if tasks is not None and (not isinstance(tasks, dict) or tasks.get("backend") not in TASKS_BACKENDS):
        raise SetupError(f'tasks must be {{"backend": one of {", ".join(TASKS_BACKENDS)}, "list": "..."}}')
    curation_model = raw.get("curation_model")
    if curation_model is not None and curation_model not in CURATION_MODELS:
        raise SetupError(f"curation_model must be one of {', '.join(CURATION_MODELS)}")
    executables = raw.get("executables") or {}
    if not isinstance(executables, dict) or not all(isinstance(value, str) for value in executables.values()):
        raise SetupError("executables must map names to absolute paths")
    return Answers(
        store=StoreLocation(store["backend"], path),
        curates=raw["curates"],
        machine_id=_optional_text(raw, "machine_id"),
        calendar=calendar,
        tasks=tasks,
        owner=_optional_text(raw, "owner"),
        language=_optional_text(raw, "language"),
        executables=executables,
        create_store=create,
        curation_model=curation_model,
    )


def _optional_text(raw: Mapping[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SetupError(f"{key} must be a text")
    return value.strip()


def inspect(machine: MachinePaths, location: StoreLocation | None) -> dict[str, Any]:
    """What the machine and the store hold already, after downloading the store's own files.

    The setup skill starts here on a new machine, so its two first answers are data, not errors: no
    machine config and no store named gives ``"store": null``, and a store folder that does not
    exist yet in a folder that does (the quick start's ``~/m2b``) gives ``"store_exists": false``.
    A folder whose parent is missing too may be a volume that is not mounted, and stays unreachable.
    ``store_path_problem`` says why a curating machine could not use the path, before the interview.
    """
    config = read_json_object(machine.config_file)
    if location is None:
        if config is None:
            return _nothing_there(None, config)
        location = parse_machine_config(config, machine.home).store
    if not location.path.exists() and location.path.parent.is_dir():
        return _nothing_there(location, config)
    store = open_store(location, machine.temp_dir)
    store.fetch(EXISTING, FETCH_TIMEOUT_SECONDS)
    return {
        "store": {"backend": location.backend, "path": str(location.path)},
        "store_path_problem": store_path.problem(location.path),
        "store_exists": True,
        "store_settings": read_store_json_object(store, STORE_SETTINGS_FILE_NAME),
        "profile": read_store_json_object(store, PROFILE_FILE_NAME),
        "distillate": store.exists(MEMORY_INDEX_PATH),
        "machine_config": config,
    }


def _nothing_there(location: StoreLocation | None, config: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "store": {"backend": location.backend, "path": str(location.path)} if location is not None else None,
        "store_path_problem": store_path.problem(location.path) if location is not None else None,
        "store_exists": False,
        "store_settings": None,
        "profile": None,
        "distillate": False,
        "machine_config": config,
    }


def apply(machine: MachinePaths, answers: Answers, environ: Mapping[str, str], today: datetime.date) -> SetupResult:
    created = _create_store_folder(answers) if answers.create_store else False
    try:
        return _apply(machine, answers, environ, today)
    except BaseException:
        if created:
            # Only the empty folder this call made; anything written into it stays.
            with contextlib.suppress(OSError):
                answers.store.path.rmdir()
        raise


def _create_store_folder(answers: Answers) -> bool:
    """Makes the folder of a quick start; True when this call made it.

    A folder that exists is used only when it is empty or holds a store already, so a folder that
    holds other files never becomes a store without the owner naming it.
    """
    folder = answers.store.path
    if folder.exists():
        if folder.is_dir() and (not any(folder.iterdir()) or (folder / STORE_SETTINGS_FILE_NAME).exists()):
            return False
        raise SetupError(f"{folder} exists and holds files that are no m2b store; name another folder")
    if not folder.parent.is_dir():
        raise SetupError(f"{folder.parent} does not exist, so the store folder is not created")
    folder.mkdir()
    return True


def _apply(machine: MachinePaths, answers: Answers, environ: Mapping[str, str], today: datetime.date) -> SetupResult:
    store = open_store(answers.store, machine.temp_dir)
    store.fetch(EXISTING, FETCH_TIMEOUT_SECONDS)
    result = SetupResult()

    existing_config = read_json_object(machine.config_file)
    existing_settings = read_store_json_object(store, STORE_SETTINGS_FILE_NAME)
    tasks_backend: object = None
    if answers.tasks is not None:
        tasks_backend = answers.tasks.get("backend")
    elif existing_settings is not None:
        tasks_backend = parse_store_settings(existing_settings).tasks.backend
    config_raw = _machine_config(existing_config, answers, tasks_backend, environ, result)
    result.machine_id = config_raw["machine_id"]
    settings_raw = _store_settings(store, answers, result.machine_id, today, result)
    profile_raw = _profile(store, answers)

    # Everything is checked before the first write, so a wrong answer writes nothing.
    parse_machine_config(config_raw, machine.home)
    if settings_raw is not None:
        require_writable(parse_store_settings(settings_raw))
    if profile_raw is not None:
        parse_profile(profile_raw)

    if config_raw != existing_config:
        save_machine_config(machine, config_raw)
        result.written.append(str(machine.config_file))
    if settings_raw is not None:
        save_store_settings(store, settings_raw)
        result.written.append(STORE_SETTINGS_FILE_NAME)
    if profile_raw is not None:
        save_profile(store, profile_raw)
        result.written.append(PROFILE_FILE_NAME)
    settings = parse_store_settings(read_store_json_object(store, STORE_SETTINGS_FILE_NAME))
    result.curating_machine = settings.curating_machine
    _layout(store, settings.tasks.backend)
    if not store.exists(MEMORY_INDEX_PATH):
        store.create_exclusive(MEMORY_INDEX_PATH, f"# Memory\n\n{FACTS_HEADING}\n\n{CURRENT_HEADING}\n".encode())
        result.written.append(MEMORY_INDEX_PATH)
    if settings_raw is not None or not store.exists(STORE_CONTRACT):
        write_store_contract(store, settings)
        result.written.append(STORE_CONTRACT)
    _launcher(machine, config_raw, environ, result)
    configured = parse_machine_config(config_raw, machine.home).addons
    result.addons = [
        {"name": addon.name, "on": is_on(configured, addon.name), "summary": addon.summary} for addon in ADDONS
    ]
    return result


def _machine_config(
    existing: dict[str, Any] | None,
    answers: Answers,
    tasks_backend: object,
    environ: Mapping[str, str],
    result: SetupResult,
) -> dict[str, Any]:
    """The machine config with this store; a path recorded before wins unless an answer names another."""
    raw: dict[str, Any] = json.loads(json.dumps(existing)) if existing else {"version": 1}
    raw["machine_id"] = raw.get("machine_id") or answers.machine_id or _new_machine_id()
    raw["store"] = {"backend": answers.store.backend, "path": str(answers.store.path)}
    calendar = dict(raw.get("calendar") or {})
    calendar["backend"] = answers.calendar or calendar.get("backend") or "none"
    raw["calendar"] = calendar
    executables = dict(raw.get("executables") or {})
    wanted = {"python3": sys.executable, "claude": None}
    if tasks_backend == APPLE_REMINDERS:
        wanted["reminders"] = None
    if calendar["backend"] == APPLE_CALENDAR:
        wanted["osascript"] = None
    for name, known in wanted.items():
        found = (
            answers.executables.get(name)
            or executables.get(name)
            or known
            or shutil.which(name, path=environ.get("PATH"))
        )
        if found:
            executables[name] = found
        elif name not in executables:
            result.missing_executables.append(name)
    raw["executables"] = executables
    if answers.curation_model is not None:
        raw["curation"] = {**(raw.get("curation") or {}), "model": answers.curation_model}
    return raw


def _new_machine_id() -> str:
    host = "".join(character for character in socket.gethostname().split(".")[0].lower() if character.isalnum())
    return f"{secrets.token_hex(2)}-{host or 'machine'}"


def _store_settings(
    store: Store, answers: Answers, machine_id: str, today: datetime.date, result: SetupResult
) -> dict[str, Any] | None:
    """The new ``store.json``, or None when it stays as it is."""
    existing = read_store_json_object(store, STORE_SETTINGS_FILE_NAME)
    if existing is None:
        if not answers.curates:
            raise SetupError(
                "a new store needs a curating machine: answer curates true here, "
                "or set the store up on the machine that curates"
            )
        if answers.tasks is None:
            raise SetupError("a new store needs the tasks backend and, for apple-reminders, its list")
        return {
            "format": KNOWN_STORE_FORMAT,
            "tasks": dict(answers.tasks),
            "curating_machine": machine_id,
            "journal_since": today.isoformat(),
        }
    current = parse_store_settings(existing)
    require_writable(current)
    if answers.curates and current.curating_machine != machine_id:
        result.take_over = (
            f"{current.curating_machine} curates this store. To move curation here, run m2b curate take-over "
            "on this machine; setup did not change it."
        )
    if answers.tasks is None:
        return None
    tasks = {**existing.get("tasks", {}), **answers.tasks}
    if tasks == existing.get("tasks"):
        return None
    return {**existing, "tasks": tasks}


def _profile(store: Store, answers: Answers) -> dict[str, Any] | None:
    """The new ``profile.json``, or None when it stays as it is."""
    existing = read_store_json_object(store, PROFILE_FILE_NAME)
    if existing is None:
        if answers.owner is None:
            raise SetupError("a new store needs the owner's name")
        return {"version": 1, "owner": answers.owner, "language": answers.language or "en"}
    changed = dict(existing)
    if answers.owner is not None:
        changed["owner"] = answers.owner
    if answers.language is not None:
        changed["language"] = answers.language
    return changed if changed != existing else None


def _layout(store: Store, tasks_backend: str) -> None:
    folders = [INBOX, CORPUS, MEMORY, f"{STATE}/core"]
    if tasks_backend == "markdown":
        folders.append(TASKS)
    for folder in folders:
        store.path(folder).mkdir(parents=True, exist_ok=True)


def _launcher(
    machine: MachinePaths, config_raw: dict[str, Any], environ: Mapping[str, str], result: SetupResult
) -> None:
    before = launcher.installed_launcher_version(machine)
    try:
        hooks.launcher_check(parse_machine_config(config_raw, machine.home), machine, environ)
    except launcher.LauncherError as error:
        result.problems.append(str(error))
        return
    if launcher.installed_launcher_version(machine) != before:
        result.written.append(str(machine.launcher))


def write_store_contract(store: Store, settings: StoreSettings) -> None:
    """Writes ``STORE.md`` from the settings, so it names the format a migration just wrote."""
    contract = store_contract(settings.format, settings.tasks.backend, settings.tasks.list_name)
    store.replace(STORE_CONTRACT, contract.encode("utf-8"))


def store_contract(store_format: int, tasks_backend: str, tasks_list: str | None) -> str:
    """``STORE.md``: what an integration may do in this store, from ``store.json``."""
    if tasks_backend == APPLE_REMINDERS:
        tasks = f'Apple Reminders, the list "{tasks_list}"'
    else:
        tasks = f"one Markdown file per task in `{TASKS}/`"
    return f"""# m2b store

This folder is an m2b store, format {store_format}. It is written by the m2b plugin for Claude Code;
this file is generated from `store.json` and says what anything else may do here.

- `{INBOX}/`: new captures. Create a new file, never change one: a name like
  `20261107T091500Z-<source>-<4 hex>.md`, time in UTC, a frontmatter block with `created` (with
  offset) and `source` (your own lowercase name), then the text.
- Tasks: {tasks}.
- `{CORPUS}/`, `{MEMORY}/`, `profile.json`: read only.
- `{STATE}/integrations/<your name>/`: your own state.

Never move, rename, edit or delete anything else. Only the curating machine curates.
"""


def answers_from_text(text: str, home: Path) -> Answers:
    try:
        raw = json.loads(text)
    except ValueError as error:
        raise InvalidConfigError(f"the answers are not valid JSON: {error}") from error
    return parse_answers(raw, home)
