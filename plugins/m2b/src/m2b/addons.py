"""The add-ons of m2b and whether each is on.

An add-on is on while ``config.json`` holds ``"addons": {"<add-on>": {"on": true}}``; an add-on
that is missing there, or has no ``on``, is off, so a fresh install runs the core alone. The
add-on's own settings sit beside ``on`` and are the add-on's to check. An add-on with a curation
step runs it from this plugin's folder in its slot; the core needs no registration and nothing is
left behind when an add-on is turned off.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

CURATION_SLOTS = ("before_ingest", "after_ingest", "after_journal")
ON = "on"


@dataclass(frozen=True)
class AddonStep:
    slot: str
    # Relative to this plugin's folder.
    command: tuple[str, ...]


@dataclass(frozen=True)
class Addon:
    name: str
    summary: str
    step: AddonStep | None = None


ADDONS = (
    Addon("band", "open memory candidates, the open review and the state of curation above the prompt"),
    Addon("herdr", "at session start, the other agent sessions open in herdr"),
    Addon(
        "worklog",
        "records activity in herdr and writes a daily worklog with time spans and booking proposals",
        AddonStep("before_ingest", ("bin/m2b-worklog", "run")),
    ),
    Addon(
        "backup",
        "after each curation run, a local snapshot of the store and the task list",
        AddonStep("after_journal", ("bin/m2b-backup", "run")),
    ),
)
ADDON_NAMES = tuple(addon.name for addon in ADDONS)


class UnknownAddonError(ValueError):
    def __init__(self, name: str) -> None:
        super().__init__(f"{name!r} is not an add-on of m2b; the add-ons are {', '.join(ADDON_NAMES)}")


def addon_named(name: str) -> Addon:
    for addon in ADDONS:
        if addon.name == name:
            return addon
    raise UnknownAddonError(name)


def is_on(addons: Mapping[str, Mapping[str, Any]], name: str) -> bool:
    return addons.get(name, {}).get(ON) is True


def names_on(addons: Mapping[str, Mapping[str, Any]]) -> tuple[str, ...]:
    return tuple(addon.name for addon in ADDONS if is_on(addons, addon.name))


def steps_in(slot: str, addons: Mapping[str, Mapping[str, Any]]) -> tuple[Addon, ...]:
    """The add-ons that are on and have a step in ``slot``, in catalogue order."""
    return tuple(addon for addon in ADDONS if addon.step and addon.step.slot == slot and is_on(addons, addon.name))
