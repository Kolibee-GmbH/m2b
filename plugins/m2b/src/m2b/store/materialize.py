"""Reads one file, or lists one folder, with materialization on, so that a sync service downloads it.

Run as a separate process: the store's own process has materialization switched off, and a
child inherits that policy until it sets its own. Usage: python3 materialize.py <path>
"""

from __future__ import annotations

import ctypes
import os
import sys

IOPOL_TYPE_VFS_MATERIALIZE_DATALESS_FILES = 3
IOPOL_SCOPE_PROCESS = 0
IOPOL_MATERIALIZE_DATALESS_FILES_ON = 2
CHUNK_BYTES = 1 << 20


def main(path: str) -> int:
    libc = ctypes.CDLL(None, use_errno=True)
    libc.setiopolicy_np(
        IOPOL_TYPE_VFS_MATERIALIZE_DATALESS_FILES, IOPOL_SCOPE_PROCESS, IOPOL_MATERIALIZE_DATALESS_FILES_ON
    )
    if os.path.isdir(path):
        os.listdir(path)
        return 0
    with open(path, "rb") as file:
        while file.read(CHUNK_BYTES):
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
