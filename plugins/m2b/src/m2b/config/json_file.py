"""Reading and writing the JSON config files, and changing one key of them."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from m2b.atomic_file import replace_atomically
from m2b.config.errors import InvalidConfigError
from m2b.store.base import Store


def read_json_object(path: Path) -> dict[str, Any] | None:
    """The file's object, or None when the file does not exist."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as error:
        raise InvalidConfigError(f"{path} cannot be read: {error}") from error
    return parse_json_object(text, str(path))


def read_store_json_object(store: Store, name: str) -> dict[str, Any] | None:
    """A JSON object in the store, read through the store's guard; None when the file does not exist.

    An evicted file raises ``EvictedFileError``: the file is there, it just cannot be read now.
    """
    try:
        data = store.read_bytes(name)
    except FileNotFoundError:
        return None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise InvalidConfigError(f"{name} in the store cannot be read: {error}") from error
    return parse_json_object(text, f"{name} in the store")


def write_store_json_object(store: Store, name: str, data: dict[str, Any]) -> None:
    store.replace(name, _json_bytes(data))


def parse_json_object(text: str, where: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except ValueError as error:
        raise InvalidConfigError(f"{where} is not valid JSON: {error}") from error
    if not isinstance(data, dict):
        raise InvalidConfigError(f"{where} must hold a JSON object")
    return data


def write_json_object(path: Path, data: dict[str, Any], temp_dir: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    replace_atomically(path, _json_bytes(data), temp_dir)


def _json_bytes(data: dict[str, Any]) -> bytes:
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def with_value(data: dict[str, Any], dotted_key: str, value: object) -> dict[str, Any]:
    """A copy of ``data`` with one value set; ``a.b`` creates the object ``a`` when missing."""
    result = json.loads(json.dumps(data))
    *parents, last = dotted_key.split(".")
    target = result
    for part in parents:
        child = target.setdefault(part, {})
        if not isinstance(child, dict):
            raise InvalidConfigError(f"cannot set {dotted_key}: {part} is not an object")
        target = child
    target[last] = value
    return result  # type: ignore[no-any-return]
