"""The ``Store`` interface and the behavior both backends share.

Paths are relative to the store root, written with ``/``. Hidden files (a leading dot) are
not content: readers skip them, so a hidden temp file is never taken for a note. A symlink is not
content either, and no way to content: a listing passes it over, and a path that is one or leads
through one is neither read nor written (``m2b.store.symlinks`` says why).
"""

from __future__ import annotations

import contextlib
import errno
import shlex
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from m2b.atomic_file import create_exclusively, replace_atomically
from m2b.store import symlinks
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


class SymlinkError(StoreReadError):
    """The path is a symlink or leads through one; below its root the store follows none.

    A read error, so that a reader which lists a file it could not read and goes on does so here too.
    """

    def __init__(self, relative: str, link: str) -> None:
        self.relative = relative
        self.link = link
        left_alone = "" if link == relative else f"{relative} was left alone: "
        super().__init__(
            f"{left_alone}{link} is a symlink, and m2b follows none in the store; "
            "put the file or folder itself in its place, or remove it"
        )


class FetchError(StoreError):
    """Evicted files could not be downloaded in time."""


class DownloadTimeoutError(FetchError):
    """One file did not download within its share of the time; ``fetch`` goes on with the others."""


class UnsupportedStoreError(StoreError):
    """The folder cannot be used with this backend."""


class PathOutsideStoreError(ValueError):
    """A path that is empty, absolute or leaves the store."""


@dataclass(frozen=True)
class ConflictCopy:
    """A file a sync service made next to ``original``; only an identical copy may be removed.

    ``identical`` is None when the two were not compared: one is evicted or cannot be read.
    """

    path: str
    original: str
    identical: bool | None

    @property
    def removable(self) -> bool:
        return self.identical is True


@dataclass(frozen=True)
class Scan:
    """What a folder holds on this machine: the local files, and apart from them what is evicted.

    ``symlinks`` are the symlinks met on the way, which are in neither list: nothing reads them.
    """

    files: list[str]
    evicted: list[str]
    symlinks: list[str] = field(default_factory=list)


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
        """The absolute path of a store path; refuses a spelling that would leave the store.

        A symlink on the way would leave it too; that is refused where the path is read or written.
        """
        parts = PurePosixPath(relative).parts
        if not relative or relative.startswith("/") or ".." in parts:
            raise PathOutsideStoreError(f"{relative!r} is not a path inside the store")
        return self.root.joinpath(*parts)

    def exists(self, relative: str) -> bool:
        """Whether the name is taken; for a symlink, whether its target is there, of which nothing else is told."""
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
            if symlinks.symlink_on(self.root, relative) is None:
                evicted.extend(self._evicted_at(relative))
        return evicted

    def _evicted_at(self, relative: str) -> list[str]:
        target = self.path(relative)
        if target.is_symlink() or not target.exists():
            return []
        if self.guard.is_evicted(target):
            return [relative]
        if not target.is_dir():
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

    def _refuse_symlinks(self, relative: str, folders_only: bool = False) -> None:
        """Raises when the path is a symlink or leads through one; ``folders_only`` lets the name itself be one.

        A write replaces or removes the name, whatever it is, and so stays in the store; only a
        symlinked folder on the way to it would take the write elsewhere.
        """
        checked = PurePosixPath(relative).parent.as_posix() if folders_only else relative
        link = symlinks.symlink_on(self.root, checked)
        if link is not None:
            raise SymlinkError(relative, link)

    def read_bytes(self, relative: str) -> bytes:
        target = self.path(relative)
        self._refuse_symlinks(relative)
        if self.guard.is_evicted(target):
            raise EvictedFileError(relative)
        try:
            # Opened past no symlink: one slipped in since the check above fails the read like any other error.
            return symlinks.read_bytes(self.root, relative)
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

        Symlinks are neither listed nor followed, and a folder that is one or lies behind one holds
        nothing. A folder that cannot be listed raises, so an evicted subfolder is never shown as
        empty.
        """
        base = self.path(folder) if folder else self.root
        if symlinks.symlink_on(self.root, folder) is not None or not base.is_dir():
            return []
        files = []
        for entry in self._visible_entries(folder):
            relative = entry.relative_to(self.root).as_posix()
            if entry.is_symlink():
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
        it, because its contents cannot be listed without downloading it. Hidden files are left out
        as in ``list_files``, and symlinks are named apart, the one ``folder`` lies behind too; a
        missing folder holds nothing; ``""`` is the whole store.
        """
        link = symlinks.symlink_on(self.root, folder)
        if link is not None:
            return Scan([], [], [link])
        files: list[str] = []
        evicted: list[str] = []
        links: list[str] = []
        self._scan_into(folder, files, evicted, links)
        return Scan(sorted(files), sorted(evicted), sorted(links))

    def _scan_into(self, relative: str, files: list[str], evicted: list[str], links: list[str]) -> None:
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
                if entry.is_symlink():
                    links.append(child)
                elif self.guard.is_evicted(entry):
                    evicted.append(child)
                elif entry.is_dir():
                    self._scan_into(child, files, evicted, links)
                elif entry.is_file():
                    files.append(child)
            except FileNotFoundError:
                continue

    def make_folder(self, relative: str) -> None:
        """Makes a folder and the folders on the way to it; one that is there stays as it is."""
        target = self.path(relative)
        self._refuse_symlinks(relative)
        target.mkdir(parents=True, exist_ok=True)

    def create_exclusive(self, relative: str, data: bytes) -> None:
        """Creates a new file; raises ``FileExistsError`` and changes nothing if the name is taken."""
        target = self.path(relative)
        self._refuse_symlinks(relative, folders_only=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        create_exclusively(target, data, self.temp_dir)

    def replace(self, relative: str, data: bytes) -> None:
        """Writes a file atomically; refused when the file on disk is only a placeholder."""
        target = self.path(relative)
        self._refuse_symlinks(relative, folders_only=True)
        if target.exists() and self.guard.is_evicted(target):
            raise EvictedFileError(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        replace_atomically(target, data, self.temp_dir)

    def delete(self, relative: str) -> None:
        """Removes one file; an evicted file can be removed without downloading it."""
        target = self.path(relative)
        self._refuse_symlinks(relative, folders_only=True)
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
            # Each new request gets an equal share of the time left: a download that waits for its
            # file (a folder store) must not use up the time of the paths after it.
            new = [relative for relative in pending if relative not in requested]
            for index, relative in enumerate(new):
                requested.add(relative)
                share = max(deadline - self._clock(), 0.0) / (len(new) - index)
                with contextlib.suppress(DownloadTimeoutError):
                    self._start_download(relative, share)
            self._sleep(FETCH_POLL_SECONDS)

    @abstractmethod
    def _start_download(self, relative: str, timeout_seconds: float) -> None:
        """Asks the sync service for one file; ``fetch`` then waits until it is local."""

    def conflict_copies(self, folder: str = "") -> list[ConflictCopy]:
        """Files below ``folder`` that the sync service named as a copy of a file still next to them.

        The name alone proves little: every service's name for a copy is one a person could give
        a file. So a file counts only while the file it names as its original is there, and a
        caller may remove it only when ``identical`` is true.
        """
        copies = []
        # scan, not a recursive listing: an evicted folder is skipped instead of failing the whole walk,
        # while an evicted file stays a copy, so callers keep leaving it alone.
        scan = self.scan(folder)
        evicted_files = [relative for relative in scan.evicted if not self.path(relative).is_dir()]
        for relative in sorted([*scan.files, *evicted_files]):
            parent, _, name = relative.rpartition("/")
            original_name = self._original_name(name)
            if original_name is None:
                continue
            original = f"{parent}/{original_name}" if parent else original_name
            # Not a symlink: one that points at the copy would compare equal to it, and removing the
            # copy would then remove the only bytes.
            if self.path(original).is_file() and not self.path(original).is_symlink():
                copies.append(ConflictCopy(relative, original, self._same_bytes(relative, original)))
        return copies

    def _same_bytes(self, first: str, second: str) -> bool | None:
        """None when the two cannot be compared: one is evicted, where comparing would mean
        downloading, or cannot be read, or is gone since the folder was listed. One such pair must not
        end the walk for all the others.
        """
        try:
            if self.is_evicted(first) or self.is_evicted(second):
                return None
            return self.read_bytes(first) == self.read_bytes(second)
        except (StoreError, FileNotFoundError):
            return None

    @abstractmethod
    def _original_name(self, name: str) -> str | None:
        """The name of the file that ``name`` would be a conflict copy of, or None for any other name.

        Asked by ``conflict_copies`` for every file name; it knows how this backend's sync
        service names a copy and looks at nothing but the name.
        """


def _name(entry: Path) -> str:
    return entry.name
