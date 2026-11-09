"""The snapshot of the store in the target folder: a mirror, an attic of what the mirror replaced, a task dump.

The target holds three things::

    <target>/mirror/          the store's visible files as of the last backup
    <target>/attic/YYYY-MM-DD/ each mirror file a backup replaced or removed, under that day
    <target>/tasks.json       the task list with completed tasks, as ``m2b tasks list`` gave it

Hidden files and folders (a part starting with ``.``, such as the product's temp files and
iCloud's own) and Excel's lock files (``~$<name>``) are not copied. A file iCloud Drive has not
downloaded (evicted) is never read, because reading would download it or hang: the mirror keeps
the copy it has, and the backup counts it (B27). The same holds for a folder that is evicted or
cannot be listed (under a curation run, listing an evicted folder fails, because the run turns
downloading off): its files are unknown, not gone, so their mirror copies stay where they are.
An attic folder older than ``attic_days`` is removed, the only thing the part deletes besides
what it moves into the attic.
"""

from __future__ import annotations

import contextlib
import datetime
import filecmp
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

MIRROR = "mirror"
ATTIC = "attic"
TASK_DUMP = "tasks.json"
TEMP_PREFIX = ".sb-tmp-"
# macOS marks a file whose contents live only in the cloud (sys/stat.h SF_DATALESS).
SF_DATALESS = 0x40000000


@dataclass
class Result:
    copied: int = 0
    unchanged: int = 0
    to_attic: int = 0
    evicted: list[str] = field(default_factory=list)
    unread: list[str] = field(default_factory=list)
    pruned: list[str] = field(default_factory=list)


def is_evicted(path: Path) -> bool:
    try:
        return bool(getattr(os.lstat(path), "st_flags", 0) & SF_DATALESS)
    except OSError:
        return False


def is_copied(relative: Path) -> bool:
    """Whether a store path belongs in the mirror: nothing hidden, no Excel lock file."""
    return not any(part.startswith(".") for part in relative.parts) and not relative.name.startswith("~$")


class UnlistableStoreError(Exception):
    """The store's own folder cannot be listed, so nothing in it is known."""


class Listing:
    def __init__(self, files: list[Path], unread: list[Path]) -> None:
        self.files, self.unread = files, unread
        self._seen = frozenset(files)

    def holds(self, relative: Path) -> bool:
        """Whether the store may still hold this path: it was seen, or it lies in a folder not read."""
        return relative in self._seen or any(folder in relative.parents for folder in self.unread)


def list_store(store: Path) -> Listing:
    """The store's files that belong in the mirror, relative to the store, and the folders not read.

    Symbolic links are not followed. A folder that is evicted is not entered; one that cannot be
    listed is reported by ``os.walk`` through ``onerror``. Both count as not read.
    """
    files: list[Path] = []
    unread: list[Path] = []

    def failed(error: OSError) -> None:
        unread.append(Path(error.filename).relative_to(store) if error.filename else Path("."))

    for folder, folders, names in os.walk(store, onerror=failed):
        base = Path(folder)
        entered = []
        for name in sorted(folders):
            if name.startswith("."):
                continue
            if is_evicted(base / name):
                unread.append((base / name).relative_to(store))
            else:
                entered.append(name)
        folders[:] = entered
        for name in sorted(names):
            path = base / name
            relative = path.relative_to(store)
            if is_copied(relative) and not path.is_symlink() and path.is_file():
                files.append(relative)
    if Path(".") in unread:
        raise UnlistableStoreError(f"the store {store} cannot be listed")
    return Listing(files, sorted(unread))


def mirror(store: Path, target: Path, today: datetime.date) -> Result:
    result = Result()
    mirrored = target / MIRROR
    attic = target / ATTIC / today.isoformat()
    _remove_leftover_temp_files(mirrored)
    listing = list_store(store)
    result.unread = [folder.as_posix() for folder in listing.unread]
    for relative in listing.files:
        source, copy = store / relative, mirrored / relative
        if is_evicted(source):
            result.evicted.append(relative.as_posix())
            continue
        if copy.is_file() and filecmp.cmp(source, copy, shallow=False):
            result.unchanged += 1
            continue
        if copy.exists():
            _to_attic(copy, attic / relative)
            result.to_attic += 1
        _copy(source, copy)
        result.copied += 1
    for relative in _mirrored_files(mirrored):
        if not listing.holds(relative):
            _to_attic(mirrored / relative, attic / relative)
            result.to_attic += 1
    _remove_empty_folders(mirrored)
    return result


def prune(target: Path, today: datetime.date, attic_days: int) -> list[str]:
    """Removes the attic's day folders older than ``attic_days``; any other name there is left alone."""
    removed = []
    cutoff = today - datetime.timedelta(days=attic_days)
    attic = target / ATTIC
    for day in sorted(attic.iterdir()) if attic.is_dir() else []:
        try:
            date = datetime.date.fromisoformat(day.name)
        except ValueError:
            continue
        if day.is_dir() and date < cutoff:
            shutil.rmtree(day)
            removed.append(day.name)
    return removed


def write_dump(target: Path, data: bytes) -> None:
    _replace(target / TASK_DUMP, data)


def _mirrored_files(mirrored: Path) -> list[Path]:
    if not mirrored.is_dir():
        return []
    found = (p.relative_to(mirrored) for p in mirrored.rglob("*") if p.is_file() or p.is_symlink())
    return sorted(relative for relative in found if is_copied(relative))


def _remove_leftover_temp_files(mirrored: Path) -> None:
    """A copy a crash cut off: only this part's own temporary files, never a hidden file of the owner's."""
    if mirrored.is_dir():
        for leftover in mirrored.rglob(f"{TEMP_PREFIX}*"):
            with contextlib.suppress(OSError):
                leftover.unlink()


def _copy(source: Path, copy: Path) -> None:
    """Copies whole: the bytes go to a temporary file beside the copy, which then replaces it."""
    copy.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=copy.parent, prefix=f"{TEMP_PREFIX}{copy.name}.")
    os.close(descriptor)
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, copy)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def _replace(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f"{TEMP_PREFIX}{path.name}.")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def _to_attic(copy: Path, place: Path) -> None:
    """Moves a mirror file into today's attic; a second one of the same name that day gets a number."""
    place.parent.mkdir(parents=True, exist_ok=True)
    candidate, number = place, 2
    while candidate.exists() or candidate.is_symlink():
        candidate = place.with_name(f"{place.stem} ({number}){place.suffix}")
        number += 1
    os.replace(copy, candidate)


def _remove_empty_folders(mirrored: Path) -> None:
    if not mirrored.is_dir():
        return
    for folder, _, _ in sorted(os.walk(mirrored), key=lambda entry: len(entry[0]), reverse=True):
        if Path(folder) != mirrored:
            with contextlib.suppress(OSError):
                os.rmdir(folder)
