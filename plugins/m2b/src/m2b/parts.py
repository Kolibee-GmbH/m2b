"""The optional parts of m2b and whether each is on.

A part is on while ``config.json`` holds ``"parts": {"<part>": {"on": true}}``; a part that is
missing there, or has no ``on``, is off, so a fresh install runs the core alone. The part's own
settings sit beside ``on`` and are the part's to check. A part with a curation step runs it from
this plugin's folder in its slot; the core needs no registration and nothing is left behind when a
part is turned off.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

CURATION_SLOTS = ("before_ingest", "after_ingest", "after_journal")
ON = "on"


@dataclass(frozen=True)
class PartStep:
    slot: str
    # Relative to this plugin's folder.
    command: tuple[str, ...]


@dataclass(frozen=True)
class Part:
    name: str
    summary: str
    step: PartStep | None = None


PARTS = (
    Part("band", "open memory candidates, the open review and the state of curation above the prompt"),
    Part("herdr", "at session start, the other agent sessions open in herdr"),
    Part(
        "worklog",
        "records activity in herdr and writes a daily worklog with time spans and booking proposals",
        PartStep("before_ingest", ("bin/m2b-worklog", "run")),
    ),
    Part(
        "backup",
        "after each curation run, a local snapshot of the store and the task list",
        PartStep("after_journal", ("bin/m2b-backup", "run")),
    ),
)
PART_NAMES = tuple(part.name for part in PARTS)


class UnknownPartError(ValueError):
    def __init__(self, name: str) -> None:
        super().__init__(f"{name!r} is not a part of m2b; the parts are {', '.join(PART_NAMES)}")


def part_named(name: str) -> Part:
    for part in PARTS:
        if part.name == name:
            return part
    raise UnknownPartError(name)


def is_on(parts: Mapping[str, Mapping[str, Any]], name: str) -> bool:
    return parts.get(name, {}).get(ON) is True


def names_on(parts: Mapping[str, Mapping[str, Any]]) -> tuple[str, ...]:
    return tuple(part.name for part in PARTS if is_on(parts, part.name))


def steps_in(slot: str, parts: Mapping[str, Mapping[str, Any]]) -> tuple[Part, ...]:
    """The parts that are on and have a step in ``slot``, in catalogue order."""
    return tuple(part for part in PARTS if part.step and part.step.slot == slot and is_on(parts, part.name))
