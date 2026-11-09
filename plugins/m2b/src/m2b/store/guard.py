"""The guard against evicted files: files a sync service keeps only as a placeholder.

On macOS, iCloud Drive, Dropbox and OneDrive mark such a file with the ``SF_DATALESS`` flag,
and reading it would download it or hang. With the process I/O policy set, a read of such a
file fails at once instead; the flag lets the store refuse before it even opens the file.
"""

from __future__ import annotations

import ctypes
import os
import sys
from collections.abc import Callable
from typing import Any

SF_DATALESS = 0x40000000

IOPOL_TYPE_VFS_MATERIALIZE_DATALESS_FILES = 3
IOPOL_SCOPE_PROCESS = 0
IOPOL_MATERIALIZE_DATALESS_FILES_OFF = 1
IOPOL_MATERIALIZE_DATALESS_FILES_ON = 2

_process_policy_set = False


class DatalessGuard:
    """Tells whether a file is evicted; an inactive guard (any platform but macOS) says never."""

    def __init__(self, active: bool, lstat: Callable[[str | os.PathLike[str]], Any] = os.lstat) -> None:
        self.active = active
        self._lstat = lstat

    def is_evicted(self, path: str | os.PathLike[str]) -> bool:
        if not self.active:
            return False
        return bool(getattr(self._lstat(path), "st_flags", 0) & SF_DATALESS)


def set_materialization(enabled: bool) -> None:
    """Sets the macOS I/O policy for this process and its children."""
    libc = ctypes.CDLL(None, use_errno=True)
    policy = IOPOL_MATERIALIZE_DATALESS_FILES_ON if enabled else IOPOL_MATERIALIZE_DATALESS_FILES_OFF
    if libc.setiopolicy_np(IOPOL_TYPE_VFS_MATERIALIZE_DATALESS_FILES, IOPOL_SCOPE_PROCESS, policy) != 0:
        raise OSError(ctypes.get_errno(), "setiopolicy_np failed")


def guard_for_platform(platform: str = sys.platform) -> DatalessGuard:
    """The guard for this machine; on macOS it also turns off materialization for the process."""
    global _process_policy_set
    if platform != "darwin":
        return DatalessGuard(False)
    if not _process_policy_set:
        set_materialization(False)
        _process_policy_set = True
    return DatalessGuard(True)
