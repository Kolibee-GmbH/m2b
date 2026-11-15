"""The commit of a curation run: what goes into it, what git is asked, and what it never touches."""

from __future__ import annotations

import datetime
import os
import shlex
import shutil
import subprocess
import tempfile
import types
import unicodedata
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from m2b import git_program
from m2b.curate import run_commit
from m2b.run_record import StepResult
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard
from store_contract import FakeEviction
from test_git_program import make_partial_clone

GIT = shutil.which("git")
START = datetime.datetime(2026, 11, 7, 9, 0).astimezone()
TEXT = run_commit.Message("m2b: curation run 2026-11-07 09:00", "succeeded: ingest")
NEW_CAPTURE = "20261107T080000Z-cli-c3d4.md"
OWNER = ("-c", "user.name=Alex", "-c", "user.email=alex@example.com")
# The last option m2b gives git before the subcommand.
GIT_OPTIONS_END = git_program.SETTINGS[-1]


class RecordingRunner:
    """Runs what it is given and keeps each git command with the paths it got on standard input."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], list[str]]] = []
        self.before: dict[str, Any] = {}

    def __call__(self, command: list[str], **options: Any) -> Any:
        if GIT_OPTIONS_END in command:
            arguments = command[command.index(GIT_OPTIONS_END) + 1 :]
            handed = [os.fsdecode(path) for path in (options.get("input") or b"").split(b"\0") if path]
            self.calls.append((arguments, handed))
            if arguments[0] in self.before:
                self.before[arguments[0]]()
        return subprocess.run(command, **options)

    def paths_handed_to_git(self) -> set[str]:
        return {path for _, handed in self.calls for path in handed}

    def subcommands(self) -> list[str]:
        return [arguments[0] for arguments, _ in self.calls]


@unittest.skipIf(GIT is None, "git is not installed")
class RunCommitTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        base = Path(self._temp.name).resolve()
        self.root = base / "sb-test-store"
        self.root.mkdir()
        self.temp_dir = base / "machine-tmp"
        self.eviction = FakeEviction()
        self.store = FolderStore(self.root, self.temp_dir, DatalessGuard(True, lstat=self.eviction.lstat))
        # Neither the developer's nor the machine's git configuration reaches a test.
        self.environ = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(base / "user-home"),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
        }
        self.runner = RecordingRunner()
        # The git directory the machine config names; none, as on a machine that keeps `.git` in the store.
        self.named: Path | None = None

    def write(self, relative: str, text: str) -> None:
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def git(self, *arguments: str, cwd: Path | None = None) -> str:
        result = subprocess.run(
            ["git", *OWNER, *arguments],
            cwd=cwd or self.root,
            env=self.environ,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def repository_with_a_commit(self) -> None:
        self.git("init", "-q", "-b", "main")
        self.write("memory/MEMORY.md", "# Memory\n")
        self.write("inbox/20261107T070000Z-cli-a1b2.md", "Dana likes old maps\n")
        self.git("add", "memory", "inbox")
        self.git("commit", "-q", "-m", "the store as Alex set it up")

    def repository(self) -> run_commit.Repository:
        found = run_commit.find_repository(self.store, self.environ, run=self.runner, named_directory=self.named)
        assert found is not None
        return found

    def commit(self, before: run_commit.StoreListing, **options: Any) -> str | None:
        return run_commit.commit(self.repository(), before, TEXT, self.temp_dir, **options)

    def log(self) -> list[str]:
        return self.git("log", "--format=%an <%ae> | %cn <%ce> | %s").splitlines()

    def committed_paths(self) -> list[str]:
        return sorted(self.git("show", "--name-status", "--format=", "--no-renames", "HEAD").splitlines())

    def a_run(self) -> run_commit.StoreListing:
        """What a run does to the store: files a capture, writes a fact, and its record."""
        before = run_commit.listing(self.store)
        (self.root / "corpus/2026/11").mkdir(parents=True)
        os.replace(
            self.root / "inbox/20261107T070000Z-cli-a1b2.md", self.root / "corpus/2026/11/20261107T070000Z-cli-a1b2.md"
        )
        self.write("memory/MEMORY.md", "# Memory\n\n- Dana likes old maps (dana.md)\n")
        self.write("memory/dana.md", "# Dana\n\n- Likes old maps.\n")
        self.write("state/core/last-run.json", '{"state": "succeeded"}\n')
        return before


class WhatGoesInTest(RunCommitTest):
    def test_a_run_is_one_commit_of_what_changed_while_it_ran(self) -> None:
        """Covers: B139"""
        self.repository_with_a_commit()

        new = self.commit(self.a_run())

        self.assertEqual(new, self.git("rev-parse", "HEAD").strip())
        self.assertEqual(len(self.log()), 2)
        self.assertEqual(
            self.committed_paths(),
            [
                "A\tcorpus/2026/11/20261107T070000Z-cli-a1b2.md",
                "A\tmemory/dana.md",
                "A\tstate/core/last-run.json",
                "D\tinbox/20261107T070000Z-cli-a1b2.md",
                "M\tmemory/MEMORY.md",
            ],
        )
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_what_the_owner_left_uncommitted_or_staged_stays_out_and_stays_as_it_is(self) -> None:
        """Covers: B139, B140"""
        self.repository_with_a_commit()
        self.write("draft.md", "a thought Alex has not committed\n")
        self.write("memory/alex.md", "# Alex\n")
        self.git("add", "memory/alex.md")

        self.commit(self.a_run())

        self.assertNotIn("draft.md", "\n".join(self.committed_paths()))
        self.assertNotIn("memory/alex.md", "\n".join(self.committed_paths()))
        self.assertEqual(self.git("status", "--porcelain").splitlines(), ["A  memory/alex.md", "?? draft.md"])

    def test_hidden_files_and_files_git_ignores_stay_out(self) -> None:
        """Covers: B139"""
        self.repository_with_a_commit()
        self.write(".gitignore", "state/\n")
        before = self.a_run()
        self.write("memory/.dana.md.tmp", "a temporary file\n")

        self.commit(before)

        committed = "\n".join(self.committed_paths())
        self.assertNotIn("state/", committed)
        self.assertNotIn(".tmp", committed)
        self.assertNotIn(".gitignore", committed)
        self.assertIn("memory/dana.md", committed)

    def test_a_file_name_that_reads_like_pathspec_magic_is_only_a_name(self) -> None:
        self.repository_with_a_commit()
        self.write(".gitignore", "notes.md\n")
        before = self.a_run()
        # Only a path that begins with the colon is read as magic, so the files lie in the store folder.
        self.write(":!odd.md", "a name that starts like an exclusion\n")
        self.write(":(top)notes.md", "a name that starts like a prefix\n")
        self.write("notes.md", "ignored by the rule\n")

        self.commit(before)

        committed = self.committed_paths()
        self.assertIn("A\t:!odd.md", committed)
        self.assertIn("A\t:(top)notes.md", committed)
        self.assertNotIn("A\tnotes.md", committed)

    def test_a_tracked_file_goes_in_whatever_an_ignore_rule_says(self) -> None:
        self.repository_with_a_commit()
        self.write(".gitignore", "memory/\n")

        self.commit(self.a_run())

        self.assertIn("M\tmemory/MEMORY.md", self.committed_paths())
        self.assertNotIn("A\tmemory/dana.md", self.committed_paths())

    def test_nothing_changed_makes_no_commit_and_starts_no_git(self) -> None:
        """Covers: B139"""
        self.repository_with_a_commit()

        new = self.commit(run_commit.listing(self.store))

        self.assertIsNone(new)
        self.assertEqual(self.runner.calls, [])
        self.assertEqual(len(self.log()), 1)

    def test_a_run_that_changed_only_its_record_makes_no_commit(self) -> None:
        """Covers: B139"""
        self.repository_with_a_commit()
        before = run_commit.listing(self.store)
        self.write("state/core/last-run.json", '{"state": "succeeded"}\n')

        new = self.commit(before, no_reason_alone=("state/core/last-run.json",))

        self.assertIsNone(new)
        self.assertEqual(len(self.log()), 1)

    def test_the_record_and_a_file_written_again_as_it_was_make_no_commit(self) -> None:
        """Covers: B139"""
        self.repository_with_a_commit()
        before = run_commit.listing(self.store)
        self.write("state/core/last-run.json", '{"state": "succeeded"}\n')
        os.utime(self.root / "memory/MEMORY.md", ns=(1, 1))

        new = self.commit(before, no_reason_alone=("state/core/last-run.json",))

        self.assertIsNone(new)
        self.assertEqual(len(self.log()), 1)

    def test_a_file_written_again_with_the_same_bytes_makes_no_commit(self) -> None:
        self.repository_with_a_commit()
        before = run_commit.listing(self.store)
        os.utime(self.root / "memory/MEMORY.md", ns=(1, 1))

        new = self.commit(before)

        self.assertIsNone(new)
        self.assertEqual(len(self.log()), 1)

    def test_only_ignored_changes_make_no_commit(self) -> None:
        self.repository_with_a_commit()
        self.write(".gitignore", "state/\n")
        before = run_commit.listing(self.store)
        self.write("state/core/proposals.json", "{}\n")

        self.assertIsNone(self.commit(before))
        self.assertEqual(len(self.log()), 1)

    def test_a_repository_without_a_commit_gets_its_first_one(self) -> None:
        self.git("init", "-q", "-b", "main")
        before = run_commit.listing(self.store)
        self.write("memory/MEMORY.md", "# Memory\n")

        new = self.commit(before)

        self.assertEqual(new, self.git("rev-parse", "main").strip())
        self.assertEqual(self.committed_paths(), ["A\tmemory/MEMORY.md"])
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_a_git_directory_outside_the_store_is_committed_into(self) -> None:
        outside = self.root.parent / "store-history"
        self.git("init", "-q", "-b", "main", "--separate-git-dir", str(outside))
        self.assertTrue((self.root / ".git").is_file())
        self.named = outside
        before = run_commit.listing(self.store)
        self.write("memory/MEMORY.md", "# Memory\n")

        self.commit(before)

        self.assertEqual(self.committed_paths(), ["A\tmemory/MEMORY.md"])

    def test_a_folder_where_a_file_was_takes_its_place(self) -> None:
        self.repository_with_a_commit()
        before = run_commit.listing(self.store)
        (self.root / "memory/MEMORY.md").unlink()
        self.write("memory/MEMORY.md/part.md", "# Part\n")

        self.commit(before)

        self.assertEqual(self.committed_paths(), ["A\tmemory/MEMORY.md/part.md", "D\tmemory/MEMORY.md"])


class WhereNothingIsDoneTest(RunCommitTest):
    def test_a_store_without_a_git_folder_has_no_repository(self) -> None:
        """Covers: B139"""
        self.assertIsNone(run_commit.find_repository(self.store, self.environ, run=self.runner))
        self.assertEqual(self.runner.calls, [])

    def test_a_store_inside_somebody_elses_work_tree_has_no_repository(self) -> None:
        """Covers: B139"""
        self.git("init", "-q", "-b", "main", cwd=self.root.parent)

        self.assertIsNone(run_commit.find_repository(self.store, self.environ, run=self.runner))

    def test_a_machine_without_git_has_no_repository(self) -> None:
        """Covers: B139"""
        self.git("init", "-q", "-b", "main")
        empty = self.root.parent / "no-programs"
        empty.mkdir()

        found = run_commit.find_repository(self.store, {**self.environ, "PATH": str(empty)}, run=self.runner)

        self.assertIsNone(found)
        self.assertEqual(self.runner.calls, [])

    def test_on_macos_the_stand_in_for_git_is_never_started_without_the_developer_tools(self) -> None:
        """Covers: B139"""
        self.git("init", "-q", "-b", "main")
        if not git_program.APPLE_GIT_STAND_IN.exists():
            self.skipTest("this machine has no /usr/bin/git")
        started: list[list[str]] = []

        def no_developer_tools(command: list[str], **options: Any) -> Any:
            started.append(command)
            return types.SimpleNamespace(returncode=2)

        environ = {**self.environ, "PATH": str(git_program.APPLE_GIT_STAND_IN.parent)}
        found = run_commit.find_repository(self.store, environ, platform="darwin", run=no_developer_tools)

        self.assertIsNone(found)
        self.assertEqual(started, [list(git_program.DEVELOPER_TOOLS_CHECK)])


class TheOwnersRepositoryTest(RunCommitTest):
    def test_the_commit_is_m2bs_and_says_how_the_run_went(self) -> None:
        """Covers: B140"""
        self.repository_with_a_commit()
        steps = [
            StepResult("harvest", "succeeded"),
            StepResult("ingest", "succeeded"),
            StepResult("refresh", "skipped"),
        ]
        text = run_commit.message(START, steps)

        run_commit.commit(self.repository(), self.a_run(), text, self.temp_dir)

        self.assertEqual(
            self.log()[0], f"m2b <m2b@localhost> | m2b <m2b@localhost> | m2b: curation run {START:%Y-%m-%d %H:%M}"
        )
        self.assertEqual(self.git("log", "-1", "--format=%b").strip(), "succeeded: harvest, ingest\nskipped: refresh")

    def test_no_configuration_is_written_no_hook_runs_and_nothing_but_plumbing_is_asked(self) -> None:
        """Covers: B140"""
        self.repository_with_a_commit()
        ran = self.root.parent / "a-hook-ran"
        for name in ("pre-commit", "commit-msg", "post-commit", "reference-transaction"):
            hook = self.root / ".git/hooks" / name
            hook.write_text(f'#!/bin/sh\necho {name} >> "{ran}"\n', encoding="utf-8")
            hook.chmod(0o755)
        self.git("config", "commit.gpgsign", "true")
        self.git("config", "gpg.program", str(self.root.parent / "no-such-gpg"))
        config = (self.root / ".git/config").read_bytes()

        self.commit(self.a_run())

        self.assertEqual(len(self.log()), 2)
        self.assertFalse(ran.exists())
        self.assertEqual((self.root / ".git/config").read_bytes(), config)
        self.assertEqual(
            set(self.runner.subcommands()),
            {
                "rev-parse",
                "config",
                "read-tree",
                "check-ignore",
                "update-index",
                "write-tree",
                "commit-tree",
                "update-ref",
            },
        )

    def test_variables_that_point_git_elsewhere_do_not_reach_it(self) -> None:
        self.repository_with_a_commit()
        elsewhere = self.root.parent / "another-repository"
        elsewhere.mkdir()
        self.git("init", "-q", "-b", "main", cwd=elsewhere)
        pointing_elsewhere = {
            **self.environ,
            "GIT_DIR": str(elsewhere / ".git"),
            "GIT_WORK_TREE": str(elsewhere),
            "GIT_INDEX_FILE": str(elsewhere / "index"),
        }
        repository = run_commit.find_repository(self.store, pointing_elsewhere, run=self.runner)
        assert repository is not None

        run_commit.commit(repository, self.a_run(), TEXT, self.temp_dir)

        self.assertEqual(len(self.log()), 2)
        self.assertFalse((elsewhere / "index").exists())

    def test_a_head_the_owner_moved_during_the_commit_keeps_the_owners_commit(self) -> None:
        """Covers: B140"""
        self.repository_with_a_commit()
        before = self.a_run()

        def the_owner_commits() -> None:
            self.write("draft.md", "committed by Alex in between\n")
            self.git("add", "draft.md")
            self.git("commit", "-q", "-m", "a commit of Alex")

        self.runner.before["update-ref"] = the_owner_commits

        with self.assertRaisesRegex(run_commit.CommitError, "git update-ref failed"):
            self.commit(before)

        self.assertEqual(self.log()[0].rpartition(" | ")[2], "a commit of Alex")
        self.assertEqual(len(self.log()), 2)

    def test_an_operation_the_owner_has_not_finished_means_no_commit(self) -> None:
        """Covers: B140"""
        self.repository_with_a_commit()
        (self.root / ".git/MERGE_HEAD").write_text(self.git("rev-parse", "HEAD"), encoding="utf-8")

        with self.assertRaisesRegex(run_commit.CommitError, "in the middle of a merge"):
            self.commit(self.a_run())

        self.assertEqual(len(self.log()), 1)

    def test_a_repository_whose_work_tree_is_another_folder_means_no_commit(self) -> None:
        self.repository_with_a_commit()
        elsewhere = self.root.parent / "another-work-tree"
        elsewhere.mkdir()
        self.git("config", "core.worktree", str(elsewhere))

        with self.assertRaisesRegex(run_commit.CommitError, "not the top of the repository's work tree"):
            self.commit(self.a_run())

        self.assertEqual(len(self.log()), 1)

    def test_each_git_keeps_what_the_run_hands_its_children(self) -> None:
        """Covers: B63"""
        self.repository_with_a_commit()
        held, other_end = os.pipe()
        self.addCleanup(os.close, held)
        self.addCleanup(os.close, other_end)
        handed = []

        def remembering(command: list[str], **options: Any) -> Any:
            if GIT_OPTIONS_END in command:
                handed.append(options["pass_fds"])
            return subprocess.run(command, **options)

        repository = run_commit.find_repository(self.store, self.environ, pass_fds=(held,), run=remembering)
        assert repository is not None

        run_commit.commit(repository, self.a_run(), TEXT, self.temp_dir)

        self.assertEqual(set(handed), {(held,)})
        self.assertGreater(len(handed), 5)

    def test_a_git_that_does_not_answer_is_a_failed_commit(self) -> None:
        self.repository_with_a_commit()
        before = self.a_run()

        def hangs(command: list[str], **options: Any) -> Any:
            raise subprocess.TimeoutExpired(command, options["timeout"])

        repository = run_commit.Repository(self.store, "git", self.environ, run=hangs)

        with self.assertRaisesRegex(run_commit.CommitError, "did not answer within 60 seconds"):
            run_commit.commit(repository, before, TEXT, self.temp_dir)

    def test_an_index_that_cannot_be_brought_up_to_date_names_the_commit_that_was_made(self) -> None:
        self.repository_with_a_commit()
        before = self.a_run()
        self.runner.before["update-ref"] = lambda: (self.root / ".git/index.lock").write_text("", encoding="utf-8")

        with self.assertRaisesRegex(run_commit.CommitError, r"the run is committed as [0-9a-f]{12}, but") as raised:
            self.commit(before)

        self.assertIn("git update-index failed", str(raised.exception))
        self.assertEqual(len(self.log()), 2)


class WaitingCapturesTest(RunCommitTest):
    """The commit before a run: the captures in the inbox that git does not know yet, and nothing else."""

    def waiting(self, name: str = NEW_CAPTURE, text: str = "Robin moved to Lisbon\n") -> str:
        self.write(f"inbox/{name}", text)
        return f"inbox/{name}"

    def commit_captures(self, before: run_commit.StoreListing | None = None) -> str | None:
        """Commits the captures of a run that begins now, or began when ``before`` was taken."""
        listed = before or run_commit.listing(self.store)
        text = run_commit.captures_message(START)
        return run_commit.commit_waiting_captures(self.repository(), listed, text, self.temp_dir)

    def test_a_capture_git_does_not_know_is_committed_where_it_waits(self) -> None:
        """Covers: B162"""
        self.repository_with_a_commit()
        capture = self.waiting()

        new = self.commit_captures()

        self.assertEqual(new, self.git("rev-parse", "HEAD").strip())
        self.assertEqual(self.committed_paths(), [f"A\t{capture}"])
        self.assertEqual(self.git("show", f"HEAD:{capture}"), "Robin moved to Lisbon\n")
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(
            self.log()[0],
            f"m2b <m2b@localhost> | m2b <m2b@localhost> | m2b: captures before the curation run {START:%Y-%m-%d %H:%M}",
        )

    def test_reverting_the_run_that_filed_it_puts_the_capture_back_into_the_inbox(self) -> None:
        """Covers: B162"""
        self.repository_with_a_commit()
        capture = self.waiting()
        self.commit_captures()
        before = run_commit.listing(self.store)
        filed = self.root / "corpus/2026/11" / NEW_CAPTURE
        filed.parent.mkdir(parents=True)
        os.replace(self.root / capture, filed)
        self.write("memory/MEMORY.md", "# Memory\n\n- Robin lives in Lisbon (robin.md)\n")
        self.commit(before)

        self.git("revert", "--no-edit", "HEAD")

        self.assertEqual((self.root / capture).read_text(encoding="utf-8"), "Robin moved to Lisbon\n")
        self.assertFalse(filed.exists())
        self.assertEqual((self.root / "memory/MEMORY.md").read_text(encoding="utf-8"), "# Memory\n")
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_a_capture_that_came_in_after_the_run_listed_the_store_stays_out(self) -> None:
        """Covers: B162"""
        self.repository_with_a_commit()
        capture = self.waiting()
        before = run_commit.listing(self.store)
        late = self.waiting("20261107T090030Z-cli-a7b8.md", "arrived while the run was starting\n")

        self.commit_captures(before)

        # The run's commit takes a path out of the inbox only when its listing had it there.
        self.assertEqual(self.committed_paths(), [f"A\t{capture}"])
        self.assertEqual(self.git("status", "--porcelain").splitlines(), [f"?? {late}"])

    def test_a_capture_that_came_in_during_the_run_and_still_waits_outlives_a_revert_of_the_run(self) -> None:
        """Covers: B167"""
        self.repository_with_a_commit()
        before = self.a_run()
        late = self.waiting("20261107T090030Z-cli-a7b8.md", "arrived while the run was filing\n")

        self.commit(before)

        self.assertNotIn(late, "\n".join(self.committed_paths()))
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all").splitlines(), [f"?? {late}"])

        self.git("revert", "--no-edit", "HEAD")

        self.assertEqual((self.root / late).read_text(encoding="utf-8"), "arrived while the run was filing\n")

    def test_the_next_run_commits_a_capture_the_run_before_it_left_waiting(self) -> None:
        """Covers: B167"""
        self.repository_with_a_commit()
        before = self.a_run()
        late = self.waiting("20261107T090030Z-cli-a7b8.md", "arrived while the run was filing\n")
        self.commit(before)

        self.commit_captures()

        self.assertEqual(self.committed_paths(), [f"A\t{late}"])
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_a_capture_that_came_in_while_a_run_changed_only_its_record_makes_no_commit(self) -> None:
        """Covers: B167"""
        self.repository_with_a_commit()
        before = run_commit.listing(self.store)
        self.write("state/core/last-run.json", '{"state": "succeeded"}\n')
        self.waiting()

        new = self.commit(before, no_reason_alone=("state/core/last-run.json",))

        self.assertIsNone(new)
        self.assertEqual(len(self.log()), 1)

    def test_a_waiting_capture_the_run_wrote_into_goes_into_the_runs_commit(self) -> None:
        """Covers: B167"""
        self.repository_with_a_commit()
        before = run_commit.listing(self.store)
        self.write("inbox/20261107T070000Z-cli-a1b2.md", "Dana likes old maps\n\nfiled: waits for a download\n")

        self.commit(before)

        self.assertEqual(self.committed_paths(), ["M\tinbox/20261107T070000Z-cli-a1b2.md"])

    def test_a_waiting_file_with_a_name_outside_the_schema_that_changed_goes_into_the_runs_commit(self) -> None:
        """Covers: B167"""
        self.repository_with_a_commit()
        self.write("inbox/report.docx", "the report as Alex wrote it\n")
        self.git("add", "inbox/report.docx")
        self.git("commit", "-q", "-m", "a report Alex dropped into the inbox")
        before = run_commit.listing(self.store)
        self.write("inbox/report.docx", "the report, saved again while the run ran\n")

        self.commit(before)

        self.assertEqual(self.committed_paths(), ["M\tinbox/report.docx"])

    def test_a_new_file_whose_name_only_begins_like_the_inbox_goes_into_the_runs_commit(self) -> None:
        """Covers: B167"""
        self.repository_with_a_commit()
        before = run_commit.listing(self.store)
        self.write("inbox-rules.md", "what Alex wants filed where\n")

        self.commit(before)

        self.assertEqual(self.committed_paths(), ["A\tinbox-rules.md"])

    def test_a_capture_the_run_gave_a_new_name_goes_in_under_it_and_a_revert_takes_the_renaming_back(self) -> None:
        """Covers: B167"""
        self.repository_with_a_commit()
        self.write("inbox/dentist.md", "Dentist on Friday at nine\n")
        self.git("add", "inbox/dentist.md")
        self.git("commit", "-q", "-m", "a note Alex dropped into the inbox")
        before = run_commit.listing(self.store)
        renamed = f"inbox/{NEW_CAPTURE}"
        os.replace(self.root / "inbox/dentist.md", self.root / renamed)

        self.commit(before, carried_on={renamed: "dentist.md"})

        self.assertEqual(self.committed_paths(), [f"A\t{renamed}", "D\tinbox/dentist.md"])

        self.git("revert", "--no-edit", "HEAD")

        self.assertEqual((self.root / "inbox/dentist.md").read_text(encoding="utf-8"), "Dentist on Friday at nine\n")
        self.assertFalse((self.root / renamed).exists())
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_a_capture_the_run_renamed_out_of_a_subfolder_of_the_inbox_goes_in_under_its_new_name(self) -> None:
        """Covers: B167"""
        self.repository_with_a_commit()
        self.write("inbox/scans/dentist.md", "Dentist on Friday at nine\n")
        self.git("add", "inbox/scans/dentist.md")
        self.git("commit", "-q", "-m", "a note Alex dropped into a folder of the inbox")
        before = run_commit.listing(self.store)
        renamed = f"inbox/{NEW_CAPTURE}"
        os.replace(self.root / "inbox/scans/dentist.md", self.root / renamed)

        self.commit(before, carried_on={renamed: "dentist.md"})

        self.assertEqual(self.committed_paths(), [f"A\t{renamed}", "D\tinbox/scans/dentist.md"])

    def test_the_note_and_the_reading_copy_the_run_put_beside_a_waiting_file_go_into_the_runs_commit(self) -> None:
        """Covers: B167"""
        self.repository_with_a_commit()
        self.write("inbox/scans/20261107T071500Z-phone-e5f6.heic", "a photo of the receipt\n")
        self.git("add", "inbox/scans")
        self.git("commit", "-q", "-m", "a photo Alex dropped into the inbox")
        before = run_commit.listing(self.store)
        self.write("inbox/20261107T071500Z-phone-e5f6.md", "A heic file.\n\nfacts_filed by the run\n")
        self.write("inbox/20261107T071500Z-phone-e5f6.jpg", "a copy the model can read\n")

        self.commit(before)

        self.assertEqual(
            self.committed_paths(),
            ["A\tinbox/20261107T071500Z-phone-e5f6.jpg", "A\tinbox/20261107T071500Z-phone-e5f6.md"],
        )

        self.git("revert", "--no-edit", "HEAD")

        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all"), "")

    def test_a_file_that_came_in_and_shares_only_a_free_name_with_a_waiting_one_still_waits(self) -> None:
        """Covers: B167"""
        self.repository_with_a_commit()
        self.write("inbox/report.docx", "the report as Alex wrote it\n")
        self.git("add", "inbox/report.docx")
        self.git("commit", "-q", "-m", "a report Alex dropped into the inbox")
        before = run_commit.listing(self.store)
        self.write("memory/dana.md", "# Dana\n\n- Likes old maps.\n")
        self.write("inbox/report.pdf", "the report as a PDF, synced in later\n")

        self.commit(before)

        self.assertEqual(self.committed_paths(), ["A\tmemory/dana.md"])

    def test_two_new_captures_that_claim_one_old_name_both_wait_and_a_revert_deletes_neither(self) -> None:
        """Covers: B167"""
        self.repository_with_a_commit()
        self.write("inbox/scans/dentist.md", "Dentist on Friday at nine\n")
        self.git("add", "inbox/scans/dentist.md")
        self.git("commit", "-q", "-m", "a note Alex dropped into a folder of the inbox")
        before = run_commit.listing(self.store)
        renamed = f"inbox/{NEW_CAPTURE}"
        os.replace(self.root / "inbox/scans/dentist.md", self.root / renamed)
        late = self.waiting("20261107T090030Z-cli-a7b8.md", "another dentist.md, synced in and renamed\n")

        self.commit(before, carried_on={renamed: "dentist.md", late: "dentist.md"})

        self.assertEqual(self.committed_paths(), ["D\tinbox/scans/dentist.md"])

        self.git("revert", "--no-edit", "HEAD")

        self.assertTrue((self.root / late).exists())
        self.assertTrue((self.root / renamed).exists())

    def test_every_file_of_one_renamed_bundle_claims_the_old_name_once(self) -> None:
        """Covers: B167"""
        self.repository_with_a_commit()
        self.write("inbox/IMG_0042.HEIC", "a photo of the receipt\n")
        self.git("add", "inbox/IMG_0042.HEIC")
        self.git("commit", "-q", "-m", "a photo Alex dropped into the inbox")
        before = run_commit.listing(self.store)
        stem = "inbox/20261107T071500Z-cli-e5f6"
        os.replace(self.root / "inbox/IMG_0042.HEIC", self.root / f"{stem}.HEIC")
        self.write(f"{stem}.md", "A HEIC file.\n")
        self.write(f"{stem}.jpg", "a copy the model can read\n")

        self.commit(before, carried_on={f"{stem}.{extension}": "IMG_0042.HEIC" for extension in ("HEIC", "md", "jpg")})

        self.assertEqual(
            self.committed_paths(),
            [f"A\t{stem}.HEIC", f"A\t{stem}.jpg", f"A\t{stem}.md", "D\tinbox/IMG_0042.HEIC"],
        )

    def test_an_old_name_with_a_space_around_it_is_the_name_its_trailer_holds(self) -> None:
        """Covers: B167"""
        self.repository_with_a_commit()
        self.write("inbox/ notes.txt", "milk\n")
        self.git("add", "inbox/ notes.txt")
        self.git("commit", "-q", "-m", "a note Alex dropped into the inbox")
        before = run_commit.listing(self.store)
        renamed = f"inbox/{NEW_CAPTURE}"
        os.replace(self.root / "inbox/ notes.txt", self.root / renamed)

        self.commit(before, carried_on={renamed: "notes.txt"})

        self.assertEqual(self.committed_paths(), [f"A\t{renamed}", "D\tinbox/ notes.txt"])

    def test_a_capture_that_names_a_file_the_run_did_not_take_out_of_the_inbox_still_waits(self) -> None:
        """Covers: B167"""
        self.repository_with_a_commit()
        before = run_commit.listing(self.store)
        self.write("memory/dana.md", "# Dana\n\n- Likes old maps.\n")
        still_there = self.waiting("20261107T090030Z-cli-a7b8.md", "says it was 20261107T070000Z-cli-a1b2.md\n")
        never_there = self.waiting("20261107T090100Z-cli-c9d0.md", "says it was dentist.md\n")

        self.commit(
            before,
            carried_on={still_there: "20261107T070000Z-cli-a1b2.md", never_there: "dentist.md"},
        )

        self.assertEqual(self.committed_paths(), ["A\tmemory/dana.md"])

    def test_a_tracked_capture_renamed_in_its_letter_case_alone_is_known(self) -> None:
        self.repository_with_a_commit()
        self.write("inbox/Note.md", "a note Alex committed\n")
        self.git("add", "inbox")
        self.git("commit", "-q", "-m", "a capture Alex committed")
        os.replace(self.root / "inbox/Note.md", self.root / "inbox/note.md")
        self.write("inbox/note.md", "a note Alex committed and changed since\n")

        self.assertIsNone(self.commit_captures())

        self.assertEqual(len(self.log()), 2)

    def test_a_capture_where_git_knows_a_folder_or_below_a_file_git_knows_stays_out(self) -> None:
        self.repository_with_a_commit()
        self.write("inbox/scans", "a file Alex committed\n")
        self.write("inbox/letters/dana.md", "a letter Alex committed\n")
        self.git("add", "inbox")
        self.git("commit", "-q", "-m", "captures Alex committed")
        (self.root / "inbox/scans").unlink()
        self.write("inbox/scans/page.md", "below a folder that took the file's name\n")
        shutil.rmtree(self.root / "inbox/letters")
        self.write("inbox/letters", "a file that took the folder's name\n")
        capture = self.waiting()

        self.commit_captures()

        self.assertEqual(self.committed_paths(), [f"A\t{capture}"])
        self.assertEqual(
            self.git("ls-tree", "-r", "--name-only", "HEAD", "inbox").splitlines(),
            ["inbox/20261107T070000Z-cli-a1b2.md", capture, "inbox/letters/dana.md", "inbox/scans"],
        )

    def test_an_inbox_that_is_a_link_to_another_folder_is_left_alone(self) -> None:
        self.repository_with_a_commit()
        elsewhere = self.root.parent / "another-inbox"
        elsewhere.mkdir()
        (elsewhere / NEW_CAPTURE).write_text("kept outside the store\n", encoding="utf-8")
        shutil.rmtree(self.root / "inbox")
        (self.root / "inbox").symlink_to(elsewhere, target_is_directory=True)

        self.assertIsNone(self.commit_captures())

        self.assertEqual(self.runner.calls, [])

    def test_a_capture_that_is_gone_before_git_gets_it_makes_no_empty_commit(self) -> None:
        self.repository_with_a_commit()
        capture = self.waiting()
        self.runner.before["update-index"] = lambda: (self.root / capture).unlink(missing_ok=True)

        self.assertIsNone(self.commit_captures())

        self.assertEqual(len(self.log()), 1)

    def test_what_else_the_owner_left_uncommitted_or_staged_stays_out_and_stays_as_it_is(self) -> None:
        """Covers: B162"""
        self.repository_with_a_commit()
        self.write("draft.md", "a thought Alex has not committed\n")
        self.write("memory/alex.md", "# Alex\n")
        self.git("add", "memory/alex.md")
        self.write("inbox/20261107T070000Z-cli-a1b2.md", "Dana likes old maps and globes\n")
        staged = self.waiting("20261107T081500Z-cli-e5f6.md", "staged by Alex, not committed\n")
        self.git("add", staged)
        capture = self.waiting()

        self.commit_captures()

        self.assertEqual(self.committed_paths(), [f"A\t{capture}"])
        self.assertEqual(
            self.git("status", "--porcelain").splitlines(),
            [
                " M inbox/20261107T070000Z-cli-a1b2.md",
                f"A  {staged}",
                "A  memory/alex.md",
                "?? draft.md",
            ],
        )

    def test_a_capture_the_owner_took_out_of_the_index_is_not_put_back_into_it(self) -> None:
        """Covers: B162"""
        self.repository_with_a_commit()
        self.git("rm", "-q", "--cached", "inbox/20261107T070000Z-cli-a1b2.md")
        self.write("inbox/20261107T070000Z-cli-a1b2.md", "Dana likes old maps and globes\n")
        # No failure either while a merge is unfinished: there is no capture to commit.
        (self.root / ".git/MERGE_HEAD").write_text(self.git("rev-parse", "HEAD"), encoding="utf-8")

        self.assertIsNone(self.commit_captures())

        self.assertEqual(len(self.log()), 1)
        self.assertIn("D  inbox/20261107T070000Z-cli-a1b2.md", self.git("status", "--porcelain").splitlines())

    def test_hidden_files_and_files_git_ignores_stay_out(self) -> None:
        """Covers: B162"""
        self.repository_with_a_commit()
        self.write(".gitignore", "*.pdf\n")
        self.waiting(".20261107T080000Z-cli-c3d4.md.tmp", "half written\n")
        self.waiting("scan.pdf", "a scan Alex keeps out of the repository\n")
        capture = self.waiting()

        self.commit_captures()

        self.assertEqual(self.committed_paths(), [f"A\t{capture}"])

    def test_only_ignored_files_wait_makes_no_commit_also_in_the_middle_of_a_merge(self) -> None:
        """Covers: B162"""
        self.repository_with_a_commit()
        self.write(".gitignore", "*.pdf\n")
        self.waiting("scan.pdf", "a scan Alex keeps out of the repository\n")
        (self.root / ".git/MERGE_HEAD").write_text(self.git("rev-parse", "HEAD"), encoding="utf-8")

        self.assertIsNone(self.commit_captures())

        self.assertEqual(len(self.log()), 1)

    def test_an_empty_inbox_makes_no_commit_and_starts_no_git(self) -> None:
        """Covers: B162"""
        self.repository_with_a_commit()
        (self.root / "inbox/20261107T070000Z-cli-a1b2.md").unlink()

        self.assertIsNone(self.commit_captures())

        self.assertEqual(self.runner.calls, [])

    def test_an_inbox_git_knows_makes_no_commit_whatever_state_the_repository_is_in(self) -> None:
        """Covers: B162"""
        self.repository_with_a_commit()
        (self.root / ".git/MERGE_HEAD").write_text(self.git("rev-parse", "HEAD"), encoding="utf-8")

        self.assertIsNone(self.commit_captures())

        self.assertEqual(len(self.log()), 1)

    def test_a_capture_that_is_not_downloaded_never_reaches_git(self) -> None:
        """Covers: B6, B162"""
        self.repository_with_a_commit()
        evicted = self.waiting("20261107T081500Z-phone-e5f6.md", "came in from another device\n")
        self.eviction.evicted.add(self.root / evicted)
        capture = self.waiting()

        self.commit_captures()

        self.assertNotIn(evicted, self.runner.paths_handed_to_git())
        self.assertEqual(self.committed_paths(), [f"A\t{capture}"])

    def test_a_file_name_is_only_a_name_whatever_it_reads_like(self) -> None:
        self.repository_with_a_commit()
        odd_names = ["--help.md", "a name with 'quotes' and spaces.md", ":(top)notes.md", "line\nbreak.md"]
        for name in odd_names:
            self.waiting(name)

        self.commit_captures()

        committed = self.git("show", "-z", "--name-only", "--format=", "HEAD").split("\0")
        self.assertEqual(sorted(path for path in committed if path), sorted(f"inbox/{name}" for name in odd_names))

    def test_a_tracked_capture_whose_name_the_file_system_spells_decomposed_is_known(self) -> None:
        self.repository_with_a_commit()
        composed = unicodedata.normalize("NFC", "Müller.md")
        on_disk = self.waiting(unicodedata.normalize("NFD", composed), "a note about Müller\n")
        # What a git that composes names keeps: the composed name, whatever the folder spells.
        blob = self.git("hash-object", "-w", on_disk).strip()
        self.git("update-index", "--add", "--cacheinfo", f"100644,{blob},inbox/{composed}")
        self.git("commit", "-q", "-m", "a capture Alex committed")

        self.assertIsNone(self.commit_captures())

        self.assertEqual(len(self.log()), 2)

    def test_a_repository_without_a_commit_gets_the_captures_as_its_first(self) -> None:
        self.git("init", "-q", "-b", "main")
        capture = self.waiting()

        self.commit_captures()

        self.assertEqual(self.committed_paths(), [f"A\t{capture}"])
        self.assertEqual(len(self.log()), 1)

    def test_it_is_made_like_the_commit_of_a_run(self) -> None:
        """Covers: B140, B162"""
        self.repository_with_a_commit()
        ran = self.root.parent / "a-hook-ran"
        for name in ("pre-commit", "commit-msg", "post-commit", "reference-transaction"):
            hook = self.root / ".git/hooks" / name
            hook.write_text(f'#!/bin/sh\necho {name} >> "{ran}"\n', encoding="utf-8")
            hook.chmod(0o755)
        self.git("config", "commit.gpgsign", "true")
        self.git("config", "gpg.program", str(self.root.parent / "no-such-gpg"))
        config = (self.root / ".git/config").read_bytes()
        self.waiting()

        self.commit_captures()

        self.assertEqual(len(self.log()), 2)
        self.assertFalse(ran.exists())
        self.assertEqual((self.root / ".git/config").read_bytes(), config)
        self.assertEqual(
            set(self.runner.subcommands()),
            {
                "rev-parse",
                "config",
                "ls-files",
                "read-tree",
                "check-ignore",
                "update-index",
                "write-tree",
                "commit-tree",
                "update-ref",
            },
        )

    def test_an_operation_the_owner_has_not_finished_means_no_commit(self) -> None:
        """Covers: B140, B162"""
        self.repository_with_a_commit()
        self.waiting()
        (self.root / ".git/MERGE_HEAD").write_text(self.git("rev-parse", "HEAD"), encoding="utf-8")

        with self.assertRaisesRegex(run_commit.CommitError, "in the middle of a merge"):
            self.commit_captures()

        self.assertEqual(len(self.log()), 1)

    def test_an_evicted_git_file_stops_the_commit_before_git_reads_it(self) -> None:
        """Covers: B6, B162"""
        self.repository_with_a_commit()
        self.waiting()
        self.eviction.evicted.add(self.root / ".git")

        with self.assertRaisesRegex(run_commit.CommitError, r"\.git is not downloaded"):
            self.commit_captures()

        self.assertEqual(self.runner.calls, [])

    def test_an_evicted_ignore_file_stops_the_commit_and_names_the_fetch(self) -> None:
        """Covers: B6, B162"""
        self.repository_with_a_commit()
        self.waiting()
        self.write("inbox/.gitignore", "*.pdf\n")
        self.eviction.evicted.add(self.root / "inbox/.gitignore")

        with self.assertRaisesRegex(run_commit.CommitError, r"inbox/\.gitignore is not downloaded"):
            self.commit_captures()

        self.assertNotIn("check-ignore", self.runner.subcommands())
        self.assertEqual(len(self.log()), 1)

    def test_an_index_that_cannot_be_brought_up_to_date_names_the_commit_that_was_made(self) -> None:
        self.repository_with_a_commit()
        self.waiting()
        self.runner.before["update-ref"] = lambda: (self.root / ".git/index.lock").write_text("", encoding="utf-8")

        with self.assertRaisesRegex(run_commit.StaleIndexError, r"the captures are committed as [0-9a-f]{12}, but"):
            self.commit_captures()

        self.assertEqual(len(self.log()), 2)


class HandedInFilesTest(RunCommitTest):
    """A proposal a session handed in waits as a file of its own, like a capture in the inbox."""

    HANDED_IN = "state/core/handed-in/0a1b2c3d-1111-4222-8333-444455556666.38d8f71e327f.json"
    LATE = "state/core/handed-in/0a1b2c3d-1111-4222-8333-444455556666.aaaaaaaaaaaa.json"

    def commit_what_waits(self) -> str | None:
        text = run_commit.captures_message(START)
        return run_commit.commit_waiting_captures(
            self.repository(), run_commit.listing(self.store), text, self.temp_dir
        )

    def a_run_that_takes_it_in(self) -> run_commit.StoreListing:
        before = run_commit.listing(self.store)
        (self.root / self.HANDED_IN).unlink()
        self.write("state/core/proposals.json", '{"format": 3, "proposals": {"38d8f71e327f": {}}}\n')
        return before

    def test_a_handed_in_file_git_does_not_know_is_committed_where_it_waits(self) -> None:
        """Covers: B182"""
        self.repository_with_a_commit()
        self.write(self.HANDED_IN, '{"format": 1}\n')

        self.commit_what_waits()

        self.assertEqual(self.committed_paths(), [f"A\t{self.HANDED_IN}"])
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_what_head_holds_of_the_folder_is_what_a_run_may_take_in(self) -> None:
        """Covers: B182"""
        self.git("init", "-q", "-b", "main")
        self.write(self.HANDED_IN, '{"format": 1}\n')
        before_any_commit = run_commit.handed_in_in_head(self.repository())
        self.repository_with_a_commit()
        self.commit_what_waits()
        self.write(self.LATE, '{"format": 1}\n')
        self.git("add", self.LATE)

        self.assertEqual(before_any_commit, frozenset())
        self.assertEqual(run_commit.handed_in_in_head(self.repository()), {self.HANDED_IN})

    def test_reverting_the_run_that_took_it_in_puts_the_file_back_for_the_next_run(self) -> None:
        """Covers: B182"""
        self.repository_with_a_commit()
        self.write(self.HANDED_IN, '{"format": 1}\n')
        self.commit_what_waits()
        self.commit(self.a_run_that_takes_it_in())

        self.git("revert", "--no-edit", "HEAD")

        self.assertEqual((self.root / self.HANDED_IN).read_text(encoding="utf-8"), '{"format": 1}\n')
        self.assertFalse((self.root / "state/core/proposals.json").exists())
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_one_that_came_in_during_the_run_and_still_waits_outlives_a_revert_of_the_run(self) -> None:
        """Covers: B182"""
        self.repository_with_a_commit()
        self.write(self.HANDED_IN, '{"format": 1}\n')
        self.commit_what_waits()
        before = self.a_run_that_takes_it_in()
        self.write(self.LATE, '{"format": 1, "kind": "person"}\n')

        self.commit(before)

        self.assertNotIn(self.LATE, "\n".join(self.committed_paths()))
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all").splitlines(), [f"?? {self.LATE}"])

        self.git("revert", "--no-edit", "HEAD")

        self.assertEqual((self.root / self.LATE).read_text(encoding="utf-8"), '{"format": 1, "kind": "person"}\n')

    def test_the_next_run_commits_the_one_the_run_before_it_left_waiting(self) -> None:
        """Covers: B182"""
        self.repository_with_a_commit()
        before = self.a_run()
        self.write(self.LATE, '{"format": 1}\n')
        self.commit(before)

        self.commit_what_waits()

        self.assertEqual(self.committed_paths(), [f"A\t{self.LATE}"])


class WhichRepositoryTest(RunCommitTest):
    """A store whose ``.git`` is a file that points at a git directory kept outside the store folder."""

    def setUp(self) -> None:
        super().setUp()
        self.outside = self.root.parent / "store-history"
        self.marker = self.root.parent / "a-command-ran"

    def repository_kept_outside(self) -> None:
        """The store as its owner committed it, with the git directory outside and named in the machine config."""
        self.git("init", "-q", "-b", "main", "--separate-git-dir", str(self.outside))
        self.write("memory/MEMORY.md", "# Memory\n")
        self.git("add", "memory")
        self.git("commit", "-q", "-m", "the store as Alex set it up")
        self.named = self.outside

    def another_repository(self) -> Path:
        """The git directory of a repository of its own, whose configuration names a command for
        every file added; the store's attributes ask for that command."""
        elsewhere = self.root.parent / "another-repository"
        elsewhere.mkdir()
        self.git("init", "-q", "-b", "main", cwd=elsewhere)
        self.git("commit", "-q", "--allow-empty", "-m", "other work", cwd=elsewhere)
        self.git("config", "filter.marked.clean", f"touch {shlex.quote(str(self.marker))}; cat", cwd=elsewhere)
        self.write(".gitattributes", "* filter=marked\n")
        return elsewhere / ".git"

    def point_at(self, written: object) -> None:
        (self.root / ".git").write_text(f"gitdir: {written}\n", encoding="utf-8")

    def a_new_fact(self) -> run_commit.StoreListing:
        before = run_commit.listing(self.store)
        self.write("memory/dana.md", "# Dana\n\n- Likes old maps.\n")
        return before

    def subjects_in(self, git_directory: Path) -> list[str]:
        return self.git("--git-dir", str(git_directory), "log", "--format=%s").splitlines()

    def test_the_git_directory_the_config_names_is_committed_into(self) -> None:
        """Covers: B168"""
        self.repository_kept_outside()

        self.commit(self.a_new_fact())

        self.assertEqual(self.subjects_in(self.outside), [TEXT.subject, "the store as Alex set it up"])

    def test_a_git_file_rewritten_to_another_repository_stops_the_commit_before_any_git_starts(self) -> None:
        """Covers: B168"""
        self.repository_kept_outside()
        other = self.another_repository()
        before = self.a_new_fact()
        self.point_at(other)

        with self.assertRaisesRegex(
            run_commit.CommitError, r"leads to \S+another-repository/\.git, not to \S+store-history"
        ):
            self.commit(before)

        self.assertEqual(self.runner.calls, [])
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.subjects_in(other), ["other work"])
        self.assertEqual(self.subjects_in(self.outside), ["the store as Alex set it up"])

    def test_the_other_repositorys_command_runs_once_the_config_names_that_repository(self) -> None:
        # What the test above keeps from happening, shown to happen: the filter is the named repository's.
        self.repository_kept_outside()
        other = self.another_repository()
        before = self.a_new_fact()
        self.point_at(other)
        self.named = other

        self.commit(before)

        self.assertTrue(self.marker.exists())
        self.assertEqual(self.subjects_in(other), [TEXT.subject, "other work"])

    def test_waiting_captures_are_not_committed_into_another_repository_either(self) -> None:
        """Covers: B168"""
        self.repository_kept_outside()
        other = self.another_repository()
        self.write(f"inbox/{NEW_CAPTURE}", "Dana moved to Lisbon\n")
        before = run_commit.listing(self.store)
        self.point_at(other)

        with self.assertRaisesRegex(run_commit.CommitError, "not to .*the git directory this machine's config names"):
            run_commit.commit_waiting_captures(self.repository(), before, TEXT, self.temp_dir)

        self.assertEqual(self.runner.calls, [])
        self.assertEqual(self.subjects_in(other), ["other work"])

    def test_a_git_file_is_not_followed_while_the_config_names_no_git_directory(self) -> None:
        """Covers: B168"""
        self.repository_kept_outside()
        self.named = None

        with self.assertRaises(run_commit.CommitError) as raised:
            self.commit(self.a_new_fact())

        self.assertIn(
            f".git in the store folder points at {self.outside}, and this machine's config names no",
            str(raised.exception),
        )
        self.assertIn("m2b config set curation.git_directory", str(raised.exception))
        self.assertEqual(self.runner.calls, [])
        self.assertEqual(self.subjects_in(self.outside), ["the store as Alex set it up"])

    def test_git_is_given_the_named_directory_with_every_call_and_reads_no_rewritten_file(self) -> None:
        """Covers: B168"""
        self.repository_kept_outside()
        other = self.another_repository()
        before = self.a_new_fact()
        commands: list[list[str]] = []

        def remembering(command: list[str], **options: Any) -> Any:
            if GIT_OPTIONS_END in command:
                commands.append(command)
            return self.runner(command, **options)

        # git has started with the directory in its command line; the file changes under it.
        self.runner.before["read-tree"] = lambda: self.point_at(other)
        repository = run_commit.find_repository(self.store, self.environ, run=remembering, named_directory=self.named)
        assert repository is not None

        with self.assertRaisesRegex(run_commit.CommitError, "leads to"):
            run_commit.commit(repository, before, TEXT, self.temp_dir)

        self.assertEqual(self.runner.subcommands(), ["rev-parse", "config", "rev-parse", "read-tree"])
        self.assertEqual(len(commands), 4)
        for command in commands:
            self.assertEqual(command[3:5], ["--git-dir", str(self.outside)], command)
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.subjects_in(other), ["other work"])
        self.assertEqual(self.subjects_in(self.outside), ["the store as Alex set it up"])

    def test_a_git_file_may_name_the_directory_from_the_store_folder(self) -> None:
        self.repository_kept_outside()
        self.point_at("../store-history")

        self.commit(self.a_new_fact())

        self.assertEqual(len(self.subjects_in(self.outside)), 2)

    def test_the_named_directory_may_be_reached_through_a_link_outside_the_store(self) -> None:
        self.repository_kept_outside()
        link = self.root.parent / "history-link"
        os.symlink(self.outside, link)
        self.named = link

        self.commit(self.a_new_fact())

        self.assertEqual(len(self.subjects_in(self.outside)), 2)

    def test_a_git_folder_in_the_store_needs_no_naming_and_takes_its_own_name(self) -> None:
        """Covers: B168"""
        self.repository_with_a_commit()
        self.commit(self.a_new_fact())
        self.named = self.root / ".git"
        self.write("memory/dana.md", "# Dana\n")
        before = run_commit.listing(self.store)
        self.write("memory/dana.md", "# Dana\n\n- Moved to Lisbon.\n")

        self.commit(before)

        self.assertEqual(len(self.log()), 3)
        self.assertNotIn("--git-dir", [argument for arguments, _ in self.runner.calls for argument in arguments])

    def test_a_git_folder_in_the_store_is_not_committed_into_while_the_config_names_another(self) -> None:
        """Covers: B168"""
        self.repository_with_a_commit()
        self.outside.mkdir()
        self.named = self.outside

        with self.assertRaisesRegex(
            run_commit.CommitError, r"leads to \S+sb-test-store/\.git, not to \S+store-history"
        ):
            self.commit(self.a_new_fact())

        self.assertEqual(self.runner.calls, [])
        self.assertEqual(len(self.log()), 1)

    def test_a_named_directory_inside_the_store_folder_is_not_committed_into(self) -> None:
        """Covers: B168"""
        inside = self.root / "history.git"
        self.git("init", "-q", "-b", "main", "--separate-git-dir", str(inside))
        self.git("commit", "-q", "--allow-empty", "-m", "the store as Alex set it up")
        link = self.root.parent / "a-link-to-the-history"
        os.symlink(inside, link)
        ways_to_name_it = [inside, link]
        store_in_other_letters = self.root.parent / self.root.name.upper()
        if store_in_other_letters.exists():
            # This file system tells no letter case apart, so the other spelling is the same folder.
            ways_to_name_it += [self.root / "HISTORY.git", store_in_other_letters / "history.git"]
        for named in ways_to_name_it:
            with self.subTest(named=named.name):
                self.named = named

                with self.assertRaisesRegex(
                    run_commit.CommitError, "lies in the store folder or is reached through it, where everything"
                ):
                    self.commit(self.a_new_fact())

        self.assertEqual(self.runner.calls, [])
        self.assertEqual(self.subjects_in(inside), ["the store as Alex set it up"])

    def test_a_directory_named_by_a_path_through_a_link_in_the_store_is_not_committed_into(self) -> None:
        """Covers: B168"""
        self.repository_kept_outside()
        other = self.another_repository()
        os.symlink(self.outside, self.root / "history")
        self.named = self.root / "history"
        self.point_at("history")
        before = self.a_new_fact()

        with self.assertRaisesRegex(
            run_commit.CommitError, "lies in the store folder or is reached through it, where everything"
        ):
            self.commit(before)

        # What the refusal keeps from happening: the link is the store's, and it is pointed elsewhere.
        (self.root / "history").unlink()
        os.symlink(other, self.root / "history")
        with self.assertRaisesRegex(
            run_commit.CommitError, "lies in the store folder or is reached through it, where everything"
        ):
            self.commit(before)
        self.assertEqual(self.runner.calls, [])
        self.assertEqual(self.subjects_in(other), ["other work"])
        self.assertFalse(self.marker.exists())

    def test_a_link_outside_that_leads_on_through_a_link_in_the_store_is_a_way_through_the_store(self) -> None:
        """Covers: B168"""
        self.repository_kept_outside()
        os.symlink(self.outside, self.root / "history")
        chained = self.root.parent / "a-link-to-the-link-in-the-store"
        os.symlink(self.root / "history", chained)
        self.named = chained
        self.point_at(chained)

        with self.assertRaisesRegex(run_commit.CommitError, "is reached through it, where everything"):
            self.commit(self.a_new_fact())

        self.assertEqual(self.runner.calls, [])
        self.named = None
        with self.assertRaises(run_commit.CommitError) as raised:
            self.commit(self.a_new_fact())
        self.assertNotIn("name it with", str(raised.exception))

    def test_a_step_back_up_after_a_link_in_the_store_is_a_way_through_the_store(self) -> None:
        """Covers: B168"""
        self.repository_kept_outside()
        deeper = self.root.parent / "sb-test-deep" / "er"
        deeper.mkdir(parents=True)
        os.symlink(deeper, self.root / "link")
        self.named = Path(f"{self.root}/link/../../store-history")
        self.assertTrue(os.path.samefile(self.named, self.outside))

        with self.assertRaisesRegex(run_commit.CommitError, "is reached through it, where everything"):
            self.commit(self.a_new_fact())

        self.assertEqual(self.runner.calls, [])

    def test_a_step_back_up_out_of_the_store_folder_itself_leads_through_nothing_in_it(self) -> None:
        self.repository_kept_outside()
        self.named = Path(f"{self.root}/../store-history")

        self.commit(self.a_new_fact())

        self.assertEqual(len(self.subjects_in(self.outside)), 2)

    def test_links_that_lead_round_in_a_ring_lead_to_no_git_directory(self) -> None:
        self.repository_kept_outside()
        one, other = self.root.parent / "sb-test-ring-one", self.root.parent / "sb-test-ring-other"
        os.symlink(other, one)
        os.symlink(one, other)
        self.point_at(one)
        self.named = None

        with self.assertRaisesRegex(run_commit.CommitError, "follows more than 40 links, so it leads to no git"):
            self.commit(self.a_new_fact())

    def test_a_git_file_that_points_through_a_link_in_the_store_is_not_offered_for_naming(self) -> None:
        """Covers: B168"""
        self.repository_kept_outside()
        self.named = None
        os.symlink(self.outside, self.root / "history")
        self.point_at("history")

        with self.assertRaises(run_commit.CommitError) as raised:
            self.commit(self.a_new_fact())

        self.assertIn(
            "which lies in the store folder or is reached through it, where everything that writes",
            str(raised.exception),
        )
        self.assertNotIn("name it with", str(raised.exception))

    def test_a_git_file_that_points_into_the_store_is_not_offered_for_naming(self) -> None:
        """Covers: B168"""
        inside = self.root / "history.git"
        self.git("init", "-q", "-b", "main", "--separate-git-dir", str(inside))
        for written in (inside, "history.git", "."):
            with self.subTest(written=str(written)):
                self.point_at(written)

                with self.assertRaises(run_commit.CommitError) as raised:
                    self.commit(self.a_new_fact())

                self.assertIn(
                    "which lies in the store folder or is reached through it, where everything that writes",
                    str(raised.exception),
                )
                self.assertNotIn("name it with", str(raised.exception))

        self.assertEqual(self.runner.calls, [])

    def test_a_git_that_is_a_link_is_not_followed(self) -> None:
        """Covers: B168"""
        self.repository_kept_outside()
        (self.root / ".git").unlink()
        os.symlink(self.outside, self.root / ".git")

        with self.assertRaisesRegex(run_commit.CommitError, r"\.git in the store folder is a symbolic link"):
            self.commit(self.a_new_fact())

        self.assertEqual(self.runner.calls, [])
        self.assertEqual(self.subjects_in(self.outside), ["the store as Alex set it up"])

    def test_a_link_that_takes_the_files_place_after_the_look_at_it_is_not_followed(self) -> None:
        self.repository_kept_outside()
        pointer = self.root.parent / "a-git-file-elsewhere"
        os.replace(self.root / ".git", pointer)
        os.symlink(pointer, self.root / ".git")

        with (
            mock.patch.object(Path, "is_symlink", return_value=False),
            self.assertRaisesRegex(run_commit.CommitError, r"\.git in the store folder could not be read"),
        ):
            self.commit(self.a_new_fact())

        self.assertEqual(self.runner.calls, [])

    def test_a_git_file_that_names_no_directory_stops_the_commit(self) -> None:
        self.repository_kept_outside()
        nothing_named = (
            "",
            "gitdir:",
            f"worktree: {self.outside}\n",
            "gitdir: " + "x" * run_commit.GITFILE_MAX_BYTES,
            f"gitdir: {self.outside}\0elsewhere\n",
        )
        for content in nothing_named:
            with self.subTest(content=content[:20]):
                (self.root / ".git").write_text(content, encoding="utf-8")

                with self.assertRaisesRegex(
                    run_commit.CommitError, "neither a git directory nor a file that names one"
                ):
                    self.commit(self.a_new_fact())

        self.assertEqual(self.runner.calls, [])

    def test_a_named_directory_that_is_not_there_is_the_reason(self) -> None:
        self.repository_kept_outside()
        self.named = self.root.parent / "sb-test-gone"

        with self.assertRaisesRegex(run_commit.CommitError, r"sb-test-gone, the git directory .* is not there"):
            self.commit(self.a_new_fact())

        self.assertEqual(self.runner.calls, [])

    def test_a_named_path_that_is_a_file_is_said_to_be_no_directory(self) -> None:
        self.repository_kept_outside()
        self.named = self.root.parent / "sb-test-a-file"
        self.named.write_text("", encoding="utf-8")

        with self.assertRaisesRegex(run_commit.CommitError, r"sb-test-a-file, the git directory .* is not a directory"):
            self.commit(self.a_new_fact())

    def test_a_pipe_in_the_place_of_the_git_file_is_not_waited_for(self) -> None:
        self.repository_kept_outside()
        (self.root / ".git").unlink()
        os.mkfifo(self.root / ".git")
        really_open = os.open

        def never_blocking(path: Any, flags: int, *more: Any, **options: Any) -> int:
            # Without the flag this open would wait for a writer for ever, and the test with it.
            if not flags & os.O_NONBLOCK:
                raise AssertionError("the git file is opened in a way that waits for a pipe's writer")
            return really_open(path, flags, *more, **options)

        with (
            mock.patch.object(os, "open", never_blocking),
            self.assertRaisesRegex(run_commit.CommitError, "neither a git directory nor a file that names one"),
        ):
            self.commit(self.a_new_fact())

        self.assertEqual(self.runner.calls, [])

    def test_a_path_in_the_git_file_is_shown_in_one_line_and_without_control_characters(self) -> None:
        self.repository_kept_outside()
        self.point_at("/sb-test-x\x1b[2K\rstore-git: found\nanother line")

        with self.assertRaises(run_commit.CommitError) as raised:
            self.commit(self.a_new_fact())

        self.assertIn("leads to /sb-test-x?[2K?store-git: found?another line, not to", str(raised.exception))
        self.assertEqual(len(str(raised.exception).splitlines()), 1)

    def test_what_no_output_can_encode_or_keep_in_one_line_is_shown_as_a_question_mark(self) -> None:
        self.repository_kept_outside()
        separators = "\u2028store-git: found\u2029".encode()
        (self.root / ".git").write_bytes(b"gitdir: /sb-test-x\xffy" + separators + b"\n")

        with self.assertRaises(run_commit.CommitError) as raised:
            self.commit(self.a_new_fact())

        self.assertIn("leads to /sb-test-x?y?store-git: found?, not to", str(raised.exception))
        self.assertTrue(str(raised.exception).encode("utf-8"))
        self.assertEqual(len(str(raised.exception).splitlines()), 1)

    def test_a_long_path_in_the_git_file_is_shown_cut(self) -> None:
        self.repository_kept_outside()
        self.point_at("/sb-test-" + "x" * 2000)

        with self.assertRaises(run_commit.CommitError) as raised:
            self.commit(self.a_new_fact())

        self.assertIn("/sb-test-" + "x" * (run_commit.SHOWN_PATH_LENGTH - 9) + "..., not to", str(raised.exception))


class NoRemoteTest(RunCommitTest):
    """A store that is a partial clone, whose remote names a command for fetching what it lacks."""

    def setUp(self) -> None:
        super().setUp()
        self.marker = self.root.parent / "a-command-ran"
        self.head = make_partial_clone(self.environ, self.root.parent / "made-from", self.root, self.marker)

    def test_a_partial_clone_is_not_committed_into_and_nothing_is_fetched(self) -> None:
        """Covers: B169"""
        before = run_commit.listing(self.store)
        self.write("memory/dana.md", "# Dana\n")

        with self.assertRaisesRegex(run_commit.CommitError, "the repository is a partial clone"):
            self.commit(before)

        self.assertEqual(self.runner.subcommands(), ["rev-parse", "config"])
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), self.head)

    def test_waiting_captures_are_not_committed_into_a_partial_clone(self) -> None:
        """Covers: B169"""
        self.write(f"inbox/{NEW_CAPTURE}", "Dana moved to Lisbon\n")
        before = run_commit.listing(self.store)

        with self.assertRaisesRegex(run_commit.CommitError, "the repository is a partial clone"):
            run_commit.commit_waiting_captures(self.repository(), before, TEXT, self.temp_dir)

        self.assertFalse(self.marker.exists())

    def test_no_git_of_a_run_fetches_even_past_that_refusal(self) -> None:
        """Covers: B169"""
        with self.assertRaisesRegex(run_commit.CommitError, "git read-tree failed"):
            self.repository().call(["read-tree", self.head], self.temp_dir / "index")

        self.assertFalse(self.marker.exists())


class EvictedFilesTest(RunCommitTest):
    def test_a_changed_file_that_is_evicted_never_reaches_git(self) -> None:
        """Covers: B6, B141"""
        self.repository_with_a_commit()
        before = self.a_run()
        self.write("inbox/20261107T080000Z-phone-c3d4.md", "came in from another device\n")
        self.eviction.evicted.add(self.root / "inbox/20261107T080000Z-phone-c3d4.md")

        self.commit(before)

        self.assertNotIn("inbox/20261107T080000Z-phone-c3d4.md", self.runner.paths_handed_to_git())
        self.assertIn("memory/dana.md", self.runner.paths_handed_to_git())
        self.assertNotIn("phone", "\n".join(self.committed_paths()))

    def test_a_file_that_was_evicted_before_the_run_and_only_downloaded_is_no_change(self) -> None:
        """Covers: B6"""
        self.repository_with_a_commit()
        self.write("corpus/2025/01/old.md", "an old note\n")
        self.eviction.evicted.add(self.root / "corpus/2025/01/old.md")
        before = run_commit.listing(self.store)
        self.eviction.evicted.clear()

        self.assertIsNone(self.commit(before))
        self.assertEqual(self.runner.calls, [])

    def test_the_files_of_a_folder_the_run_downloaded_are_no_change(self) -> None:
        """Covers: B139"""
        self.repository_with_a_commit()
        self.write("memory/people/kim.md", "# Kim\n\nnever committed by Alex\n")
        os.utime(self.root / "memory/people/kim.md", ns=(1_700_000_000 * 10**9, 1_700_000_000 * 10**9))
        self.eviction.evicted.add(self.root / "memory/people")
        before = self.a_run()
        self.eviction.evicted.clear()
        self.write("memory/people/dana.md", "# Dana\n\nwritten by the run\n")

        self.commit(before)

        self.assertNotIn("memory/people/kim.md", self.runner.paths_handed_to_git())
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all"), "?? memory/people/kim.md\n")
        self.assertIn("A\tmemory/people/dana.md", self.committed_paths())

    def test_a_file_evicted_during_the_run_is_not_taken_for_removed(self) -> None:
        """Covers: B6"""
        self.repository_with_a_commit()
        before = self.a_run()
        self.eviction.evicted.add(self.root / "memory")

        self.commit(before)

        self.assertFalse(any(path.startswith("memory/") for path in self.runner.paths_handed_to_git()))
        self.assertNotIn("D\tmemory/MEMORY.md", self.committed_paths())

    def test_an_evicted_ignore_or_attributes_file_stops_the_commit_and_names_the_fetch(self) -> None:
        """Covers: B6, B141"""
        for rule_file in (".gitattributes", "memory/.gitignore"):
            with self.subTest(rule_file):
                self.setUp()
                self.repository_with_a_commit()
                self.write(rule_file, "*.md text\n" if rule_file.endswith("attributes") else "*.tmp\n")
                self.eviction.evicted.add(self.root / rule_file)

                with self.assertRaisesRegex(run_commit.CommitError, "m2b store fetch") as raised:
                    self.commit(self.a_run())

                self.assertIn(f"{rule_file} is not downloaded", str(raised.exception))
                self.assertEqual(self.runner.calls, [])
                self.assertEqual(len(self.log()), 1)

    def test_an_evicted_git_file_stops_the_commit_before_git_reads_it(self) -> None:
        """Covers: B6, B141"""
        self.repository_with_a_commit()
        before = self.a_run()
        self.eviction.evicted.add(self.root / ".git")

        with self.assertRaisesRegex(run_commit.CommitError, r"\.git is not downloaded"):
            self.commit(before)

        self.assertEqual(self.runner.calls, [])


if __name__ == "__main__":
    unittest.main()
