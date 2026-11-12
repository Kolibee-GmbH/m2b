"""The curation run in a store that is a git repository: one commit per run, after the record."""

from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
import unittest

import test_runner
from m2b.curate import machine_state
from m2b.run_record import FAILED, RUN_RECORD, SUCCEEDED, load_run_record

OWNER = ("-c", "user.name=Alex", "-c", "user.email=alex@example.com")
CAPTURE_NAME = "20261107T070000Z-cli-a1b2.md"


@unittest.skipIf(shutil.which("git") is None, "git is not installed")
class RunInARepositoryTest(test_runner.RunnerTest):
    def setUp(self) -> None:
        super().setUp()
        # Neither the developer's nor the machine's git configuration reaches a test.
        self.environ["GIT_CONFIG_GLOBAL"] = os.devnull
        self.environ["GIT_CONFIG_SYSTEM"] = os.devnull

    def git(self, *arguments: str) -> str:
        result = subprocess.run(
            ["git", *OWNER, *arguments],
            cwd=self.store_root,
            env=self.environ,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def repository(self) -> None:
        """The store as its owner committed it, before anything waits in the inbox."""
        self.git("init", "-q", "-b", "main")
        self.git("add", "--all")
        self.git("commit", "-q", "-m", "the store as Alex set it up")

    def authors(self) -> list[str]:
        return self.git("log", "--format=%an").splitlines()

    def committed_paths(self) -> list[str]:
        return sorted(self.git("show", "--name-only", "--format=", "--no-renames", "HEAD").splitlines())

    def test_a_run_ends_with_one_commit_that_holds_its_changes_its_record_and_nothing_else(self) -> None:
        """Covers: B139"""
        self.curating()
        self.repository()
        self.capture(CAPTURE_NAME)
        self.write("draft.md", "a thought Alex has not committed\n")
        self.model({"m2b:ingest": test_runner.INGEST_FILES_THE_CAPTURE})

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.authors(), ["m2b", "Alex"])
        # A first run also starts the list of candidates.
        self.assertEqual(
            self.committed_paths(), [f"corpus/2026/11/{CAPTURE_NAME}", "state/core/candidates.json", RUN_RECORD]
        )
        committed_record = json.loads(self.git("show", f"HEAD:{RUN_RECORD}"))
        self.assertEqual(committed_record["state"], SUCCEEDED)
        self.assertIsNotNone(committed_record["finished_at"])
        self.assertEqual(self.git("status", "--porcelain").splitlines(), ["?? draft.md"])
        record = load_run_record(self.store)
        assert record is not None
        self.assertNotIn("commit", [step.name for step in record.steps])
        self.assertIn("succeeded: harvest, ingest", self.git("log", "-1", "--format=%b"))

    def test_a_run_with_nothing_to_do_makes_no_commit(self) -> None:
        """Covers: B139"""
        self.curating()
        self.repository()
        self.run_curate()
        self.assertEqual(self.authors(), ["m2b", "Alex"])
        self.clock = test_runner.START + datetime.timedelta(days=1)

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.authors(), ["m2b", "Alex"])
        self.assertEqual(self.git("status", "--porcelain").splitlines(), [f" M {RUN_RECORD}"])

    def test_a_failed_run_is_committed_too(self) -> None:
        """Covers: B139"""
        self.curating()
        self.repository()
        self.capture(CAPTURE_NAME)
        self.model({"m2b:ingest": []}, outcomes={"m2b:ingest": "error_max_turns"})

        outcome = self.run_curate()

        self.assertEqual(outcome.state, FAILED)
        self.assertEqual(self.authors(), ["m2b", "Alex"])
        self.assertIn("failed: ingest", self.git("log", "-1", "--format=%b"))

    def test_a_run_stopped_at_preflight_commits_nothing(self) -> None:
        """Covers: B139"""
        self.curating()
        self.repository()
        self.capture(CAPTURE_NAME)
        unreachable = test_runner.TasksUnreachableError("the task list did not answer")

        failing_tasks = test_runner.mock.patch.object(test_runner.runner, "open_tasks", side_effect=unreachable)
        with failing_tasks, self.assertRaises(test_runner.TasksUnreachableError):
            self.run_curate()

        self.assertEqual(self.authors(), ["Alex"])

    def test_a_run_stopped_before_its_end_commits_nothing(self) -> None:
        """Covers: B139"""
        self.curating()
        self.repository()
        self.capture(CAPTURE_NAME)
        stopped = SystemExit(143)

        stopping_model = test_runner.mock.patch.object(
            test_runner.runner._Run, "_model", autospec=True, side_effect=stopped
        )
        with stopping_model, self.assertRaises(SystemExit):
            self.run_curate()

        self.assertEqual(self.authors(), ["Alex"])

    def test_a_commit_that_fails_reaches_the_review_and_the_record_and_leaves_the_run_succeeded(self) -> None:
        """Covers: B141"""
        self.curating()
        self.repository()
        self.capture(CAPTURE_NAME)
        self.model({"m2b:ingest": test_runner.INGEST_FILES_THE_CAPTURE})
        (self.store_root / ".git" / "MERGE_HEAD").write_text(self.git("rev-parse", "HEAD"), encoding="utf-8")

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED)
        self.assertIn("commit: the repository is in the middle of a merge", outcome.message)
        self.assertEqual(self.authors(), ["Alex"])
        record = load_run_record(self.store)
        assert record is not None
        self.assertEqual(record.state, SUCCEEDED)
        self.assertEqual((record.steps[-1].name, record.steps[-1].result), ("commit", FAILED))
        self.assertEqual(record.last_success, test_runner.START)
        (review,) = self.review_tasks()
        self.assertIn("commit", review.notes)
        self.assertIn("in the middle of a merge", review.notes)
        self.assertIsNone(machine_state.load_backoff(self.machine))

    def test_a_store_that_cannot_be_listed_before_the_run_is_a_failed_commit_not_a_failed_run(self) -> None:
        """Covers: B141"""
        self.curating()
        self.repository()
        self.capture(CAPTURE_NAME)
        self.model({"m2b:ingest": test_runner.INGEST_FILES_THE_CAPTURE})
        listed = {"times": 0}
        real_listing = test_runner.runner.run_commit.listing

        def fails_once(store: object) -> object:
            listed["times"] += 1
            if listed["times"] == 1:
                raise test_runner.StoreReadError("corpus could not be listed: permission denied")
            return real_listing(store)  # type: ignore[arg-type]

        with test_runner.mock.patch.object(test_runner.runner.run_commit, "listing", fails_once):
            outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED)
        self.assertEqual(self.authors(), ["Alex"])
        (review,) = self.review_tasks()
        self.assertIn("the store could not be listed before the run", review.notes)

    def test_with_the_setting_off_a_run_in_a_repository_commits_nothing(self) -> None:
        """Covers: B139"""
        self.curating(curation={"git_commit": False})
        self.repository()
        self.capture(CAPTURE_NAME)
        self.model({"m2b:ingest": test_runner.INGEST_FILES_THE_CAPTURE})

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.authors(), ["Alex"])
        self.assertEqual(self.review_tasks(), [])


class RunWithoutARepositoryTest(test_runner.RunnerTest):
    def test_a_store_that_is_no_repository_gets_none_and_the_run_says_nothing_of_it(self) -> None:
        """Covers: B139"""
        self.curating()
        self.capture(CAPTURE_NAME)
        self.model({"m2b:ingest": test_runner.INGEST_FILES_THE_CAPTURE})

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(outcome.message, "the curation run succeeded")
        self.assertFalse((self.store_root / ".git").exists())
        self.assertEqual(self.review_tasks(), [])
        record = load_run_record(self.store)
        assert record is not None
        self.assertNotIn("commit", [step.name for step in record.steps])


if __name__ == "__main__":
    unittest.main()
