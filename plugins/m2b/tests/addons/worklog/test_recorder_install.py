"""Installing and removing the recorder in a fake herdr, and refreshing the installed copy."""

from __future__ import annotations

import os
import subprocess
import sys

from m2b_worklog import recorder
from m2b_worklog.paths import RECORDER_ID, RECORDER_SOURCE, worklog_paths
from worklog_fixtures import COMMAND, WorklogFixture


class RecorderTest(WorklogFixture):
    def run_command(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environ = {**self.environ, "PATH": os.environ.get("PATH", ""), "M2B_PYTHON": sys.executable}
        return subprocess.run([str(COMMAND), *arguments], capture_output=True, text=True, env=environ, timeout=30)

    @property
    def copy(self):  # type: ignore[no-untyped-def]
        return self.home / ".local" / "share" / "m2b" / "worklog-recorder"

    def test_install_copies_the_recorder_and_links_the_copy(self) -> None:
        result = self.run_command("recorder", "install")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(p.name for p in self.copy.iterdir()), ["herdr-plugin.toml", "record.py"])
        self.assertEqual((self.copy / "record.py").read_bytes(), (RECORDER_SOURCE / "record.py").read_bytes())
        self.assertEqual(self.linked(), {RECORDER_ID: str(self.copy)})

    def test_install_twice_links_once(self) -> None:
        self.run_command("recorder", "install")
        again = self.run_command("recorder", "install")

        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("already linked", again.stdout)
        self.assertEqual(
            [call for call in self.herdr_calls_made() if call.startswith("plugin link")], [f"plugin link {self.copy}"]
        )

    def test_remove_unlinks_and_deletes_the_copy_and_runs_twice(self) -> None:
        self.run_command("recorder", "install")
        self.state.mkdir(parents=True)
        (self.state / "w1.jsonl").write_text('{"kind": "focus"}\n', encoding="utf-8")

        first = self.run_command("recorder", "remove")
        second = self.run_command("recorder", "remove")

        self.assertEqual((first.returncode, second.returncode), (0, 0), first.stderr + second.stderr)
        self.assertEqual(self.linked(), {})
        self.assertFalse(self.copy.exists())
        self.assertIn("was not linked", second.stdout)
        self.assertTrue((self.state / "w1.jsonl").exists())

    def test_a_herdr_that_cannot_be_run_is_one_error_line(self) -> None:
        environ_herdr = self.environ["M2B_HERDR"]
        self.environ["M2B_HERDR"] = str(self.base / "no-herdr")

        result = self.run_command("recorder", "install")

        self.environ["M2B_HERDR"] = environ_herdr
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr.count("\n"), 1)
        self.assertIn("was not found", result.stderr)

    def test_refresh_replaces_an_installed_copy_and_leaves_a_missing_one_absent(self) -> None:
        paths = worklog_paths(self.environ)
        self.assertFalse(recorder.refresh(paths))
        self.assertFalse(self.copy.exists())

        self.run_command("recorder", "install")
        (self.copy / "record.py").write_text("# an older recorder\n", encoding="utf-8")

        self.assertTrue(recorder.refresh(paths))
        self.assertEqual((self.copy / "record.py").read_bytes(), (RECORDER_SOURCE / "record.py").read_bytes())
        self.assertFalse(recorder.refresh(paths))

    def test_a_plugin_list_herdr_does_not_answer_as_a_list_is_an_error(self) -> None:
        paths = worklog_paths(self.environ)

        def garbled(command: list[str], **options: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(command, 0, "plugins: none", "")

        with self.assertRaises(recorder.HerdrError):
            recorder.install(paths, self.environ, garbled)
