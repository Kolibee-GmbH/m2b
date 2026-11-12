"""Writing a file whole and telling an evicted one, by the core's rules.

How a file reaches a synced folder without the sync service seeing half of it or a leftover, and
how a file whose content is only in the cloud is told from one that is here, is the core's
knowledge (``m2b.atomic_file``, ``m2b.store.guard``) and exists once, there. A file in the store is
written through a temporary file in the machine's temp folder (``WorklogPaths.temp_dir``); a file
on this machine, outside the store, through a hidden one beside it.
"""

from __future__ import annotations

from pathlib import Path

from m2b.atomic_file import create_exclusively, replace_atomically
from m2b.store.guard import guard_for_platform


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


def is_evicted(path: Path) -> bool:
    """Whether the file's content is only in the cloud, where reading it would download it or hang."""
    return guard_for_platform().is_evicted(path)
