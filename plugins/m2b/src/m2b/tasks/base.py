"""The ``Tasks`` interface and its data.

Ids are stable: they stay the same across completing, reopening and every machine. "Could not
look" is never "no tasks": a backend that cannot reach its list raises ``TasksUnreachableError``.
"""

from __future__ import annotations

import datetime
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Union

from m2b.store.base import ConflictCopy
from m2b.tasks.markers import marker_of

Due = Union[datetime.date, datetime.datetime]


class TasksError(Exception):
    """A tasks call failed."""


class TasksUnreachableError(TasksError):
    """The tasks backend could not be asked: no access, no list, no answer in time."""


class UnknownTaskError(TasksError):
    """No task has this id."""


class UnconfirmedTaskError(TasksError):
    """The task was added but could not be identified afterwards; adding it again would make a second one."""


class TaskStateError(TasksError):
    """The task is in a state that does not allow this change; the user has to change it first."""


@dataclass(frozen=True)
class Task:
    """A task; a dropped one counts as completed, as dropping means marking it dropped and done."""

    id: str
    title: str
    notes: str = ""
    due: Due | None = None
    completed: bool = False
    completed_at: datetime.datetime | None = None
    dropped: bool = False

    @property
    def marker(self) -> str | None:
        found = marker_of(self.notes)
        return found[0] if found else None


class Tasks(ABC):
    @abstractmethod
    def check_reachable(self) -> None:
        """Raises ``TasksUnreachableError`` unless the list can be read."""

    def lists_every_task(self) -> bool:
        """Whether ``items`` answers with every task in the list.

        A backend that leaves out a task it cannot read says no; then a task missing from the
        answer may still be there, and no caller may take it for one the owner deleted.
        """
        return not self.unreadable()

    def unreadable(self) -> list[tuple[str, str]]:
        """The tasks ``items`` leaves out because they cannot be read, by where they are, with the reason.

        Only a backend that keeps tasks as files has any.
        """
        return []

    def conflict_copies(self) -> list[ConflictCopy]:
        """The copies a sync service made of task files, by their path in the store; ``items`` reads none.

        Only a backend that keeps tasks as files has any.
        """
        return []

    @abstractmethod
    def items(self, marker: str | None = None, include_completed: bool = False) -> list[Task]:
        """Open tasks, optionally only those with a marker, optionally with completed ones."""

    @abstractmethod
    def completed_items(self, since: datetime.datetime) -> list[Task]:
        """Tasks completed at or after ``since``, each with its completion time; dropped ones are no completion."""

    @abstractmethod
    def add(self, title: str, notes: str = "", due: Due | None = None) -> str:
        """Creates a task and returns its id."""

    @abstractmethod
    def set_notes(self, task_id: str, notes: str) -> None:
        """Replaces the notes; Apple Reminders refuses this for a completed task, so reopen it first."""

    @abstractmethod
    def complete(self, task_id: str) -> None: ...

    @abstractmethod
    def uncomplete(self, task_id: str) -> None: ...

    @abstractmethod
    def drop(self, task_id: str) -> None:
        """Marks the task dropped and completes it; it is not a completion for the journal."""

    @abstractmethod
    def delete(self, task_id: str) -> None: ...

    @abstractmethod
    def export(self) -> Sequence[Any]:
        """Everything in the list, completed items included, in the backend's own shape."""


def keep(tasks: Sequence[Task], marker: str | None, include_completed: bool) -> list[Task]:
    """The filter every backend's ``items`` applies."""
    return [
        task
        for task in tasks
        if (include_completed or not task.completed) and (marker is None or task.marker == marker)
    ]
