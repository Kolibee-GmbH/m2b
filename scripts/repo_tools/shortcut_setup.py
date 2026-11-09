"""A test setup for the Shortcuts check: can a personal automation start curation?

``set_up`` builds a machine of its own under ``~/sb-test-shortcut`` (so its launcher lies there, not
in the owner's ``~/.local/bin``), with a store ``sb-test-shortcut-store`` in iCloud Drive, the
Reminders list ``sb-test-inbox`` and ``M2B_CORE_ROOT`` on this checkout, and prints the one line the
automation runs. The store holds a fact file with a link to nothing, so lint reports an action and
the run leaves a review task in the list, which shows that the run reached Reminders from
Shortcuts. ``remove`` deletes that task, the test home and the store. Every path it touches has a
name starting with ``sb-test-``.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from m2b import launcher

TEST_PREFIX = "sb-test-"
HOME_NAME = "sb-test-shortcut"
STORE_NAME = "sb-test-shortcut-store"
TASK_LIST = "sb-test-inbox"
MACHINE_ID = "sb-test-shortcut"
BROKEN_LINK = "20260101T000000Z-cli-dead.md"

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


def locations(user_home: Path) -> tuple[Path, Path]:
    drive = user_home / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    return user_home / HOME_NAME, drive / STORE_NAME


def require_test_name(path: Path) -> None:
    if not path.name.startswith(TEST_PREFIX):
        raise ValueError(f"{path} is not a test resource; its name must start with {TEST_PREFIX}")


def set_up(user_home: Path, core_root: Path, environ: Mapping[str, str], run: Runner = subprocess.run) -> list[str]:
    test_home, store = locations(user_home)
    for path in (test_home, store):
        require_test_name(path)
    try:
        _seed(store)
        answers = {
            "machine_id": MACHINE_ID,
            "store": {"backend": "icloud", "path": str(store)},
            "tasks": {"backend": "apple-reminders", "list": TASK_LIST},
            "owner": "Alex",
            "language": "en",
            "calendar": "none",
            "curates": True,
        }
        apply = ["setup", "apply", "--json", "--answers", json.dumps(answers)]
        result = json.loads(_m2b(apply, test_home, core_root, environ, run, (0, 1)).stdout or "{}")
        # A run from Shortcuts has a minimal PATH: without the recorded paths and the launcher it fails
        # for a reason the check does not ask about, so the check would read as a false no.
        missing = result.get("missing_executables") or []
        open_points = [
            *(result.get("problems") or []),
            *([f"not found on PATH: {', '.join(missing)}"] if missing else []),
        ]
        if open_points:
            raise RuntimeError("setup left something open: " + "; ".join(open_points))
        # Exit 3 when the list is missing or the terminal has no Reminders access; the run would stop there.
        _m2b(["tasks", "list", "--json"], test_home, core_root, environ, run)
    except (RuntimeError, OSError, ValueError):
        # Nothing is in Reminders yet, and --remove would stop at the same cause: clean up here.
        for path in (test_home, store):
            shutil.rmtree(path, ignore_errors=True)
        raise
    variables = f"M2B_HOME={shlex.quote(str(test_home))} M2B_CORE_ROOT={shlex.quote(str(core_root))}"
    launcher_path = shlex.quote(str(test_home / ".local" / "bin" / "m2b"))
    return [
        f"test home: {test_home}",
        f"test store: {store}",
        f"the automation runs: {variables} {launcher_path} curate --force",
        f"afterwards, look: {variables} {launcher_path} tasks list --marker review",
    ]


def remove(user_home: Path, core_root: Path, environ: Mapping[str, str], run: Runner = subprocess.run) -> list[str]:
    test_home, store = locations(user_home)
    for path in (test_home, store):
        require_test_name(path)
    lines = []
    if test_home.exists():
        listed = _m2b(
            ["tasks", "list", "--marker", "review", "--include-completed", "--json"], test_home, core_root, environ, run
        )
        for task in json.loads(listed.stdout or "[]"):
            _m2b(["tasks", "delete", str(task["id"])], test_home, core_root, environ, run, (0, 1))
            lines.append(f"deleted the review task {task['id']} from {TASK_LIST}")
    for path in (test_home, store):
        if path.exists():
            shutil.rmtree(path)
            lines.append(f"removed {path}")
    return lines


def _seed(store: Path) -> None:
    memory = store / "memory"
    memory.mkdir(parents=True, exist_ok=True)
    (memory / "MEMORY.md").write_text(
        "# Memory\n\n## Facts\n\n- Dana likes old maps (dana.md)\n\n## Current\n", encoding="utf-8"
    )
    (memory / "dana.md").write_text(
        f"# Dana\n\n- Likes old maps.\n\n## Evidence\n\n- [[{BROKEN_LINK}]]\n", encoding="utf-8"
    )


def _m2b(
    arguments: Sequence[str],
    test_home: Path,
    core_root: Path,
    environ: Mapping[str, str],
    run: Runner,
    accepted: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[str]:
    env: dict[str, Any] = {**environ, "M2B_HOME": str(test_home), "M2B_CORE_ROOT": str(core_root)}
    result = run(launcher.core_command(list(arguments)), env=env, capture_output=True, text=True, check=False)
    if result.returncode not in accepted:
        raise RuntimeError(f"m2b {' '.join(arguments[:2])} failed: {result.stderr.strip()[:400]}")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="e2e-shortcut-setup", description="A test setup for the Shortcuts check.")
    parser.add_argument("--remove", action="store_true", help="delete the review task, the test home and the store")
    arguments = parser.parse_args(argv)
    # Asked at run time: mypy works sys.platform out and would call the rest unreachable on Linux.
    if platform.system() != "Darwin" or os.environ.get("M2B_IT") != "1":
        print("e2e-shortcut-setup: runs on macOS only and only with M2B_IT=1", file=sys.stderr)
        return 2
    user_home = Path.home()
    action = remove if arguments.remove else set_up
    for line in action(user_home, launcher.PLUGIN_ROOT, os.environ):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
