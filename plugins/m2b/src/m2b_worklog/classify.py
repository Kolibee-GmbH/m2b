"""A session's sphere from the profile's rules: a git remote it contains, or a folder it lies under.

The first sphere whose rule matches wins; no match leaves the sphere open for the verdict.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SphereRule:
    sphere_id: str
    label: str | None
    billable: bool
    default: bool
    remotes: tuple[str, ...]
    folders: tuple[Path, ...]


def sphere_rules(profile: Mapping[str, Any], home: Path) -> list[SphereRule]:
    rules = []
    for sphere in profile.get("spheres", []):
        if not isinstance(sphere, dict) or not isinstance(sphere.get("id"), str):
            continue
        match: dict[str, Any] = sphere["match"] if isinstance(sphere.get("match"), dict) else {}
        remotes = tuple(r for r in match.get("git_remote_contains", []) if isinstance(r, str) and r)
        folders = tuple(_expand(p, home) for p in match.get("path_under", []) if isinstance(p, str) and p)
        label = sphere.get("label") if isinstance(sphere.get("label"), str) else None
        billable, default = sphere.get("billable") is True, sphere.get("default") is True
        rules.append(SphereRule(sphere["id"], label, billable, default, remotes, folders))
    return rules


def sphere_of(rules: Sequence[SphereRule], folder: str | None, remote: str | None) -> str | None:
    for rule in rules:
        if remote is not None and any(part in remote for part in rule.remotes):
            return rule.sphere_id
        if folder is not None and any(_is_under(Path(folder), root) for root in rule.folders):
            return rule.sphere_id
    return None


def _expand(path: str, home: Path) -> Path:
    if path == "~" or path.startswith("~/"):
        return home / path[2:]
    return Path(path) if path.startswith("/") else home / path


def _is_under(folder: Path, root: Path) -> bool:
    return folder == root or root in folder.parents
