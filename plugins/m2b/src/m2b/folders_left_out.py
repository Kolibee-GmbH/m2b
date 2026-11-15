"""Which sessions m2b never reads, by the folder they worked in: one rule for the core's readers.

The reading of a period's sessions (``curate.glean_step``) asks it, and so does whoever takes
words from one session while it runs, so "work m2b does not read" cannot be forgotten in one of
two places in the core. A folder is left out when

- it is, or lies below, a folder the profile's ``worklog_leave_out`` names or a folder with
  ``m2b distillate off``; a folder that is not an absolute path cannot be compared with either and
  is left out too;
- the profile leaves work out by git remote, and a remote noted for the folder at a session
  start, or one git names there now, holds a part the profile names; and also when neither says
  anything of the folder, since it is then not shown to be other work (``session_remotes``).

The reading judges a session after it ended, when its folder may be gone: ``reason`` compares the
folder with the profile's folders as written. A caller inside a session judges a path that is
there (``reason_for_a_path``): it is read as the disk has it, so ``..``, a link and another
spelling of a folder's name all lead to the folder they name. A second name the file system
itself gives one file (a hard link) is not known for one.
"""

from __future__ import annotations

import datetime
import os
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from m2b import session_remotes
from m2b.config.machine import DistillateSettings, MachineConfig
from m2b.config.profile import require_profile
from m2b.git_program import usable_git
from m2b.paths import MachinePaths, expand
from m2b.store.base import Store

# Why a folder is left out.
IN_A_FOLDER_LEFT_OUT = "folder"
OF_A_REPOSITORY_LEFT_OUT = "repository"
OF_NO_KNOWN_REPOSITORY = "unknown repository"

_SLASHES_AT_THE_START = re.compile(r"\A/+")
# No file system opens a longer path, and no person's work lies deeper; judging a path costs more
# the deeper it is.
LONGEST_PATH = 4096
DEEPEST_PATH = 256


@dataclass(frozen=True)
class LeftOutRule:
    """What the profile and this machine leave out, asked folder by folder."""

    named: tuple[Path, ...]
    distillate: DistillateSettings
    by_remote: session_remotes.RemoteRule
    # The home folder a path that starts with ``~`` is read from, as the named folders were.
    home: Path

    def reason(self, folder: str) -> str | None:
        """Why a session that worked in ``folder`` is not read, or None when it is."""
        path = Path(folder)
        # A folder that cannot be compared with the list is not shown to be outside it.
        if not path.is_absolute() or any(path == root or root in path.parents for root in self.named):
            return IN_A_FOLDER_LEFT_OUT
        if self.distillate.covering(path) is not None:
            return IN_A_FOLDER_LEFT_OUT
        return _by_its_repository(self.by_remote.judge(folder))

    def reason_for_a_path(self, path: str) -> str | None:
        """Why what lies at ``path`` on this machine is not read, or None when it is.

        The path may be a file or a folder and need not exist; the repository is asked about in
        the nearest folder above it that does. A path that cannot be looked at, through a link
        that leads nowhere or a folder that may not be entered, is left out.
        """
        folders = (*self.named, *self.distillate.skip_under)
        try:
            if "\x00" in path or len(path) > LONGEST_PATH or path.count("/") > DEEPEST_PATH:
                return IN_A_FOLDER_LEFT_OUT
            expanded = _SLASHES_AT_THE_START.sub("/", str(expand(path, self.home)))
            if not os.path.isabs(expanded):
                return IN_A_FOLDER_LEFT_OUT
            # The links are followed before ``..`` is worked out, as the system does when it opens
            # the path: behind a link, ``..`` is the folder above where the link leads.
            where_it_leads = Path(os.path.realpath(expanded))
            as_written = Path(os.path.normpath(expanded))
            folder = _nearest_folder_that_is_there(where_it_leads)
            if _lies_in_one_of(as_written, folders) or _lies_in_one_of(where_it_leads, folders):
                return IN_A_FOLDER_LEFT_OUT
        except (OSError, RuntimeError, ValueError):
            return IN_A_FOLDER_LEFT_OUT
        return _by_its_repository(self.by_remote.judge(str(folder)))


def _by_its_repository(judged: session_remotes.ByRemote) -> str | None:
    if judged is session_remotes.ByRemote.UNKNOWN:
        return OF_NO_KNOWN_REPOSITORY
    return OF_A_REPOSITORY_LEFT_OUT if judged is session_remotes.ByRemote.LEFT_OUT else None


def _nearest_folder_that_is_there(path: Path) -> Path:
    """``path`` or the first folder above it that exists; an ``OSError`` where what is there cannot be looked at."""
    for above in (path, *path.parents):
        try:
            os.lstat(above)
        # Only what is not there is passed over; a folder that may not be entered raises.
        except (FileNotFoundError, NotADirectoryError):
            continue
        if _on_disk(above) is None:
            raise OSError(f"{above} cannot be looked at")
        if above.is_dir():
            return above
    raise OSError(f"no folder above {path} is there")


def _lies_in_one_of(path: Path, folders: Iterable[Path]) -> bool:
    """Whether ``path`` is one of the folders or lies below one, as written or as the disk has it.

    On the disk a folder is known by its device and number, so a name in other case, where the
    file system takes both as one, is the folder too.
    """
    folders = tuple(folders)
    above = (path, *path.parents)
    if any(folder in above or Path(os.path.realpath(folder)) in above for folder in folders):
        return True
    on_disk = {_on_disk(folder) for folder in folders} - {None}
    return bool(on_disk) and any(_on_disk(candidate) in on_disk for candidate in above)


def _on_disk(path: Path) -> tuple[int, int] | None:
    """What tells this file or folder from every other on the machine; None when it is not there."""
    try:
        found = path.stat()
    except (OSError, ValueError):
        return None
    return found.st_dev, found.st_ino


def rule(
    store: Store, config: MachineConfig, machine: MachinePaths, environ: Mapping[str, str], now: datetime.datetime
) -> LeftOutRule:
    """The rule as the store's profile and this machine's config state it at ``now``.

    Reads the profile, so a store that cannot be read raises as ``require_profile`` does.
    """
    left_out = require_profile(store).worklog_leave_out
    by_remote = session_remotes.RemoteRule(
        left_out.git_remote_contains,
        machine.state_dir / session_remotes.NOTES_FOLDER,
        now,
        _asking_git(environ),
    )
    return LeftOutRule(tuple(left_out.folders(machine.home)), config.distillate, by_remote, machine.home)


def _asking_git(environ: Mapping[str, str]) -> Callable[[Path], frozenset[str] | None]:
    """What git names as a folder's remotes now; nothing on a machine without a git to start.

    Which git that is, is looked up at the first folder asked about, so a caller that needs no
    folder's remotes starts nothing.
    """
    found: list[str | None] = []

    def ask(folder: Path) -> frozenset[str] | None:
        if not found:
            found.append(usable_git(environ))
        git = found[0]
        return session_remotes.remotes_in(folder, git, environ=environ) if git is not None else None

    return ask
