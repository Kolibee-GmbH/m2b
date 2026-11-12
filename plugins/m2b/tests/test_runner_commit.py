"""The curation run in a store that is a git repository: the waiting captures committed before its
first step, one commit of the run after the record."""

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
CAPTURES_SUBJECT = "m2b: captures before the curation run 2026-11-07 09:00"
INGEST_FILES_A_FACT = [
    {"tool": "Bash", "command": "m2b ingest list --json"},
    {"tool": "Write", "file_path": "<store>/memory/dana.md", "content": "# Dana\n\n- Likes old maps.\n"},
    {
        "tool": "Edit",
        "file_path": "<store>/memory/MEMORY.md",
        "old_string": "## Facts\n",
        "new_string": "## Facts\n\n- Dana likes old maps (dana.md)\n",
    },
    {"tool": "Bash", "command": "m2b ingest facts-filed <capture:cli>"},
    {"tool": "Bash", "command": "m2b ingest note <capture:cli> 'filed: fact dana.md'"},
    {"tool": "Bash", "command": "m2b ingest finish <capture:cli>"},
]


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

    def subjects(self) -> list[str]:
        return self.git("log", "--format=%s").splitlines()

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
        self.assertEqual(self.authors(), ["m2b", "m2b", "Alex"])
        # A first run also starts the list of candidates.
        self.assertEqual(
            self.committed_paths(),
            [f"corpus/2026/11/{CAPTURE_NAME}", f"inbox/{CAPTURE_NAME}", "state/core/candidates.json", RUN_RECORD],
        )
        committed_record = json.loads(self.git("show", f"HEAD:{RUN_RECORD}"))
        self.assertEqual(committed_record["state"], SUCCEEDED)
        self.assertIsNotNone(committed_record["finished_at"])
        self.assertEqual(self.git("status", "--porcelain").splitlines(), ["?? draft.md"])
        record = load_run_record(self.store)
        assert record is not None
        self.assertNotIn("commit", [step.name for step in record.steps])
        self.assertIn("succeeded: harvest, ingest", self.git("log", "-1", "--format=%b"))

    def test_a_capture_git_does_not_know_is_committed_before_the_run_and_a_revert_puts_it_back(self) -> None:
        """Covers: B162"""
        self.curating()
        self.repository()
        self.capture(CAPTURE_NAME)
        waiting = (self.store_root / "inbox" / CAPTURE_NAME).read_bytes()
        memory = (self.store_root / "memory/MEMORY.md").read_bytes()
        self.model({"m2b:ingest": INGEST_FILES_A_FACT})

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.subjects()[1:], [CAPTURES_SUBJECT, "the store as Alex set it up"])
        self.assertEqual(self.git("show", "--name-status", "--format=", "HEAD~1"), f"A\tinbox/{CAPTURE_NAME}\n")
        self.assertEqual(self.git("show", f"HEAD~1:inbox/{CAPTURE_NAME}").encode(), waiting)
        self.assertIn("Dana likes old maps", (self.store_root / "memory/MEMORY.md").read_text(encoding="utf-8"))
        self.assertFalse((self.store_root / "inbox" / CAPTURE_NAME).exists())

        self.git("revert", "--no-edit", "HEAD")

        self.assertEqual((self.store_root / "inbox" / CAPTURE_NAME).read_bytes(), waiting)
        self.assertFalse((self.store_root / "corpus/2026/11" / CAPTURE_NAME).exists())
        self.assertEqual((self.store_root / "memory/MEMORY.md").read_bytes(), memory)
        self.assertFalse((self.store_root / "memory/dana.md").exists())
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_after_a_later_run_with_nothing_to_do_the_revert_needs_its_record_dropped_first(self) -> None:
        """The way the docs name: git refuses while the later run's record is uncommitted."""
        self.curating()
        self.repository()
        self.capture(CAPTURE_NAME)
        self.model({"m2b:ingest": INGEST_FILES_A_FACT})
        self.run_curate()
        self.clock = test_runner.START + datetime.timedelta(days=1)
        self.run_curate()
        self.assertEqual(self.git("status", "--porcelain").splitlines(), [f" M {RUN_RECORD}"])

        with self.assertRaises(subprocess.CalledProcessError) as refused:
            self.git("revert", "--no-edit", "HEAD")
        self.assertIn(RUN_RECORD, refused.exception.stderr)
        self.git("restore", RUN_RECORD)
        self.git("revert", "--no-edit", "HEAD")

        self.assertTrue((self.store_root / "inbox" / CAPTURE_NAME).exists())
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_with_no_capture_git_does_not_know_a_run_makes_one_commit(self) -> None:
        """Covers: B162"""
        self.curating()
        self.capture(CAPTURE_NAME)
        self.repository()
        self.model({"m2b:ingest": test_runner.INGEST_FILES_THE_CAPTURE})

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.authors(), ["m2b", "Alex"])

    def test_captures_that_could_not_be_committed_reach_the_review_and_leave_the_run_succeeded(self) -> None:
        """Covers: B162"""
        self.curating()
        self.repository()
        self.capture(CAPTURE_NAME)
        self.model({"m2b:ingest": test_runner.INGEST_FILES_THE_CAPTURE})
        refused = test_runner.runner.run_commit.CommitError("git update-ref failed: cannot lock ref 'HEAD'")

        failing = test_runner.mock.patch.object(
            test_runner.runner.run_commit, "commit_waiting_captures", side_effect=refused
        )
        with failing:
            outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED)
        self.assertEqual(self.subjects()[1:], ["the store as Alex set it up"])
        told = "the captures in the inbox were not committed before the run"
        self.assertIn(f"commit: {told}", outcome.message)
        self.assertIn("cannot lock ref", outcome.message)
        record = load_run_record(self.store)
        assert record is not None
        self.assertEqual([(step.name, step.result) for step in record.steps].count(("commit", FAILED)), 1)
        (review,) = self.review_tasks()
        self.assertIn(told, review.notes)
        self.assertIsNone(machine_state.load_backoff(self.machine))
        # The run's commit holds the record and the review that say so, and names no step of its own.
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertIn(told, self.git("show", f"HEAD:{RUN_RECORD}"))
        self.assertNotIn("commit", self.git("log", "-1", "--format=%b"))

    def test_a_capture_that_comes_in_during_preflight_is_filed_and_leaves_the_work_tree_clean(self) -> None:
        self.curating()
        self.repository()
        self.model({"m2b:ingest": test_runner.INGEST_FILES_THE_CAPTURE})
        real_open_tasks = test_runner.runner.open_tasks

        def a_capture_syncs_in_first(*arguments: object, **options: object) -> object:
            self.capture(CAPTURE_NAME)
            return real_open_tasks(*arguments, **options)  # type: ignore[arg-type]

        with test_runner.mock.patch.object(test_runner.runner, "open_tasks", a_capture_syncs_in_first):
            outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        # The run's listing is from before preflight, so its commit could not take the capture out
        # of the inbox again: it is committed only where the run filed it.
        self.assertEqual(self.authors(), ["m2b", "Alex"])
        self.assertIn(f"corpus/2026/11/{CAPTURE_NAME}", self.committed_paths())
        self.assertEqual(self.git("ls-tree", "-r", "--name-only", "HEAD", "inbox"), "")
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all"), "")

    def test_a_run_committed_with_an_index_left_behind_still_says_its_captures_were_not_committed(self) -> None:
        self.curating()
        self.repository()
        self.capture(CAPTURE_NAME)
        self.model({"m2b:ingest": test_runner.INGEST_FILES_THE_CAPTURE})
        commits = test_runner.runner.run_commit
        refused = commits.CommitError("inbox/.gitignore is not downloaded to this machine")
        left_behind = commits.StaleIndexError("the run is committed as 0123456789ab, but the index was not updated")

        no_captures = test_runner.mock.patch.object(commits, "commit_waiting_captures", side_effect=refused)
        stale_index = test_runner.mock.patch.object(commits, "commit", side_effect=left_behind)
        with no_captures, stale_index:
            outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED)
        self.assertIn("the captures in the inbox were not committed before the run", outcome.message)
        self.assertIn("the run is committed as 0123456789ab", outcome.message)
        (review,) = self.review_tasks()
        self.assertIn("were not committed before the run", review.notes)

    def test_captures_committed_with_an_index_left_behind_are_not_said_to_be_uncommitted(self) -> None:
        self.curating()
        self.repository()
        self.capture(CAPTURE_NAME)
        self.model({"m2b:ingest": test_runner.INGEST_FILES_THE_CAPTURE})
        left_behind = test_runner.runner.run_commit.StaleIndexError(
            "the captures are committed as 0123456789ab, but the repository's index was not brought up to date"
        )

        failing = test_runner.mock.patch.object(
            test_runner.runner.run_commit, "commit_waiting_captures", side_effect=left_behind
        )
        with failing:
            outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED)
        self.assertIn("commit: the captures are committed as 0123456789ab, but", outcome.message)
        self.assertNotIn("were not committed", outcome.message)

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
        self.assertEqual(self.authors(), ["m2b", "m2b", "Alex"])
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

    def test_a_run_stopped_before_its_end_leaves_only_the_commit_of_the_waiting_captures(self) -> None:
        """Covers: B139, B162"""
        self.curating()
        self.repository()
        self.capture(CAPTURE_NAME)
        stopped = SystemExit(143)

        stopping_model = test_runner.mock.patch.object(
            test_runner.runner._Run, "_model", autospec=True, side_effect=stopped
        )
        with stopping_model, self.assertRaises(SystemExit):
            self.run_curate()

        self.assertEqual(self.subjects(), [CAPTURES_SUBJECT, "the store as Alex set it up"])
        self.assertEqual(self.committed_paths(), [f"inbox/{CAPTURE_NAME}"])

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
        # Both commits were refused for it; the run's own says so, once.
        self.assertEqual(review.notes.count("in the middle of a merge"), 1)
        self.assertEqual(outcome.message.count("in the middle of a merge"), 1)
        self.assertEqual([step.name for step in record.steps].count("commit"), 1)
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
