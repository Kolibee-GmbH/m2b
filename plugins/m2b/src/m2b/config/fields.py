"""A small hand-written validator for JSON objects; every error names the key path."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from typing import Any

from m2b.config.errors import InvalidConfigError


class Fields:
    """Typed access to one JSON object, reporting errors as ``<file>: <key path> ...``."""

    def __init__(self, data: object, file_name: str, key_path: str = "") -> None:
        if not isinstance(data, dict):
            where = key_path or "the top level"
            raise InvalidConfigError(f"{file_name}: {where} must be an object, got {_describe(data)}")
        self._data: dict[str, Any] = data
        self._file_name = file_name
        self._key_path = key_path

    def path_of(self, key: str) -> str:
        return f"{self._key_path}.{key}" if self._key_path else key

    def error(self, key: str, problem: str) -> InvalidConfigError:
        return InvalidConfigError(f"{self._file_name}: {self.path_of(key)} {problem}")

    def has(self, key: str) -> bool:
        return key in self._data

    def raw(self, key: str) -> Any:
        if key not in self._data:
            raise self.error(key, "is missing")
        return self._data[key]

    def string(self, key: str, default: str | None = None) -> str:
        if key not in self._data and default is not None:
            return default
        value: object = self.raw(key)
        if not isinstance(value, str) or not value:
            raise self.error(key, f"must be a non-empty string, got {_describe(value)}")
        return value

    def optional_string(self, key: str) -> str | None:
        return self.string(key) if key in self._data else None

    def choice(self, key: str, allowed: Collection[str], default: str | None = None) -> str:
        value = self.string(key, default)
        if value not in allowed:
            raise self.error(key, f"is {value!r}; allowed: {', '.join(allowed)}")
        return value

    def integer(self, key: str, default: int | None = None, minimum: int = 1) -> int:
        if key not in self._data and default is not None:
            return default
        value: object = self.raw(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise self.error(key, f"must be a whole number of at least {minimum}, got {_describe(value)}")
        return value

    def boolean(self, key: str, default: bool) -> bool:
        if key not in self._data:
            return default
        value: object = self.raw(key)
        if not isinstance(value, bool):
            raise self.error(key, f"must be true or false, got {_describe(value)}")
        return value

    def strings(self, key: str, allow_empty: bool = True) -> tuple[str, ...]:
        if key not in self._data:
            return ()
        value: object = self.raw(key)
        if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
            raise self.error(key, f"must be a list of non-empty strings, got {_describe(value)}")
        if not value and not allow_empty:
            raise self.error(key, "must not be empty")
        return tuple(value)

    def section(self, key: str, required: bool = True) -> Fields:
        if key not in self._data and not required:
            return Fields({}, self._file_name, self.path_of(key))
        return Fields(self.raw(key), self._file_name, self.path_of(key))

    def items(self, key: str) -> list[Fields]:
        """The objects of a list, each with its index in the key path."""
        if key not in self._data:
            return []
        value: object = self.raw(key)
        if not isinstance(value, list):
            raise self.error(key, f"must be a list, got {_describe(value)}")
        return [Fields(item, self._file_name, f"{self.path_of(key)}[{index}]") for index, item in enumerate(value)]

    def mapping(self, key: str) -> Mapping[str, Any]:
        """An object whose content is not validated here, such as an add-on's own settings."""
        if key not in self._data:
            return {}
        return Fields(self.raw(key), self._file_name, self.path_of(key))._data

    def names(self) -> Iterable[str]:
        return self._data.keys()

    def reject_unknown(self, known: Collection[str]) -> None:
        for key in self._data:
            if key not in known:
                raise self.error(key, f"is not a known key; known here: {', '.join(known)}")


def _describe(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return "an object" if isinstance(value, dict) else "a list"
    return repr(value)
