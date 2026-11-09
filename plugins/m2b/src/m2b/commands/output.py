"""Printing answers: plain text for people, ``--json`` for skills, the band and add-ons."""

from __future__ import annotations

import dataclasses
import datetime
import json
from typing import Any

from m2b.commands import UsageError


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def print_value(value: Any, as_json: bool) -> None:
    """A single text, number or key as it is, anything else as JSON."""
    if as_json or not isinstance(value, (str, int, float)) or isinstance(value, bool):
        print_json(value)
    else:
        print(value)


def as_json(value: Any) -> Any:
    """A dataclass as plain JSON data, paths and dates as strings."""
    return json.loads(json.dumps(dataclasses.asdict(value), default=str))


def lookup(data: Any, dotted_key: str | None, file_name: str) -> Any:
    if not dotted_key:
        return data
    value = data
    for part in dotted_key.split("."):
        if not isinstance(value, dict) or part not in value:
            raise UsageError(f"{file_name} has no key {dotted_key}")
        value = value[part]
    return value


def parse_value(text: str) -> Any:
    """A JSON value when the text is one (``true``, ``45``, ``["a"]``), else the text itself."""
    try:
        return json.loads(text)
    except ValueError:
        return text


def iso(value: datetime.date | None) -> str | None:
    if isinstance(value, datetime.datetime):
        return value.isoformat(timespec="seconds")
    return value.isoformat() if value is not None else None
