"""The store settings, ``store.json``: what every machine using the store must agree on."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any

from m2b.config.errors import FormatTooNewError, InvalidConfigError, NotSetUpError
from m2b.config.fields import Fields
from m2b.config.json_file import read_store_json_object, write_store_json_object
from m2b.store.base import Store

STORE_SETTINGS_FILE_NAME = "store.json"
KNOWN_STORE_FORMAT = 2

TASKS_BACKENDS = ("apple-reminders", "markdown")
DEFAULT_TASKS_TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class TasksSettings:
    backend: str
    list_name: str | None
    timeout_seconds: int = DEFAULT_TASKS_TIMEOUT_SECONDS


@dataclass(frozen=True)
class StoreSettings:
    format: int
    tasks: TasksSettings
    curating_machine: str
    journal_since: datetime.date

    @property
    def is_newer_than_known(self) -> bool:
        return self.format > KNOWN_STORE_FORMAT


def parse_store_settings(raw: object) -> StoreSettings:
    """Validates store settings; a newer format is read leniently, so it can still be shown."""
    fields = Fields(raw, STORE_SETTINGS_FILE_NAME)
    store_format = fields.integer("format")
    known_format = store_format <= KNOWN_STORE_FORMAT
    try:
        if known_format:
            fields.reject_unknown(("format", "tasks", "curating_machine", "journal_since"))
        return StoreSettings(
            format=store_format,
            tasks=_tasks(fields.section("tasks"), strict=known_format),
            curating_machine=fields.string("curating_machine"),
            journal_since=_date(fields, "journal_since"),
        )
    except InvalidConfigError as error:
        if known_format:
            raise
        raise FormatTooNewError(f"the store ({STORE_SETTINGS_FILE_NAME})", store_format, KNOWN_STORE_FORMAT) from error


def _tasks(fields: Fields, strict: bool) -> TasksSettings:
    if strict:
        fields.reject_unknown(("backend", "list", "timeout_seconds"))
    backend = fields.choice("backend", TASKS_BACKENDS)
    return TasksSettings(
        backend=backend,
        list_name=fields.string("list") if backend == "apple-reminders" else fields.optional_string("list"),
        timeout_seconds=fields.integer("timeout_seconds", default=DEFAULT_TASKS_TIMEOUT_SECONDS),
    )


def _date(fields: Fields, key: str) -> datetime.date:
    text = fields.string(key)
    try:
        return datetime.date.fromisoformat(text)
    except ValueError as error:
        raise fields.error(key, f"must be a date like 2026-11-06, got {text!r}") from error


CURRENT, NEWER, MIGRATES = "current", "newer", "migrates"


def format_state(settings: StoreSettings) -> str:
    """``newer`` when this m2b is too old for the store, ``migrates`` when the next curation run brings it up."""
    if settings.format > KNOWN_STORE_FORMAT:
        return NEWER
    return MIGRATES if settings.format < KNOWN_STORE_FORMAT else CURRENT


def describe_format(settings: StoreSettings) -> str:
    state = format_state(settings)
    if state == CURRENT:
        return f"format {settings.format}"
    known = f"the store has format {settings.format}, this m2b knows {KNOWN_STORE_FORMAT}"
    if state == NEWER:
        return f"{known}: update m2b on this machine"
    return f"{known}: once {settings.curating_machine} runs this m2b, its next curation run migrates it"


def require_writable(settings: StoreSettings) -> None:
    if settings.is_newer_than_known:
        raise FormatTooNewError(f"the store ({STORE_SETTINGS_FILE_NAME})", settings.format, KNOWN_STORE_FORMAT)


def load_store_settings(store: Store, for_writing: bool = False) -> StoreSettings:
    raw = read_store_json_object(store, STORE_SETTINGS_FILE_NAME)
    if raw is None:
        raise NotSetUpError(f"no {STORE_SETTINGS_FILE_NAME} in the store {store.root}")
    settings = parse_store_settings(raw)
    if for_writing:
        require_writable(settings)
    return settings


def require_store_writable(store: Store) -> None:
    """Refuses any write into a store whose settings come from a newer version."""
    existing = read_store_json_object(store, STORE_SETTINGS_FILE_NAME)
    if existing is not None:
        require_writable(parse_store_settings(existing))


def require_inbox_writable(store: Store) -> None:
    """Refuses a capture only into a store whose settings cannot be read at all.

    ``format`` counts the rules for curated content; the inbox contract (file names, ``created``,
    ``source``) is not among them, so a capture also goes into a store of a newer format.
    """
    existing = read_store_json_object(store, STORE_SETTINGS_FILE_NAME)
    if existing is not None:
        parse_store_settings(existing)


def write_store_format(store: Store, store_format: int) -> StoreSettings:
    """Writes ``format`` into ``store.json`` and leaves every other key as it is; returns the new settings."""
    raw = read_store_json_object(store, STORE_SETTINGS_FILE_NAME)
    if raw is None:
        raise NotSetUpError(f"no {STORE_SETTINGS_FILE_NAME} in the store {store.root}")
    save_store_settings(store, {**raw, "format": store_format})
    return parse_store_settings({**raw, "format": store_format})


def save_store_settings(store: Store, raw: dict[str, Any]) -> None:
    """Writes validated settings, never over settings of a format this version does not know."""
    require_store_writable(store)
    require_writable(parse_store_settings(raw))
    write_store_json_object(store, STORE_SETTINGS_FILE_NAME, raw)
