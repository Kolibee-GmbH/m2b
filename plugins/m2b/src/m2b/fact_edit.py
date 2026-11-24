"""An editing copy of a fact file: ``m2b store edit``, its ``--keep`` and its ``--discard``.

The owner edits a copy, never the fact file: a curation run writes ``memory/`` alone, and a file
changed by hand under a run's step would count as the step's write, be undone with it or fail the
run. The copy lies in this machine's state folder, readable by the owner alone, beside the hash of
the fact file as it was when the copy was made. ``--keep`` hands the copy to the inbox as a capture
with ``kind: edit``, ``about`` and that hash as ``base``; the next curation run puts it in place
only while the fact file still has that hash, so an edit made on a file a run has changed since is
never put over that change. No function here writes under ``memory/``.

The copy is opened in the system's text editor where the session has a screen, as ``m2b store
open`` decides it, and its path is named either way, so any editor takes it. No editor command is
read from the environment or the config: a project's settings can set both for a session.
"""

from __future__ import annotations

import hashlib
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from m2b import viewer
from m2b.capture import capture
from m2b.notes import frontmatter as keys
from m2b.notes.layout import MEMORY
from m2b.paths import MachinePaths
from m2b.source import fact_file_named
from m2b.store.base import EvictedFileError, Store, StoreReadError, SymlinkError, fetch_command

EDITS_FOLDER = "edits"
BASE_SUFFIX = ".base"
# `open -t` hands a file to the system's text editor, whatever application the extension names.
MAC_TEXT_EDITOR = "-t"
_PRIVATE_FILE = 0o600
_PRIVATE_FOLDER = 0o700


class EditRefusedError(Exception):
    """No copy is made, kept or dropped; the message says why in one line."""


@dataclass(frozen=True)
class Opened:
    copy: Path
    opened: bool
    # Why the copy did not open, None where it did.
    not_opened: str | None


@dataclass(frozen=True)
class CopyState:
    copy: Path
    differs: bool
    fact_file_changed: bool


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def copy_path(machine: MachinePaths, fact_file: str) -> Path:
    return machine.state_dir / EDITS_FOLDER / fact_file


def open_copy(
    store: Store,
    machine: MachinePaths,
    fact_file: str,
    environ: Mapping[str, str],
    run_holds_lock: bool,
    platform: str | None = None,
    start: viewer.Launch | None = None,
) -> Opened:
    """Makes the copy unless it exists and opens it where the session has a screen."""
    copy = copy_path(machine, fact_file)
    if _base_of(copy) is None:
        if run_holds_lock:
            raise EditRefusedError("a curation run is under way; edit the fact file once it has finished")
        data = _fact_file_bytes(store, fact_file)
        # The base first: a copy whose base was not written, or one left without it, is no copy, and
        # one whose base is left over from a copy the owner removed must not keep that old hash.
        _remove(copy)
        _write_private(_base_path(copy), content_hash(data).encode("ascii"))
        _write_private(copy, data)
    try:
        command = _editor_command(environ, platform or sys.platform)
        exit_code = (start or viewer.launch)([*command, str(copy)])
    except viewer.NotOpenedError as error:
        return Opened(copy, False, str(error))
    if exit_code not in (0, None):
        return Opened(copy, False, f"{command[0]} ended with exit {exit_code}")
    return Opened(copy, True, None)


def keep_copy(store: Store, machine: MachinePaths, fact_file: str) -> str | None:
    """The capture the copy became, None when it did not differ; the copy is removed either way."""
    fact_file_named(store, fact_file)
    copy = copy_path(machine, fact_file)
    base = _base_of(copy)
    if base is None:
        raise EditRefusedError(f"there is no editing copy of {fact_file}; m2b store edit {fact_file} makes one")
    data = copy.read_bytes()
    path = None
    if content_hash(data) != base:
        if not data.strip():
            raise EditRefusedError(f"the copy of {fact_file} is empty; m2b store edit --discard {fact_file} drops it")
        text = data.decode("utf-8", errors="replace")
        path = capture(store, text, "cli", kind=keys.KIND_EDIT, about=fact_file, base=base).path
    _remove(copy)
    return path


def discard_copy(machine: MachinePaths, fact_file: str) -> bool:
    """Removes the copy; whether there was one."""
    copy = copy_path(machine, fact_file)
    existed = copy.exists() or _base_path(copy).exists()
    _remove(copy)
    return existed


def copy_state(store: Store, machine: MachinePaths, fact_file: str) -> CopyState | None:
    """Whether the copy differs from what it was made from, and whether the fact file changed since."""
    copy = copy_path(machine, fact_file)
    base = _base_of(copy)
    if base is None:
        return None
    try:
        now = content_hash(store.read_bytes(f"{MEMORY}/{fact_file}"))
    except (FileNotFoundError, EvictedFileError, StoreReadError):
        now = None
    return CopyState(copy, content_hash(copy.read_bytes()) != base, now != base)


def differing_copies(machine: MachinePaths) -> int:
    """How many editing copies differ from what they were made from: edits not kept yet. Read from
    this machine alone, so the band counts them without reaching the store."""
    folder = machine.state_dir / EDITS_FOLDER
    if not folder.is_dir():
        return 0
    count = 0
    for copy in folder.iterdir():
        base = None if copy.suffix == BASE_SUFFIX else _base_of(copy)
        if base is not None and content_hash(copy.read_bytes()) != base:
            count += 1
    return count


def _fact_file_bytes(store: Store, fact_file: str) -> bytes:
    relative = fact_file_named(store, fact_file)
    try:
        return store.read_bytes(relative)
    except EvictedFileError as error:
        raise EditRefusedError(
            f"{relative} is not downloaded to this machine; {fetch_command(relative)} fetches it"
        ) from error
    except SymlinkError as error:
        raise EditRefusedError(f"{relative} is a symbolic link, which m2b never follows") from error
    except StoreReadError as error:
        raise EditRefusedError(str(error)) from error


def _editor_command(environ: Mapping[str, str], platform: str) -> list[str]:
    command = viewer.screen_command(environ, platform)
    return [*command, MAC_TEXT_EDITOR] if command == [viewer.MAC_OPEN] else command


def _base_path(copy: Path) -> Path:
    return copy.with_name(copy.name + BASE_SUFFIX)


def _base_of(copy: Path) -> str | None:
    """The hash the copy was made from; None where the copy or its base is missing: no copy then."""
    base = _base_path(copy)
    if not copy.is_file() or not base.is_file():
        return None
    return base.read_text(encoding="ascii").strip()


def _write_private(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True, mode=_PRIVATE_FOLDER)
    os.chmod(target.parent, _PRIVATE_FOLDER)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _PRIVATE_FILE)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)


def _remove(copy: Path) -> None:
    copy.unlink(missing_ok=True)
    _base_path(copy).unlink(missing_ok=True)
