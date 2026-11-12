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
from typing import Any
from unittest import mock

from m2b import cli, paths
from m2b.config import machine, profile
from m2b.config.store_settings import KNOWN_STORE_FORMAT, save_store_settings
from m2b.store.base import EvictedFileError, FetchError, UnsupportedStoreError
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"


class CommandLineTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.home = Path(self._temp.name) / "home"
        self.machine = paths.MachinePaths(self.home)
        self.store = Path(self._temp.name) / "store"
        self.store.mkdir()

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _run(self, *arguments: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(SOURCE_ROOT),
            "M2B_HOME": str(self.home),
            **(extra_env or {}),
        }
        return subprocess.run(
            [sys.executable, "-m", "m2b.cli", *arguments],
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def _set_up(self, **profile_raw: Any) -> None:
        machine.save_machine_config(
            self.machine,
            {"version": 1, "machine_id": "sb-test-m1", "store": {"backend": "folder", "path": str(self.store)}},
        )
        if profile_raw:
            profile.save_profile(FolderStore(self.store, self.machine.temp_dir, DatalessGuard(False)), profile_raw)

    def test_without_config_a_command_exits_2_with_one_line_naming_setup(self) -> None:
        """Covers: B7"""
        result = self._run("config", "get")

        self.assertEqual(result.returncode, cli.EXIT_USAGE)
        self.assertEqual(result.stdout, "")
        self.assertEqual(len(result.stderr.splitlines()), 1, result.stderr)
        self.assertIn("/m2b:m2b setup", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_without_config_a_hook_exits_0_and_prints_nothing(self) -> None:
        """Covers: B7"""
        result = self._run("hook", "session-start")

        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_a_hook_with_a_broken_config_exits_0_and_says_so_in_one_line(self) -> None:
        """Covers: B7"""
        self.machine.config_file.parent.mkdir(parents=True)
        self.machine.config_file.write_text("{broken", encoding="utf-8")

        result = self._run("hook", "session-start")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(result.stdout.splitlines()), 1, result.stdout)
        self.assertIn("config.json", result.stdout)
        self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_a_missing_store_folder_exits_3(self) -> None:
        machine.save_machine_config(
            self.machine,
            {
                "version": 1,
                "machine_id": "sb-test-m1",
                "store": {"backend": "folder", "path": str(self.store / "gone")},
            },
        )

        result = self._run("profile", "get")

        self.assertEqual(result.returncode, cli.EXIT_UNREACHABLE)
        self.assertNotIn("setup", result.stderr)

    def test_an_invalid_config_exits_2_with_the_reason(self) -> None:
        self.machine.config_file.parent.mkdir(parents=True)
        self.machine.config_file.write_text(json.dumps({"version": 1}), encoding="utf-8")

        result = self._run("config", "get")

        self.assertEqual(result.returncode, cli.EXIT_USAGE)
        self.assertIn("machine_id", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_a_store_of_a_newer_format_exits_2_when_writing(self) -> None:
        self._set_up(version=1, owner="Alex")
        (self.store / "store.json").write_text(
            json.dumps(
                {"format": 99, "tasks": {"backend": "markdown"}, "curating_machine": "m", "journal_since": "2026-11-06"}
            ),
            encoding="utf-8",
        )

        result = self._run("profile", "set", "language", "de")

        self.assertEqual(result.returncode, cli.EXIT_USAGE)
        self.assertIn("update", result.stderr)

    def test_config_get_prints_the_store_path_with_the_tilde_expanded(self) -> None:
        machine.save_machine_config(
            self.machine, {"version": 1, "machine_id": "sb-test-m1", "store": {"backend": "folder", "path": "~/notes"}}
        )

        result = self._run("config", "get", "store.path")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f"{self.home / 'notes'}\n")

    def test_config_get_json_prints_the_whole_config(self) -> None:
        self._set_up()

        result = self._run("config", "get", "--json")

        self.assertEqual(json.loads(result.stdout)["machine_id"], "sb-test-m1")

    def test_config_get_of_an_unknown_key_is_a_usage_error(self) -> None:
        self._set_up()

        result = self._run("config", "get", "store.colour")

        self.assertEqual(result.returncode, cli.EXIT_USAGE)
        self.assertIn("store.colour", result.stderr)

    def test_profile_get_reads_the_profile_from_the_store(self) -> None:
        self._set_up(version=1, owner="Alex", customers=["Globex"])

        result = self._run("profile", "get", "customers", "--json")

        self.assertEqual(json.loads(result.stdout), ["Globex"])

    def test_profile_get_prints_what_the_worklog_leaves_out_in_the_shape_of_the_file(self) -> None:
        """Covers: B111"""
        self._set_up(version=1, owner="Alex")
        merged = self._run("profile", "merge", '{"worklog_leave_out": {"path_under": ["~/code/globex"]}}')
        self.assertEqual(merged.returncode, 0, merged.stderr)

        # The worklog add-on reads this answer, not the file: an object with ``path_under``.
        printed = json.loads(self._run("profile", "get", "--json").stdout)

        self.assertEqual(printed["worklog_leave_out"], {"path_under": ["~/code/globex"], "git_remote_contains": []})
        self.assertEqual(printed["version"], 2)

    def test_profile_get_prints_the_remotes_the_worklog_leaves_out_in_the_shape_of_the_file(self) -> None:
        """Covers: B153"""
        self._set_up(version=1, owner="Alex")
        # One key of the setting is set beside the other; a merge would replace the setting as a whole.
        added = self._run("profile", "set", "worklog_leave_out.git_remote_contains", '["globex-ag/"]')
        self.assertEqual(added.returncode, 0, added.stderr)
        beside = self._run("profile", "set", "worklog_leave_out.path_under", '["~/code/globex"]')
        self.assertEqual(beside.returncode, 0, beside.stderr)

        printed = json.loads(self._run("profile", "get", "--json").stdout)

        self.assertEqual(
            printed["worklog_leave_out"], {"path_under": ["~/code/globex"], "git_remote_contains": ["globex-ag/"]}
        )
        self.assertEqual(printed["version"], 2)

    def test_profile_get_without_a_profile_names_setup(self) -> None:
        self._set_up()

        result = self._run("profile", "get")

        self.assertEqual(result.returncode, cli.EXIT_USAGE)
        self.assertIn("/m2b:m2b setup", result.stderr)

    def test_a_profile_that_cannot_be_read_exits_3_in_one_line(self) -> None:
        self._set_up()
        (self.store / "profile.json").mkdir()

        result = self._run("profile", "get")

        self.assertEqual(result.returncode, cli.EXIT_UNREACHABLE)
        self.assertEqual(len(result.stderr.splitlines()), 1, result.stderr)

    def test_store_errors_map_to_their_exit_codes_in_one_line(self) -> None:
        self._set_up()
        cases = [
            (EvictedFileError("profile.json"), cli.EXIT_UNREACHABLE, "m2b store fetch profile.json"),
            (FetchError("not downloaded after 20 seconds: profile.json"), cli.EXIT_UNREACHABLE, "not downloaded"),
            (UnsupportedStoreError("the icloud backend runs on macOS only"), cli.EXIT_USAGE, "macOS only"),
        ]
        for error, code, text in cases:
            stderr = io.StringIO()
            failing = mock.patch("m2b.commands.backends.open_store", side_effect=error)
            with self.subTest(error=type(error).__name__), failing, contextlib.redirect_stderr(stderr):
                result = cli.main(["profile", "get"], {"M2B_HOME": str(self.home)})

                self.assertEqual(result, code)
                self.assertEqual(len(stderr.getvalue().splitlines()), 1)
                self.assertIn(text, stderr.getvalue())

    def test_an_unknown_command_is_a_usage_error(self) -> None:
        self.assertEqual(self._run("fly").returncode, cli.EXIT_USAGE)

    def test_version_prints_the_version_of_the_plugin_manifest_also_without_a_config(self) -> None:
        """Covers: B159"""
        manifest = json.loads((SOURCE_ROOT.parent / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))

        result = self._run("--version")

        self.assertEqual((result.returncode, result.stderr), (cli.EXIT_OK, ""))
        self.assertEqual(result.stdout, f"m2b {manifest['version']}\n")

    def test_a_command_that_groups_actions_prints_its_help_when_named_alone(self) -> None:
        """Covers: B160"""
        for group, actions in (("lint", ("scan", "fix")), ("tasks", ("list", "complete")), ("setup", ("apply",))):
            with self.subTest(group=group):
                result = self._run(group)

                self.assertEqual((result.returncode, result.stderr), (cli.EXIT_OK, ""))
                self.assertIn(f"usage: m2b {group}", result.stdout)
                for action in actions:
                    self.assertIn(action, result.stdout)

    def test_an_unknown_action_of_a_group_stays_a_usage_error(self) -> None:
        self.assertEqual(self._run("lint", "polish").returncode, cli.EXIT_USAGE)


class CuratorCommandsTest(unittest.TestCase):
    """The commands that move, rename or edit store files belong to the curation run alone."""

    CURATOR_COMMANDS = (
        ["ingest", "normalize"],
        ["ingest", "task", "20260301T090000Z-cli-a1b2.md", "--title", "Call Dana"],
        ["ingest", "ref", "20260301T090000Z-cli-a1b2.md", "https://example.org"],
        ["ingest", "note", "20260301T090000Z-cli-a1b2.md", "filed"],
        ["ingest", "facts-filed", "20260301T090000Z-cli-a1b2.md"],
        ["ingest", "finish", "20260301T090000Z-cli-a1b2.md"],
        ["harvest"],
        ["journal"],
        ["lint", "fix"],
    )

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.home = Path(self._temp.name) / "home"
        self.store = Path(self._temp.name) / "store"
        self.store.mkdir()
        (self.store / "inbox").mkdir()
        (self.store / "inbox" / "20260301T090000Z-cli-a1b2.md").write_text(
            "---\ncreated: 2026-03-01T09:00:00Z\nsource: cli\n---\nCall Dana\n", encoding="utf-8"
        )
        machine.save_machine_config(
            paths.MachinePaths(self.home),
            {"version": 1, "machine_id": "sb-test-m1", "store": {"backend": "folder", "path": str(self.store)}},
        )

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _main(self, arguments: list[str], environ: dict[str, str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(arguments, environ)
        return code, out.getvalue(), err.getvalue()

    def _store_files(self) -> dict[str, str]:
        return {
            str(path.relative_to(self.store)): path.read_text(encoding="utf-8")
            for path in sorted(self.store.rglob("*"))
            if path.is_file()
        }

    def test_outside_a_curation_run_each_curator_command_is_refused_and_changes_nothing(self) -> None:
        """Covers: B53"""
        before = self._store_files()
        for arguments in self.CURATOR_COMMANDS:
            with self.subTest(command=" ".join(arguments[:2])):
                code, out, err = self._main(arguments, {"M2B_HOME": str(self.home)})

                self.assertEqual(code, cli.EXIT_USAGE)
                self.assertEqual(out, "")
                self.assertEqual(len(err.splitlines()), 1)
                self.assertIn("only inside a curation run", err)
                self.assertIn("m2b curate", err)
        self.assertEqual(self._store_files(), before)

    def test_inside_a_curation_run_a_curator_command_runs(self) -> None:
        """Covers: B53"""
        store = FolderStore(self.store, self.home / "tmp", DatalessGuard(False))
        save_store_settings(
            store,
            {
                "format": KNOWN_STORE_FORMAT,
                "tasks": {"backend": "markdown"},
                "curating_machine": "sb-test-m1",
                "journal_since": "2026-03-01",
            },
        )

        code, _, err = self._main(["lint", "fix"], {"M2B_HOME": str(self.home), "M2B_CURATION_RUN": "1"})

        self.assertEqual(code, cli.EXIT_OK, err)

    def test_help_lists_the_owner_commands_and_leaves_the_curator_ones_out(self) -> None:
        """Covers: B53"""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["--help"], {})

        self.assertEqual(code, cli.EXIT_OK)
        for command in ("capture", "search", "todos", "status", "doctor", "curate"):
            self.assertIn(command, out.getvalue())
        for command in ("ingest", "harvest", "journal", "hook"):
            self.assertNotIn(command, out.getvalue())


if __name__ == "__main__":
    unittest.main()
