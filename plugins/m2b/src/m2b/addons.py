"""The add-ons of m2b and whether each is on.

An add-on is on while ``config.json`` holds ``"addons": {"<add-on>": {"on": true}}``; an add-on
that is missing there, or has no ``on``, is off, so a fresh install runs the core alone. The
add-on's own settings sit beside ``on`` and are the add-on's to check. An add-on with a curation
step runs it from this plugin's folder in its slot; the core needs no registration and nothing is
left behind when an add-on is turned off.

An add-on m2b no longer has keeps its name in ``REMOVED_ADDONS``: a ``config.json`` written by an
older version still names it, and loading that file must not fail over an entry nobody reads.
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
    Addon(
        "worklog",
        "records activity in herdr and writes a daily worklog with time spans and booking proposals",
        AddonStep("before_ingest", ("bin/m2b-worklog", "run")),
    ),
)
# Why each add-on an older version had is gone, in words for the owner who still has it set up.
REMOVED_ADDONS = {
    "herdr": "m2b 0.3.0 removed it, because listing the other agent sessions is herdr's own business "
    "and never touched the store; herdr shows them itself",
    "backup": "m2b 0.3.0 removed it until a backup with a way back replaces it; "
    "the folder it wrote is left as it was, and Time Machine or a copy of the store folder keeps the store safe",
}


def addon_names() -> tuple[str, ...]:
    return tuple(addon.name for addon in ADDONS)


class UnknownAddonError(ValueError):
    def __init__(self, name: str) -> None:
        super().__init__(f"{name!r} is not an add-on of m2b; the add-ons are {', '.join(addon_names())}")


class RemovedAddonError(ValueError):
    def __init__(self, name: str) -> None:
        super().__init__(f"{removed_addon_notice(name)}; m2b addons off {name} removes its entry from config.json")


def removed_addon_notice(name: str) -> str:
    return f"{name} is no longer an add-on of m2b: {REMOVED_ADDONS[name]}"


def addon_named(name: str) -> Addon:
    for addon in ADDONS:
        if addon.name == name:
            return addon
    if name in REMOVED_ADDONS:
        raise RemovedAddonError(name)
    raise UnknownAddonError(name)


def is_on(addons: Mapping[str, Mapping[str, Any]], name: str) -> bool:
    return addons.get(name, {}).get(ON) is True


def names_on(addons: Mapping[str, Mapping[str, Any]]) -> tuple[str, ...]:
    return tuple(addon.name for addon in ADDONS if is_on(addons, addon.name))


def steps_in(slot: str, addons: Mapping[str, Mapping[str, Any]]) -> tuple[Addon, ...]:
    """The add-ons that are on and have a step in ``slot``, in catalogue order."""
    return tuple(addon for addon in ADDONS if addon.step and addon.step.slot == slot and is_on(addons, addon.name))
