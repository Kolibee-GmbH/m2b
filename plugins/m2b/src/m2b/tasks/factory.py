"""Opening the tasks backend the store settings name."""

from __future__ import annotations

from collections.abc import Mapping

from m2b.config.store_settings import TasksSettings
from m2b.store.base import Store
from m2b.tasks.apple_reminders import AppleRemindersTasks
from m2b.tasks.base import Tasks
from m2b.tasks.markdown import MarkdownTasks


def open_tasks(settings: TasksSettings, store: Store, executables: Mapping[str, str]) -> Tasks:
    """The backend for these settings; Apple Reminders runs the ``reminders`` setup recorded."""
    if settings.backend == "markdown":
        return MarkdownTasks(store)
    assert settings.list_name is not None, "store settings require a list for apple-reminders"
    command = [executables.get("reminders", "reminders")]
    return AppleRemindersTasks(settings.list_name, command=command, timeout_seconds=settings.timeout_seconds)
