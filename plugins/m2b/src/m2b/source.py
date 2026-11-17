"""One source behind a fact, read by its name: a fact file of ``memory/`` or a note of ``corpus/``.

A distillate line ends with the name of its fact file (``dana.md``), and a fact file's evidence
links name notes of the archive, a document's note or the document itself. This reads what such a
name stands for, whole, so a session can answer from the details without reading the store's files
itself.

It takes a name and never a path. A name is refused before anything is read when it holds a
separator, a character that ends a line, or has the form of neither a fact file nor a note; so
only ``memory/<name>`` and the notes of ``corpus/`` can be reached, never the machine config, the
state or the tasks. Where the file lies is found by listing, which opens no file, and reading goes
through the guard as search's does: a file that lives only in the cloud is named with the command
that fetches it and never read (B6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Union

from m2b.ingest import ORIGINAL_NAME_PREFIX, READING_COPY_EXTENSION, READING_COPY_FROM, is_outline_line
from m2b.notes import frontmatter as keys
from m2b.notes.frontmatter import Note, NoteFormatError, read_created
from m2b.notes.layout import CORPUS, MEMORY, MEMORY_INDEX, bundle_stem
from m2b.notes.names import NoteName
from m2b.notes.trailer import find_trailer
from m2b.store.base import EvictedFileError, Scan, Store, StoreReadError

NOTE = "note"
PICTURE = "picture"
DOCUMENT = "document"
PICTURE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".tif", ".tiff", ".bmp"})

TITLE_PREFIX = "# "
EARLIER_HEADING = "## Earlier"
EVIDENCE_HEADING = "## Evidence"
_LINK = re.compile(r"\[\[([^\[\]\n]+)\]\]")
_NOT_A_NAME = re.compile("[/\\\\\x00-\x1f\x7f\u2028\u2029]")


class SourceRefusedError(ValueError):
    """The name is no name of a source; nothing was read."""


class SourceNotFoundError(LookupError):
    """No fact file or note has this name."""


@dataclass(frozen=True)
class Evidence:
    """One link under a fact file's ``## Evidence``, and what its note says it is.

    ``state`` is ``read``, ``evicted`` (``path`` is not on this machine), ``missing`` (no note of
    the archive has this name) or ``unreadable`` (``reason`` says why).
    """

    name: str
    state: str
    day: str | None = None
    kind: str | None = None
    original_name: str | None = None
    first_line: str | None = None
    path: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class FactFile:
    path: str
    title: str
    lines: list[str]
    until: str | None
    earlier: list[str]
    evidence: list[Evidence]


@dataclass(frozen=True)
class NoteSource:
    """A note of the archive. For a picture or a document, ``kind`` says which, ``original`` is the
    file itself beside the note, ``original_here`` whether it is on this machine, and ``outline``
    what the curation run wrote on which page; ``added`` is the rest of what the run wrote."""

    path: str
    kind: str
    day: str | None
    captured: str
    added: list[str]
    original_name: str | None = None
    outline: list[str] = field(default_factory=list)
    original: str | None = None
    original_here: bool | None = None


@dataclass(frozen=True)
class NotRead:
    """The source is there but was not read: not on this machine, or it could not be read."""

    path: str
    evicted: bool
    reason: str = ""


Source = Union[FactFile, NoteSource, NotRead]


def read_source(store: Store, name: str) -> Source:
    """What ``name`` stands for, read whole.

    Raises ``SourceRefusedError`` before the store is touched for a name that is no source's name,
    ``SourceNotFoundError`` when neither ``memory/`` nor ``corpus/`` holds it, and ``StoreError``
    when a folder cannot be listed.
    """
    note_name = _checked(name)
    if note_name is None:
        return _fact_file(store, name)
    return _note(store, name, note_name, store.scan(CORPUS))


def _checked(name: str) -> NoteName | None:
    """The parts of a note's name, None for a fact file's; refuses every other name."""
    if not name.strip():
        raise SourceRefusedError(
            "no name given: give the name a distillate line ends with, or one a note or link names"
        )
    if _NOT_A_NAME.search(name) or name in (".", ".."):
        raise SourceRefusedError(
            f"{name!r} is not a name: give the file name alone, as a distillate line ends with it, never a path"
        )
    note_name = NoteName.parse(name)
    if note_name is not None:
        return note_name
    if name.startswith(".") or not name.endswith(".md"):
        raise SourceRefusedError(
            f"{name!r} is no fact file and no note: a source is a fact file of memory/ or a note of corpus/"
        )
    if name == MEMORY_INDEX:
        raise SourceRefusedError(f"{name} is the distillate, which every session starts with; search finds its lines")
    return None


def _fact_file(store: Store, name: str) -> Source:
    relative = f"{MEMORY}/{name}"
    found = _located(store.scan(MEMORY), relative, name)
    if isinstance(found, NotRead):
        return found
    text = _read(store, relative)
    if isinstance(text, NotRead):
        return text
    body, until = _body_and_until(text)
    lines = [line.rstrip("\r") for line in body.split("\n")]
    title, rest = _title(lines)
    sections = _sections(rest)
    links = _links(sections.get(EVIDENCE_HEADING, []))
    corpus = store.scan(CORPUS) if links else Scan([], [])
    evidence = [_evidence(store, corpus, link) for link in links]
    return FactFile(
        relative,
        title or name,
        _kept(sections.get("", [])),
        until,
        _kept(sections.get(EARLIER_HEADING, [])),
        evidence,
    )


def _note(store: Store, name: str, note_name: NoteName, corpus: Scan) -> Source:
    relative = _corpus_path(corpus, name, note_name)
    if note_name.extension.lower() != "md":
        relative = f"{relative.rsplit('/', 1)[0]}/{bundle_stem(relative)}.md"
    found = _located(corpus, relative, name)
    if isinstance(found, NotRead):
        return found
    text = _read(store, relative)
    if isinstance(text, NotRead):
        return text
    return _note_source(relative, text, corpus, note_name)


def _corpus_path(corpus: Scan, name: str, note_name: NoteName) -> str:
    """Where a note of this name lies: found by listing, else the month its name says (lint moves a
    note into that month, so a note elsewhere is found too, until then)."""
    for path in corpus.files:
        if PurePosixPath(path).name == name:
            return path
    utc = note_name.time
    return f"{CORPUS}/{utc:%Y}/{utc:%m}/{name}"


def _located(scan: Scan, relative: str, name: str) -> NotRead | None:
    """None where the file is on this machine; why not, or ``SourceNotFoundError``."""
    if relative in scan.files:
        return None
    for entry in scan.evicted:
        if relative == entry or relative.startswith(entry + "/"):
            return NotRead(entry, evicted=True)
    if relative in scan.symlinks:
        return NotRead(relative, evicted=False, reason=f"{relative} is a symbolic link, which m2b never follows")
    raise SourceNotFoundError(f"no fact file or note is named {name}")


def _read(store: Store, relative: str) -> str | NotRead:
    try:
        return store.read_bytes(relative).decode("utf-8", errors="replace")
    except EvictedFileError:
        return NotRead(relative, evicted=True)
    except FileNotFoundError as error:
        raise SourceNotFoundError(f"{relative} was moved away while it was read") from error
    except StoreReadError as error:
        return NotRead(relative, evicted=False, reason=str(error))


def _parsed(text: str) -> Note | None:
    try:
        return Note.parse(text)
    except NoteFormatError:
        return None


def _body_and_until(text: str) -> tuple[str, str | None]:
    note = _parsed(text)
    if note is None or note.frontmatter is None:
        return text, None
    until = note.frontmatter.get(keys.UNTIL)
    return note.body, str(until) if until is not None else None


def _title(lines: list[str]) -> tuple[str | None, list[str]]:
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        if line.startswith(TITLE_PREFIX):
            return line[len(TITLE_PREFIX) :].strip(), lines[index + 1 :]
        return None, lines[index:]
    return None, []


def _sections(lines: list[str]) -> dict[str, list[str]]:
    """The lines before ``## Earlier`` and ``## Evidence`` under ``""``, and those of each of the two.

    Any other ``##`` heading is part of the facts, as a fact file groups its lines under them.
    """
    sections: dict[str, list[str]] = {"": []}
    current = ""
    for line in lines:
        if line.strip() in (EARLIER_HEADING, EVIDENCE_HEADING):
            current = line.strip()
            sections.setdefault(current, [])
            continue
        sections[current].append(line)
    return sections


def _kept(lines: list[str]) -> list[str]:
    return [line.strip() for line in lines if line.strip()]


def _links(lines: list[str]) -> list[str]:
    links: list[str] = []
    for line in lines:
        for link in _LINK.findall(line):
            if link.strip() not in links:
                links.append(link.strip())
    return links


def _evidence(store: Store, corpus: Scan, link: str) -> Evidence:
    try:
        note_name = _checked(link)
    except SourceRefusedError:
        return Evidence(link, "missing")
    if note_name is None:
        return Evidence(link, "missing")
    day = note_name.time.date().isoformat()
    try:
        found = _note(store, link, note_name, corpus)
    except SourceNotFoundError:
        return Evidence(link, "missing", day, _kind_of_name(link))
    if isinstance(found, NotRead):
        state = "evicted" if found.evicted else "unreadable"
        return Evidence(link, state, day, _kind_of_name(link), path=found.path, reason=found.reason or None)
    assert isinstance(found, NoteSource)
    first = found.outline[0] if found.outline else _first_line(found.captured) if found.kind == NOTE else None
    return Evidence(link, "read", found.day or day, found.kind, found.original_name, first, found.path)


def _note_source(relative: str, text: str, corpus: Scan, note_name: NoteName) -> NoteSource:
    note = _parsed(text)
    if note is None:
        return NoteSource(relative, NOTE, note_name.time.date().isoformat(), text, [])
    trailer = find_trailer(note)
    captured, added = (trailer.captured, _kept(trailer.notes.split("\n"))) if trailer else (note.body, [])
    day = _day(note) or note_name.time.date().isoformat()
    is_bundle = note.frontmatter is not None and note.frontmatter.get(keys.KIND) == keys.KIND_SIDECAR
    if not is_bundle:
        return NoteSource(relative, NOTE, day, captured, added)
    original_name = next(
        (line[len(ORIGINAL_NAME_PREFIX) :].strip() for line in added if line.startswith(ORIGINAL_NAME_PREFIX)), None
    )
    outline = [line for line in added if is_outline_line(line)]
    rest = [line for line in added if line not in outline and not line.startswith(ORIGINAL_NAME_PREFIX)]
    original = _original(relative, corpus)
    kind = _kind_of_name(original) if original else DOCUMENT
    here = None if original is None else original in corpus.files
    return NoteSource(relative, kind, day, captured, rest, original_name, outline, original, here)


def _day(note: Note) -> str | None:
    if note.frontmatter is None:
        return None
    try:
        created = read_created(note.frontmatter)
    except NoteFormatError:
        return None
    return created.value.date().isoformat() if created is not None else None


def _original(sidecar: str, corpus: Scan) -> str | None:
    """The file a sidecar note stands for: a member of its bundle, not the reading copy of another."""
    folder, stem = sidecar.rsplit("/", 1)[0], bundle_stem(sidecar)
    members = sorted(
        path
        for path in [*corpus.files, *corpus.evicted]
        if path != sidecar and path.startswith(folder + "/") and bundle_stem(path) == stem
    )
    has_source_of_copy = any(PurePosixPath(path).suffix.lower() in READING_COPY_FROM for path in members)
    for path in members:
        if has_source_of_copy and PurePosixPath(path).suffix.lower() == f".{READING_COPY_EXTENSION}":
            continue
        return path
    return None


def _kind_of_name(name: str) -> str:
    suffix = PurePosixPath(name).suffix.lower()
    if suffix == ".md":
        return NOTE
    return PICTURE if suffix in PICTURE_EXTENSIONS else DOCUMENT


def _first_line(text: str) -> str | None:
    return next((line.strip() for line in text.split("\n") if line.strip()), None)
