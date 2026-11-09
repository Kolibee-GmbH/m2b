"""Writing a file so that a reader sees either nothing, the old content or the new content.

Temp files live in the machine's temp folder, so a synced store never sees them. When the
final rename or link would cross volumes, the content goes into a hidden temp file next to
the target instead, which readers skip because it is hidden.
"""

from __future__ import annotations

import ctypes
import errno
import os
import secrets
import stat
import sys
from collections.abc import Callable
from pathlib import Path

HIDDEN_TEMP_PREFIX = ".sb-tmp-"

_NO_HARD_LINKS = frozenset({errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP})
_RENAME_EXCL = 0x00000004
_RENAME_NOREPLACE = 1
_AT_FDCWD = -100


def write_text_atomically(target: Path, text: str, temp_dir: Path) -> None:
    replace_atomically(target, text.encode("utf-8"), temp_dir)


def replace_atomically(target: Path, data: bytes, temp_dir: Path) -> None:
    """Writes ``data`` over ``target``; an existing target keeps its mode."""
    _place(target, data, temp_dir, _existing_mode(target), os.replace)


def create_exclusively(target: Path, data: bytes, temp_dir: Path) -> None:
    """Creates ``target`` with ``data``; raises ``FileExistsError`` and changes nothing if it exists.

    The file appears complete or not at all: the content is written to a temp file first and
    then hard-linked to the target name, which fails when that name is taken. A volume without
    hard links (FAT, exFAT, SMB) gets an exclusive rename instead.
    """
    _place(target, data, temp_dir, None, _link_exclusively)


def _link_exclusively(source: Path, target: Path) -> None:
    try:
        os.link(source, target)
    except OSError as error:
        if error.errno not in _NO_HARD_LINKS:
            raise
        _rename_exclusively(source, target)


def _rename_exclusively(source: Path, target: Path) -> None:
    """Renames without replacing: ``renamex_np`` on macOS, ``renameat2`` on Linux."""
    libc = ctypes.CDLL(None, use_errno=True)
    encoded_source, encoded_target = os.fsencode(source), os.fsencode(target)
    if sys.platform == "darwin":
        result = libc.renamex_np(encoded_source, encoded_target, _RENAME_EXCL)
    elif sys.platform.startswith("linux"):
        result = libc.renameat2(_AT_FDCWD, encoded_source, _AT_FDCWD, encoded_target, _RENAME_NOREPLACE)
    else:
        raise OSError(errno.ENOTSUP, f"cannot create {target} exclusively on this platform without hard links")
    if result != 0:
        code = ctypes.get_errno()
        if code == errno.EEXIST:
            raise FileExistsError(code, os.strerror(code), str(target))
        raise OSError(code, os.strerror(code), str(target))


def _place(target: Path, data: bytes, temp_dir: Path, mode: int | None, publish: Callable[[Path, Path], None]) -> None:
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp = _write_temp(temp_dir, data, mode)
    try:
        publish(temp, target)
    except OSError as error:
        if error.errno != errno.EXDEV:
            raise
        hidden = _write_temp(target.parent, data, mode)
        try:
            publish(hidden, target)
        finally:
            hidden.unlink(missing_ok=True)
    finally:
        temp.unlink(missing_ok=True)


def _existing_mode(target: Path) -> int | None:
    try:
        return stat.S_IMODE(target.stat().st_mode)
    except FileNotFoundError:
        return None


def _write_temp(folder: Path, data: bytes, mode: int | None) -> Path:
    """A new hidden file holding ``data``; created with 0o666 so that the umask applies."""
    while True:
        path = folder / f"{HIDDEN_TEMP_PREFIX}{secrets.token_hex(8)}"
        try:
            handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
            break
        except FileExistsError:
            continue
    try:
        if mode is not None:
            os.fchmod(handle, mode)
        with os.fdopen(handle, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path
