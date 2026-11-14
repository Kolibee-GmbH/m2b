"""The git this machine can start without asking the person anything, and how m2b starts it.

On macOS ``/usr/bin/git`` is a stand-in: without the developer tools it opens a dialog that offers
to install them, which nothing that runs in the background or at a session start must cause. So it
is taken only once ``xcode-select -p`` says the tools are there.

Whatever m2b starts git for, git reads a configuration m2b did not write: the store's repository,
or the repository of a folder a session ran in. Such a configuration can name programs git starts
by itself, and m2b's git runs unattended. So every git m2b starts in a folder is started the same
way (``git_command`` and ``git_environment``): no hook and no file-system monitor of the repository runs,
no signature is checked, which would start the ``gpg.program`` the repository names, and nothing
reaches a remote, so neither the command a remote names for fetching runs nor are the objects a
partial clone lacks fetched. A setting given on the command line wins over the repository's and
the person's own.

The transports are closed in the environment, not by ``protocol.allow=never`` alone: that setting
is only the default for a transport without a policy of its own, and a repository that says
``protocol.file.allow=always`` would open its transport again. ``GIT_ALLOW_PROTOCOL`` is a list of
the transports allowed whatever any configuration says, and an empty one allows none.
``GIT_NO_LAZY_FETCH`` keeps a git from 2.45 on from even trying to fetch a missing object.

Standard library only and nothing else of m2b: the worklog add-on imports it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

APPLE_GIT_STAND_IN = Path("/usr/bin/git")
DEVELOPER_TOOLS_CHECK = ("/usr/bin/xcode-select", "-p")
CHECK_TIMEOUT_SECONDS = 60.0

# Given to every git m2b starts, after the caller's own settings and before the subcommand.
SETTINGS = (
    f"core.hooksPath={os.devnull}",
    "core.fsmonitor=false",
    "log.showSignature=false",
    "protocol.allow=never",
)
# Variables that would point git at another repository, index or work tree than the folder's,
# and the one that has ``git config`` read another file than the repository's. The person's own
# configuration, and the variables that say where it lies, pass.
REDIRECTING_VARIABLES = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_PREFIX",
    "GIT_CONFIG",
)
REACHES_NO_REMOTE = {"GIT_ALLOW_PROTOCOL": "", "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0"}

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


def git_command(
    git: str,
    folder: Path,
    arguments: Sequence[str],
    settings: Sequence[str] = (),
    git_directory: Path | None = None,
) -> list[str]:
    """The command line of ``git <arguments>`` in ``folder``, under ``SETTINGS``.

    ``settings`` are the caller's own, each ``key=value``. With ``git_directory`` git takes that
    directory for the repository's and does not look for one from ``folder``.
    """
    named = ["--git-dir", str(git_directory)] if git_directory is not None else []
    given = [option for setting in (*settings, *SETTINGS) for option in ("-c", setting)]
    return [git, "-C", str(folder), *named, *given, *arguments]


def git_environment(environ: Mapping[str, str]) -> dict[str, str]:
    """``environ`` for a git m2b starts: nothing in it points git at another repository, and
    nothing reaches a remote."""
    kept = {name: value for name, value in environ.items() if name not in REDIRECTING_VARIABLES}
    return {**kept, **REACHES_NO_REMOTE}


def _developer_tools_installed(run: Runner, timeout: float) -> bool:
    try:
        result = run(list(DEVELOPER_TOOLS_CHECK), capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return bool(result.returncode == 0)
