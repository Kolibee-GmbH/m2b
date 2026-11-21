"""A project the owner makes known with one sentence: a capture that names the folder's remote.

"Merk dir dieses Projekt" in a session is a capture of a fixed form, so the curation run can file it
as a project topic (``- Repository: <address> (<file>.md)``, B247) without guessing which repository
was meant:

    Keep this project: <what the owner calls it>
    Repository: github.com/acme/portal

The address is the remote's, the same on every machine; the folder on this machine never goes into
the store. A folder without a remote has no such address, so nothing is captured there. A project
that already has a topic, or whose capture still waits in the inbox, is not captured again: two
captures of one repository would make two topics.

A pointer kept from a reading of the sessions is a capture of the same kind, ``Keep this pointer:``
with the line and the repository's ``Repository:`` lines, so the run files the line into the topic
whose ``Repository:`` line names one of them.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import PurePosixPath

from m2b.notes.layout import INBOX, MEMORY, MEMORY_INDEX
from m2b.notes.memory_index import split_topics
from m2b.repository_places import REPOSITORY_LINE
from m2b.session_remotes import address_of, name_of
from m2b.store.base import Store, StoreError

FIRST_LINE = "Keep this project: "
# A pointer the owner kept from a reading of the sessions: one line for a project's topic.
POINTER_FIRST_LINE = "Keep this pointer: "
_CAPTURED_ADDRESS = re.compile(r"^Repository: (\S+)[ \t]*$", re.MULTILINE)


def capture_text(addresses: Sequence[str], words: str) -> str:
    """The capture: what the owner calls the project, or the repository's name, and each address."""
    called = " ".join(words.split()) or name_of(addresses)
    return FIRST_LINE + called + "\n" + "".join(f"Repository: {address}\n" for address in addresses)


def pointer_capture_text(addresses: Sequence[str], line: str) -> str:
    """The capture of a kept pointer: its line, ``<sentence> → <path>``, and the repository it is of."""
    return POINTER_FIRST_LINE + line + "\n" + "".join(f"Repository: {address}\n" for address in addresses)


def known_as(store: Store, addresses: Sequence[str]) -> str | None:
    """The topic whose ``Repository:`` line names one of the repository's addresses; None without one,
    and None where the distillate cannot be read, so the capture is made and the run decides."""
    try:
        text = store.read_bytes(f"{MEMORY}/{MEMORY_INDEX}").decode("utf-8", errors="replace")
    except (OSError, StoreError):
        return None
    return topic_naming(text, addresses)


def topic_naming(distillate: str, addresses: Sequence[str]) -> str | None:
    """The topic of ``distillate`` whose ``Repository:`` line names one of ``addresses``; None without one."""
    for block in split_topics(distillate).blocks:
        for line in block.text.split("\n"):
            found = REPOSITORY_LINE.match(line)
            if found is not None and address_of(found.group("address")) in addresses:
                return block.topic.name
    return None


def waiting_capture(store: Store, addresses: Sequence[str]) -> str | None:
    """The name of a project capture of this repository that waits in the inbox; captures that are
    not downloaded or cannot be read are not looked at, so the capture is made and the run decides."""
    try:
        scan = store.scan(INBOX)
    except (OSError, StoreError):
        return None
    # A capture is a note; the copies ``m2b capture-file`` puts beside them are not read.
    for path in sorted(name for name in scan.files if name.endswith(".md")):
        try:
            text = store.read_bytes(path).decode("utf-8", errors="replace")
        except (OSError, StoreError):
            continue
        if f"\n{FIRST_LINE}" not in text and not text.startswith(FIRST_LINE):
            continue
        if any(address_of(address) in addresses for address in _CAPTURED_ADDRESS.findall(text)):
            return PurePosixPath(path).name
    return None
