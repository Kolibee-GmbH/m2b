"""The ``icloud`` backend: a folder in iCloud Drive, on macOS 14 or newer.

iCloud names a conflict copy ``<stem> <n>.<ext>`` next to the original, for any n of 2 or more.
The pattern also matches files a user named that way (``plan 2026.md``), so the name is only a
candidate: ``Store.conflict_copies`` counts it next to its original and lets it be removed only
when its bytes equal the original's. Before macOS 14, iCloud kept evicted files as
hidden ``.<name>.icloud`` stubs, which the guard cannot see: the backend refuses an older macOS
and a store whose top folders hold such stubs; ``old_stub_files`` searches the whole store, for
setup and doctor, where that walk costs once.
"""

from __future__ import annotations

import errno
import os
import platform
import re
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from m2b.store.base import FetchError, Store, StoreReadError, UnsupportedStoreError
from m2b.store.guard import DatalessGuard

_CONFLICT_NAME = re.compile(r"(?P<stem>.+) (?:[2-9]|[1-9][0-9]+)\.(?P<extension>[^.]+)\Z")
_OLD_STUB_NAME = re.compile(r"\..+\.icloud\Z")
MINIMUM_MACOS = 14


class ICloudStore(Store):
    def __init__(
        self,
        root: Path,
        temp_dir: Path,
        guard: DatalessGuard,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        macos_release: str | None = None,
    ) -> None:
        super().__init__(root, temp_dir, guard, clock, sleep)
        _refuse_macos_before_14(platform.mac_ver()[0] if macos_release is None else macos_release)
        self._refuse_old_stub_files_at_the_top()

    def _start_download(self, relative: str, timeout_seconds: float) -> None:
        try:
            subprocess.run(
                ["brctl", "download", str(self.path(relative))],
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise FetchError(f"iCloud did not start downloading {relative}: {error}") from error

    def _original_name(self, name: str) -> str | None:
        match = _CONFLICT_NAME.match(name)
        if match is None:
            return None
        return f"{match.group('stem')}.{match.group('extension')}"

    def _refuse_old_stub_files_at_the_top(self) -> None:
        """Looks into the root and its direct subfolders; an evicted subfolder is left alone."""
        folders = [""] + [
            entry.name
            for entry in self._visible_entries("")
            if entry.is_dir() and not entry.is_symlink() and not self.guard.is_evicted(entry)
        ]
        for folder in folders:
            target = self.path(folder) if folder else self.root
            try:
                names = [entry.name for entry in target.iterdir()]
            except OSError as error:
                if error.errno == errno.EDEADLK:
                    continue
                raise StoreReadError(f"{folder or 'the store'} could not be listed: {error}") from error
            if any(_OLD_STUB_NAME.match(name) for name in names):
                raise UnsupportedStoreError(
                    f"{self.root} holds old-style .icloud placeholder files, which this backend cannot guard; "
                    f"the icloud backend needs macOS {MINIMUM_MACOS} or newer"
                )

    def old_stub_files(self) -> list[str]:
        """Every old-style stub file in the store; walks the whole tree."""
        found: list[str] = []
        for folder, _, names in os.walk(self.root):
            found.extend(
                (Path(folder) / name).relative_to(self.root).as_posix() for name in names if _OLD_STUB_NAME.match(name)
            )
        return sorted(found)


def _refuse_macos_before_14(release: str) -> None:
    major = release.split(".")[0]
    if major.isdigit() and int(major) < MINIMUM_MACOS:
        raise UnsupportedStoreError(f"the icloud backend needs macOS {MINIMUM_MACOS} or newer; this is {release}")
