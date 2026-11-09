"""The ``markdown`` backend: one file per task in ``tasks/`` of the store.

Creating a task is creating a file, so several machines and add-ons never write the same file.
A task file has the frontmatter keys ``status`` (open, done, dropped), ``due``, ``created`` and
``done``, the title as its first line and the notes below. A dropped task counts as
completed but is no completion for ``completed_items``. A file the owner adds by hand,
without frontmatter, is an open task named by its file; a ``done`` status without a date takes
the file's modification time. A file that cannot be read as a task (an unknown status, a date the
codec cannot read, not UTF-8) is left out of every list, so one hand edit does not stop every task
step of a run; lint names it (``unreadable``).
"""

from __future__ import annotations

import datetime
import secrets
from collections.abc import Callable, Sequence
from typing import Any

from m2b.notes import layout
from m2b.notes.frontmatter import Frontmatter, Note, NoteFormatError, parse_time, set_created
from m2b.store.base import Store, StoreError
from m2b.tasks.base import Due, Task, Tasks, TasksUnreachableError, UnknownTaskError, keep

STATUS = "status"
DUE = "due"
DONE = "done"
OPEN, COMPLETED, DROPPED = "open", "done", "dropped"
STATUSES = (OPEN, COMPLETED, DROPPED)
ID_BYTES = 6


class MarkdownTasks(Tasks):
    def __init__(
        self, store: Store, now: Callable[[], datetime.datetime] = lambda: datetime.datetime.now().astimezone()
    ) -> None:
        self._store = store
        self._now = now

    def check_reachable(self) -> None:
        self._task_files()

    def items(self, marker: str | None = None, include_completed: bool = False) -> list[Task]:
        return keep([task for task, _ in self._all()], marker, include_completed)

    def completed_items(self, since: datetime.datetime) -> list[Task]:
        return [
            task
            for task, status in self._all()
            if status == COMPLETED and task.completed_at is not None and task.completed_at >= since
        ]

    def add(self, title: str, notes: str = "", due: Due | None = None) -> str:
        _check_title(title)
        note = Note.new({STATUS: OPEN}, _body(title, notes))
        assert note.frontmatter is not None
        if due is not None:
            note.frontmatter.set(DUE, _due_text(due))
        set_created(note.frontmatter, self._now())
        while True:
            task_id = secrets.token_hex(ID_BYTES)
            try:
                self._store.create_exclusive(_path(task_id), note.render().encode("utf-8"))
                return task_id
            except FileExistsError:
                continue

    def set_notes(self, task_id: str, notes: str) -> None:
        note = self._read(task_id)
        title = note.body.split("\n", 1)[0]
        note.body = _body(title, notes)
        self._write(task_id, note)

    def complete(self, task_id: str) -> None:
        note = self._read(task_id)
        fields = _frontmatter_of(note)
        fields.set(STATUS, COMPLETED)
        fields.set(DONE, self._now().isoformat(timespec="seconds"))
        self._write(task_id, note)

    def drop(self, task_id: str) -> None:
        note = self._read(task_id)
        fields = _frontmatter_of(note)
        fields.set(STATUS, DROPPED)
        fields.set(DONE, self._now().isoformat(timespec="seconds"))
        self._write(task_id, note)

    def uncomplete(self, task_id: str) -> None:
        note = self._read(task_id)
        fields = _frontmatter_of(note)
        fields.set(STATUS, OPEN)
        fields.remove(DONE)
        self._write(task_id, note)

    def delete(self, task_id: str) -> None:
        try:
            self._store.delete(_path(task_id))
        except FileNotFoundError as error:
            raise UnknownTaskError(task_id) from error

    def export(self) -> Sequence[Any]:
        return [
            {
                "id": task.id,
                "title": task.title,
                "notes": task.notes,
                "status": status,
                "due": _iso(task.due),
                "completed_at": _iso(task.completed_at),
            }
            for task, status in self._all()
        ]

    def unreadable(self) -> list[tuple[str, str]]:
        """The task files left out of every list, by store path, with the reason."""
        return [(path, problem) for path, _, problem in self._each() if problem is not None]

    def lists_every_task(self) -> bool:
        return not self.unreadable()

    def _all(self) -> list[tuple[Task, str]]:
        return [parsed for _, parsed, _ in self._each() if parsed is not None]

    def _each(self) -> list[tuple[str, tuple[Task, str] | None, str | None]]:
        """Each task file by its path, read as a task or with the reason it cannot be."""
        found: list[tuple[str, tuple[Task, str] | None, str | None]] = []
        try:
            for path in self._task_files():
                try:
                    found.append((path, self._parse(path), None))
                except NoteFormatError as error:
                    text = str(error)
                    found.append((path, None, text if text.startswith(path) else f"{path}: {text}"))
        except StoreError as error:
            raise TasksUnreachableError(f"the task files could not be read: {error}") from error
        return found

    def _task_files(self) -> list[str]:
        """The task files; a sync service's conflict copy is left to lint, never read as a task."""
        try:
            copies = {copy.path for copy in self._store.conflict_copies(layout.TASKS)}
            return [
                path for path in self._store.list_files(layout.TASKS) if path.endswith(".md") and path not in copies
            ]
        except StoreError as error:
            raise TasksUnreachableError(f"the task folder could not be read: {error}") from error

    def _read(self, task_id: str) -> Note:
        try:
            return Note.parse(_decoded(self._store.read_bytes(_path(task_id)), _path(task_id)))
        except FileNotFoundError as error:
            raise UnknownTaskError(task_id) from error
        except StoreError as error:
            raise TasksUnreachableError(f"the task {task_id} could not be read: {error}") from error

    def _write(self, task_id: str, note: Note) -> None:
        try:
            self._store.replace(_path(task_id), note.render().encode("utf-8"))
        except StoreError as error:
            raise TasksUnreachableError(f"the task {task_id} could not be written: {error}") from error

    def _parse(self, path: str) -> tuple[Task, str]:
        task_id = path.rsplit("/", 1)[-1][: -len(".md")]
        note = Note.parse(_decoded(self._store.read_bytes(path), path))
        title, _, notes = note.body.partition("\n")
        fields = note.frontmatter
        status = (fields.get(STATUS) if fields else None) or OPEN
        if status not in STATUSES:
            raise NoteFormatError(f"{path}: status is {status!r}; allowed: {', '.join(STATUSES)}")
        completed_at = None
        if status == COMPLETED:
            completed_at = _time(fields.get(DONE) if fields else None) or self._modified(path)
        task = Task(
            id=task_id,
            title=title.strip(),
            notes=notes.rstrip("\n"),
            due=_due(fields.get(DUE) if fields else None),
            completed=status in (COMPLETED, DROPPED),
            completed_at=completed_at,
            dropped=status == DROPPED,
        )
        return task, status

    def _modified(self, path: str) -> datetime.datetime:
        modified = self._store.path(path).stat().st_mtime
        return datetime.datetime.fromtimestamp(modified, datetime.timezone.utc).astimezone()


def _decoded(data: bytes, path: str) -> str:
    """A task file is UTF-8; one saved in another encoding is named, never read as garbage."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise NoteFormatError(f"{path}: not UTF-8 text ({error.reason} at byte {error.start})") from error


def _path(task_id: str) -> str:
    if not task_id or "/" in task_id or task_id.startswith("."):
        raise UnknownTaskError(task_id)
    return f"{layout.TASKS}/{task_id}.md"


def _check_title(title: str) -> None:
    if not title.strip() or "\n" in title or "\r" in title:
        raise ValueError("a task title is one non-empty line")


def _body(title: str, notes: str) -> str:
    return f"{title}\n{notes}\n" if notes else f"{title}\n"


def _frontmatter_of(note: Note) -> Frontmatter:
    """The note's frontmatter; a hand-added task without one gets a block."""
    if note.frontmatter is None:
        note.frontmatter = Note.new({STATUS: OPEN}, "").frontmatter
    assert note.frontmatter is not None
    return note.frontmatter


def _time(text: str | None) -> datetime.datetime | None:
    """A time from a task file; one written by hand without an offset is read as local time."""
    if not text:
        return None
    value = parse_time(text)
    return value if value.utcoffset() is not None else value.astimezone()


def _due(text: str | None) -> Due | None:
    if not text:
        return None
    if "T" in text:
        return _time(text)
    try:
        return datetime.date.fromisoformat(text)
    except ValueError as error:
        raise NoteFormatError(f"due must be a date like 2026-12-01 or a time with offset, got {text!r}") from error


def _iso(value: Due | None) -> str | None:
    return _due_text(value) if value is not None else None


def _due_text(value: Due) -> str:
    """Dates and times in the one syntax the task files are read with: whole seconds."""
    if isinstance(value, datetime.datetime):
        return value.isoformat(timespec="seconds")
    return value.isoformat()
