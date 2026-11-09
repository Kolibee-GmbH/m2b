"""Writing a file whole, so a reader never sees half of it: replacing one, or creating one only if it is new."""

from __future__ import annotations

import contextlib
import errno
import os
import tempfile
from pathlib import Path

# The core's prefix for its own temporary files: in the store, its lint removes those left by a crash.
TEMP_PREFIX = ".sb-tmp-"
# What os.link raises on a volume that has no hard links.
NO_HARD_LINKS = frozenset({errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP})


def replace_file(path: Path, data: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f"{TEMP_PREFIX}{path.name}.")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def create_file(path: Path, data: bytes) -> bool:
    """Writes a new file whole; False, with nothing changed, when one exists under that name already.

    A volume without hard links (FAT, exFAT, SMB) gets the file by a rename once the name is seen
    free. That check and the rename are not one step, which is safe only because a name passed here
    has one writer: the worklog's notes are written by the curating machine, under the run's lock.
    """
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f"{TEMP_PREFIX}{path.name}.")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        try:
            os.link(temporary, path)
        except OSError as error:
            if error.errno not in NO_HARD_LINKS:
                raise
            if path.exists():
                return False
            os.replace(temporary, path)
    except FileExistsError:
        return False
    finally:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
    return True
