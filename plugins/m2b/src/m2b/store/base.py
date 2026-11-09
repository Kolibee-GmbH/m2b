"""The ``Store`` interface and the behavior both backends share.

Paths are relative to the store root, written with ``/``. Hidden files (a leading dot) are
not content: readers skip them, so a hidden temp file is never taken for a note.
"""

from __future__ import annotations

import errno
import shlex
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from m2b.atomic_file import create_exclusively, replace_atomically
from m2b.store.guard import DatalessGuard


class StoreError(Exception):
    """A store operation could not be done."""


class EvictedFileError(StoreError):
    """The file is only a placeholder on this machine; reading it would download it or hang."""

    def __init__(self, relative: str) -> None:
        self.relative = relative
        super().__init__(f"{relative} is not downloaded to this machine; run: {fetch_command(relative)}")


def fetch_command(relative: str) -> str:
    """The command that downloads an evicted file or folder, ready to paste into a shell."""
    return f"m2b store fetch {shlex.quote(relative)}"


class StoreReadError(StoreError):
    """A file is there but could not be read, for example after a privacy grant was withdrawn."""


class FetchError(StoreError):
    """Evicted files could not be downloaded in time."""


class UnsupportedStoreError(StoreError):
    """The folder cannot be used with this backend."""


class PathOutsideStoreError(ValueError):
    """A path that is empty, absolute or leaves the store."""


@dataclass(frozen=True)
class ConflictCopy:
    """A file a sync service made next to ``original``; only an identical copy may be removed."""

    path: str
    original: str
    identical: bool | None

    @property
    def removable(self) -> bool:
        return self.identical is True


@dataclass(frozen=True)
class Scan:
    """What a folder holds on this machine: the local files, and apart from them what is evicted."""

    files: list[str]
    evicted: list[str]


FETCH_POLL_SECONDS = 0.2
DEFAULT_FETCH_TIMEOUT_SECONDS = 60


class Store(ABC):
    def __init__(
        self,
        root: Path,
        temp_dir: Path,
        guard: DatalessGuard,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.root = root
        self.temp_dir = temp_dir
        self.guard = guard
        self._clock = clock
        self._sleep = sleep

    def path(self, relative: str) -> Path:
        """The absolute path of a store path; refuses anything that would leave the store."""
        parts = PurePosixPath(relative).parts
        if not relative or relative.startswith("/") or ".." in parts:
            raise PathOutsideStoreError(f"{relative!r} is not a path inside the store")
        return self.root.joinpath(*parts)

    def exists(self, relative: str) -> bool:
        return self.path(relative).exists()

    def is_evicted(self, relative: str) -> bool:
        return self.guard.is_evicted(self.path(relative))

    def check_local(self, relatives: Iterable[str]) -> list[str]:
        """The evicted files and folders among these paths; a folder stands for everything in it.

        An evicted folder is listed as the folder: its contents cannot be listed without
        downloading it.
        """
        evicted: list[str] = []
        for relative in relatives:
            evicted.extend(self._evicted_at(relative))
        return evicted

    def _evicted_at(self, relative: str) -> list[str]:
        target = self.path(relative)
        if not target.exists():
            return []
        if self.guard.is_evicted(target):
            return [relative]
        if target.is_symlink() or not target.is_dir():
            return []
        try:
            entries = self._visible_entries(relative)
        except EvictedFileError:
            return [relative]
        return [found for entry in entries for found in self._evicted_at(f"{relative}/{entry.name}")]

    def _visible_entries(self, relative: str) -> list[Path]:
        """The folder's entries without hidden ones, sorted; a folder that cannot be listed raises.

        Each level is listed here rather than with ``rglob``, which skips unreadable folders
        silently from Python 3.13 on.
        """
        folder = self.path(relative) if relative else self.root
        try:
            return sorted((entry for entry in folder.iterdir() if not entry.name.startswith(".")), key=_name)
        except OSError as error:
            if error.errno == errno.EDEADLK:
                raise EvictedFileError(relative or ".") from error
            raise StoreReadError(f"{relative or 'the store'} could not be listed: {error}") from error

    def read_bytes(self, relative: str) -> bytes:
        target = self.path(relative)
        if self.guard.is_evicted(target):
            raise EvictedFileError(relative)
        try:
            return target.read_bytes()
        except FileNotFoundError:
            raise
        except OSError as error:
            if error.errno == errno.EDEADLK:
                raise EvictedFileError(relative) from error
            raise StoreReadError(f"{relative} could not be read: {error}") from error

    def read_text(self, relative: str) -> str:
        return self.read_bytes(relative).decode("utf-8")

    def list_files(self, folder: str = "", recursive: bool = False) -> list[str]:
        """Visible files below ``folder`` as store paths, sorted; nothing for a missing folder.

        Folder symlinks are not followed. A folder that cannot be listed raises, so an evicted
        subfolder is never shown as empty.
        """
        base = self.path(folder) if folder else self.root
        if not base.is_dir():
            return []
        files = []
        for entry in self._visible_entries(folder):
            relative = entry.relative_to(self.root).as_posix()
            if entry.is_symlink() and entry.is_dir():
                continue
            if entry.is_dir():
                if recursive:
                    files.extend(self.list_files(relative, recursive=True))
            elif entry.is_file():
                files.append(relative)
        return sorted(files)

    def scan(self, folder: str) -> Scan:
        """The local files below ``folder`` and the evicted files and folders, in one walk.

        No file is opened, so nothing is downloaded. An evicted folder stands for everything in
        it, because its contents cannot be listed without downloading it. Hidden files and folder
        symlinks are left out as in ``list_files``; a missing folder holds nothing; ``""`` is the
        whole store.
        """
        files: list[str] = []
        evicted: list[str] = []
        self._scan_into(folder, files, evicted)
        return Scan(sorted(files), sorted(evicted))

    def _scan_into(self, relative: str, files: list[str], evicted: list[str]) -> None:
        target = self.path(relative) if relative else self.root
        if not target.is_dir():
            return
        if self.guard.is_evicted(target):
            evicted.append(relative)
            return
        try:
            entries = self._visible_entries(relative)
        except EvictedFileError:
            evicted.append(relative)
            return
        for entry in entries:
            child = f"{relative}/{entry.name}" if relative else entry.name
            try:
                if self.guard.is_evicted(entry):
                    evicted.append(child)
                elif entry.is_symlink() and entry.is_dir():
                    continue
                elif entry.is_dir():
                    self._scan_into(child, files, evicted)
                elif entry.is_file():
                    files.append(child)
            except FileNotFoundError:
                continue

    def create_exclusive(self, relative: str, data: bytes) -> None:
        """Creates a new file; raises ``FileExistsError`` and changes nothing if the name is taken."""
        target = self.path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        create_exclusively(target, data, self.temp_dir)

    def replace(self, relative: str, data: bytes) -> None:
        """Writes a file atomically; refused when the file on disk is only a placeholder."""
        target = self.path(relative)
        if target.exists() and self.guard.is_evicted(target):
            raise EvictedFileError(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        replace_atomically(target, data, self.temp_dir)

    def delete(self, relative: str) -> None:
        """Removes one file; an evicted file can be removed without downloading it."""
        target = self.path(relative)
        if target.is_dir():
            raise IsADirectoryError(f"{relative} is a folder")
        target.unlink()

    def fetch(self, relatives: Iterable[str], timeout_seconds: float) -> None:
        """Downloads everything evicted below these paths, or raises ``FetchError`` after the timeout.

        A downloaded folder can still hold evicted files, so the check repeats until nothing
        is left; each path is asked for once.
        """
        wanted = list(relatives)
        deadline = self._clock() + timeout_seconds
        requested: set[str] = set()
        while True:
            pending = self.check_local(wanted)
            if not pending:
                return
            if self._clock() >= deadline:
                raise FetchError(f"not downloaded after {timeout_seconds:g} seconds: {', '.join(pending)}")
            for relative in pending:
                if relative not in requested:
                    requested.add(relative)
                    self._start_download(relative, max(deadline - self._clock(), 0.0))
            self._sleep(FETCH_POLL_SECONDS)

    @abstractmethod
    def _start_download(self, relative: str, timeout_seconds: float) -> None:
        """Asks the sync service for one file; ``fetch`` then waits until it is local."""

    @abstractmethod
    def conflict_copies(self, folder: str = "") -> list[ConflictCopy]:
        """Conflict copies below ``folder`` that this backend's sync service names its own way."""


def _name(entry: Path) -> str:
    return entry.name
