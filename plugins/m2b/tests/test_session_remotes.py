"""The git remotes of the folders sessions start in, and the work the owner names by them."""

from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from m2b import session_remotes
from m2b.session_remotes import ByRemote, RemoteRule

NOW = datetime.datetime(2026, 11, 7, 9, 0, tzinfo=datetime.timezone.utc)
DAY = datetime.timedelta(days=1)
GLOBEX = "https://git.globex.example/globex-ag/portal.git"


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.base = Path(self._temp.name).resolve()
        self.notes = self.base / "state" / session_remotes.NOTES_FOLDER
        self.repo = self.base / "code" / "portal"
        self.repo.mkdir(parents=True)
        self.environ = {
            "PATH": os.environ.get("PATH", ""),
            "GIT_CONFIG_GLOBAL": str(self.base / "gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
        }

    def git(self, *arguments: str, folder: Path | None = None) -> None:
        subprocess.run(
            ["git", "-C", str(folder or self.repo), *arguments], check=True, env=self.environ, capture_output=True
        )

    def remotes(self, folder: Path | None = None, **options: Any) -> frozenset[str] | None:
        return session_remotes.remotes_in(folder or self.repo, environ=self.environ, **options)

    def write(self, path: Path, text: str) -> None:
        path.write_text(text, encoding="utf-8")

    def note(self, folder: Path, *remotes: str, when: datetime.datetime = NOW) -> None:
        session_remotes.note(self.notes, str(folder), frozenset(remotes), when, self.write)

    def rule(self, *parts: str, now: datetime.datetime = NOW, ask: Any = None) -> RemoteRule:
        return RemoteRule(parts, self.notes, now, ask or self.remotes)


class RemotesInTest(Fixture):
    def test_every_remote_of_the_repository_is_read_also_from_a_folder_below_its_top(self) -> None:
        """Covers: B151"""
        self.git("init", "-q")
        self.git("remote", "add", "origin", "git@github.com:alex/portal.git")
        self.git("remote", "add", "upstream", GLOBEX)
        (self.repo / "src").mkdir()

        self.assertEqual(self.remotes(self.repo / "src"), {"git@github.com:alex/portal.git", GLOBEX})

    def test_the_user_and_the_password_of_a_url_are_cut_off(self) -> None:
        """Covers: B151"""
        self.git("init", "-q")
        self.git("remote", "add", "origin", "https://ghp_Zx81kQ4tToken@git.globex.example/globex-ag/portal.git")
        self.git("remote", "add", "mirror", "https://alex:p@ss:word@mirror.example/portal.git")
        self.git("remote", "add", "by-ssh", "ssh://git@git.globex.example:2222/globex-ag/portal.git")

        self.assertEqual(
            self.remotes(),
            {GLOBEX, "https://mirror.example/portal.git", "ssh://git.globex.example:2222/globex-ag/portal.git"},
        )

    def test_a_url_git_rewrites_counts_as_written_and_as_rewritten(self) -> None:
        """Covers: B151"""
        self.git("init", "-q")
        self.git("remote", "add", "origin", "gx:portal.git")
        self.git("remote", "add", "mirror", "https://mirror.example/portal.git")
        self.git("config", "--global", "url.git@github.com:globex-ag/.insteadOf", "gx:")
        self.git("config", "--global", "url.ssh://token@push.globex.example/team a/.pushInsteadOf", "gx:")
        self.git("config", "remote.mirror.pushurl", "git@git.globex.example:team/portal.git")

        self.assertEqual(
            self.remotes(),
            {
                "gx:portal.git",
                "git@github.com:globex-ag/portal.git",
                "ssh://push.globex.example/team a/portal.git",
                "https://mirror.example/portal.git",
                # Where the mirror is pushed to, which ``git remote -v`` shows beside where it is fetched from.
                "git@git.globex.example:team/portal.git",
            },
        )

    def test_a_repository_another_user_owns_is_read_like_ones_own(self) -> None:
        """Covers: B151"""
        self.git("init", "-q")
        self.git("remote", "add", "origin", GLOBEX)
        # What git checks a repository's owner against, turned so that every repository fails it.
        self.environ["GIT_TEST_ASSUME_DIFFERENT_OWNER"] = "1"

        self.assertEqual(self.remotes(), {GLOBEX})

    def test_a_folder_that_may_not_be_looked_at_says_nothing(self) -> None:
        """Covers: B151"""
        self.git("init", "-q")

        with mock.patch.object(Path, "is_dir", side_effect=PermissionError("not permitted")):
            self.assertIsNone(self.remotes())

    def test_a_repository_without_a_remote_and_a_folder_in_no_repository_have_none(self) -> None:
        """Covers: B151"""
        plain = self.base / "notes"
        plain.mkdir()
        self.git("init", "-q")

        self.assertEqual(self.remotes(), frozenset())
        self.assertEqual(self.remotes(plain), frozenset())

    def test_a_folder_that_is_gone_and_a_git_that_does_not_answer_say_nothing(self) -> None:
        """Covers: B151"""
        self.git("init", "-q")

        def hangs(*_: Any, **__: Any) -> Any:
            raise subprocess.TimeoutExpired("git", 2.0)

        def fails(command: list[str], **_: Any) -> Any:
            return subprocess.CompletedProcess(command, 128, "", "fatal: bad config line 3")

        self.assertIsNone(self.remotes(self.base / "gone"))
        self.assertIsNone(self.remotes(run=hangs))
        self.assertIsNone(self.remotes(run=fails))
        self.assertIsNone(self.remotes(git=str(self.base / "no-git")))

    def test_a_variable_that_points_git_at_another_repository_does_not_reach_it(self) -> None:
        """Covers: B151"""
        other = self.base / "code" / "elsewhere"
        other.mkdir()
        self.git("init", "-q")
        self.git("remote", "add", "origin", GLOBEX)
        self.git("init", "-q", folder=other)
        self.environ["GIT_DIR"] = str(other / ".git")

        self.assertEqual(self.remotes(), {GLOBEX})


class NamesOneTest(unittest.TestCase):
    def test_a_part_is_found_without_regard_to_case_in_both_spellings_of_a_remote(self) -> None:
        """Covers: B152"""
        for remote in (
            "https://github.com/Globex-AG/portal.git",
            "git@github.com:globex-ag/portal.git",
            "github.com:globex-ag/portal.git",
            "git@github.com:/globex-ag/portal.git",
            "ssh://github.com:22/globex-ag/portal.git",
        ):
            with self.subTest(remote=remote):
                self.assertTrue(session_remotes.names_one(["GitHub.com/globex-ag/"], [remote]))
        self.assertTrue(session_remotes.names_one(["github.com:globex-ag/"], ["git@github.com:globex-ag/portal.git"]))

    def test_another_repository_and_an_empty_part_name_nothing(self) -> None:
        """Covers: B152"""
        remotes = ["git@github.com:alex/shed.git", "/srv/git/shed.git", "C:/code/shed"]

        self.assertFalse(session_remotes.names_one(["github.com/globex-ag/"], remotes))
        self.assertFalse(session_remotes.names_one([""], remotes))
        # A drive letter is no host: the path stays a path.
        self.assertFalse(session_remotes.names_one(["c/code/"], remotes))
        self.assertFalse(session_remotes.names_one(["globex"], []))


class NotesTest(Fixture):
    def test_what_was_noted_for_a_folder_is_known_when_the_folder_is_gone(self) -> None:
        """Covers: B151"""
        self.note(self.repo, GLOBEX)
        shutil.rmtree(self.repo)

        self.assertEqual(session_remotes.noted(self.notes, str(self.repo), NOW + DAY), {GLOBEX})
        self.assertIsNone(session_remotes.noted(self.notes, str(self.base / "code"), NOW + DAY))

    def test_a_folder_noted_without_a_remote_is_known_to_have_none(self) -> None:
        """Covers: B151"""
        self.note(self.repo)

        self.assertEqual(session_remotes.noted(self.notes, str(self.repo), NOW), frozenset())

    def test_a_remote_stays_noted_for_thirty_days_after_it_was_last_seen(self) -> None:
        """Covers: B151"""
        moved = "https://git.example/alex/portal.git"
        self.note(self.repo, GLOBEX)
        self.note(self.repo, moved, when=NOW + 2 * DAY)

        self.assertEqual(session_remotes.noted(self.notes, str(self.repo), NOW + 30 * DAY), {GLOBEX, moved})
        self.assertEqual(session_remotes.noted(self.notes, str(self.repo), NOW + 31 * DAY), {moved})
        self.note(self.repo, moved, when=NOW + 31 * DAY)
        [written] = self.notes.glob("*.json")
        self.assertEqual(list(json.loads(written.read_text(encoding="utf-8"))["remotes"]), [moved])

    def test_a_note_nobody_renewed_for_thirty_days_says_nothing_and_is_forgotten(self) -> None:
        """Covers: B151"""
        self.note(self.repo, GLOBEX)
        [old] = self.notes.glob("*.json")
        late = NOW + 31 * DAY

        self.assertIsNone(session_remotes.noted(self.notes, str(self.repo), late))
        # A note's file is as old as its last writing; the clock of the test stands still for it.
        os.utime(old, (NOW.timestamp(), NOW.timestamp()))
        self.note(self.base / "code" / "shed", when=late)
        session_remotes.forget_old_notes(self.notes, late)
        session_remotes.forget_old_notes(self.base / "no-notes-yet", late)

        self.assertFalse(old.exists())
        self.assertEqual(len(list(self.notes.glob("*.json"))), 1)

    def test_a_note_that_cannot_be_read_says_nothing(self) -> None:
        """Covers: B151"""
        self.note(self.repo, GLOBEX)
        [written] = self.notes.glob("*.json")
        for broken in (
            "not json",
            "[]",
            '{"folder": "/elsewhere", "noted": "2026-11-07T09:00:00+00:00", "remotes": {}}',
        ):
            with self.subTest(broken=broken):
                written.write_text(broken, encoding="utf-8")

                self.assertIsNone(session_remotes.noted(self.notes, str(self.repo), NOW))


class RemoteRuleTest(Fixture):
    def test_work_named_by_a_noted_remote_is_left_out_when_its_folder_is_gone(self) -> None:
        """Covers: B152"""
        self.note(self.repo, GLOBEX)
        shutil.rmtree(self.repo)

        self.assertIs(self.rule("globex-ag/").judge(str(self.repo)), ByRemote.LEFT_OUT)
        self.assertIs(self.rule("initech/").judge(str(self.repo)), ByRemote.NOT_NAMED)

    def test_a_remote_the_repository_got_after_the_session_started_counts_too(self) -> None:
        """Covers: B152"""
        self.git("init", "-q")
        self.note(self.repo)
        self.git("remote", "add", "origin", GLOBEX)

        self.assertIs(self.rule("globex-ag/").judge(str(self.repo)), ByRemote.LEFT_OUT)

    def test_a_folder_nobody_noted_that_is_gone_or_whose_git_does_not_answer_is_unknown(self) -> None:
        """Covers: B152"""
        self.git("init", "-q")
        gone = self.base / "worktrees" / "portal-fix"

        self.assertIs(self.rule("globex-ag/").judge(str(gone)), ByRemote.UNKNOWN)
        self.assertIs(self.rule("globex-ag/", ask=lambda folder: None).judge(str(self.repo)), ByRemote.UNKNOWN)
        self.assertIs(self.rule("globex-ag/").judge(None), ByRemote.UNKNOWN)
        self.assertIs(self.rule("globex-ag/").judge("code/portal"), ByRemote.UNKNOWN)

    def test_a_noted_folder_whose_git_does_not_answer_now_is_judged_by_its_note(self) -> None:
        """Covers: B152"""
        self.note(self.repo, "git@github.com:alex/shed.git")

        self.assertIs(self.rule("globex-ag/", ask=lambda folder: None).judge(str(self.repo)), ByRemote.NOT_NAMED)

    def test_a_rule_that_names_no_remote_asks_nothing_and_leaves_nothing_out(self) -> None:
        """Covers: B152"""
        asked: list[Path] = []
        rule = self.rule(ask=asked.append)

        self.assertFalse(rule.names_any)
        self.assertIs(rule.judge(str(self.base / "gone")), ByRemote.NOT_NAMED)
        self.assertEqual(asked, [])

    def test_git_is_asked_once_for_a_folder(self) -> None:
        asked: list[Path] = []

        def ask(folder: Path) -> frozenset[str]:
            asked.append(folder)
            return frozenset()

        rule = self.rule("globex-ag/", ask=ask)
        rule.judge(str(self.repo))
        rule.judge(str(self.repo))

        self.assertEqual(asked, [self.repo])


if __name__ == "__main__":
    unittest.main()
