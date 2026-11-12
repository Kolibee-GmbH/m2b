"""The git this machine can start without asking the person anything.

On macOS ``/usr/bin/git`` is a stand-in: without the developer tools it opens a dialog that offers
to install them, which nothing that runs in the background or at a session start must cause. So it
is taken only once ``xcode-select -p`` says the tools are there.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

APPLE_GIT_STAND_IN = Path("/usr/bin/git")
DEVELOPER_TOOLS_CHECK = ("/usr/bin/xcode-select", "-p")
CHECK_TIMEOUT_SECONDS = 60.0

Runner = Callable[..., Any]


def usable_git(
    environ: Mapping[str, str],
    platform: str = sys.platform,
    run: Runner = subprocess.run,
    timeout: float = CHECK_TIMEOUT_SECONDS,
) -> str | None:
    """The git on the ``PATH``; None when there is none, or only the stand-in without the developer tools."""
    git = shutil.which("git", path=environ.get("PATH"))
    if git is None:
        return None
    if platform == "darwin" and Path(git) == APPLE_GIT_STAND_IN and not _developer_tools_installed(run, timeout):
        return None
    return git


def _developer_tools_installed(run: Runner, timeout: float) -> bool:
    try:
        result = run(list(DEVELOPER_TOOLS_CHECK), capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return bool(result.returncode == 0)
