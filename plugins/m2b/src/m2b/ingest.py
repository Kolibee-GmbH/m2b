"""Ingest, the deterministic half: inbox files into the schema, tasks, refs, trailer notes, the move.

The fenced model decides what a capture means; these functions are the only way it changes a
capture, and each one can run again without doubling anything, so a crash at any point of ingest
neither loses nor doubles a task, a fact or a file:

- ``normalize`` names foreign files by the schema, fills a missing ``created`` and ``source``
  (B18), turns a binary into a bundle with a sidecar note and, where the model cannot read the
  format, a reading copy (B20), and removes conflict copies that equal their original byte for
  byte; a looser match could delete ``plan 2026.md`` beside ``plan.md``.
  A renamed file and a sidecar name their original in the curation trailer, so a rerun after a
  crash finds the work already done instead of doing it twice.
- ``add_task`` finds its task by the marker ``m2b:capture <file> <key>``, never by title (B17).
- ``pending`` lists what the model has to read: each schema-named capture once, a bundle as its
  sidecar with the other files as members, and everything normalize has not handled as a problem.
- ``finish`` moves a capture, or a whole bundle with its sidecar last, into the month of its
  ``created`` time in UTC (B19); a destination with other bytes is refused before anything moves
  (X6), one with the same bytes completes an interrupted move (B16).

Captured text is never rewritten: only the frontmatter and the trailer change.
"""

from __future__ import annotations

import datetime
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from m2b.capture import FOLLOW_UP_KEY, task_title
from m2b.notes import frontmatter as keys
from m2b.notes.frontmatter import Note, NoteFormatError, read_created, set_created
from m2b.notes.layout import CORPUS, INBOX, waiting_on_evicted
from m2b.notes.names import NoteName
from m2b.notes.trailer import MARKER_LINE, find_trailer
from m2b.store.base import Store, StoreError
from m2b.tasks import markers
from m2b.tasks.base import Due, Tasks

TEXT_EXTENSIONS = frozenset({".md", ".markdown", ".txt"})
# Formats the model cannot read get a JPEG reading copy next to the original.
READING_COPY_FROM = frozenset({".heic", ".heif"})
READING_COPY_EXTENSION = "jpg"
ORIGINAL_NAME_PREFIX = "original name: "
CONFLICT_COPY_PREFIX = "conflict copy of "
NO_READING_COPY_PREFIX = "no reading copy: "
DEFAULT_SOURCE = "cli"
NAME_ATTEMPTS = 20

Converter = Callable[[Path, Path], None]


class IngestError(Exception):
    """A capture cannot take this step; the run reports it and the capture stays where it is."""


class NotInInboxError(IngestError):
    """No such capture in the inbox, and none of that name in the corpus either."""


class DestinationTakenError(IngestError):
    """The corpus already holds a different file under the capture's name (X6)."""


@dataclass
class NormalizeReport:
    renamed: list[tuple[str, str]] = field(default_factory=list)
    completed: list[str] = field(default_factory=list)
    bundles: list[str] = field(default_factory=list)
    removed_copies: list[str] = field(default_factory=list)
    kept_copies: list[str] = field(default_factory=list)
    evicted: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Pending:
    """A capture waiting in the inbox, with what the model needs before it opens the file."""

    file: str
    source: str
    kind: str | None
    facts_filed: bool = False
    quiet: bool = False
    follow_up: str | None = None
    members: tuple[str, ...] = ()


@dataclass
class PendingReport:
    captures: list[Pending] = field(default_factory=list)
    evicted: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    # The inbox files behind the problems, which ingest cannot file as they are.
    stuck: list[str] = field(default_factory=list)


def pending(store: Store) -> PendingReport:
    """The captures in name order, which is capture order (X9); reads nothing outside the inbox."""
    report = PendingReport()
    scan = store.scan(INBOX)
    report.evicted = scan.evicted
    stems: dict[str, list[str]] = {}
    # An evicted sidecar still makes its members a bundle; it is named under evicted, never read.
    evicted_names = {PurePosixPath(relative).name for relative in scan.evicted}
    for relative in scan.files:
        stems.setdefault(PurePosixPath(relative).name.rsplit(".", 1)[0], []).append(PurePosixPath(relative).name)
    waiting = waiting_on_evicted(scan.files, scan.evicted)
    for relative in sorted(scan.files):
        if relative in waiting:
            continue
        problem = _pending_problem(store, relative, stems, evicted_names, report)
        if problem is not None:
            report.problems.append(problem)
            report.stuck.append(relative)
    return report


def _pending_problem(
    store: Store, relative: str, stems: dict[str, list[str]], evicted_names: set[str], report: PendingReport
) -> str | None:
    """Adds the capture at ``relative`` to the report, or says why ingest cannot file it as it is."""
    name = PurePosixPath(relative).name
    stem = name.rsplit(".", 1)[0]
    if NoteName.parse(name) is None:
        return f"{relative} is not named by the schema; run m2b ingest normalize first"
    # Normalize moves only files it renames; finish looks for a capture in the inbox itself.
    if PurePosixPath(relative).parent.as_posix() != INBOX:
        return f"{relative} is in a subfolder of {INBOX}/; move it into {INBOX}/ itself to have it filed"
    if not name.endswith(".md"):
        if f"{stem}.md" not in stems[stem] and f"{stem}.md" not in evicted_names:
            return f"{relative} has no sidecar note; run m2b ingest normalize first"
        return None
    try:
        report.captures.append(_pending_capture(store, relative, sorted(set(stems[stem]) - {name})))
    except (UnicodeDecodeError, NoteFormatError, IngestError, StoreError) as error:
        return f"{relative} cannot be ingested yet ({error}); run m2b ingest normalize first"
    return None


def _pending_capture(store: Store, relative: str, others: list[str]) -> Pending:
    frontmatter = _frontmatter(Note.parse(store.read_text(relative)))
    if read_created(frontmatter) is None or not frontmatter.get(keys.SOURCE):
        raise IngestError("created or source is missing")
    kind = frontmatter.get(keys.KIND)
    return Pending(
        file=PurePosixPath(relative).name,
        source=str(frontmatter.get(keys.SOURCE)),
        kind=kind,
        facts_filed=frontmatter.get_flag(keys.FACTS_FILED),
        quiet=frontmatter.get_flag(keys.QUIET),
        follow_up=frontmatter.get(keys.FOLLOW_UP),
        members=tuple(others) if kind == keys.KIND_SIDECAR else (),
    )


def sips_converter(platform: str = sys.platform) -> Converter | None:
    """The macOS converter for reading copies, None elsewhere."""
    executable = shutil.which("sips")
    if platform != "darwin" or executable is None:
        return None

    def convert(source: Path, destination: Path) -> None:
        subprocess.run(
            [executable, "-s", "format", "jpeg", str(source), "--out", str(destination)],
            check=True,
            capture_output=True,
            timeout=60,
        )

    return convert


def normalize(store: Store, convert: Converter | None) -> NormalizeReport:
    report = NormalizeReport()
    _remove_conflict_copies(store, report)
    scan = store.scan(INBOX)
    report.evicted = scan.evicted
    renamed_from, sidecar_of = _originals(store, scan.files)
    for relative in scan.files:
        if not store.exists(relative):
            continue
        # One file that cannot be normalized stays where it is, reported; the others go on.
        try:
            if _is_text(relative):
                _normalize_text(store, relative, renamed_from, report)
            else:
                _normalize_binary(store, relative, sidecar_of, convert, report)
        except UnicodeDecodeError:
            report.problems.append(f"{relative} is a text file but not UTF-8; it stays until it is saved as UTF-8")
        except (NoteFormatError, IngestError, StoreError) as error:
            report.problems.append(f"{relative} stays in the inbox: {error}")
    return report


def add_task(store: Store, tasks: Tasks, file: str, key: str, title: str, due: Due | None) -> str:
    """The capture's task for ``key``: found by its marker, or created; recorded in ``tasks:``."""
    relative, note = _inbox_note(store, file)
    name = PurePosixPath(relative).name
    if not key or any(character.isspace() for character in key):
        raise IngestError(f"the task key must be one word, not {key!r}")
    task_id = _find_task(tasks, name, key)
    if task_id is None:
        task_id = tasks.add(title, notes=markers.marker_line(markers.CAPTURE, name, key), due=due)
    fields = _frontmatter(note)
    if task_id not in fields.get_list(keys.TASKS):
        fields.add_to_list(keys.TASKS, [task_id])
        _write(store, relative, note)
    return task_id


def add_follow_up_task(store: Store, tasks: Tasks, file: str) -> str | None:
    """Turns ``follow_up:`` into its task, as capture would have done (B32); None without one."""
    relative, note = _inbox_note(store, file)
    due_text = _frontmatter(note).get(keys.FOLLOW_UP)
    if not due_text:
        return None
    try:
        due = datetime.date.fromisoformat(due_text)
    except ValueError as error:
        raise IngestError(f"{relative}: follow_up {due_text!r} is not a date like 2026-11-20") from error
    captured = _captured(note)
    title = task_title(captured) if captured.strip() else PurePosixPath(relative).name
    task_id = add_task(store, tasks, file, FOLLOW_UP_KEY, title, due)
    relative, note = _inbox_note(store, file)
    _frontmatter(note).remove(keys.FOLLOW_UP)
    _write(store, relative, note)
    return task_id


def add_ref(store: Store, file: str, ref: str) -> None:
    relative, note = _inbox_note(store, file)
    fields = _frontmatter(note)
    if ref not in fields.get_list(keys.REFS):
        fields.add_to_list(keys.REFS, [ref])
        _write(store, relative, note)


def add_note(store: Store, file: str, text: str) -> None:
    """Appends a line to the curation trailer, once; one line, and none the format reserves."""
    if "\n" in text or "\r" in text:
        raise IngestError("a trailer note is one line; add several lines one by one")
    if text.strip() == MARKER_LINE or text.startswith(ORIGINAL_NAME_PREFIX):
        raise IngestError(f"{text!r} is a line the store format reserves")
    relative, note = _inbox_note(store, file)
    if _add_trailer_line(note, text):
        _write(store, relative, note)


def set_facts_filed(store: Store, file: str) -> None:
    relative, note = _inbox_note(store, file)
    fields = _frontmatter(note)
    if not fields.get_flag(keys.FACTS_FILED):
        fields.set(keys.FACTS_FILED, True)
        _write(store, relative, note)


def clear_facts_filed(store: Store, file: str) -> None:
    """Takes the flag off again, for a capture whose facts a curation run put back out of memory."""
    relative, note = _inbox_note(store, file)
    fields = _frontmatter(note)
    if fields.get_flag(keys.FACTS_FILED):
        fields.remove(keys.FACTS_FILED)
        _write(store, relative, note)


def finish(store: Store, tasks: Tasks | None, file: str) -> list[str]:
    """Moves the capture, or its whole bundle, into the corpus; returns where everything is now."""
    name = PurePosixPath(file).name
    parsed = NoteName.parse(name)
    if parsed is None:
        raise IngestError(f"{name} does not have a schema name yet; run m2b ingest normalize first")
    stem = name.rsplit(".", 1)[0]
    month = _month_folder(parsed.time)
    members = _stem_files(store, INBOX, stem)
    if not members:
        done = _stem_files(store, month, stem)
        if done:
            return done
        raise NotInInboxError(f"{name} is neither in {INBOX}/ nor in {month}/")
    main = f"{INBOX}/{stem}.md"
    if not store.exists(main):
        raise IngestError(f"{name} has no note {stem}.md yet; run m2b ingest normalize first")
    note = Note.parse(store.read_text(main))
    month = _month_folder(_created_utc(store, main))
    ordered = [*sorted(member for member in members if member != main), main]
    destinations = [f"{month}/{PurePosixPath(member).name}" for member in ordered]
    if _frontmatter(note).get(keys.FOLLOW_UP):
        # Not copied yet, as the copy comes after the task: any file at a destination is someone else's.
        taken = [destination for destination in destinations if store.exists(destination)]
        if taken:
            raise DestinationTakenError(f"{', '.join(taken)} already exists; {main} stays in the inbox")
        if tasks is None:
            raise IngestError(f"{main} still waits for its follow-up task, and no task list is open")
        add_follow_up_task(store, tasks, main)
    for member, destination in zip(ordered, destinations):
        if store.exists(destination) and store.read_bytes(destination) != store.read_bytes(member):
            raise DestinationTakenError(f"{destination} already exists with other content; {member} stays in the inbox")
    for member, destination in zip(ordered, destinations):
        if not store.exists(destination):
            store.create_exclusive(destination, store.read_bytes(member))
        store.delete(member)
    return sorted(set(destinations) | set(_stem_files(store, month, stem)))


def _remove_conflict_copies(store: Store, report: NormalizeReport) -> None:
    for copy in store.conflict_copies(INBOX):
        if copy.removable:
            store.delete(copy.path)
            report.removed_copies.append(copy.path)
            continue
        report.kept_copies.append(copy.path)
        if copy.identical is False and _is_text(copy.path):
            note = Note.parse(store.read_text(copy.path))
            if _add_trailer_line(note, CONFLICT_COPY_PREFIX + PurePosixPath(copy.original).name):
                _write(store, copy.path, note)


def _originals(store: Store, files: list[str]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """What earlier runs left behind: renamed captures and sidecars by the original name they record.

    A file that cannot be read is skipped here; its own step reports it.
    """
    renamed_from: dict[str, list[str]] = {}
    sidecar_of: dict[str, list[str]] = {}
    for relative in files:
        if not relative.endswith(".md") or NoteName.parse(PurePosixPath(relative).name) is None:
            continue
        try:
            note = Note.parse(store.read_text(relative))
        except (UnicodeDecodeError, StoreError):
            continue
        original = _original_name(note)
        if original is None:
            continue
        if note.frontmatter is not None and note.frontmatter.get(keys.KIND) == keys.KIND_SIDECAR:
            sidecar_of.setdefault(original, []).append(relative)
        else:
            renamed_from.setdefault(original, []).append(relative)
    return renamed_from, sidecar_of


def _normalize_text(store: Store, relative: str, renamed_from: dict[str, list[str]], report: NormalizeReport) -> None:
    name = PurePosixPath(relative).name
    note = Note.parse(store.read_text(relative))
    if NoteName.parse(name) is not None and name.endswith(".md"):
        if _fill_frontmatter(store, relative, note):
            _write(store, relative, note)
            report.completed.append(relative)
        return
    for earlier in renamed_from.get(name, []):
        if _captured(Note.parse(store.read_text(earlier))) == _with_final_newline(_captured(note)):
            store.delete(relative)
            report.renamed.append((relative, earlier))
            return
    created, source = _fill_frontmatter(store, relative, note) or _created_and_source(note)
    _add_trailer_line(note, ORIGINAL_NAME_PREFIX + name)
    target = _create_new(store, created, source, "md", note.render().encode("utf-8"))
    store.delete(relative)
    report.renamed.append((relative, target))


def _normalize_binary(
    store: Store,
    relative: str,
    sidecar_of: dict[str, list[str]],
    convert: Converter | None,
    report: NormalizeReport,
) -> None:
    name = PurePosixPath(relative).name
    extension = _schema_extension(name)
    if NoteName.parse(name) is not None:
        stem = name.rsplit(".", 1)[0]
        if not store.exists(f"{INBOX}/{stem}.md"):
            _write_sidecar(store, f"{INBOX}/{stem}.md", name, _time_of(store, relative))
            report.bundles.append(f"{INBOX}/{stem}.md")
        _reading_copy(store, f"{INBOX}/{name}", convert)
        return
    sidecar = next(
        (
            candidate
            for candidate in sidecar_of.get(name, [])
            if _continues_bundle(store, candidate, extension, relative)
        ),
        None,
    )
    if sidecar is None:
        # The sidecar comes first: it is the only place the original name survives a crash (B20).
        created = _mtime(store, relative)
        sidecar = _create_free(
            store, created, DEFAULT_SOURCE, "md", lambda n: _sidecar_bytes(n, extension, name, created)
        )
        report.bundles.append(sidecar)
    stem = PurePosixPath(sidecar).name.rsplit(".", 1)[0]
    target = f"{INBOX}/{stem}.{extension}"
    if not store.exists(target):
        store.create_exclusive(target, store.read_bytes(relative))
    store.delete(relative)
    report.renamed.append((relative, target))
    _reading_copy(store, target, convert)


def _continues_bundle(store: Store, sidecar: str, extension: str, relative: str) -> bool:
    """Whether this file is the one an earlier, interrupted run made the sidecar for.

    The earlier run copies the file next to the sidecar and then removes it. A copy with the same
    bytes means the removal is all that is left; no copy anywhere means the copy never happened.
    A copy with other bytes, or one that already went to the corpus, means this is a new file that
    only shares the name.
    """
    stem = PurePosixPath(sidecar).name.rsplit(".", 1)[0]
    member = f"{INBOX}/{stem}.{extension}"
    if store.exists(member):
        return store.read_bytes(member) == store.read_bytes(relative)
    parsed = NoteName.parse(PurePosixPath(sidecar).name)
    moved = parsed is not None and store.exists(f"{_month_folder(parsed.time)}/{stem}.{extension}")
    return not moved


def _write_sidecar(store: Store, relative: str, member: str, created: datetime.datetime) -> None:
    note = _sidecar_note(member, None, created)
    store.create_exclusive(relative, note.render().encode("utf-8"))


def _sidecar_bytes(name: NoteName, extension: str, original: str, created: datetime.datetime) -> bytes:
    stem = str(name).rsplit(".", 1)[0]
    return _sidecar_note(f"{stem}.{extension}", original, created).render().encode("utf-8")


def _sidecar_note(member: str, original: str | None, created: datetime.datetime) -> Note:
    extension = member.rsplit(".", 1)[1]
    note = Note.new({keys.KIND: keys.KIND_SIDECAR}, f"A {extension} file, captured as {member}.\n")
    fields = _frontmatter(note)
    set_created(fields, created)
    parsed = NoteName.parse(member)
    fields.set(keys.SOURCE, parsed.source if parsed is not None else DEFAULT_SOURCE)
    if original is not None:
        _add_trailer_line(note, ORIGINAL_NAME_PREFIX + original)
    return note


def _reading_copy(store: Store, relative: str, convert: Converter | None) -> None:
    name = PurePosixPath(relative).name
    stem, extension = name.rsplit(".", 1)
    if f".{extension.lower()}" not in READING_COPY_FROM:
        return
    copy = f"{INBOX}/{stem}.{READING_COPY_EXTENSION}"
    if store.exists(copy):
        return
    sidecar = f"{INBOX}/{stem}.md"
    problem = "no converter on this platform"
    if convert is not None:
        store.temp_dir.mkdir(parents=True, exist_ok=True)
        temporary = store.temp_dir / f".reading-copy-{stem}.{READING_COPY_EXTENSION}"
        try:
            convert(store.path(relative), temporary)
            store.create_exclusive(copy, temporary.read_bytes())
            return
        except (OSError, subprocess.SubprocessError) as error:
            problem = str(error)
        finally:
            temporary.unlink(missing_ok=True)
    note = Note.parse(store.read_text(sidecar))
    if _add_trailer_line(note, NO_READING_COPY_PREFIX + problem):
        _write(store, sidecar, note)


def _fill_frontmatter(store: Store, relative: str, note: Note) -> tuple[datetime.datetime, str] | None:
    """Fills a missing ``created`` and ``source`` (B18); None when both were there."""
    if note.frontmatter is None:
        note.frontmatter = Note.new({}, "").frontmatter
    fields = _frontmatter(note)
    changed = False
    created = read_created(fields)
    if created is None or not created.has_offset:
        moment = created.value.astimezone() if created is not None else _time_of(store, relative)
        set_created(fields, moment)
        changed = True
    source = fields.get(keys.SOURCE)
    if not source or not _is_source(source):
        parsed = NoteName.parse(PurePosixPath(relative).name)
        fields.set(keys.SOURCE, parsed.source if parsed is not None else DEFAULT_SOURCE)
        changed = True
    return _created_and_source(note) if changed else None


def _created_and_source(note: Note) -> tuple[datetime.datetime, str]:
    fields = _frontmatter(note)
    created = read_created(fields)
    assert created is not None
    return created.value, fields.get(keys.SOURCE) or DEFAULT_SOURCE


def _create_new(store: Store, created: datetime.datetime, source: str, extension: str, data: bytes) -> str:
    return _create_free(store, created, source, extension, lambda _name: data)


def _create_free(
    store: Store,
    created: datetime.datetime,
    source: str,
    extension: str,
    render: Callable[[NoteName], bytes],
) -> str:
    """Creates a file under a free schema name; a taken name draws a new suffix."""
    for _ in range(NAME_ATTEMPTS):
        name = NoteName.for_capture(created, source, extension=extension)
        relative = f"{INBOX}/{name}"
        try:
            store.create_exclusive(relative, render(name))
            return relative
        except FileExistsError:
            continue
    raise IngestError(f"no free name in {INBOX}/ after {NAME_ATTEMPTS} attempts")


def _add_trailer_line(note: Note, line: str) -> bool:
    """Adds a line to the curation trailer and sets ``curated``; False when it is there already."""
    trailer = find_trailer(note)
    if trailer is not None and line in trailer.notes.split("\n"):
        return False
    body = note.body if not note.body or note.body.endswith("\n") else note.body + "\n"
    note.body = body + (f"{line}\n" if trailer is not None else f"{MARKER_LINE}\n{line}\n")
    if note.frontmatter is None:
        note.frontmatter = Note.new({}, "").frontmatter
    _frontmatter(note).set(keys.CURATED, True)
    return True


def _original_name(note: Note) -> str | None:
    trailer = find_trailer(note)
    if trailer is None:
        return None
    for line in trailer.notes.split("\n"):
        if line.startswith(ORIGINAL_NAME_PREFIX):
            return line[len(ORIGINAL_NAME_PREFIX) :].strip()
    return None


def _with_final_newline(text: str) -> str:
    """The captured text as it stands before a trailer, which always starts on a line of its own."""
    return text if not text or text.endswith("\n") else text + "\n"


def _captured(note: Note) -> str:
    trailer = find_trailer(note)
    return trailer.captured if trailer is not None else note.body


def _inbox_note(store: Store, file: str) -> tuple[str, Note]:
    name = PurePosixPath(file).name
    relative = f"{INBOX}/{name}"
    if not name.endswith(".md") or not store.exists(relative):
        raise NotInInboxError(f"no capture {name} in {INBOX}/")
    return relative, Note.parse(store.read_text(relative))


def _find_task(tasks: Tasks, name: str, key: str) -> str | None:
    wanted = (markers.CAPTURE, (name, key))
    return next(
        (task.id for task in tasks.items(include_completed=True) if markers.marker_of(task.notes) == wanted), None
    )


def _created_utc(store: Store, relative: str) -> datetime.datetime:
    created = read_created(_frontmatter(Note.parse(store.read_text(relative))))
    if created is None:
        raise IngestError(f"{relative} has no created time; run m2b ingest normalize first")
    value = created.value if created.has_offset else created.value.astimezone()
    return value.astimezone(datetime.timezone.utc)


def _month_folder(moment: datetime.datetime) -> str:
    utc = moment.astimezone(datetime.timezone.utc)
    return f"{CORPUS}/{utc:%Y}/{utc:%m}"


def _stem_files(store: Store, folder: str, stem: str) -> list[str]:
    return [path for path in store.list_files(folder) if PurePosixPath(path).name.rsplit(".", 1)[0] == stem]


def _frontmatter(note: Note) -> keys.Frontmatter:
    if note.frontmatter is None:
        raise IngestError("the capture has no frontmatter; run m2b ingest normalize first")
    return note.frontmatter


def _write(store: Store, relative: str, note: Note) -> None:
    store.replace(relative, note.render().encode("utf-8"))


def _time_of(store: Store, relative: str) -> datetime.datetime:
    """A schema name's own time, so name and month folder agree (X5); the modification time otherwise."""
    parsed = NoteName.parse(PurePosixPath(relative).name)
    return parsed.time.astimezone() if parsed is not None else _mtime(store, relative)


def _mtime(store: Store, relative: str) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(os.lstat(store.path(relative)).st_mtime).astimezone().replace(microsecond=0)


def _schema_extension(name: str) -> str:
    """The extension a binary keeps in its schema name; ``bin`` when the schema cannot hold it."""
    extension = name.rsplit(".", 1)[1] if "." in name else ""
    return extension if extension.isascii() and extension.isalnum() else "bin"


def _is_text(relative: str) -> bool:
    return PurePosixPath(relative).suffix.lower() in TEXT_EXTENSIONS


def _is_source(value: str) -> bool:
    try:
        NoteName.for_capture(datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc), value, suffix="0000")
    except ValueError:
        return False
    return True
