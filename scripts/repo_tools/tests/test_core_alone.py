"""The list of what each add-on puts into the plugin, the copies without add-ons, and the proof run in them."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from m2b.addons import addon_names

from repo_tools import core_alone
from repo_tools.core_alone import AddonParts

SAMPLE_HOOK = '"${CLAUDE_PLUGIN_ROOT}"/bin/m2b-sample hook session-start'
CORE_HOOK = '"${CLAUDE_PLUGIN_ROOT}"/bin/m2b hook distillate'
SAMPLE = AddonParts(
    "sample", paths=("bin/m2b-sample", "skills/sample-setup", "src/m2b_sample"), hook_commands=(SAMPLE_HOOK,)
)
CORE_TEST = (
    "import unittest\nfrom pathlib import Path\n\nimport m2b\n\n\n"
    "class CoreTest(unittest.TestCase):\n    def test_it(self) -> None:\n        {check}\n"
)
# The proof puts the copy of the plugin, named as the plugin is, where the tests' copy finds it.
READS_THE_ADDON = (
    "(Path(__file__).resolve().parents[2] / 'plugins' / 'plugin' / 'skills' / 'sample-setup' / 'SKILL.md').read_text()"
)
ADDON_TEST = (
    "import unittest\n\nimport m2b_sample\n\n\n"
    "class AddonTest(unittest.TestCase):\n    def test_it(self) -> None:\n        self.assertTrue(m2b_sample)\n"
)
# Exits 0 only when the plugin a scenario runs against is the one built here and holds no add-on package.
IN_THE_COPY_ALONE = (
    "import pathlib, sys; plugin = pathlib.Path(sys.argv[1]); "
    "sys.exit(not (plugin / 'built-for-this-test').is_file() or (plugin / 'src' / 'm2b_sample').exists())"
)

# What the core keeps at the top of the plugin's folder. An add-on's folder there does not have to
# carry its name, so whatever else appears is an add-on's listed part or a decision to take here.
CORE_AT_THE_TOP = (
    ".claude-plugin",
    "bin",
    "evals",
    "hooks",
    "locale",
    "schemas",
    "skills",
    "src",
    "tests",
    "tsconfig.json",
    "types",
)
# What the repository keeps out of git and a machine may leave in the plugin's folder.
UNTRACKED_AT_THE_TOP = {".DS_Store", ".build", ".venv", ".mypy_cache", ".ruff_cache"}


class RealPluginTest(unittest.TestCase):
    def test_every_addon_of_the_core_has_its_parts_listed(self) -> None:
        self.assertEqual(sorted(addon.name for addon in core_alone.ADDON_PARTS), sorted(addon_names()))

    def test_every_listed_part_exists(self) -> None:
        self.assertEqual(core_alone.missing_parts(core_alone.PLUGIN), [])

    def test_nothing_in_the_plugin_carries_an_addons_name_without_being_listed(self) -> None:
        self.assertEqual(core_alone.unlisted_parts(core_alone.PLUGIN), [])

    def test_every_addon_has_its_suite_in_the_folder_the_copy_of_the_tests_leaves_out(self) -> None:
        suites = core_alone.UNIT_TESTS / core_alone.ADDON_SUITES

        self.assertEqual(sorted(suite.name for suite in suites.iterdir() if suite.is_dir()), sorted(addon_names()))

    def test_the_copy_holds_the_core_and_nothing_that_carries_an_addons_name(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sb-test-") as temp:
            copy = Path(temp) / "m2b"

            core_alone.copy_without_addons(core_alone.PLUGIN, copy)

            carrying = [str(path.relative_to(copy)) for name in addon_names() for path in copy.rglob(f"*{name}*")] + [
                command for name in addon_names() for command in core_alone.hook_commands(copy) if name in command
            ]
            self.assertEqual(carrying, [])
            self.assertIn(CORE_HOOK, core_alone.hook_commands(copy))
            self.assertTrue((copy / "src" / "m2b" / "cli.py").is_file())
            self.assertTrue((copy / "bin" / "m2b").is_file())
            self.assertEqual(list(copy.rglob("__pycache__")), [])
            at_the_top = {entry.name for entry in copy.iterdir()} - UNTRACKED_AT_THE_TOP
            self.assertEqual(sorted(at_the_top), sorted(CORE_AT_THE_TOP))


class SamplePluginTest(unittest.TestCase):
    """A small plugin with a core and one add-on, ``sample``, built in a temporary folder."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="sb-test-")
        self.addCleanup(self._temp.cleanup)
        self.plugin = Path(self._temp.name) / "plugin"
        self.unit_tests = Path(self._temp.name) / "unit-tests"
        self.scenarios = Path(self._temp.name) / "scenarios"
        self.scenarios.mkdir()
        self.write("built-for-this-test", "")
        self.write("src/m2b/__init__.py", "")
        self.write("src/m2b_sample/__init__.py", "")
        self.write("bin/m2b", "#!/bin/sh\n")
        self.write("bin/m2b-sample", "#!/bin/sh\n")
        self.write("skills/capture/SKILL.md", "capture\n")
        self.write("skills/sample-setup/SKILL.md", "set the sample up\n")
        self.write_test("test_core.py", CORE_TEST.format(check="self.assertTrue(m2b)"))
        self.write_hooks(CORE_HOOK, SAMPLE_HOOK)

    def write(self, path: str, text: str) -> None:
        self._write(self.plugin / path, text)

    def write_test(self, path: str, text: str) -> None:
        self._write(self.unit_tests / path, text)

    def _write(self, target: Path, text: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def write_hooks(self, *commands: str) -> None:
        hooks = [{"type": "command", "command": command, "timeout": 20} for command in commands]
        manifest = {
            "description": "hooks",
            "modules": ["./register.tsx"],
            "hooks": {"SessionStart": [{"hooks": hooks}]},
        }
        self.write("hooks/hooks.json", json.dumps(manifest))

    def scenario(self, name: str, steps: list[dict[str, Any]]) -> None:
        folder = self.scenarios / name
        folder.mkdir()
        (folder / "steps.json").write_text(json.dumps({"steps": steps}), encoding="utf-8")
        (folder / "expect.json").write_text(json.dumps({"store_files": {}}), encoding="utf-8")

    def proof(self, parts: tuple[AddonParts, ...] = (SAMPLE,)) -> tuple[bool, str]:
        """Whether the proof holds, and what its two runs printed."""
        runs = core_alone.prove_core_alone(self.plugin, self.unit_tests, parts, self.scenarios, capture_output=True)
        return all(run.returncode == 0 for run in runs), "".join(run.stdout + run.stderr for run in runs)


class PartsListTest(SamplePluginTest):
    def test_a_complete_list_has_nothing_missing_and_nothing_unlisted(self) -> None:
        self.assertEqual(core_alone.missing_parts(self.plugin, [SAMPLE]), [])
        self.assertEqual(core_alone.unlisted_parts(self.plugin, [SAMPLE]), [])

    def test_a_listed_path_or_hook_command_the_plugin_does_not_have_is_missing(self) -> None:
        (self.plugin / "bin" / "m2b-sample").unlink()
        self.write_hooks(CORE_HOOK)

        self.assertEqual(core_alone.missing_parts(self.plugin, [SAMPLE]), ["bin/m2b-sample", SAMPLE_HOOK])

    def test_a_path_that_carries_the_addons_name_outside_every_listed_part_is_unlisted(self) -> None:
        self.write("skills/sample-verdict/SKILL.md", "judge\n")
        self.write("schemas/sample-facts.schema.json", "{}")
        self.write("src/m2b_sample/sample_files.py", "")
        self.write("src/m2b/__pycache__/sample.cpython-314.pyc", "")

        self.assertEqual(
            core_alone.unlisted_parts(self.plugin, [SAMPLE]),
            ["schemas/sample-facts.schema.json", "skills/sample-verdict"],
        )

    def test_a_hook_command_that_carries_the_addons_name_and_is_not_listed_is_unlisted(self) -> None:
        second = '"${CLAUDE_PLUGIN_ROOT}"/bin/m2b-sample hook prompt'
        self.write_hooks(CORE_HOOK, SAMPLE_HOOK, second)

        self.assertEqual(core_alone.unlisted_parts(self.plugin, [SAMPLE]), [second])


class CopyTest(SamplePluginTest):
    def test_the_copy_leaves_out_each_listed_path_and_hook_command_and_keeps_the_rest(self) -> None:
        self.write("src/m2b/__pycache__/cli.cpython-314.pyc", "")
        copy = self.plugin.parent / "copy"

        core_alone.copy_without_addons(self.plugin, copy, [SAMPLE])

        files = sorted(path.relative_to(copy).as_posix() for path in copy.rglob("*") if path.is_file())
        self.assertEqual(
            files,
            [
                "bin/m2b",
                "built-for-this-test",
                "hooks/hooks.json",
                "skills/capture/SKILL.md",
                "src/m2b/__init__.py",
            ],
        )
        manifest = json.loads((copy / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["hooks"], {"SessionStart": [{"hooks": [{"type": "command", "command": CORE_HOOK, "timeout": 20}]}]}
        )
        self.assertEqual(manifest["modules"], ["./register.tsx"])

    def test_the_plugin_itself_stays_as_it_was(self) -> None:
        before = {path: path.read_bytes() for path in self.plugin.rglob("*") if path.is_file()}

        core_alone.copy_without_addons(self.plugin, self.plugin.parent / "copy", [SAMPLE])

        self.assertEqual({path: path.read_bytes() for path in self.plugin.rglob("*") if path.is_file()}, before)

    def test_a_list_that_names_a_missing_part_stops_the_copy_before_it_starts(self) -> None:
        (self.plugin / "bin" / "m2b-sample").unlink()
        copy = self.plugin.parent / "copy"

        with self.assertRaisesRegex(core_alone.StaleAddonPartsError, "bin/m2b-sample"):
            core_alone.copy_without_addons(self.plugin, copy, [SAMPLE])

        self.assertFalse(copy.exists())

    def test_the_copy_of_the_tests_leaves_out_the_addons_suites_and_keeps_the_rest(self) -> None:
        self.write_test("addons/sample/test_sample.py", ADDON_TEST)
        self.write_test("fakes/addons/fake_command.py", "")
        self.write_test("__pycache__/test_core.cpython-314.pyc", "")
        copy = self.plugin.parent / "copy"

        core_alone.copy_tests_without_addon_suites(self.unit_tests, copy)

        files = sorted(path.relative_to(copy).as_posix() for path in copy.rglob("*") if path.is_file())
        self.assertEqual(files, ["fakes/addons/fake_command.py", "test_core.py"])


class ProofTest(SamplePluginTest):
    def test_a_core_that_needs_no_addon_passes_its_tests_and_scenarios(self) -> None:
        self.scenario("alone", [{"run": [sys.executable, "-c", IN_THE_COPY_ALONE, "{core_plugin}"]}])

        passed, output = self.proof()

        self.assertTrue(passed, output)
        self.assertIn("unit tests m2b without add-ons: 1 tests", output)
        self.assertIn("e2e stub alone: passed", output)

    def test_a_core_module_that_imports_the_addon_fails(self) -> None:
        self.write("src/m2b/__init__.py", "import m2b_sample\n")

        passed, output = self.proof()

        self.assertFalse(passed)
        self.assertIn("No module named 'm2b_sample'", output)

    def test_the_suite_of_an_addon_does_not_run(self) -> None:
        self.write_test("addons/sample/test_sample.py", ADDON_TEST)

        passed, output = self.proof()

        self.assertTrue(passed, output)
        self.assertIn("unit tests m2b without add-ons: 1 tests", output)

    def test_a_core_test_that_reads_a_file_of_the_addon_fails(self) -> None:
        self.write_test("test_core.py", CORE_TEST.format(check=READS_THE_ADDON))

        passed, output = self.proof()

        self.assertFalse(passed)
        self.assertIn("sample-setup", output)

    def test_beside_the_addon_both_faults_pass_which_is_what_the_copy_is_for(self) -> None:
        self.write("src/m2b/__init__.py", "import m2b_sample\n")
        self.write_test("test_core.py", CORE_TEST.format(check=READS_THE_ADDON))

        passed, output = self.proof(parts=())

        self.assertTrue(passed, output)

    def test_a_scenario_runs_against_the_copy_and_one_that_turns_an_addon_on_is_left_out(self) -> None:
        self.scenario("alone", [{"run": [sys.executable, "-c", IN_THE_COPY_ALONE, "{core_plugin}"]}])
        self.scenario("with-the-addon", [{"run": ["m2b", "addons", "on", "sample"], "exit": 7}])

        passed, output = self.proof()

        self.assertTrue(passed, output)
        self.assertIn("e2e: 1 of 1 scenarios passed", output)
        self.assertNotIn("with-the-addon", output)

    def test_a_scenario_that_fails_against_the_copy_fails_the_proof(self) -> None:
        self.scenario("needs-the-addon", [{"run": [sys.executable, "-c", "import sys; sys.exit(3)"]}])

        passed, output = self.proof()

        self.assertFalse(passed)
        self.assertIn("e2e stub needs-the-addon: FAILED", output)

    def test_the_command_fails_when_one_of_the_two_runs_failed(self) -> None:
        for exits, status in (((0, 0), 0), ((1, 0), 1), ((0, 1), 1)):
            runs = [subprocess.CompletedProcess([], code, "", "") for code in exits]
            with self.subTest(exits=exits), mock.patch.object(core_alone, "prove_core_alone", return_value=runs):
                self.assertEqual(core_alone.main(self.plugin, self.unit_tests, [SAMPLE], self.scenarios), status)

    def test_a_stale_list_fails_the_command_and_says_what_is_missing(self) -> None:
        (self.plugin / "bin" / "m2b-sample").unlink()
        errors = io.StringIO()

        with contextlib.redirect_stderr(errors):
            status = core_alone.main(self.plugin, self.unit_tests, [SAMPLE], self.scenarios)

        self.assertEqual(status, 1)
        self.assertIn("bin/m2b-sample", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
