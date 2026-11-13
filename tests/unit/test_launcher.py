"""The launcher in ``~/.local/bin`` and plugin install paths, against a fake ``installed_plugins.json``.

The owner's own ``~/.claude/plugins/installed_plugins.json`` is never read: every run sets
``M2B_INSTALLED_PLUGINS`` and a temporary ``HOME``.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from locations import PLUGIN_ROOT
from m2b import cli, launcher, paths
from m2b.config import machine


class LauncherTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        self.home = self.root / "home"
        self.machine = paths.MachinePaths(self.home)
        self.installed = self.root / "installed_plugins.json"
        self.environ = {
            "HOME": str(self.root / "user-home"),
            "M2B_HOME": str(self.home),
            launcher.INSTALLED_PLUGINS_VARIABLE: str(self.installed),
            "PATH": os.environ.get("PATH", ""),
        }

    def fake_core(self, name: str) -> Path:
        core = self.root / name
        (core / "bin").mkdir(parents=True)
        script = core / "bin" / "m2b"
        script.write_text(f'#!/bin/sh\necho "{name} $*"\n', encoding="utf-8")
        script.chmod(0o755)
        return core

    def record(self, plugins: dict[str, list[dict[str, str]]]) -> None:
        self.installed.write_text(json.dumps({"version": 2, "plugins": plugins}), encoding="utf-8")

    def record_core(self, core: Path, scope: str = "user", marketplace: str = launcher.MARKETPLACE) -> None:
        self.record({f"m2b@{marketplace}": [{"scope": scope, "installPath": str(core)}]})

    def main(self, *arguments: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(arguments), self.environ)
        return code, out.getvalue(), err.getvalue()

    def run_launcher(self, *arguments: str, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.machine.launcher), *arguments],
            env={**self.environ, **extra},
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_install_writes_an_executable_launcher_with_a_version_line(self) -> None:
        code, out, _ = self.main("launcher", "install")

        self.assertEqual((code, out.strip()), (cli.EXIT_OK, str(self.machine.launcher)))
        self.assertTrue(os.access(self.machine.launcher, os.X_OK))
        self.assertEqual(launcher.installed_launcher_version(self.machine), launcher.core_version())

    def test_the_launcher_follows_an_update_without_being_reinstalled(self) -> None:
        self.record_core(self.fake_core("core-a"))
        self.main("launcher", "install")
        first = self.run_launcher("tasks", "list")

        self.record_core(self.fake_core("core-b"))
        second = self.run_launcher("tasks", "list")

        self.assertEqual((first.returncode, first.stdout), (0, "core-a tasks list\n"))
        self.assertEqual((second.returncode, second.stdout), (0, "core-b tasks list\n"))

    def test_the_core_root_variable_runs_a_checkout_instead(self) -> None:
        self.record_core(self.fake_core("core-a"))
        self.main("launcher", "install")

        result = self.run_launcher("doctor", M2B_CORE_ROOT=str(self.fake_core("checkout")))

        self.assertEqual(result.stdout, "checkout doctor\n")

    def test_arguments_with_spaces_and_quotes_arrive_unchanged(self) -> None:
        self.record_core(self.fake_core("core-a"))
        self.main("launcher", "install")

        result = self.run_launcher("tasks", "add", "Call Dana's plumber", "--notes", "two  spaces")

        self.assertEqual(result.stdout, "core-a tasks add Call Dana's plumber --notes two  spaces\n")

    def test_without_the_core_installed_the_launcher_exits_3_and_says_so(self) -> None:
        cases = {
            "no file": None,
            "another marketplace": {"m2b@another-marketplace": [{"scope": "user", "installPath": "/x"}]},
            "project scope only": {"m2b@m2b": [{"scope": "project", "installPath": "/x"}]},
            "broken entry": {"m2b@m2b": [{"scope": "user"}]},
        }
        self.main("launcher", "install")
        for case, plugins in cases.items():
            with self.subTest(case=case):
                if plugins is None:
                    self.installed.unlink(missing_ok=True)
                else:
                    self.record(plugins)
                result = self.run_launcher("doctor")
                self.assertEqual(result.returncode, 3)
                self.assertIn("not installed", result.stderr)
                self.assertEqual(launcher.resolve_install_path("m2b", self.environ), None)

    def test_resolve_prints_a_plugins_install_path_or_exits_3(self) -> None:
        self.record({"worklog@m2b": [{"scope": "user", "installPath": "/plugins/worklog/0.1.0"}]})

        found = self.main("launcher", "resolve", "worklog")
        missing = self.main("launcher", "resolve", "garden")

        self.assertEqual(found[:2], (cli.EXIT_OK, "/plugins/worklog/0.1.0\n"))
        self.assertEqual(missing[0], 3)
        self.assertIn("garden@m2b", missing[2])

    def test_the_launcher_uses_the_recorded_python(self) -> None:
        machine.save_machine_config(
            self.machine,
            {
                "version": 1,
                "machine_id": "sb-test-m1",
                "store": {"backend": "folder", "path": str(self.root)},
                "executables": {"python3": sys.executable},
            },
        )

        self.main("launcher", "install")

        self.assertIn(sys.executable, self.machine.launcher.read_text(encoding="utf-8"))

    def test_files_in_the_working_directory_never_replace_modules(self) -> None:
        """Inside Claude Code the Bash tool runs in the user's project, whatever it holds."""
        project = self.root / "project"
        (project / "m2b").mkdir(parents=True)
        for name in ("secrets.py", "json.py", "calendar.py", "m2b/__init__.py"):
            (project / name).write_text("raise SystemExit('shadowed')\n", encoding="utf-8")
        self.record({"worklog@m2b": [{"scope": "user", "installPath": "/plugins/worklog"}]})

        result = subprocess.run(
            [str(PLUGIN_ROOT / "bin" / "m2b"), "launcher", "resolve", "worklog"],
            cwd=project,
            env=self.environ,
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual((result.returncode, result.stdout), (0, "/plugins/worklog\n"), result.stderr)

    def test_the_real_entry_point_runs_this_plugin_through_the_launcher(self) -> None:
        """The whole chain: launcher, the plugin's bin/m2b, the package."""
        self.record_core(PLUGIN_ROOT)
        self.main("launcher", "install")

        result = self.run_launcher("launcher", "resolve", "m2b")

        self.assertEqual((result.returncode, result.stdout.strip()), (0, str(PLUGIN_ROOT)), result.stderr)


if __name__ == "__main__":
    unittest.main()
