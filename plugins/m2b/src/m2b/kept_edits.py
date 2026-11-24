"""A kept edit becomes the fact file: in the run's harvest step, in code, before ingest.

``m2b store edit --keep`` writes the owner's version of a fact file into the inbox as a capture of
kind ``edit``, with ``about`` naming the fact file and ``base`` the hash of the file the copy was
made from. Harvest puts the text in place here, before the ingest step takes its snapshot of
``memory/``: the edit is part of what ingest finds, so the guard never undoes it as the model's
write, and ingest brings the distillate's line in step in the same run. The capture is then marked
``placed`` and waits for ingest, which files it as any capture (``ingest.pending`` offers no edit
before that mark).

Three checks come first, each of which leaves the fact file as it is:

- **the hash**: the fact file must still be what the copy was made from. A run that changed it
  since, or a second edit put in place before this one, has its change kept, and this edit is not
  put over it;
- **the form**: a title line, a frontmatter of the codec's form holding nothing but a day as
  ``until``, some text. A fact file without them reads wrong in every session, or never expires;
- **the characters**: none that hides or reorders text, the check the guard makes on every line a
  model step writes.

``about`` must name a fact file directly under ``memory/``: never the distillate, a lesson or a
path, which only a capture written by hand could name. An edit that fails a check goes to the
archive with the reason as its trailer line, and the review names it as an action, without its
text. One whose fact file is not downloaded waits in the inbox for a run that has it.

When the guard puts ``memory/`` back after the ingest step, the fact file keeps the edit, since it
was in place before the step, while the distillate's line goes back. An edit that step filed is
then moved from the archive back into the inbox (``back_to_inbox``), still marked, so the next run
brings the line in step.

An edit in place and not yet marked, as a run stopped between the two writes leaves it, is
recognised by the fact file holding its text, and is marked. Reverting a run's commit puts the
capture back unmarked and the fact file as it was, so the next run puts the edit in place again,
as it files every capture a revert puts back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath

from m2b import ingest
from m2b.fact_edit import content_hash
from m2b.notes import frontmatter as keys
from m2b.notes.characters import unsafe_characters, with_hidden_written_out
from m2b.notes.frontmatter import Note, NoteFormatError
from m2b.notes.layout import CORPUS, INBOX, MEMORY
from m2b.notes.memory_index import is_day
from m2b.source import SourceNotFoundError, SourceRefusedError, fact_file_named
from m2b.store.base import EvictedFileError, Store, StoreError, fetch_command

TITLE_PREFIX = "# "
# The one key a fact file's frontmatter holds (``ingest`` skill, "until").
FACT_FILE_KEYS = frozenset({keys.UNTIL})


@dataclass(frozen=True)
class Placed:
    capture: str
    fact_file: str


@dataclass(frozen=True)
class Refused:
    capture: str
    # The fact file the edit names, None where it names no fact file.
    fact_file: str | None
    reason: str


@dataclass
class EditsReport:
    placed: list[Placed] = field(default_factory=list)
    refused: list[Refused] = field(default_factory=list)
    # Why an edit waits in the inbox, one line each, for the review.
    waiting: list[str] = field(default_factory=list)


class _Refusal(Exception):
    """The edit is not put in place, for the reason in the message."""


class _Wait(Exception):
    """The edit stays in the inbox for a later run, for the reason in the message."""


def waiting(store: Store) -> list[str]:
    """The inbox paths of the edits not put in place yet, in capture order."""
    return [relative for relative, note in _edits(store) if not _marked(note)]


def put_in_place(store: Store) -> EditsReport:
    """Puts each kept edit that passes the checks in place, in capture order, and archives the others."""
    report = EditsReport()
    for relative, note in _edits(store):
        if _marked(note):
            continue
        name = PurePosixPath(relative).name
        fact_file: str | None = None
        try:
            fact_file = _fact_file(store, note)
            _put(store, relative, note, fact_file)
            report.placed.append(Placed(name, fact_file))
        except _Wait as wait:
            report.waiting.append(f"your edit of {fact_file} waits ({name}): {wait}")
        except _Refusal as refusal:
            _archive(store, name, str(refusal), report, fact_file)
        except StoreError as error:
            report.waiting.append(f"an edit waits ({name}): {error}")
    return report


def back_to_inbox(store: Store, names: list[str]) -> list[str]:
    """Moves each placed edit among the archived captures ``names`` back into the inbox, without
    ``facts_filed``, so the next ingest step files it again; the names moved."""
    archived = {PurePosixPath(path).name: path for path in store.scan(CORPUS).files}
    moved = []
    for name in names:
        path = archived.get(name)
        if path is None:
            continue
        note = Note.parse(store.read_text(path))
        if note.frontmatter is None or note.frontmatter.get(keys.KIND) != keys.KIND_EDIT or not _marked(note):
            continue
        note.frontmatter.remove(keys.FACTS_FILED)
        store.create_exclusive(f"{INBOX}/{name}", note.render().encode("utf-8"))
        store.delete(path)
        moved.append(name)
    return moved


def _edits(store: Store) -> list[tuple[str, Note]]:
    """The captures of kind edit that can be read; one that cannot is ingest's to report."""
    found = []
    for relative in sorted(store.scan(INBOX).files):
        if PurePosixPath(relative).parent.as_posix() != INBOX or not relative.endswith(".md"):
            continue
        try:
            note = Note.parse(store.read_text(relative))
        except (UnicodeDecodeError, StoreError):
            continue
        if note.frontmatter is not None and note.frontmatter.get(keys.KIND) == keys.KIND_EDIT:
            found.append((relative, note))
    return found


def _marked(note: Note) -> bool:
    return note.frontmatter is not None and note.frontmatter.get_flag(keys.PLACED)


def _fact_file(store: Store, note: Note) -> str:
    """The name of the fact file the edit names; refuses every name that is no fact file's."""
    assert note.frontmatter is not None
    about = note.frontmatter.get(keys.ABOUT) or ""
    try:
        fact_file_named(store, about)
    except (SourceRefusedError, SourceNotFoundError) as error:
        raise _Refusal(with_hidden_written_out(str(error))) from error
    return about


def _put(store: Store, relative: str, note: Note, fact_file: str) -> None:
    assert note.frontmatter is not None
    path = f"{MEMORY}/{fact_file}"
    text = note.body
    data = text.encode("utf-8")
    try:
        current = store.read_bytes(path)
    except EvictedFileError as error:
        raise _Wait(f"{path} is not downloaded to this machine; {fetch_command(path)} fetches it") from error
    if current != data:
        _check_form(text)
        if content_hash(current) != note.frontmatter.get(keys.BASE):
            raise _Refusal(
                f"{fact_file} changed since you made the copy; m2b store edit {fact_file} makes a new copy "
                "of it as it is now"
            )
        store.replace(path, data)
    note.frontmatter.set(keys.PLACED, True)
    store.replace(relative, note.render().encode("utf-8"))


def _check_form(text: str) -> None:
    """Refuses a text a fact file must not be: empty, with hidden characters, a broken frontmatter,
    an ``until`` that is no day, a key no fact file has, or no title line."""
    if not text.strip():
        raise _Refusal("it is empty")
    hidden = unsafe_characters(text)
    if hidden:
        raise _Refusal(f"it holds characters that hide or reorder text ({', '.join(hidden)})")
    parsed = Note.parse(text)
    if parsed.frontmatter is None and text.split("\n", 1)[0].rstrip("\r") == keys.DELIMITER:
        raise _Refusal("its frontmatter has no closing --- line")
    if parsed.frontmatter is not None:
        names = parsed.frontmatter.keys()
        until = parsed.frontmatter.get(keys.UNTIL)
        extra = [name for name in names if name not in FACT_FILE_KEYS]
        if extra:
            raise _Refusal(f"its frontmatter holds {', '.join(extra)}, which a fact file never has")
        if len(names) != _entries(parsed.frontmatter.render()):
            raise _Refusal("its frontmatter has a line that is not a key: value of its own")
        if until is not None and not is_day(until):
            raise _Refusal("its until is no YYYY-MM-DD day")
    first = next((line for line in parsed.body.split("\n") if line.strip()), "")
    if not first.startswith(TITLE_PREFIX) or not first[len(TITLE_PREFIX) :].strip():
        raise _Refusal("it has no title line (# ...) at its top")


def _entries(block: str) -> int:
    """The lines between the two ``---`` lines that hold anything."""
    lines = block.split("\n")[1:-2]
    return sum(1 for line in lines if line.strip())


def _archive(store: Store, name: str, reason: str, report: EditsReport, fact_file: str | None) -> None:
    """Files a refused edit into the archive with its reason; where that fails, it waits."""
    try:
        ingest.add_note(store, name, f"not put in place: {reason}")
        ingest.finish(store, None, name)
    # A capture written by hand may hold a ``created`` no time is read from; it waits, named.
    except (ingest.IngestError, NoteFormatError, StoreError) as error:
        report.waiting.append(f"an edit that was not put in place ({reason}) stays in {INBOX}/: {error} ({name})")
        return
    report.refused.append(Refused(name, fact_file, reason))
