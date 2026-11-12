"""The commit of a curation run: what goes into it, what git is asked, and what it never touches."""

from __future__ import annotations

import datetime
import os
import shutil
import subprocess
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any

from m2b.curate import run_commit
from m2b.run_record import StepResult
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard
from store_contract import FakeEviction

GIT = shutil.which("git")
START = datetime.datetime(2026, 11, 7, 9, 0).astimezone()
TEXT = run_commit.Message("m2b: curation run 2026-11-07 09:00", "succeeded: ingest")
OWNER = ("-c", "user.name=Alex", "-c", "user.email=alex@example.com")
# The last option m2b gives git before the subcommand.
GIT_OPTIONS_END = "core.fsmonitor=false"


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
        found = run_commit.find_repository(self.store, self.environ, run=self.runner)
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
        if not run_commit.APPLE_GIT_STAND_IN.exists():
            self.skipTest("this machine has no /usr/bin/git")
        started: list[list[str]] = []

        def no_developer_tools(command: list[str], **options: Any) -> Any:
            started.append(command)
            return types.SimpleNamespace(returncode=2)

        environ = {**self.environ, "PATH": str(run_commit.APPLE_GIT_STAND_IN.parent)}
        found = run_commit.find_repository(self.store, environ, platform="darwin", run=no_developer_tools)

        self.assertIsNone(found)
        self.assertEqual(started, [list(run_commit.DEVELOPER_TOOLS_CHECK)])


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
            {"rev-parse", "read-tree", "check-ignore", "update-index", "write-tree", "commit-tree", "update-ref"},
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
