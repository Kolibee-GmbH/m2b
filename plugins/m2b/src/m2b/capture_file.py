"""A file from a session: copied into ``inbox/`` as a bundle, the file itself and the note beside it.

The bundle has the form a curation run makes of a file dropped into the inbox (``ingest.normalize``):
the file under a schema name, and beside it a note with ``kind: sidecar`` that says what the file is,
the words it came with and its original name. So the next run reads both, and the original stays
where it is.

The command is its own, ``m2b capture-file``, and no skill may run it without asking: a session that
follows text it read could otherwise copy any file of the machine into a folder that syncs. So it
also refuses, in one line and before anything is written, a path that is not absolute, a folder, a
symbolic link, a file over the size ``capture.file_limit_mb`` names, a text file (its words are a
capture of their own) and a name that would break the note's lines.
"""

from __future__ import annotations

import datetime
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from m2b.capture import NAME_ATTEMPTS, NotSavedError
from m2b.ingest import TEXT_EXTENSIONS, schema_extension, sidecar_note
from m2b.notes import layout
from m2b.notes.names import NoteName
from m2b.store.base import Store

MEGABYTE = 1024 * 1024
_BREAKS_A_LINE = ("\n", "\r", "\x00", "\u2028", "\u2029")


class CaptureFileRefusedError(ValueError):
    """The path is no file m2b copies; nothing was written. The message is one line."""


@dataclass(frozen=True)
class CapturedFile:
    # The store paths of the note and of the copy, both in ``inbox/``.
    note: str
    file: str


def capture_file(
    store: Store,
    path: Path,
    words: str,
    source: str,
    limit_mb: int,
    now: datetime.datetime | None = None,
) -> CapturedFile:
    """Copies the file at ``path`` into the inbox with ``words`` in the note beside it.

    Raises ``CaptureFileRefusedError`` before anything is written for a path m2b does not copy,
    ``ValueError`` for a source that is no capture's, and ``NotSavedError`` when the inbox cannot be
    written; a note written for a copy that then failed is removed again.
    """
    name = _checked_name(path)
    data = _read(path, limit_mb)
    created = (now or datetime.datetime.now()).astimezone().replace(microsecond=0)
    extension = schema_extension(name)
    try:
        note_path, file_path = _write_note(store, created, source, extension, name, words)
        try:
            store.create_exclusive(file_path, data)
        except OSError:
            store.delete(note_path)
            raise
    except OSError as error:
        raise NotSavedError(f"the file was not captured: {error.strerror or error} in {layout.INBOX}") from error
    return CapturedFile(note_path, file_path)


def _checked_name(path: Path) -> str:
    if not path.is_absolute():
        raise CaptureFileRefusedError(f"{path} is not an absolute path: give the file's whole path")
    name = path.name
    if any(character in name for character in _BREAKS_A_LINE):
        raise CaptureFileRefusedError(f"{name!r}: a file name that breaks a line cannot stand in its note")
    # The extension as the copy's name takes it, after the last dot: `.txt` alone is a text file too.
    if f".{schema_extension(name).lower()}" in TEXT_EXTENSIONS:
        raise CaptureFileRefusedError(f"{name} is a text file: capture its words with m2b capture")
    return name


def _read(path: Path, limit_mb: int) -> bytes:
    """The file's bytes, opened without following a link, and refused over the limit by its size as opened."""
    try:
        found = os.lstat(path)
    except FileNotFoundError:
        raise CaptureFileRefusedError(f"there is no file at {path}") from None
    except OSError as error:
        raise CaptureFileRefusedError(f"{path} cannot be read: {error.strerror or error}") from error
    if stat.S_ISLNK(found.st_mode):
        raise CaptureFileRefusedError(f"{path} is a symbolic link, which m2b never follows; give the file it points to")
    if stat.S_ISDIR(found.st_mode):
        raise CaptureFileRefusedError(f"{path} is a folder: give one file")
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0))
    except OSError as error:
        raise CaptureFileRefusedError(f"{path} cannot be read: {error.strerror or error}") from error
    with os.fdopen(descriptor, "rb") as file:
        opened = os.fstat(file.fileno())
        if not stat.S_ISREG(opened.st_mode):
            raise CaptureFileRefusedError(f"{path} is not a file m2b copies: give a document or a picture")
        limit = limit_mb * MEGABYTE
        if opened.st_size > limit:
            raise CaptureFileRefusedError(_over_the_limit(path, opened.st_size, limit_mb))
        data = file.read(limit + 1)
    if len(data) > limit:
        raise CaptureFileRefusedError(_over_the_limit(path, len(data), limit_mb))
    return data


def _over_the_limit(path: Path, size: int, limit_mb: int) -> str:
    return (
        f"{path.name} is {size / MEGABYTE:.1f} MB, over the {limit_mb} MB capture.file_limit_mb allows; "
        "m2b config set capture.file_limit_mb <megabytes> raises it"
    )


def _write_note(
    store: Store, created: datetime.datetime, source: str, extension: str, original: str, words: str
) -> tuple[str, str]:
    """Writes the note first, under a name no file of the inbox has yet: it is where the original name survives."""
    for _ in range(NAME_ATTEMPTS):
        stem = str(NoteName.for_capture(created, source)).rsplit(".", 1)[0]
        note_path, file_path = f"{layout.INBOX}/{stem}.md", f"{layout.INBOX}/{stem}.{extension}"
        if store.exists(file_path):
            continue
        note = sidecar_note(f"{stem}.{extension}", original, created, words)
        try:
            store.create_exclusive(note_path, note.render().encode("utf-8"))
        except FileExistsError:
            continue
        return note_path, file_path
    raise FileExistsError(f"no free capture name in {layout.INBOX}/ after {NAME_ATTEMPTS} attempts")
