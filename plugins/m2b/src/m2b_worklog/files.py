"""Writing a file whole, telling an evicted one and reading past no symlink, by the core's rules.

How a file reaches a synced folder without the sync service seeing half of it or a leftover, how
a file whose content is only in the cloud is told from one that is here, and how a symlink in the
store is told and a file read past none, is the core's knowledge (``m2b.atomic_file``,
``m2b.store.guard``, ``m2b.store.symlinks``) and exists once, there. A file in the store is
written through a temporary file in the machine's temp folder (``WorklogPaths.temp_dir``); a file
on this machine, outside the store, through a hidden one beside it.
"""

from __future__ import annotations

from pathlib import Path

from m2b.atomic_file import create_exclusively, replace_atomically
from m2b.store.guard import guard_for_platform
from m2b.store.symlinks import read_bytes, symlink_on


def replace_file(path: Path, data: bytes) -> None:
    """Replaces a file on this machine, outside the store."""
    replace_atomically(path, data, path.parent)


def replace_in_store(path: Path, data: bytes, temp_dir: Path) -> None:
    replace_atomically(path, data, temp_dir)


def create_in_store(path: Path, data: bytes, temp_dir: Path) -> bool:
    """Writes a new file; False, with nothing changed, when one exists under that name already."""
    try:
        create_exclusively(path, data, temp_dir)
    except FileExistsError:
        return False
    return True


def symlink_in_store(store: Path, relative: str) -> str | None:
    """The first symlink on the way to a path of the store, as a store path; None when there is none."""
    return symlink_on(store, relative)


def read_in_store(store: Path, relative: str) -> bytes:
    """A file of the store by its store path, opened past no symlink; one on the way raises ``OSError``."""
    return read_bytes(store, relative)


def is_evicted(path: Path) -> bool:
    """Whether the file's content is only in the cloud, where reading it would download it or hang."""
    return guard_for_platform().is_evicted(path)
