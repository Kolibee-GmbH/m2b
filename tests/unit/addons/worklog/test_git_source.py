"""The worklog's git in a folder whose repository names programs of its own."""

from __future__ import annotations

import datetime
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import test_git_program as hostile
from m2b_worklog.sources.git import read_git

GIT = shutil.which("git")
SIGNED = datetime.datetime.fromtimestamp(hostile.SIGNED_AT, datetime.timezone.utc)
DAY_START = SIGNED - datetime.timedelta(hours=12)
DAY_END = SIGNED + datetime.timedelta(hours=12)


@unittest.skipIf(GIT is None, "git is not installed")
class HostileRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.base = Path(self._temp.name).resolve()
        self.marker = self.base / "a-command-ran"
        self.folder = self.base / "code" / "acme"
        self.environ = hostile.without_the_machines_configuration(
            {"PATH": os.environ.get("PATH", ""), "HOME": str(self.base / "user-home")}
        )
        hostile.make_repository_that_checks_signatures(self.environ, self.folder, self.marker)

    def read(self, environ: dict[str, str]) -> list[str]:
        assert GIT is not None
        with mock.patch.dict(os.environ, environ, clear=True):
            facts = read_git(self.folder, DAY_START, DAY_END, GIT)
        self.assertTrue(facts.state.is_read, facts.state)
        return [commit.subject for commit in facts.commits]

    def test_the_commits_are_read_and_the_program_the_repository_names_for_signatures_is_not_started(self) -> None:
        """Covers: B169"""
        self.assertEqual(self.read(self.environ), [hostile.SIGNED_SUBJECT])

        self.assertFalse(self.marker.exists())

    def test_variables_that_point_git_at_another_repository_do_not_reach_it(self) -> None:
        """Covers: B169"""
        elsewhere = self.base / "another-repository"
        elsewhere.mkdir()
        hostile.git(self.environ, elsewhere, "init", "-q", "-b", "main")
        pointing = {**self.environ, "GIT_DIR": str(elsewhere / ".git"), "GIT_WORK_TREE": str(elsewhere)}

        self.assertEqual(self.read(pointing), [hostile.SIGNED_SUBJECT])


class AuthorTimeTest(unittest.TestCase):
    def test_a_time_git_writes_with_a_z_for_utc_is_read_on_every_python(self) -> None:
        def answers(command: list[str], **options: Any) -> subprocess.CompletedProcess[str]:
            if "user.email" in command:
                said = "alex@example.com\n"
            elif "--all" in command:
                said = "abc123\x1f2026-11-07T09:30:00Z\x1fInvoice totals\n"
            else:
                said = ""
            return subprocess.CompletedProcess(command, 0, said, "")

        start = datetime.datetime(2026, 11, 7, tzinfo=datetime.timezone.utc)
        facts = read_git(Path("/work/acme"), start, start + datetime.timedelta(days=1), "git", answers)

        self.assertEqual([commit.subject for commit in facts.commits], ["Invoice totals"])


if __name__ == "__main__":
    unittest.main()
