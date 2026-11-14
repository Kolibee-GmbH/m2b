"""No symlink below the store's root is ever followed.

A store is written by more than this machine: a sync service brings what other devices and
integrations put there. A reader that followed a symlink would take a file anywhere on this
machine for a note, and a writer would write there. So below the root a symlink is neither content
nor a way to content: listings pass it over, a path that is one or leads through one is refused,
and lint names it. The root itself may be reached through symlinks: it is the folder this
machine's own config names.

How a symlink is told and how a file is read past none exists once, here: for the store of every
backend, and for the worklog add-on, which reads its files in the store by their path.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath


def symlink_on(root: Path, relative: str) -> str | None:
    """The first symlink on the way from the root to ``relative``, the path itself included.

    As a store path; None when the way holds none. Only the entries themselves are looked at, so
    nothing is opened or downloaded.
    """
    parts = PurePosixPath(relative).parts
    reached = root
    for count, part in enumerate(parts, start=1):
        reached = reached / part
        if reached.is_symlink():
            return "/".join(parts[:count])
    return None


def read_bytes(root: Path, relative: str) -> bytes:
    """The file's bytes, opened folder by folder so that no symlink below the root is followed.

    Each step is opened relative to the folder before it and refuses a symlink, so one that takes
    the place of a folder or of the file between a check and this read is not followed either.
    Raises ``OSError`` as any read does; which error a symlink gives differs by platform, and
    ``symlink_on`` tells whether one was the cause.
    """
    *folders, name = PurePosixPath(relative).parts
    folder = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in folders:
            inner = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=folder)
            os.close(folder)
            folder = inner
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=folder)
    finally:
        os.close(folder)
    with os.fdopen(descriptor, "rb") as file:
        return file.read()
