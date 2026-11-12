"""Proves that the core stands without its add-ons.

An add-on lives in the same plugin folder as the core. ``ADDON_PARTS`` names everything there that
belongs to one. ``python3 -m repo_tools.core_alone`` copies the plugin without those parts into a
temporary folder, runs the core's unit tests in the copy and then the end-to-end scenarios that
turn no add-on on against it. A core test that reads an add-on's file, or a core command that
needs one, fails there, while it passes in the checkout, where the add-on is always present. A
core module that imports an add-on fails there too; in the checkout only the core's test of its
imports says so.

The unit tests import the copy's packages only. The scenario runner is a repository tool and runs
from the checkout; every command a step runs is the copy's, whose ``bin/`` is first on ``PATH`` and
whose commands start Python with their own ``src/`` alone.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from shutil import copytree
from typing import Any

from repo_tools import REPO_ROOT

PLUGIN = REPO_ROOT / "plugins" / "m2b"
SCENARIOS = REPO_ROOT / "tests" / "e2e"
HOOKS_MANIFEST = "hooks/hooks.json"
BYTECODE_CACHE = "__pycache__"
LABEL = "m2b without add-ons"
TEST_RESOURCE_PREFIX = "sb-test-"


@dataclass(frozen=True)
class AddonParts:
    """What one add-on puts into the plugin's folder."""

    name: str
    # Relative to the plugin's folder, with forward slashes; a folder stands for everything in it.
    paths: tuple[str, ...]
    # Its commands in hooks/hooks.json, as written there.
    hook_commands: tuple[str, ...] = ()


ADDON_PARTS = (
    AddonParts(
        "worklog",
        paths=(
            "bin/m2b-worklog",
            "recorder",
            "schemas/worklog-facts.schema.json",
            "schemas/worklog-verdict.schema.json",
            "skills/worklog-setup",
            "skills/worklog-verdict",
            "src/m2b_worklog",
            "tests/addons/worklog",
        ),
        hook_commands=('"${CLAUDE_PLUGIN_ROOT}"/bin/m2b-worklog hook session-start',),
    ),
)


class StaleAddonPartsError(Exception):
    def __init__(self, missing: Sequence[str]) -> None:
        super().__init__(f"the list of add-on parts names what the plugin does not have: {', '.join(missing)}")


def hook_commands(plugin: Path) -> list[str]:
    manifest = json.loads((plugin / HOOKS_MANIFEST).read_text(encoding="utf-8"))
    return [hook["command"] for entries in manifest["hooks"].values() for entry in entries for hook in entry["hooks"]]


def missing_parts(plugin: Path, parts: Sequence[AddonParts] = ADDON_PARTS) -> list[str]:
    """The listed parts the plugin does not have: the list names something that moved or is gone."""
    commands = hook_commands(plugin)
    missing = [path for addon in parts for path in addon.paths if not (plugin / path).exists()]
    missing += [command for addon in parts for command in addon.hook_commands if command not in commands]
    return missing


def unlisted_parts(plugin: Path, parts: Sequence[AddonParts] = ADDON_PARTS) -> list[str]:
    """What carries an add-on's name in the plugin and is in no list: a part the add-on gained.

    A path counts when its own name holds the add-on's name and no listed path is it or holds it;
    a hook command counts when it holds the name.
    """
    unlisted: list[str] = []
    for addon in parts:
        listed = [PurePosixPath(path) for path in addon.paths]
        for path in sorted(plugin.rglob(f"*{addon.name}*")):
            relative = PurePosixPath(path.relative_to(plugin).as_posix())
            if BYTECODE_CACHE in relative.parts:
                continue
            if not any(part == relative or part in relative.parents for part in listed):
                unlisted.append(str(relative))
        unlisted += [
            command for command in hook_commands(plugin) if addon.name in command and command not in addon.hook_commands
        ]
    return unlisted


def copy_without_addons(plugin: Path, target: Path, parts: Sequence[AddonParts] = ADDON_PARTS) -> None:
    """Copies the plugin's folder to ``target``, which must not exist, without any part of an add-on."""
    missing = missing_parts(plugin, parts)
    if missing:
        raise StaleAddonPartsError(missing)
    left_out = {path for addon in parts for path in addon.paths}

    def addon_parts_and_bytecode(folder: str, names: list[str]) -> set[str]:
        relative = Path(folder).relative_to(plugin)
        return {name for name in names if name == BYTECODE_CACHE or (relative / name).as_posix() in left_out}

    copytree(plugin, target, ignore=addon_parts_and_bytecode, symlinks=True)
    _drop_hook_commands(target / HOOKS_MANIFEST, {command for addon in parts for command in addon.hook_commands})


def _drop_hook_commands(manifest_file: Path, commands: set[str]) -> None:
    manifest: dict[str, Any] = json.loads(manifest_file.read_text(encoding="utf-8"))
    for entries in manifest["hooks"].values():
        for entry in entries:
            entry["hooks"] = [hook for hook in entry["hooks"] if hook["command"] not in commands]
    manifest_file.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def prove_core_alone(
    plugin: Path = PLUGIN,
    parts: Sequence[AddonParts] = ADDON_PARTS,
    scenarios: Path = SCENARIOS,
    capture_output: bool = False,
) -> list[subprocess.CompletedProcess[str]]:
    """Runs the core's unit tests and the scenarios without an add-on in a copy of the plugin without add-ons.

    The two finished runs, the unit tests first; the proof holds when both ended with 0.
    """
    with tempfile.TemporaryDirectory(prefix=f"{TEST_RESOURCE_PREFIX}core-alone-") as temp:
        # Resolved, because the tests compare paths and macOS hands out a temporary folder behind a link.
        copy = Path(temp).resolve() / plugin.name
        copy_without_addons(plugin, copy, parts)
        unit_tests = ["-m", "repo_tools.unit_tests", "--tests", str(copy / "tests"), "--label", LABEL]
        unit_tests += ["--import-root", str(copy / "src")]
        end_to_end = ["-m", "repo_tools.e2e", "--level", "stub", "--core-only"]
        end_to_end += ["--plugin", str(copy), "--scenarios", str(scenarios)]
        tools = str(REPO_ROOT / "scripts")
        return [
            _run_python(unit_tests, [tools], copy.parent, capture_output),
            _run_python(end_to_end, [tools, str(PLUGIN / "src")], copy.parent, capture_output),
        ]


def _run_python(
    arguments: Sequence[str], import_roots: Sequence[str], folder: Path, capture_output: bool
) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "PYTHONPATH": os.pathsep.join(import_roots), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(
        [sys.executable, *arguments], cwd=folder, env=environment, capture_output=capture_output, text=True, check=False
    )


def main(plugin: Path = PLUGIN, parts: Sequence[AddonParts] = ADDON_PARTS, scenarios: Path = SCENARIOS) -> int:
    try:
        runs = prove_core_alone(plugin, parts, scenarios)
    except StaleAddonPartsError as error:
        print(f"core alone: {error}", file=sys.stderr)
        return 1
    return 1 if any(run.returncode for run in runs) else 0


if __name__ == "__main__":
    sys.exit(main())
