"""The two published schemas and a check against them: the subset of JSON Schema they use.

``worklog-facts.schema.json`` is what ``collect`` writes and the verdict reads;
``worklog-verdict.schema.json`` is what the verdict hands back. The standard library has no JSON
Schema validator, so this one covers exactly the keywords the two files use: ``type``, ``const``,
``enum``, ``required``, ``properties``, ``additionalProperties``, ``items``, ``anyOf``,
``minLength``, ``minimum``, ``pattern`` and ``format: date-time``.
"""

from __future__ import annotations

import datetime
import json
import re
from typing import Any

from m2b_worklog.paths import PLUGIN_ROOT

SCHEMAS = PLUGIN_ROOT / "schemas"
FACTS_SCHEMA = "worklog-facts.schema.json"
VERDICT_SCHEMA = "worklog-verdict.schema.json"


def load(name: str) -> dict[str, Any]:
    schema: dict[str, Any] = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
    return schema


def check(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Every place where ``value`` breaks ``schema``, as ``<path>: <problem>``; empty when it holds."""
    problems: list[str] = []
    if "const" in schema and value != schema["const"]:
        problems.append(f"{path}: {value!r} is not {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{path}: {value!r} is not one of {schema['enum']!r}")
    if "anyOf" in schema and not any(not check(value, option, path) for option in schema["anyOf"]):
        problems.append(f"{path}: {_short(value)} matches none of the allowed shapes")
    kinds = schema.get("type")
    if kinds is not None and not any(_is(value, kind) for kind in (kinds if isinstance(kinds, list) else [kinds])):
        return [*problems, f"{path}: {_short(value)} is not {kinds}"]
    if isinstance(value, dict):
        problems += _check_object(value, schema, path)
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            problems += check(item, schema["items"], f"{path}[{index}]")
    if isinstance(value, str):
        problems += _check_string(value, schema, path)
    if _is(value, "integer") and "minimum" in schema and value < schema["minimum"]:
        problems.append(f"{path}: {value} is below {schema['minimum']}")
    return problems


def _check_object(value: dict[str, Any], schema: dict[str, Any], path: str) -> list[str]:
    problems = [f"{path}: {key} is missing" for key in schema.get("required", []) if key not in value]
    properties = schema.get("properties", {})
    extra = schema.get("additionalProperties")
    for key, item in value.items():
        if key in properties:
            problems += check(item, properties[key], f"{path}.{key}")
        elif extra is False:
            problems.append(f"{path}: {key} is not allowed")
        elif isinstance(extra, dict):
            problems += check(item, extra, f"{path}.{key}")
    return problems


def _check_string(value: str, schema: dict[str, Any], path: str) -> list[str]:
    problems = []
    if len(value) < schema.get("minLength", 0):
        problems.append(f"{path}: the text is shorter than {schema['minLength']}")
    if "pattern" in schema and re.search(schema["pattern"], value) is None:
        problems.append(f"{path}: {value!r} does not match {schema['pattern']}")
    if schema.get("format") == "date-time":
        try:
            moment = datetime.datetime.fromisoformat(value)
        except ValueError:
            moment = None
        if moment is None or moment.tzinfo is None:
            problems.append(f"{path}: {value!r} is not a time with an offset")
    return problems


def _is(value: Any, kind: str) -> bool:
    if kind == "object":
        return isinstance(value, dict)
    if kind == "array":
        return isinstance(value, list)
    if kind == "string":
        return isinstance(value, str)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "boolean":
        return isinstance(value, bool)
    return kind == "null" and value is None


def _short(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= 60 else text[:57] + "..."
