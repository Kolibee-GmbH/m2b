"""Reading many text files under the guard: for search, rediscover and later lint (B6).

The check and the read happen in this one process with materialization off. A file that is
evicted, or becomes evicted between the check and the read, is listed apart and never read. An
evicted file of another type is not listed, because a reader of text would skip it anyway; an
evicted folder is, because it can hold text files.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath

from m2b.store.base import EvictedFileError, Store, StoreReadError

TEXT_SUFFIXES = frozenset({".md", ".txt"})


@dataclass(frozen=True)
class Unreadable:
    path: str
    reason: str


@dataclass(frozen=True)
class TextFile:
    path: str
    text: str


@dataclass(frozen=True)
class TextFiles:
    files: list[TextFile]
    evicted: list[str]
    unreadable: list[Unreadable]


def read_text_files(store: Store, folders: Iterable[str], suffixes: Collection[str] = TEXT_SUFFIXES) -> TextFiles:
    """The text files below ``folders``, folder by folder in the order given, decoded as UTF-8.

    Bytes that are no UTF-8 are replaced, never fatal. A file that is moved away while reading is
    skipped; one that cannot be read is listed with its reason. A folder that cannot be listed
    raises ``StoreError``, so a store that could not be read never looks like an empty one.
    """
    files: list[TextFile] = []
    evicted: list[str] = []
    unreadable: list[Unreadable] = []
    for folder in folders:
        scan = store.scan(folder)
        evicted.extend(path for path in scan.evicted if _has_suffix(path, suffixes) or store.path(path).is_dir())
        for relative in scan.files:
            if not _has_suffix(relative, suffixes):
                continue
            try:
                data = store.read_bytes(relative)
            except EvictedFileError:
                evicted.append(relative)
                continue
            except FileNotFoundError:
                continue
            except StoreReadError as error:
                unreadable.append(Unreadable(relative, str(error)))
                continue
            files.append(TextFile(relative, data.decode("utf-8", errors="replace")))
    return TextFiles(files, sorted(evicted), unreadable)


def _has_suffix(relative: str, suffixes: Collection[str]) -> bool:
    return PurePosixPath(relative).suffix.lower() in suffixes
