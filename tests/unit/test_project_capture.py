"""The owner makes a project known with one sentence: a capture that names the folder's remote."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from m2b import cli, paths, project_capture
from m2b.config import machine
from m2b.config.store_settings import save_store_settings
from m2b.session_remotes import Repository
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard

PORTAL = Repository(Path("/code/acme-portal"), ("github.com/acme/portal",))
MEMORY_WITH_PORTAL = (
    "# Memory\n\n## Facts\n\n- Dana likes old maps (dana.md)\n\n"
    "### Acme portal (Acme portal, portal)\n- Repository: github.com/acme/portal (acme-portal.md)\n\n## Current\n"
)


class TextTest(unittest.TestCase):
    def test_the_capture_names_the_project_the_owners_words_and_each_address(self) -> None:
        """Covers: B252"""
        two = Repository(Path("/code/acme-portal"), ("github.com/acme/portal", "gitlab.com/acme/portal"))

        text = project_capture.capture_text(two.addresses, "the customer portal we build for Acme")

        self.assertEqual(
            text,
            "Keep this project: the customer portal we build for Acme\n"
            "Repository: github.com/acme/portal\n"
            "Repository: gitlab.com/acme/portal\n",
        )

    def test_without_words_the_capture_names_the_repository(self) -> None:
        """Covers: B252"""
        self.assertEqual(
            project_capture.capture_text(PORTAL.addresses, "  "),
            "Keep this project: portal\nRepository: github.com/acme/portal\n",
        )


class StoreFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="sb-test-project-")
        self.addCleanup(self._temp.cleanup)
        self.base = Path(self._temp.name)
        self.root = self.base / "sb-test-store"
        (self.root / "memory").mkdir(parents=True)
        (self.root / "inbox").mkdir()
        self.store = FolderStore(self.root, self.base / "machine-tmp", DatalessGuard(False))

    def inbox(self) -> list[str]:
        return sorted(path.name for path in (self.root / "inbox").iterdir())


class KnownTest(StoreFixture):
    def test_a_topic_with_a_repository_line_of_that_address_is_the_project(self) -> None:
        """Covers: B253"""
        (self.root / "memory" / "MEMORY.md").write_text(MEMORY_WITH_PORTAL, encoding="utf-8")

        self.assertEqual(project_capture.known_as(self.store, PORTAL.addresses), "Acme portal")
        other = Repository(Path("/code/shop"), ("github.com/acme/shop",))
        self.assertIsNone(project_capture.known_as(self.store, other.addresses))

    def test_a_project_capture_that_waits_in_the_inbox_is_the_project_too(self) -> None:
        """Covers: B253"""
        (self.root / "inbox" / "20261120-0900-claude.md").write_text(
            "---\ncreated: 2026-11-20T09:00:00+01:00\nsource: claude\n---\n"
            + project_capture.capture_text(PORTAL.addresses, "the portal"),
            encoding="utf-8",
        )

        self.assertEqual(project_capture.waiting_capture(self.store, PORTAL.addresses), "20261120-0900-claude.md")

    def test_a_file_that_cannot_be_read_is_passed_over(self) -> None:
        """Covers: B253"""
        unreadable = self.root / "inbox" / "20261120-0800-claude.md"
        unreadable.write_text(project_capture.capture_text(PORTAL.addresses, "the portal"), encoding="utf-8")
        unreadable.chmod(0)
        self.addCleanup(unreadable.chmod, 0o600)
        (self.root / "memory" / "MEMORY.md").write_text(MEMORY_WITH_PORTAL, encoding="utf-8")
        (self.root / "memory" / "MEMORY.md").chmod(0)
        self.addCleanup((self.root / "memory" / "MEMORY.md").chmod, 0o600)

        self.assertIsNone(project_capture.waiting_capture(self.store, PORTAL.addresses))
        self.assertIsNone(project_capture.known_as(self.store, PORTAL.addresses))

    def test_a_note_that_only_mentions_the_address_is_no_project_capture(self) -> None:
        """Covers: B253"""
        (self.root / "inbox" / "20261120-0900-claude.md").write_text(
            "---\nsource: claude\n---\nThe portal moved to github.com/acme/portal last week.\n", encoding="utf-8"
        )

        self.assertIsNone(project_capture.waiting_capture(self.store, PORTAL.addresses))


class CommandTest(StoreFixture):
    def setUp(self) -> None:
        super().setUp()
        self.m2b_home = self.base / "m2b-home"
        self.machine = paths.MachinePaths(self.m2b_home)
        machine.save_machine_config(
            self.machine,
            {"version": 1, "machine_id": "sb-test-m1", "store": {"backend": "folder", "path": str(self.root)}},
        )
        settings = {
            "format": 1,
            "tasks": {"backend": "markdown"},
            "curating_machine": "sb-test-m1",
            "journal_since": "2026-11-01",
        }
        save_store_settings(self.store, settings)
        self.environ = {
            "HOME": str(self.base / "user-home"),
            "M2B_HOME": str(self.m2b_home),
            "PATH": os.environ.get("PATH", ""),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
        }

    def clone(self, *remotes: str) -> Path:
        folder = self.base / "code" / "acme-portal"
        (folder / "src").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(folder)], check=True, env=self.environ, capture_output=True)
        for number, remote in enumerate(remotes):
            subprocess.run(
                ["git", "-C", str(folder), "remote", "add", f"r{number}", remote],
                check=True,
                env=self.environ,
                capture_output=True,
            )
        return folder

    def capture_in(self, folder: Path, words: str, *more: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        given = io.StringIO(words)
        with (
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
            mock.patch("sys.stdin", given),
            mock.patch("os.getcwd", return_value=str(folder)),
        ):
            code = cli.main(["capture", "--project", "--source", "claude", *more, "-"], self.environ)
        return code, out.getvalue(), err.getvalue()

    def test_a_session_in_a_clone_captures_the_project_with_its_remote_and_the_owners_words(self) -> None:
        """Covers: B252"""
        clone = self.clone("git@github.com:acme/portal.git")

        code, out, err = self.capture_in(clone / "src", "the customer portal we build for Acme")

        self.assertEqual((code, err), (0, ""))
        [name] = self.inbox()
        self.assertIn(name, out)
        text = (self.root / "inbox" / name).read_text(encoding="utf-8")
        self.assertIn(
            "Keep this project: the customer portal we build for Acme\nRepository: github.com/acme/portal\n", text
        )

    def test_a_folder_without_a_remote_captures_nothing_and_says_why(self) -> None:
        """Covers: B252"""
        clone = self.clone()

        code, _, err = self.capture_in(clone, "the portal")

        self.assertEqual(code, 2)
        self.assertIn("needs a remote to know the project on another machine", err)
        self.assertEqual(self.inbox(), [])

    def test_a_folder_in_no_repository_captures_nothing(self) -> None:
        """Covers: B252"""
        folder = self.base / "notes"
        folder.mkdir()

        code, _, err = self.capture_in(folder, "my notes")

        self.assertEqual(code, 2)
        self.assertIn("in no git repository", err)
        self.assertEqual(self.inbox(), [])

    def test_a_project_with_a_topic_already_captures_nothing_and_names_the_topic(self) -> None:
        """Covers: B253"""
        clone = self.clone("https://github.com/acme/portal")
        (self.root / "memory" / "MEMORY.md").write_text(MEMORY_WITH_PORTAL, encoding="utf-8")

        code, out, _ = self.capture_in(clone, "the portal")

        self.assertEqual(code, 0)
        self.assertIn("already known as the topic Acme portal", out)
        self.assertEqual(self.inbox(), [])

    def test_with_json_a_known_project_is_answered_as_json(self) -> None:
        """Covers: B253"""
        clone = self.clone("https://github.com/acme/portal")
        (self.root / "memory" / "MEMORY.md").write_text(MEMORY_WITH_PORTAL, encoding="utf-8")

        code, out, _ = self.capture_in(clone, "the portal", "--json")

        self.assertEqual((code, json.loads(out)), (0, {"path": None, "known_as": "Acme portal", "waiting": None}))

    def test_asking_twice_before_a_run_captures_once(self) -> None:
        """Covers: B253"""
        clone = self.clone("https://github.com/acme/portal")

        self.capture_in(clone, "the portal")
        code, out, _ = self.capture_in(clone, "the portal, again")

        self.assertEqual(code, 0)
        self.assertIn("waits in the inbox", out)
        self.assertEqual(len(self.inbox()), 1)


if __name__ == "__main__":
    unittest.main()
