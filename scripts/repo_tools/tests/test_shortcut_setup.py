from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from repo_tools import shortcut_setup


class ShortcutSetupTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.user_home = Path(self._temp.name) / "user"
        self.drive = self.user_home / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
        self.drive.mkdir(parents=True)
        self.core = Path("/checkout/plugins/m2b")
        self.calls: list[tuple[list[str], dict[str, str]]] = []

        self.setup_answer: dict[str, Any] = {"written": [], "problems": [], "missing_executables": []}
        self.list_exit = 0
        self.reachable_exit = 0

    def fake_run(self, command: list[str], **options: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append((command, dict(options["env"])))
        if "setup" in command:
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(self.setup_answer), stderr="")
        if "list" in command and "--marker" not in command:
            return subprocess.CompletedProcess(
                command, self.reachable_exit, stdout="[]", stderr="Reminders has no list named 'sb-test-inbox'"
            )
        if "list" in command:
            stdout = json.dumps([{"id": "abc123", "title": "m2b: review"}]) if self.list_exit == 0 else ""
            return subprocess.CompletedProcess(command, self.list_exit, stdout=stdout, stderr="tasks unreachable")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    def test_set_up_seeds_a_test_store_and_applies_setup_in_its_own_home(self) -> None:
        lines = shortcut_setup.set_up(self.user_home, self.core, {"PATH": "/opt/bin"}, run=self.fake_run)

        test_home, store = shortcut_setup.locations(self.user_home)
        self.assertTrue(test_home.name.startswith("sb-test-"))
        self.assertEqual(store.parent, self.drive)
        self.assertTrue(store.name.startswith("sb-test-"))
        self.assertIn("[[20260101T000000Z-cli-dead.md]]", (store / "memory" / "dana.md").read_text(encoding="utf-8"))
        (command, env) = self.calls[0]
        self.assertEqual(command[-5:-1], ["setup", "apply", "--json", "--answers"])
        answers = json.loads(command[-1])
        self.assertEqual(answers["tasks"], {"backend": "apple-reminders", "list": "sb-test-inbox"})
        self.assertEqual(answers["store"], {"backend": "icloud", "path": str(store)})
        self.assertTrue(answers["curates"])
        self.assertEqual(
            (env["M2B_HOME"], env["M2B_CORE_ROOT"], env["PATH"]), (str(test_home), str(self.core), "/opt/bin")
        )
        shortcut = next(line for line in lines if "curate --force" in line)
        self.assertIn(f"M2B_HOME={test_home}", shortcut)
        self.assertIn(f"M2B_CORE_ROOT={self.core}", shortcut)
        self.assertIn(str(test_home / ".local" / "bin" / "m2b"), shortcut)

    def test_remove_deletes_the_review_tasks_then_the_test_home_and_store(self) -> None:
        shortcut_setup.set_up(self.user_home, self.core, {"PATH": "/opt/bin"}, run=self.fake_run)
        test_home, store = shortcut_setup.locations(self.user_home)
        test_home.mkdir(parents=True, exist_ok=True)
        self.calls.clear()

        shortcut_setup.remove(self.user_home, self.core, {"PATH": "/opt/bin"}, run=self.fake_run)

        first = self.calls[0][0]
        self.assertEqual(
            first[first.index("tasks") :], ["tasks", "list", "--marker", "review", "--include-completed", "--json"]
        )
        self.assertIn(["tasks", "delete", "abc123"], [command[-3:] for command, _ in self.calls])
        self.assertFalse(test_home.exists())
        self.assertFalse(store.exists())

    def test_a_missing_program_or_a_launcher_problem_stops_set_up_before_it_prints_the_line(self) -> None:
        for answer in ({"missing_executables": ["reminders"]}, {"problems": ["the launcher could not be written"]}):
            with self.subTest(answer=answer):
                self.setup_answer = {"written": [], "problems": [], "missing_executables": [], **answer}
                with self.assertRaisesRegex(RuntimeError, "reminders|launcher"):
                    shortcut_setup.set_up(self.user_home, self.core, {"PATH": "/opt/bin"}, run=self.fake_run)
                test_home, store = shortcut_setup.locations(self.user_home)
                self.assertFalse(store.exists())
                self.assertFalse(test_home.exists())

    def test_a_missing_task_list_stops_set_up_with_the_reason(self) -> None:
        self.reachable_exit = 3

        with self.assertRaisesRegex(RuntimeError, "sb-test-inbox"):
            shortcut_setup.set_up(self.user_home, self.core, {"PATH": "/opt/bin"}, run=self.fake_run)

    def test_off_macos_or_without_m2b_it_main_refuses_and_creates_nothing(self) -> None:
        for platform, it in (("linux", "1"), ("darwin", "0")):
            environ = {"M2B_IT": it, "HOME": str(self.user_home)}
            with (
                self.subTest(platform=platform, it=it),
                mock.patch("repo_tools.shortcut_setup.sys.platform", platform),
                mock.patch.dict("os.environ", environ, clear=True),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(shortcut_setup.main([]), 2)
        self.assertEqual(list(self.drive.iterdir()), [])
        self.assertFalse((self.user_home / "sb-test-shortcut").exists())

    def test_remove_stops_when_it_cannot_list_the_review_tasks(self) -> None:
        test_home, _ = shortcut_setup.locations(self.user_home)
        test_home.mkdir(parents=True)
        self.list_exit = 3

        with self.assertRaisesRegex(RuntimeError, "tasks unreachable"):
            shortcut_setup.remove(self.user_home, self.core, {"PATH": "/opt/bin"}, run=self.fake_run)
        self.assertTrue(test_home.exists())

    def test_nothing_is_touched_without_sb_test_names(self) -> None:
        with self.assertRaises(ValueError):
            shortcut_setup.require_test_name(Path("/Users/alex/Second Brain"))


if __name__ == "__main__":
    unittest.main()
