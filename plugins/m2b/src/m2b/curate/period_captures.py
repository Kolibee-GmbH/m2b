"""What the person captured in a period, read from the inbox and the archive by the time in each name.

Two ways to a proposal compare with it, so that nothing the person noted themselves comes back as
a proposal: the reading of the sessions (``glean_step``) and the taking in of what a session
handed in (``handed_in_intake``).
"""

from __future__ import annotations

import datetime
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import PurePosixPath

from m2b.ingest import TEXT_EXTENSIONS
from m2b.notes.frontmatter import Note
from m2b.notes.layout import CORPUS, INBOX
from m2b.notes.names import NoteName
from m2b.store.base import Store, StoreError


@dataclass(frozen=True)
class Captures:
    """The texts captured in a period, and how many of its captures could not be read."""

    texts: tuple[str, ...]
    not_downloaded: int
    unreadable: int


def captures_since(store: Store, start: datetime.datetime, end: datetime.datetime) -> Captures:
    """What was captured since ``start``, from the inbox and the archive, by the time in each name.

    A capture that is not downloaded is counted and not read (a read would download it or hang),
    and so is a folder that is not: what it holds cannot be listed. A text file the person dropped
    into the inbox under a name of its own is a capture too: ingest names it only after this step.
    """
    texts: list[str] = []
    not_downloaded = unreadable = 0
    for folder in (INBOX, *_month_folders(start, end)):
        scan = store.scan(folder)
        dropped = folder == INBOX
        not_downloaded += sum(1 for path in scan.evicted if _may_be_of_the_period(path, start, dropped))
        for path in scan.files:
            if not _is_capture_since(path, start, dropped):
                continue
            try:
                texts.append(Note.parse(store.read_text(path)).body)
            except (OSError, StoreError, UnicodeDecodeError):
                unreadable += 1
    return Captures(tuple(texts), not_downloaded, unreadable)


def _month_folders(start: datetime.datetime, end: datetime.datetime) -> Iterator[str]:
    """The archive's folders for the months of the period; a capture is filed by its name's UTC time."""
    month = start.astimezone(datetime.timezone.utc).date().replace(day=1)
    last = end.astimezone(datetime.timezone.utc).date()
    while month <= last:
        yield f"{CORPUS}/{month:%Y}/{month:%m}"
        month = (month + datetime.timedelta(days=32)).replace(day=1)


def _is_capture_since(path: str, start: datetime.datetime, dropped: bool) -> bool:
    """A capture by its name and the time in it; with ``dropped`` also a text file under any other name."""
    name = NoteName.parse(PurePosixPath(path).name)
    if name is not None:
        return name.extension == "md" and name.time >= start
    return dropped and PurePosixPath(path).suffix.lower() in TEXT_EXTENSIONS


def _may_be_of_the_period(evicted: str, start: datetime.datetime, dropped: bool) -> bool:
    """A capture of the period by its name, or a folder, which may hold one."""
    return _is_capture_since(evicted, start, dropped) or not PurePosixPath(evicted).suffix


def capture_notes(captures: Captures) -> list[str]:
    notes = []
    if captures.not_downloaded:
        one = captures.not_downloaded == 1
        notes.append(
            f"{_count(captures.not_downloaded, 'capture')} of the period {'is' if one else 'are'} not downloaded, "
            f"so a proposal may repeat {'it' if one else 'one'}"
        )
    if captures.unreadable:
        one = captures.unreadable == 1
        notes.append(
            f"{_count(captures.unreadable, 'capture')} of the period could not be read, "
            f"so a proposal may repeat {'it' if one else 'one'}"
        )
    return notes


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"
