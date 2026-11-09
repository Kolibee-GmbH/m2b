"""The ``apple-reminders`` backend, through ``reminders`` (reminders-cli from Homebrew).

Every call goes through ``_run``: one timeout, one check of the exit code, one JSON check that
keeps the raw reply in the error. A reminder is always addressed by its ``externalId``, which
iCloud keeps the same on every device, never by its position in the list. reminders-cli finds
only open reminders for ``edit`` and ``delete``, which ``set_notes`` and ``delete`` handle. Option values go in
the ``--name=value`` form and the title after ``--``, so text starting with a dash stays text.
Without the privacy grant macOS answers with zero lists and exit 0, so zero lists means "not
reachable".
"""

from __future__ import annotations

import contextlib
import datetime
import json
import secrets
import subprocess
from collections.abc import Sequence
from typing import Any

from m2b.tasks import markers
from m2b.tasks.base import (
    Due,
    Task,
    Tasks,
    TasksError,
    TaskStateError,
    TasksUnreachableError,
    UnconfirmedTaskError,
    UnknownTaskError,
    keep,
)

NONCE_PREFIX = "m2b:nonce "
_UNKNOWN_ITEM_HINTS = ("No reminder at index", "no reminder", "not found")


class AppleRemindersTasks(Tasks):
    def __init__(self, list_name: str, command: Sequence[str] = ("reminders",), timeout_seconds: float = 20) -> None:
        self._list = list_name
        self._command = list(command)
        self._timeout = timeout_seconds

    def check_reachable(self) -> None:
        lists = self._run(["show-lists", "--format", "json"])
        names = [entry if isinstance(entry, str) else entry.get("title") for entry in _as_list(lists)]
        if not names:
            raise TasksUnreachableError(
                "Reminders answered with no lists at all; give the terminal or Claude access to Reminders "
                "in System Settings, Privacy & Security, Reminders"
            )
        if self._list not in names:
            raise TasksUnreachableError(f"Reminders has no list named {self._list!r}")

    def items(self, marker: str | None = None, include_completed: bool = False) -> list[Task]:
        flags = ["--include-completed"] if include_completed else []
        return keep([_task(item) for item in self._show(flags)], marker, include_completed)

    def completed_items(self, since: datetime.datetime) -> list[Task]:
        done = [_task(item) for item in self._show(["--only-completed"])]
        return [
            task for task in done if not task.dropped and task.completed_at is not None and task.completed_at >= since
        ]

    def add(self, title: str, notes: str = "", due: Due | None = None) -> str:
        if not title.strip() or "\n" in title:
            raise ValueError("a task title is one non-empty line")
        nonce = secrets.token_hex(8)
        tagged = f"{notes}\n{NONCE_PREFIX}{nonce}" if notes else f"{NONCE_PREFIX}{nonce}"
        arguments = ["add", self._list, f"--notes={tagged}", "--format=json"]
        if due is not None:
            arguments.append(f"--due-date={_due_argument(due)}")
        reply = self._run([*arguments, "--", title], expect_json=False)
        task_id = _external_id(reply) or self._id_by_nonce(nonce)
        # The reminder exists either way; a failed cleanup only leaves the one-time line in its notes.
        with contextlib.suppress(TasksError):
            self._run(["edit", self._list, task_id, f"--notes={notes}"], expect_json=False)
        return task_id

    def set_notes(self, task_id: str, notes: str) -> None:
        """reminders-cli edits open reminders only; a completed one has to be reopened first.

        Reopening, editing and completing it here would move its completion time to now, and
        the journal would record it a second time.
        """
        try:
            self._run_on_item(["edit", self._list, task_id, f"--notes={notes}"])
        except UnknownTaskError:
            if self._is_completed(task_id):
                raise TaskStateError(
                    f"the reminder {task_id} is completed; reopen it before changing its notes"
                ) from None
            raise

    def complete(self, task_id: str) -> None:
        self._run_on_item(["complete", self._list, task_id])

    def drop(self, task_id: str) -> None:
        """Reminders has no dropped state: the notes get the dropped line, then the reminder is completed."""
        task = next((task for task in self.items(include_completed=True) if task.id == task_id), None)
        if task is None:
            raise UnknownTaskError(task_id)
        if task.completed:
            self._run_on_item(["uncomplete", self._list, task_id])
        self._run_on_item(["edit", self._list, task_id, f"--notes={markers.with_dropped_line(task.notes)}"])
        self._run_on_item(["complete", self._list, task_id])

    def uncomplete(self, task_id: str) -> None:
        """Reopening a dropped reminder takes the dropped line out of its notes, so it is open again."""
        self._run_on_item(["uncomplete", self._list, task_id])
        reopened = next((task for task in self.items() if task.id == task_id), None)
        if reopened is not None and reopened.dropped:
            notes = markers.without_dropped_line(reopened.notes)
            self._run_on_item(["edit", self._list, task_id, f"--notes={notes}"])

    def delete(self, task_id: str) -> None:
        """Deletes a reminder; a completed one is reopened first, as reminders-cli finds open ones only."""
        try:
            self._run_on_item(["delete", self._list, task_id])
        except UnknownTaskError:
            if not self._is_completed(task_id):
                raise
            self._run_on_item(["uncomplete", self._list, task_id])
            self._run_on_item(["delete", self._list, task_id])

    def _is_completed(self, task_id: str) -> bool:
        return any(str(item.get("externalId")) == task_id for item in self._show(["--only-completed"]))

    def export(self) -> Sequence[Any]:
        return self._show(["--include-completed"])

    def _show(self, flags: list[str]) -> list[dict[str, Any]]:
        reply = self._run(["show", self._list, *flags, "--format", "json"])
        return [item for item in _as_list(reply) if isinstance(item, dict)]

    def _id_by_nonce(self, nonce: str) -> str:
        """Finds a new reminder by the one-time line in its notes, for a CLI whose add prints no id."""
        for item in self._show(["--include-completed"]):
            if f"{NONCE_PREFIX}{nonce}" in str(item.get("notes", "")):
                return str(item["externalId"])
        raise UnconfirmedTaskError(
            f"the reminder was added to {self._list!r} but could not be found again; "
            "check the list before adding it again"
        )

    def _run_on_item(self, arguments: list[str]) -> None:
        try:
            self._run(arguments, expect_json=False)
        except TasksError as error:
            if any(hint in str(error) for hint in _UNKNOWN_ITEM_HINTS):
                raise UnknownTaskError(arguments[2]) from error
            raise

    def _run(self, arguments: list[str], expect_json: bool = True) -> Any:
        command = [*self._command, *arguments]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=self._timeout)
        except subprocess.TimeoutExpired as error:
            raise TasksUnreachableError(f"reminders did not answer within {self._timeout:g} seconds") from error
        except OSError as error:
            raise TasksUnreachableError(f"reminders could not be started: {error}") from error
        if result.returncode != 0:
            raise TasksError(f"reminders {arguments[0]} failed: {result.stderr.strip() or result.stdout.strip()}")
        if not expect_json:
            return result.stdout
        try:
            return json.loads(result.stdout)
        except ValueError as error:
            raise TasksError(
                f"reminders {arguments[0]} did not answer with JSON: {result.stdout.strip()[:300]!r}"
            ) from error


def _as_list(reply: Any) -> list[Any]:
    if not isinstance(reply, list):
        raise TasksError(f"reminders answered with {type(reply).__name__} where a list was expected: {reply!r:.300}")
    return reply


def _external_id(reply: str) -> str | None:
    try:
        item = json.loads(reply)
    except ValueError:
        return None
    external_id = item.get("externalId") if isinstance(item, dict) else None
    return external_id if isinstance(external_id, str) and external_id else None


def _task(item: dict[str, Any]) -> Task:
    try:
        external_id, title = item["externalId"], item["title"]
    except KeyError as error:
        raise TasksError(f"a reminder without {error.args[0]}: {item!r:.300}") from error
    return Task(
        id=str(external_id),
        title=str(title),
        notes=str(item.get("notes") or ""),
        due=_due(item.get("dueDate")),
        completed=item.get("isCompleted") is True,
        completed_at=_instant(item.get("completionDate")),
        dropped=markers.is_dropped(str(item.get("notes") or "")),
    )


def _due(text: object) -> Due | None:
    """reminders-cli reports a due as an instant in UTC, a date-only due as local midnight.

    That midnight comes back as the day; any other due in local time. A reminder set for exactly
    midnight reads as a day as well, because reminders-cli reports the two the same way.
    """
    instant = _instant(text)
    if instant is None:
        return None
    local = instant.astimezone()
    return local.date() if local.time() == datetime.time.min else local


def _instant(text: object) -> datetime.datetime | None:
    if not isinstance(text, str) or not text:
        return None
    try:
        return datetime.datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    except ValueError as error:
        raise TasksError(f"reminders gave a time it cannot be read: {text!r}") from error


def _due_argument(due: Due) -> str:
    """reminders-cli reads the due date in local time."""
    if isinstance(due, datetime.datetime):
        local = due.astimezone() if due.utcoffset() is not None else due
        return local.strftime("%Y-%m-%d %H:%M")
    return due.isoformat()
