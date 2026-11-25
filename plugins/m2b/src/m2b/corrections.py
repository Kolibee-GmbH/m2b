"""Corrections and edits that wait: captures in ``inbox/`` whose ``about`` names a fact file.

``m2b capture --about <fact file>`` writes such a capture. Until a curation run files it, the
pane's view of that fact file names it, so the person sees that the correction was kept. Only the
captures in ``inbox/`` itself count, as ingest files them; one that is not downloaded, cannot be
read or has no frontmatter is left out, since it cannot be told what it is about.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from m2b.notes import frontmatter as keys
from m2b.notes.frontmatter import Note, NoteFormatError
from m2b.notes.layout import INBOX
from m2b.store.base import Store, StoreError


@dataclass(frozen=True)
class WaitingCorrection:
    capture: str
    first_line: str
    is_edit: bool = False


def waiting_for(store: Store, fact_file: str) -> list[WaitingCorrection]:
    """The corrections about ``fact_file`` (its name alone, ``dana.md``), oldest first by name; an
    edit of the whole file (``kind: edit``) is no correction and is left out."""
    return [item for item in _about_file(store, fact_file) if not item.is_edit]


def edits_waiting(store: Store, fact_file: str) -> list[str]:
    """The names of the kept edits of ``fact_file`` that wait in the inbox, oldest first."""
    return [item.capture for item in _about_file(store, fact_file) if item.is_edit]


def _about_file(store: Store, fact_file: str) -> list[WaitingCorrection]:
    found = []
    for relative in sorted(store.scan(INBOX).files):
        path = PurePosixPath(relative)
        if path.parent.as_posix() != INBOX or path.suffix != ".md":
            continue
        correction = _about(store, relative, fact_file)
        if correction is not None:
            found.append(correction)
    return found


def _about(store: Store, relative: str, fact_file: str) -> WaitingCorrection | None:
    try:
        note = Note.parse(store.read_text(relative))
    except (UnicodeDecodeError, NoteFormatError, StoreError, OSError):
        return None
    if note.frontmatter is None or note.frontmatter.get(keys.ABOUT) != fact_file:
        return None
    first = next((line.strip() for line in note.body.split("\n") if line.strip()), "")
    is_edit = note.frontmatter.get(keys.KIND) == keys.KIND_EDIT
    return WaitingCorrection(PurePosixPath(relative).name, first, is_edit)
