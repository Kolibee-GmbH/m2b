"""Capture: one new file in ``inbox/`` per capture, the text verbatim, never edited afterwards.

The file is created exclusively, so nothing is ever overwritten; a name taken in the same second
draws a new random suffix (B2). With a follow-up, the file name is picked first, the task is
created naming it, and only then the file is written, once, with the task recorded (B32). A
collision after that draws a new name and corrects the task's notes before the file is written;
if that correction fails, the task is removed and the file carries ``follow_up:`` instead, or,
when it cannot be removed either, the file gets neither and the caller is told.
When the task list cannot be reached the file carries ``follow_up:`` instead, and ingest creates
the task later. A task that was added but could not be identified afterwards gets neither, so
ingest does not create a second one; the capture is still written and the caller is told.
A file that cannot be written at all (no write permission, a full or read-only disk) raises
``NotSavedError`` with one line, and the follow-up task made for it is removed again, since it
would point to no capture; one that cannot be removed is named in that line.
"""

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass
from pathlib import Path, PurePath

from m2b.notes import frontmatter, layout
from m2b.notes.frontmatter import Note, set_created
from m2b.notes.names import NoteName
from m2b.store.base import Store
from m2b.tasks import markers
from m2b.tasks.base import Tasks, TasksError, UnconfirmedTaskError

FOLLOW_UP_KEY = "follow-up"
TITLE_LENGTH = 120
NAME_ATTEMPTS = 20
# The words the capture skill recognizes a failed capture by, whatever the exit code.
NOT_SAVED = "the capture was not saved"


class NotSavedError(Exception):
    """The capture file could not be written, so nothing was kept; the message is one line."""


@dataclass(frozen=True)
class CaptureResult:
    path: str
    task_id: str | None = None
    follow_up: datetime.date | None = None
    notice: str | None = None


def capture(
    store: Store,
    text: str,
    source: str,
    quiet: bool = False,
    follow_up: datetime.date | None = None,
    tasks: Tasks | None = None,
    now: datetime.datetime | None = None,
    from_candidate: str | None = None,
) -> CaptureResult:
    """Writes the capture; empty text or a bad source raise ``ValueError`` before anything is written."""
    if not text.strip():
        raise ValueError("there is nothing to capture: the text is empty")
    if follow_up is not None and tasks is None:
        raise ValueError("a follow-up needs the task list")
    created = (now or datetime.datetime.now()).astimezone().replace(microsecond=0)
    name = NoteName.for_capture(created, source)
    body = text if text.endswith("\n") else text + "\n"

    task_id: str | None = None
    pending: datetime.date | None = None
    notice: str | None = None
    unconfirmed: UnconfirmedTaskError | None = None
    try:
        if follow_up is not None and tasks is not None:
            try:
                task_id = tasks.add(task_title(text), notes=_task_notes(name), due=follow_up)
            except UnconfirmedTaskError as error:
                unconfirmed = error
            # A task list in the store (Markdown tasks) that cannot be written is out of reach too.
            except (TasksError, OSError) as error:
                pending = follow_up
                notice = f"the follow-up task waits for the next curation run: {error}"

        for _ in range(NAME_ATTEMPTS):
            path = f"{layout.INBOX}/{name}"
            try:
                store.create_exclusive(path, _render(created, source, quiet, task_id, pending, body, from_candidate))
                break
            except FileExistsError:
                name = NoteName.for_capture(created, source)
                if task_id is not None and tasks is not None:
                    try:
                        tasks.set_notes(task_id, _task_notes(name))
                    except TasksError as error:
                        task_id, pending, notice, unconfirmed = _drop_misnamed_task(tasks, task_id, follow_up, error)
        else:
            raise FileExistsError(f"no free capture name in {layout.INBOX}/ after {NAME_ATTEMPTS} attempts")
    except OSError as error:
        raise NotSavedError(
            _not_saved(error, store.path(layout.INBOX), tasks, task_id, unconfirmed is not None)
        ) from error

    if unconfirmed is not None:
        raise UnconfirmedTaskError(f"{path} was captured, but its follow-up task: {unconfirmed}")
    return CaptureResult(path, task_id, pending, notice)


def _drop_misnamed_task(
    tasks: Tasks, task_id: str, follow_up: datetime.date | None, error: TasksError
) -> tuple[None, datetime.date | None, str | None, UnconfirmedTaskError | None]:
    """The task names a file another capture took. Removed, ingest creates it anew from
    ``follow_up``; if it cannot be removed it stays, and the capture gets neither field."""
    try:
        tasks.delete(task_id)
    except TasksError:
        return (
            None,
            None,
            None,
            UnconfirmedTaskError(
                f"it was added but names another capture and could not be corrected or removed: {error}"
            ),
        )
    return None, follow_up, f"the follow-up task waits for the next curation run: {error}", None


def _not_saved_message(error: OSError, inbox: Path) -> str:
    """One line for a write the file system refused.

    It names the folder, not the file: a saved capture prints its ``inbox/`` path, and this line
    must never read like one. A full disk often fails a write that carries no file name; the
    inbox is then the folder the capture was meant for.
    """
    where = error.filename2 if error.filename2 is not None else error.filename
    folder = PurePath(os.fsdecode(where)).parent if where is not None else inbox
    return _one_line(f"{NOT_SAVED}: {error.strerror or error} in {folder}")


def _not_saved(error: OSError, inbox: Path, tasks: Tasks | None, task_id: str | None, task_unconfirmed: bool) -> str:
    """Removes the follow-up task made for the capture that was not written, and says what became of it."""
    message = _not_saved_message(error, inbox)
    if task_unconfirmed:
        return f"{message}; a follow-up task may have been added for it, look at the task list"
    if task_id is None or tasks is None:
        return message
    try:
        tasks.delete(task_id)
    except (TasksError, OSError) as delete_error:
        return _one_line(f"{message}; its follow-up task {task_id} could not be removed, delete it: {delete_error}")
    return message


def _one_line(text: str) -> str:
    return " ".join(text.splitlines())


def task_title(text: str) -> str:
    """A task title from a capture: its first non-empty line, shortened with an ellipsis."""
    first = next(line.strip() for line in text.split("\n") if line.strip())
    return first if len(first) <= TITLE_LENGTH else first[: TITLE_LENGTH - 1] + "…"


def _task_notes(name: NoteName) -> str:
    return markers.marker_line(markers.CAPTURE, str(name), FOLLOW_UP_KEY)


def _render(
    created: datetime.datetime,
    source: str,
    quiet: bool,
    task_id: str | None,
    pending: datetime.date | None,
    body: str,
    from_candidate: str | None = None,
) -> bytes:
    note = Note.new({}, body)
    assert note.frontmatter is not None
    set_created(note.frontmatter, created)
    note.frontmatter.set(frontmatter.SOURCE, source)
    if quiet:
        note.frontmatter.set(frontmatter.QUIET, True)
    if task_id is not None:
        note.frontmatter.set(frontmatter.TASKS, [task_id])
    if pending is not None:
        note.frontmatter.set(frontmatter.FOLLOW_UP, pending.isoformat())
    if from_candidate is not None:
        note.frontmatter.set(frontmatter.FROM_CANDIDATE, from_candidate)
    return note.render().encode("utf-8")
