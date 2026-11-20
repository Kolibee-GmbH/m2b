"""Where a project's repository lies on this machine, below the topic line that names it (B247).

A project topic names its repository by the address of its remote, which is the same on every
machine: ``- Repository: github.com/acme/portal (acme-portal.md)``. Which folder holds a clone is
different on each machine, so it is never written into the store. Where a topic comes into a
session, at its start or before a prompt, the line gets one more below it: the folder noted with
that remote and seen last that is still there, or that no such folder was noted. A session reads a
project's files by that folder instead of asking where they are.

Only machine state is read for it, the notes the session start writes (``session_remotes``): no
file of the store, no git, nothing on the network, so the prompt hook stays as cheap as it was.
"""

from __future__ import annotations

import contextlib
import os
import re
from collections.abc import Callable
from pathlib import Path

from m2b.notes.characters import without_hidden
from m2b.session_remotes import NotedFolder, address_of, noted_folders

REPOSITORY_LINE = re.compile(r"- Repository: (?P<address>\S+) \((?P<file>[^()/\s]+\.md)\)\s*\Z")
ON_THIS_MACHINE = "  on this machine: "
NOT_CLONED = "  not cloned on this machine"


def with_places(text: str, notes: Path, is_there: Callable[[Path], bool] = os.path.isdir) -> str:
    """``text`` with the place on this machine below each of its repository lines; unchanged
    without one, and the notes are read only when there is one."""
    lines = text.split("\n")
    if not any(REPOSITORY_LINE.match(line) for line in lines):
        return text
    folders = noted_folders(notes)
    placed: list[str] = []
    for line in lines:
        placed.append(line)
        found = REPOSITORY_LINE.match(line)
        if found is not None:
            placed.append(_place(address_of(found.group("address")), folders, is_there))
    return "\n".join(placed)


def _place(address: str, folders: list[NotedFolder], is_there: Callable[[Path], bool]) -> str:
    clones = sorted(
        (noted for noted in folders if address in {address_of(remote) for remote in noted.remotes}),
        key=lambda noted: noted.noted,
        reverse=True,
    )
    # A folder that cannot be looked at counts as not there: one such note must never cost a
    # session its distillate or a prompt its topics.
    for clone in clones:
        with contextlib.suppress(OSError):
            if is_there(Path(clone.top)):
                return ON_THIS_MACHINE + without_hidden(clone.top)
    return NOT_CLONED
