"""The tasks contract against a real Apple Reminders list; it runs only when asked to.

    M2B_IT=1 M2B_IT_REMINDERS_LIST=sb-test-inbox scripts/check --quick m2b

The list must exist, be empty, and have a name starting with ``sb-test-``; any other name is
refused, so the owner's own lists are never touched. Every test deletes the reminders it made.
"""

from __future__ import annotations

import datetime
import os
import shutil
import sys
import unittest
from collections.abc import Mapping
from pathlib import Path

from m2b.tasks.apple_reminders import AppleRemindersTasks
from m2b.tasks.base import Tasks, TasksError
from tasks_contract import Contracts

TEST_LIST_PREFIX = "sb-test-"
LIST_VARIABLE = "M2B_IT_REMINDERS_LIST"


def integration_list(environ: Mapping[str, str]) -> str | None:
    """The test list to use, None when the run was not asked for; refuses any other list name."""
    if environ.get("M2B_IT") != "1" or sys.platform != "darwin" or not environ.get(LIST_VARIABLE):
        return None
    name = environ[LIST_VARIABLE]
    if not name.startswith(TEST_LIST_PREFIX):
        raise RuntimeError(f"{LIST_VARIABLE} must name a list starting with {TEST_LIST_PREFIX}, got {name!r}")
    return name


class IntegrationListTest(unittest.TestCase):
    def test_a_list_not_named_for_tests_is_refused(self) -> None:
        for name in ("Inbox", "Groceries", "test-inbox"):
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                integration_list({"M2B_IT": "1", LIST_VARIABLE: name, "HOME": "/tmp"})

    def test_without_the_switch_nothing_runs(self) -> None:
        self.assertIsNone(integration_list({LIST_VARIABLE: "sb-test-inbox"}))


@unittest.skipUnless(sys.platform == "darwin", "Apple Reminders exists on macOS only")
class AppleRemindersIntegrationTest(Contracts.TasksContract):
    def make_tasks(self, folder: Path) -> Tasks:
        name = integration_list(os.environ)
        if name is None:
            self.skipTest(f"set M2B_IT=1 and {LIST_VARIABLE} on macOS")
        tasks = AppleRemindersTasks(name, command=[shutil.which("reminders") or "reminders"], timeout_seconds=30)
        if tasks.items(include_completed=True):
            self.fail(f"the test list {name} must be empty before the run")
        self.addCleanup(self._delete_everything, tasks)
        return tasks

    def test_a_due_date_reads_back_as_that_day_and_a_due_time_in_local_time(self) -> None:
        self.tasks.add("sb-test due day", due=datetime.date(2026, 12, 1))
        timed = datetime.datetime(2026, 12, 1, 15, 30).astimezone()
        self.tasks.add("sb-test due time", due=timed)

        dues = {task.title: task.due for task in self.tasks.items()}

        self.assertEqual(dues["sb-test due day"], datetime.date(2026, 12, 1))
        self.assertEqual(dues["sb-test due time"], timed)

    def test_notes_of_a_completed_reminder_need_it_reopened_first(self) -> None:
        task_id = self.tasks.add("sb-test completed", notes="first")
        self.tasks.complete(task_id)

        with self.assertRaises(TasksError) as caught:
            self.tasks.set_notes(task_id, "second")

        self.assertIn("reopen", str(caught.exception))

    def _delete_everything(self, tasks: AppleRemindersTasks) -> None:
        for task in tasks.items(include_completed=True):
            if task.completed:
                tasks.uncomplete(task.id)
            tasks.delete(task.id)


if __name__ == "__main__":
    unittest.main()
