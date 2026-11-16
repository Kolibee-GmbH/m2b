"""A PDF or a picture of the archive, opened in the system's viewer: the pane's ``open the file``.

Only a PDF or a picture opens, because a viewer for them shows the file without running anything
it holds; a browser on an HTML page or a script someone sent would. The kind is told by the name
and checked against the file's first bytes, since a viewer on Linux may choose by what the bytes
say and a page named ``.pdf`` would then open in a browser.

It takes the file's name and never a path, and finds it by listing ``corpus/``: only a file of the
archive is reached, never one of the inbox, the config or the machine. A file that lives only in
the cloud is named with the command that fetches it, and a symbolic link is not followed.

It opens only where the session has a screen: on a Mac, unless the session runs over SSH, where
the file would open on a screen nobody at the session sees; on Linux where a display is named.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Callable, Optional

from m2b.notes.layout import CORPUS
from m2b.notes.names import NoteName
from m2b.source import SourceNotFoundError
from m2b.store.base import EvictedFileError, Store, StoreReadError, SymlinkError, fetch_command

MAC_OPEN = "/usr/bin/open"
LINUX_OPEN = "xdg-open"
# A viewer started by `open` hands over and ends at once; xdg-open may stay as long as the viewer.
VIEWER_WAIT_SECONDS = 5.0

# Two letters alone would let a page pass as a bitmap; its header names its own size, one of these.
_BMP_HEADER_SIZES = frozenset({12, 40, 52, 56, 64, 108, 124})
# SVG is a picture that may hold scripts, and no viewer here is needed for it.
_FIRST_BYTES: dict[str, Callable[[bytes], bool]] = {
    # At the start, as `file` looks for it: a page with `%PDF-` further in is a page to `xdg-open`.
    ".pdf": lambda head: head.startswith(b"%PDF-"),
    ".jpg": lambda head: head.startswith(b"\xff\xd8\xff"),
    ".jpeg": lambda head: head.startswith(b"\xff\xd8\xff"),
    ".png": lambda head: head.startswith(b"\x89PNG\r\n\x1a\n"),
    ".gif": lambda head: head[:6] in (b"GIF87a", b"GIF89a"),
    ".webp": lambda head: head[:4] == b"RIFF" and head[8:12] == b"WEBP",
    ".heic": lambda head: head[4:8] == b"ftyp",
    ".heif": lambda head: head[4:8] == b"ftyp",
    ".tif": lambda head: head[:4] in (b"II*\x00", b"MM\x00*"),
    ".tiff": lambda head: head[:4] in (b"II*\x00", b"MM\x00*"),
    ".bmp": lambda head: head.startswith(b"BM") and int.from_bytes(head[14:18], "little") in _BMP_HEADER_SIZES,
}
VIEWABLE_EXTENSIONS = frozenset(_FIRST_BYTES)
_HEAD_BYTES = 32

ONLY_PDF_AND_PICTURES = "m2b opens only a PDF or a picture: a viewer for any other kind can run what the file holds"
_NOT_A_NAME = ("/", "\\", "\x00", "\n", "\r")

Launch = Callable[[list[str]], Optional[int]]


class OpenRefusedError(ValueError):
    """The name is no name of a PDF or a picture of the archive; nothing was read."""


class NotOpenedError(Exception):
    """The file is there and was not opened; the message says why."""


class NoScreenError(NotOpenedError):
    """This session has no screen the file could open on."""


def launch(command: list[str]) -> int | None:
    """Starts the viewer apart from this process; its exit, or None while it still runs."""
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as error:
        raise NotOpenedError(f"could not start {command[0]}: {error.strerror or error}") from error
    try:
        return process.wait(timeout=VIEWER_WAIT_SECONDS)
    except subprocess.TimeoutExpired:
        return None


def screen_command(environ: Mapping[str, str], platform: str) -> list[str]:
    """The command that opens a file on this session's screen; ``NoScreenError`` says why there is none."""
    if platform == "darwin":
        if environ.get("SSH_CONNECTION") or environ.get("SSH_TTY"):
            raise NoScreenError("this session runs over SSH: the file would open on a screen nobody at it sees")
        return [MAC_OPEN]
    if platform.startswith("linux"):
        if not (environ.get("DISPLAY") or environ.get("WAYLAND_DISPLAY")):
            raise NoScreenError("this session has no screen: neither DISPLAY nor WAYLAND_DISPLAY is set")
        found = shutil.which(LINUX_OPEN, path=environ.get("PATH"))
        if found is None:
            raise NoScreenError(f"{LINUX_OPEN} is not installed, which opens a file in its viewer on Linux")
        return [found]
    raise NoScreenError("m2b opens a file only on macOS and Linux")


def why_not_opened(original: str, here: bool, environ: Mapping[str, str], platform: str | None = None) -> str | None:
    """Why ``open_original`` would not open this file of the archive, or None where it would, as far
    as can be told without reading it."""
    if PurePosixPath(original).suffix.lower() not in VIEWABLE_EXTENSIONS:
        return ONLY_PDF_AND_PICTURES
    if not here:
        return f"not downloaded to this machine; {fetch_command(original)} fetches it"
    try:
        screen_command(environ, platform or sys.platform)
    except NoScreenError as error:
        return str(error)
    return None


def open_original(
    store: Store,
    name: str,
    environ: Mapping[str, str],
    platform: str | None = None,
    start: Launch | None = None,
) -> str:
    """Opens the PDF or picture of the archive named ``name`` in the system's viewer; its store path.

    Raises ``OpenRefusedError`` before anything is listed for a name that is no such file's,
    ``SourceNotFoundError`` when the archive holds none of this name, and ``NotOpenedError`` when it
    is there and does not open: not on this machine, a symbolic link, bytes of another kind, no
    screen, or a viewer that failed.
    """
    note_name, suffix = _checked(name)
    relative = _located(store, name, note_name)
    command = screen_command(environ, platform or sys.platform)
    try:
        head = store.read_bytes(relative)[:_HEAD_BYTES]
    except EvictedFileError as error:
        raise NotOpenedError(f"not downloaded to this machine; {fetch_command(relative)} fetches it") from error
    except SymlinkError as error:
        raise NotOpenedError(f"{relative} is a symbolic link, which m2b never follows") from error
    except StoreReadError as error:
        raise NotOpenedError(str(error)) from error
    except FileNotFoundError as error:
        raise SourceNotFoundError(f"{relative} was moved away while it was read") from error
    if not _FIRST_BYTES[suffix](head):
        raise NotOpenedError(f"{relative} is not a {suffix[1:]} file as its name says, so it is not opened")
    exit_code = (start or launch)([*command, str(store.path(relative))])
    if exit_code not in (0, None):
        raise NotOpenedError(f"{command[0]} ended with exit {exit_code}")
    return relative


def _checked(name: str) -> tuple[NoteName, str]:
    """The name's parts and its extension, lower case; refuses every name that is no PDF's or
    picture's of the archive."""
    if not name or any(character in name for character in _NOT_A_NAME):
        raise OpenRefusedError(f"{name!r} is not a file's name: give the name alone, never a path")
    note_name = NoteName.parse(name)
    if note_name is None:
        raise OpenRefusedError(f"{name!r} is no file of the archive")
    suffix = PurePosixPath(name).suffix.lower()
    if suffix not in VIEWABLE_EXTENSIONS:
        raise OpenRefusedError(ONLY_PDF_AND_PICTURES)
    return note_name, suffix


def _located(store: Store, name: str, note_name: NoteName) -> str:
    """Where the file lies in ``corpus/``, found by listing, which opens no file."""
    corpus = store.scan(CORPUS)
    for path in corpus.files:
        if PurePosixPath(path).name == name:
            return path
    for path in corpus.symlinks:
        if PurePosixPath(path).name == name:
            raise NotOpenedError(f"{path} is a symbolic link, which m2b never follows")
    month = f"{CORPUS}/{note_name.time:%Y}/{note_name.time:%m}"
    for entry in corpus.evicted:
        # A month that lives only in the cloud is listed as the folder: its files cannot be named.
        if PurePosixPath(entry).name == name or month == entry or month.startswith(entry + "/"):
            raise NotOpenedError(f"not downloaded to this machine; {fetch_command(entry)} fetches it")
    raise SourceNotFoundError(f"no file of the archive is named {name}")
