"""The owner's profile, ``profile.json`` in the store: who the owner is and which spheres of work exist.

Client commands work without a profile; curation and the worklog need one. Setup and the
module setups each contribute part of it, so writes merge instead of replacing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from m2b import locale
from m2b.config.errors import FormatTooNewError, InvalidConfigError, NotSetUpError
from m2b.config.fields import Fields
from m2b.config.json_file import read_store_json_object, with_value, write_store_json_object
from m2b.config.store_settings import require_store_writable
from m2b.paths import expand
from m2b.store.base import Store

PROFILE_FILE_NAME = "profile.json"
KNOWN_PROFILE_VERSION = 2
# Version 2 added ``worklog_leave_out``. A profile is written as version 2 only once it holds that
# key: an m2b from before it refuses a version 1 profile with a key it does not know, also when
# reading, and would stop curating; a version 2 profile it reads without the key and does not write.
PLAIN_PROFILE_VERSION = 1
ADDED_IN_VERSION_TWO = "worklog_leave_out"

_SPHERE_ID = re.compile(r"[a-z][a-z0-9-]*\Z")


def _under_home(paths: tuple[str, ...], home: Path) -> tuple[Path, ...]:
    return tuple(expand(path if path.startswith("~") else f"~/{path}", home) for path in paths)


@dataclass(frozen=True)
class SphereMatch:
    git_remote_contains: tuple[str, ...] = ()
    path_under: tuple[str, ...] = ()

    def folders(self, home: Path) -> tuple[Path, ...]:
        """The sphere's folders on a machine whose home folder is ``home``."""
        return _under_home(self.path_under, home)


@dataclass(frozen=True)
class Sphere:
    id: str
    label: str | None = None
    billable: bool = False
    default: bool = False
    match: SphereMatch = SphereMatch()


@dataclass(frozen=True)
class WorklogLeaveOut:
    """Folders under the home folder whose sessions m2b reads nowhere: the worklog add-on leaves them
    out of the worklog, and a curation run that reads the sessions leaves them out too.

    It has the shape of the key in the file, because ``m2b profile get --json`` prints the profile
    from here and the add-on reads that answer.
    """

    path_under: tuple[str, ...] = ()

    def folders(self, home: Path) -> tuple[Path, ...]:
        """The folders on a machine whose home folder is ``home``."""
        return _under_home(self.path_under, home)


@dataclass(frozen=True)
class Profile:
    version: int
    owner: str
    language: str
    spheres: tuple[Sphere, ...]
    customers: tuple[str, ...]
    worklog_leave_out: WorklogLeaveOut = WorklogLeaveOut()


def parse_profile(raw: object, for_writing: bool = True) -> Profile:
    """Validates a profile.

    Machines sharing a store can run different versions, so reading is lenient: a newer
    version is read without the keys it added, and a language without a locale on this
    machine reads as English. Writing accepts only what this version knows.
    """
    fields = Fields(raw, PROFILE_FILE_NAME)
    version = fields.integer("version")
    newer = version > KNOWN_PROFILE_VERSION
    if newer and for_writing:
        raise FormatTooNewError(PROFILE_FILE_NAME, version, KNOWN_PROFILE_VERSION)
    try:
        return _profile(fields, version, strict_keys=not newer, strict_language=for_writing)
    except InvalidConfigError as error:
        if not newer:
            raise
        raise FormatTooNewError(PROFILE_FILE_NAME, version, KNOWN_PROFILE_VERSION) from error


def _profile(fields: Fields, version: int, strict_keys: bool, strict_language: bool) -> Profile:
    if strict_keys:
        fields.reject_unknown(("version", "owner", "language", "spheres", "customers", ADDED_IN_VERSION_TWO))
    spheres = tuple(_sphere(sphere, strict_keys) for sphere in fields.items("spheres"))
    _check_spheres(spheres)
    return Profile(
        version=version,
        owner=fields.string("owner"),
        language=_language(fields, strict_language),
        spheres=spheres,
        customers=fields.strings("customers"),
        worklog_leave_out=_left_out(fields.section(ADDED_IN_VERSION_TWO, required=False), strict_keys),
    )


def _left_out(left_out: Fields, strict_keys: bool) -> WorklogLeaveOut:
    if strict_keys:
        left_out.reject_unknown(("path_under",))
    return WorklogLeaveOut(_paths_under(left_out))


def _language(fields: Fields, strict: bool) -> str:
    available = locale.available_languages()
    if strict:
        return fields.choice("language", available, default=locale.DEFAULT_LANGUAGE)
    language = fields.string("language", default=locale.DEFAULT_LANGUAGE)
    return language if language in available else locale.DEFAULT_LANGUAGE


def _sphere(fields: Fields, strict_keys: bool) -> Sphere:
    if strict_keys:
        fields.reject_unknown(("id", "label", "billable", "default", "match"))
    sphere_id = fields.string("id")
    if not _SPHERE_ID.match(sphere_id):
        raise fields.error("id", f"is {sphere_id!r}; use lowercase letters, digits and dashes, like acme-ltd")
    return Sphere(
        id=sphere_id,
        label=fields.optional_string("label"),
        billable=fields.boolean("billable", default=False),
        default=fields.boolean("default", default=False),
        match=_match(fields.section("match", required=False), strict_keys),
    )


def _match(match: Fields, strict_keys: bool) -> SphereMatch:
    if strict_keys:
        match.reject_unknown(("git_remote_contains", "path_under"))
    return SphereMatch(git_remote_contains=match.strings("git_remote_contains"), path_under=_paths_under(match))


def _paths_under(section: Fields) -> tuple[str, ...]:
    """Folders written relative to the home folder, which each machine sharing the store has its own."""
    path_under = section.strings("path_under")
    for path in path_under:
        if path.startswith("/") or (path.startswith("~") and path != "~" and not path.startswith("~/")):
            raise section.error("path_under", f"holds {path!r}; write it relative to the home folder, like ~/code/acme")
    return path_under


def _check_spheres(spheres: tuple[Sphere, ...]) -> None:
    ids = [sphere.id for sphere in spheres]
    duplicates = sorted({sphere_id for sphere_id in ids if ids.count(sphere_id) > 1})
    if duplicates:
        raise InvalidConfigError(f"{PROFILE_FILE_NAME}: spheres has the id {', '.join(duplicates)} more than once")
    if sum(sphere.default for sphere in spheres) > 1:
        raise InvalidConfigError(f"{PROFILE_FILE_NAME}: spheres has more than one default sphere")


def language_for_clients(profile: Profile | None) -> str:
    return profile.language if profile is not None else locale.DEFAULT_LANGUAGE


def merge_profile(current: dict[str, Any] | None, patch: dict[str, Any]) -> dict[str, Any]:
    """Spheres merge by id, customers are added once, every other key of ``patch`` replaces."""
    merged: dict[str, Any] = json.loads(json.dumps(current)) if current else {"version": PLAIN_PROFILE_VERSION}
    for key, value in json.loads(json.dumps(patch)).items():
        existing = merged.get(key, [])
        if key in ("spheres", "customers") and not isinstance(existing, list):
            # Left as it is, so that validation refuses the broken file instead of losing data.
            continue
        if key == "spheres" and isinstance(value, list):
            merged[key] = _merge_spheres(existing, value)
        elif key == "customers" and isinstance(value, list):
            customers = list(existing)
            for name in value:
                if name not in customers:
                    customers.append(name)
            merged[key] = customers
        else:
            merged[key] = value
    return merged


def _merge_spheres(existing: list[Any], added: list[Any]) -> list[Any]:
    result = list(existing)
    positions = {sphere.get("id"): index for index, sphere in enumerate(result) if isinstance(sphere, dict)}
    for sphere in added:
        sphere_id = sphere.get("id") if isinstance(sphere, dict) else None
        if sphere_id in positions:
            result[positions[sphere_id]] = sphere
        else:
            result.append(sphere)
    return result


def load_profile(store: Store) -> Profile | None:
    """The profile, or None when the store has none yet."""
    raw = read_store_json_object(store, PROFILE_FILE_NAME)
    return parse_profile(raw, for_writing=False) if raw is not None else None


def require_profile(store: Store) -> Profile:
    """The profile for curation and the worklog, which cannot run without one."""
    loaded = load_profile(store)
    if loaded is None:
        raise NotSetUpError(f"no {PROFILE_FILE_NAME} in the store {store.root}")
    return loaded


def save_profile(store: Store, raw: dict[str, Any]) -> None:
    """Writes a validated profile into a store whose format this version knows."""
    require_store_writable(store)
    if ADDED_IN_VERSION_TWO in raw and raw.get("version") == PLAIN_PROFILE_VERSION:
        raw = {**raw, "version": KNOWN_PROFILE_VERSION}
    parse_profile(raw)
    write_store_json_object(store, PROFILE_FILE_NAME, raw)


def merge_into_profile(store: Store, patch: dict[str, Any]) -> None:
    save_profile(store, merge_profile(read_store_json_object(store, PROFILE_FILE_NAME), patch))


def set_profile_value(store: Store, dotted_key: str, value: object) -> None:
    raw = read_store_json_object(store, PROFILE_FILE_NAME)
    if raw is None:
        raise NotSetUpError(f"no {PROFILE_FILE_NAME} in the store {store.root}")
    save_profile(store, with_value(raw, dotted_key, value))
