from __future__ import annotations

import contextlib
import datetime
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar
from unittest import mock

from m2b.config.machine import parse_machine_config
from m2b.curate import model, runner
from m2b.paths import MachinePaths
from m2b.store.base import DEFAULT_FETCH_TIMEOUT_SECONDS

from repo_tools import e2e


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


class ScenarioTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        root = Path(self._temp.name)
        self.scenarios = root / "scenarios"
        self.scenario = self.scenarios / "sample"
        (self.scenario / "given" / "inbox").mkdir(parents=True)
        (self.scenario / "given" / "inbox" / "note.md").write_text("Dana likes maps.\n", encoding="utf-8")
        self.real_home = root / "real-home"
        self.environ = {"PATH": "/usr/bin:/bin", "M2B_HOME": str(self.real_home)}

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _given_steps(self, steps: list[dict[str, Any]]) -> None:
        _write_json(self.scenario / "steps.json", {"steps": steps})

    def _expect(self, files: dict[str, str]) -> None:
        _write_json(self.scenario / "expect.json", {"store_files": files})

    def _python_step(self, code: str, **extra: Any) -> dict[str, Any]:
        return {"run": [sys.executable, "-c", code], **extra}

    def test_an_unchanged_store_passes(self) -> None:
        self._given_steps([])
        self._expect({"inbox/note.md": "Dana likes maps.\n"})

        result = e2e.run_scenario(self.scenario, self.environ)

        self.assertTrue(result.passed, result.problems)

    def test_steps_see_an_isolated_home_with_a_test_config_for_the_scenario_store(self) -> None:
        code = (
            "import json, os, pathlib\n"
            "home = pathlib.Path(os.environ['M2B_HOME'])\n"
            "config = json.loads((home / '.config/m2b/config.json').read_text())\n"
            "store = pathlib.Path(config['store']['path'])\n"
            "(store / 'inbox/seen.md').write_text(home.parent.name.startswith('sb-test-') and 'isolated' or 'shared')\n"
        )
        self._given_steps([self._python_step(code)])
        self._expect({"inbox/note.md": "Dana likes maps.\n", "inbox/seen.md": "isolated"})

        result = e2e.run_scenario(self.scenario, self.environ)

        self.assertTrue(result.passed, result.problems)

    def test_a_store_that_differs_from_the_expectation_is_reported(self) -> None:
        self._given_steps([self._python_step("pass")])
        self._expect({"inbox/other.md": "x\n", "inbox/note.md": "Dana likes tea.\n"})

        result = e2e.run_scenario(self.scenario, self.environ)

        self.assertFalse(result.passed)
        joined = "\n".join(result.problems)
        self.assertIn("missing in store: inbox/other.md", joined)
        self.assertIn("content differs: inbox/note.md", joined)

    def test_hidden_files_are_not_part_of_the_end_state(self) -> None:
        (self.scenario / "given" / ".hidden-temp").write_text("x", encoding="utf-8")
        self._given_steps([])
        self._expect({"inbox/note.md": "Dana likes maps.\n"})

        self.assertTrue(e2e.run_scenario(self.scenario, self.environ).passed)

    def test_a_step_with_an_unexpected_exit_code_fails_the_scenario(self) -> None:
        self._given_steps([self._python_step("import sys; sys.exit(3)", exit=0)])
        self._expect({"inbox/note.md": "Dana likes maps.\n"})

        result = e2e.run_scenario(self.scenario, self.environ)

        self.assertIn("exit 3, expected 0", result.problems[0])

    def test_a_step_whose_output_does_not_match_its_pattern_fails_the_scenario(self) -> None:
        self._given_steps(
            [
                self._python_step("print('Due within 7 days:')", stdout="Due within 7 days:"),
                self._python_step("print('Later:')", stdout="Due within 7 days:"),
            ]
        )
        self._expect({"inbox/note.md": "Dana likes maps.\n"})

        result = e2e.run_scenario(self.scenario, self.environ)

        self.assertEqual(len(result.problems), 1)
        self.assertIn("step 2", result.problems[0])
        self.assertIn("does not match", result.problems[0])

    def test_the_model_runner_replays_the_scenarios_model_actions_under_its_rules(self) -> None:
        code = (
            "import json, os, pathlib, subprocess\n"
            "home = pathlib.Path(os.environ['M2B_HOME'])\n"
            "store = json.loads((home / '.config/m2b/config.json').read_text())['store']['path']\n"
            "subprocess.run([os.environ['M2B_MODEL_RUNNER'], '-p', '/m2b:x', '--allowedTools',\n"
            "                f'Edit(/{store}/inbox/**)'], check=True)\n"
        )
        steps = {
            "model": {
                "actions": [
                    {"tool": "Write", "file_path": "<store>/inbox/allowed.md", "content": "in\n"},
                    {"tool": "Write", "file_path": "<store>/memory/denied.md", "content": "out\n"},
                ]
            },
            "steps": [self._python_step(code)],
        }
        _write_json(self.scenario / "steps.json", steps)
        self._expect({"inbox/note.md": "Dana likes maps.\n", "inbox/allowed.md": "in\n"})

        result = e2e.run_scenario(self.scenario, self.environ)

        self.assertTrue(result.passed, result.problems)

    def test_without_a_model_script_the_runner_is_still_the_stub(self) -> None:
        code = "import os, subprocess; subprocess.run([os.environ['M2B_MODEL_RUNNER'], '-p', '/m2b:x'], check=True)"
        self._given_steps([self._python_step(code, stdout='"type": "result"')])
        self._expect({"inbox/note.md": "Dana likes maps.\n"})

        result = e2e.run_scenario(self.scenario, self.environ)

        self.assertTrue(result.passed, result.problems)

    def test_a_value_saved_from_one_steps_output_is_put_into_later_arguments(self) -> None:
        write = (
            "import json, os, pathlib, sys\n"
            "home = pathlib.Path(os.environ['M2B_HOME'])\n"
            "store = pathlib.Path(json.loads((home / '.config/m2b/config.json').read_text())['store']['path'])\n"
            "(store / 'inbox/seen.md').write_text(sys.argv[1])\n"
        )
        self._given_steps(
            [
                self._python_step("print('the id is 0a1b2c')", save={"task": "id is ([0-9a-f]+)"}),
                {"run": [sys.executable, "-c", write, "done {task}"]},
            ]
        )
        self._expect({"inbox/note.md": "Dana likes maps.\n", "inbox/seen.md": "done 0a1b2c"})

        result = e2e.run_scenario(self.scenario, self.environ)

        self.assertTrue(result.passed, result.problems)

    def test_core_plugin_in_an_argument_is_the_core_plugin_folder(self) -> None:
        write = (
            "import json, os, pathlib, sys\n"
            "home = pathlib.Path(os.environ['M2B_HOME'])\n"
            "store = pathlib.Path(json.loads((home / '.config/m2b/config.json').read_text())['store']['path'])\n"
            "(store / 'inbox/seen.md').write_text(sys.argv[1])\n"
        )
        self._given_steps([{"run": [sys.executable, "-c", write, "{core_plugin}"]}])
        self._expect({"inbox/note.md": "Dana likes maps.\n", "inbox/seen.md": str(e2e.CORE_PLUGIN)})

        result = e2e.run_scenario(self.scenario, self.environ)

        self.assertTrue(result.passed, result.problems)

    def test_a_value_that_cannot_be_saved_fails_the_scenario(self) -> None:
        self._given_steps([self._python_step("print('nothing here')", save={"task": "id is (\\w+)"})])
        self._expect({"inbox/note.md": "Dana likes maps.\n"})

        result = e2e.run_scenario(self.scenario, self.environ)

        self.assertIn("cannot save task", result.problems[0])

    def test_the_sandbox_is_removed_afterwards(self) -> None:
        self._given_steps([self._python_step("import os; print(os.environ['M2B_HOME'])")])
        self._expect({"inbox/note.md": "Dana likes maps.\n"})
        before = set(Path(tempfile.gettempdir()).glob("sb-test-e2e-sample-*"))

        e2e.run_scenario(self.scenario, self.environ)

        self.assertEqual(set(Path(tempfile.gettempdir()).glob("sb-test-e2e-sample-*")), before)

    def test_main_runs_every_scenario_and_fails_when_one_fails(self) -> None:
        self._given_steps([])
        self._expect({"inbox/note.md": "changed\n"})

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = e2e.main(["--level", "stub", "--scenarios", str(self.scenarios)])

        self.assertEqual(code, e2e.EXIT_FAILED)
        self.assertIn("0 of 1 scenarios passed", output.getvalue())

    def test_an_unknown_scenario_name_is_a_usage_error(self) -> None:
        self._given_steps([])
        self._expect({})

        with contextlib.redirect_stderr(io.StringIO()):
            code = e2e.main(["--level", "stub", "--scenarios", str(self.scenarios), "missing"])

        self.assertEqual(code, e2e.EXIT_USAGE)


class RealStoreGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.real_store = self.root / "Second Brain"
        self.real_store.mkdir()
        self.real_machine = MachinePaths(self.root / "real-home")
        self._write_real_config(str(self.real_store))

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _write_real_config(self, store_path: str) -> None:
        self.real_machine.config_file.parent.mkdir(parents=True, exist_ok=True)
        _write_json(
            self.real_machine.config_file,
            {"version": 1, "machine_id": "real", "store": {"backend": "folder", "path": store_path}},
        )

    def test_the_real_store_itself_is_refused(self) -> None:
        with self.assertRaises(e2e.RealStoreError):
            e2e.refuse_real_store(self.real_store, self.real_machine)

    def test_a_folder_inside_the_real_store_is_refused(self) -> None:
        inside = self.real_store / "inbox"
        inside.mkdir()

        with self.assertRaises(e2e.RealStoreError):
            e2e.refuse_real_store(inside, self.real_machine)

    def test_a_folder_holding_the_real_store_is_refused(self) -> None:
        with self.assertRaises(e2e.RealStoreError):
            e2e.refuse_real_store(self.root, self.real_machine)

    def test_a_tilde_in_the_real_config_means_the_real_machine_home(self) -> None:
        self._write_real_config("~/notes")

        with self.assertRaises(e2e.RealStoreError):
            e2e.refuse_real_store(self.real_machine.home / "notes", self.real_machine)

    def test_a_separate_folder_is_allowed(self) -> None:
        other = self.root / "sb-test-store"
        other.mkdir()

        e2e.refuse_real_store(other, self.real_machine)

    def test_no_real_config_means_nothing_to_protect(self) -> None:
        e2e.refuse_real_store(self.real_store, MachinePaths(self.root / "empty-home"))

    def test_an_unreadable_real_config_is_refused(self) -> None:
        self.real_machine.config_file.write_text("{not json", encoding="utf-8")

        with self.assertRaises(e2e.RealStoreError):
            e2e.refuse_real_store(self.root / "elsewhere", self.real_machine)

    def test_a_scenario_is_refused_when_the_real_config_names_its_store(self) -> None:
        scenario = self.root / "scenarios" / "sample"
        (scenario / "given").mkdir(parents=True)
        (scenario / "given" / "note.md").write_text("Dana\n", encoding="utf-8")
        _write_json(scenario / "steps.json", {"steps": []})
        _write_json(scenario / "expect.json", {"store_files": {}})
        self._write_real_config(tempfile.gettempdir())

        with mock.patch("repo_tools.e2e.shutil.copytree") as copy, self.assertRaises(e2e.RealStoreError):
            e2e.run_scenario(scenario, {"M2B_HOME": str(self.real_machine.home), "PATH": "/usr/bin"})

        copy.assert_not_called()


class IsolatedConfigTest(unittest.TestCase):
    def test_the_harness_config_passes_the_products_validation(self) -> None:
        store = Path("/tmp/sb-test-store")

        config = parse_machine_config(e2e.isolated_machine_config(store), Path("/tmp/sb-test-home"))

        self.assertEqual(config.store.path, store)
        self.assertTrue(config.machine_id.startswith("sb-test-"))


CAPTURE_PATTERN = {"path": "inbox/*-cli-*.md", "content": r"---\ncreated: .+\nsource: cli\n---\nDana likes maps\.\n"}


class StorePatternTest(unittest.TestCase):
    """Captures and tasks get generated names, so a scenario can expect a file by pattern."""

    def test_a_file_matching_path_and_content_passes(self) -> None:
        actual = {"inbox/20261107T101500Z-cli-3f9a.md": "---\ncreated: x\nsource: cli\n---\nDana likes maps.\n"}

        self.assertEqual(e2e.compare_store({}, actual, [CAPTURE_PATTERN]), [])

    def test_content_that_does_not_match_is_reported(self) -> None:
        actual = {"inbox/20261107T101500Z-cli-3f9a.md": "---\ncreated: x\nsource: claude\n---\nDana likes maps.\n"}

        problems = e2e.compare_store({}, actual, [CAPTURE_PATTERN])

        self.assertTrue(problems)
        self.assertTrue(all("inbox/" in problem for problem in problems))
        self.assertIn("source: claude", problems[0], "the content that failed to match is shown")

    def test_a_pattern_without_a_file_is_missing_and_a_second_match_is_unexpected(self) -> None:
        text = "---\ncreated: x\nsource: cli\n---\nDana likes maps.\n"
        two = {"inbox/20261107T101500Z-cli-3f9a.md": text, "inbox/20261107T101500Z-cli-0b1c.md": text}

        self.assertEqual(len(e2e.compare_store({}, {}, [CAPTURE_PATTERN])), 1)
        self.assertEqual(len(e2e.compare_store({}, two, [CAPTURE_PATTERN])), 1)

    def test_exact_files_and_patterns_together_cover_the_store(self) -> None:
        actual = {
            "inbox/sample.md": "Alex.\n",
            "inbox/20261107T101500Z-cli-3f9a.md": "---\ncreated: x\nsource: cli\n---\nDana likes maps.\n",
        }

        self.assertEqual(e2e.compare_store({"inbox/sample.md": "Alex.\n"}, actual, [CAPTURE_PATTERN]), [])


class InvariantTest(unittest.TestCase):
    """The model level checks what must hold, not the wording the model chose."""

    FILES: ClassVar[dict[str, str]] = {
        "memory/MEMORY.md": "# Memory\n\n## Facts\n\n- Alex prefers green tea (alex.md)\n\n## Current\n",
        "memory/alex.md": "# Alex\n\n- Green tea.\n\n## Evidence\n\n- [[20261107T091500Z-cli-a1b2.md]]\n",
        "corpus/2026/11/20261107T091500Z-cli-a1b2.md": "---\ncurated: true\n---\ntea\n",
        "tasks/aaaaaaaaaaaa.md": "---\nstatus: open\n---\nCall Dana\nm2b:capture 20261107T091500Z-cli-a1b2.md call\n",
        "state/core/last-run.json": json.dumps(
            {"state": "succeeded", "findings": [{"step": "ingest", "kind": "info", "text": "x"}]}
        ),
    }

    def check(self, invariant: dict[str, Any]) -> list[str]:
        return e2e.check_invariants([invariant], self.FILES)

    def test_count_matches_by_glob_and_content(self) -> None:
        self.assertEqual(self.check({"count": 1, "glob": "corpus/*/*/*-cli-*.md"}), [])
        self.assertEqual(self.check({"count": 1, "glob": "tasks/*.md", "content": "m2b:capture \\S+ call"}), [])
        self.assertEqual(len(self.check({"count": 2, "glob": "tasks/*.md"})), 1)

    def test_once_counts_occurrences_across_the_files(self) -> None:
        link = "\\[\\[\\d{8}T\\d{6}Z-cli-[0-9a-f]{4}\\.md\\]\\]"
        self.assertEqual(self.check({"once": link, "glob": "memory/*.md"}), [])
        doubled = {**self.FILES, "memory/dana.md": "- [[20261107T091500Z-cli-a1b2.md]]\n"}
        self.assertEqual(len(e2e.check_invariants([{"once": link, "glob": "memory/*.md"}], doubled)), 1)

    def test_matches_searches_one_file_and_a_missing_file_fails(self) -> None:
        self.assertEqual(self.check({"matches": "(?i)green tea", "path": "memory/MEMORY.md"}), [])
        self.assertEqual(len(self.check({"matches": "tea", "path": "memory/none.md"})), 1)

    def test_the_run_state_and_no_denial_come_from_the_run_record(self) -> None:
        self.assertEqual(self.check({"run_state": "succeeded"}), [])
        self.assertEqual(self.check({"no_denials": True}), [])
        finding = {"step": "lint", "kind": "action", "text": "the model step m2b:lint was denied Bash: rm"}
        record = json.dumps({"state": "failed", "findings": [finding]})
        denied = {**self.FILES, "state/core/last-run.json": record}
        problems = e2e.check_invariants([{"run_state": "succeeded"}, {"no_denials": True}], denied)
        self.assertEqual(len(problems), 2)

    def test_an_empty_folder_named_by_a_saved_value_passes_and_one_with_a_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "memory"
            invariant = {"empty_folder": "{auto_memory}"}
            self.assertEqual(e2e.check_invariants([invariant], self.FILES, {"auto_memory": str(folder)}), [])
            folder.mkdir()
            (folder / "kim.md").write_text("x", encoding="utf-8")
            problems = e2e.check_invariants([invariant], self.FILES, {"auto_memory": str(folder)})
            self.assertEqual(len(problems), 1)
            self.assertIn("kim.md", problems[0])

    def test_an_empty_folder_without_its_saved_value_is_a_problem(self) -> None:
        self.assertEqual(len(self.check({"empty_folder": "{auto_memory}"})), 1)

    def test_an_unknown_invariant_is_a_problem_not_a_pass(self) -> None:
        self.assertEqual(len(self.check({"whatever": 1})), 1)


class ModelLevelTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        root = Path(self._temp.name)
        self.scenarios = root / "scenarios"
        self.sandboxes = root / "sandboxes"
        self.sandboxes.mkdir()
        for name, with_model in (("with-model", True), ("stub-only", False)):
            folder = self.scenarios / name
            (folder / "given").mkdir(parents=True)
            (folder / "given" / "note.md").write_text("x\n", encoding="utf-8")
            _write_json(folder / "steps.json", {"steps": []})
            _write_json(folder / "expect.json", {"store_files": {"note.md": "x\n"}})
            if with_model:
                probe = "import os; print(os.environ.get('M2B_MODEL_RUNNER', 'real'))"
                steps = [{"run": [sys.executable, "-c", probe], "stdout": "real"}]
                _write_json(folder / "model.json", {"steps": steps, "invariants": [{"count": 1, "glob": "note.md"}]})
        self.environ = {"PATH": "/usr/bin:/bin", "M2B_HOME": str(root / "real-home"), "M2B_MODEL_RUNNER": "/tmp/stub"}

    def test_the_model_level_runs_only_scenarios_with_a_model_file_without_the_stub_in_the_given_folder(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.dict("os.environ", self.environ, clear=True):
            code = e2e.main(
                ["--level", "model", "--scenarios", str(self.scenarios), "--sandbox-root", str(self.sandboxes)]
            )

        self.assertEqual(code, e2e.EXIT_PASSED, out.getvalue())
        self.assertIn("e2e model with-model: passed", out.getvalue())
        self.assertNotIn("stub-only", out.getvalue())
        self.assertEqual(list(self.sandboxes.iterdir()), [])

    def test_a_value_saved_by_a_model_step_reaches_the_invariants(self) -> None:
        folder = Path(self._temp.name) / "auto-memory"
        folder.mkdir()
        (folder / "kim.md").write_text("x", encoding="utf-8")
        steps = [{"run": [sys.executable, "-c", f"print('auto: {folder}')"], "save": {"auto_memory": "auto: (\\S+)"}}]
        _write_json(
            self.scenarios / "with-model" / "model.json",
            {"steps": steps, "invariants": [{"empty_folder": "{auto_memory}"}]},
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.dict("os.environ", self.environ, clear=True):
            code = e2e.main(
                ["--level", "model", "--scenarios", str(self.scenarios), "--sandbox-root", str(self.sandboxes)]
            )

        self.assertEqual(code, e2e.EXIT_FAILED, out.getvalue())
        self.assertIn("kim.md", out.getvalue())

    def test_a_failed_invariant_fails_the_scenario(self) -> None:
        _write_json(
            self.scenarios / "with-model" / "model.json", {"steps": [], "invariants": [{"count": 2, "glob": "note.md"}]}
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.dict("os.environ", self.environ, clear=True):
            code = e2e.main(
                ["--level", "model", "--scenarios", str(self.scenarios), "--sandbox-root", str(self.sandboxes)]
            )

        self.assertEqual(code, e2e.EXIT_FAILED)
        self.assertIn("FAILED", out.getvalue())

    def test_a_named_scenario_without_a_model_file_is_a_usage_error_not_a_pass(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        with (
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
            mock.patch.dict("os.environ", self.environ, clear=True),
        ):
            code = e2e.main(["--level", "model", "--scenarios", str(self.scenarios), "stub-only"])

        self.assertEqual(code, e2e.EXIT_USAGE)
        self.assertIn("stub-only", err.getvalue())

    def test_a_tree_where_no_scenario_has_a_model_file_is_a_usage_error(self) -> None:
        (self.scenarios / "with-model" / "model.json").unlink()
        err = io.StringIO()
        with contextlib.redirect_stderr(err), mock.patch.dict("os.environ", self.environ, clear=True):
            code = e2e.main(["--level", "model", "--scenarios", str(self.scenarios)])

        self.assertEqual(code, e2e.EXIT_USAGE)
        self.assertIn("model.json", err.getvalue())

    def test_the_model_level_gives_each_model_step_a_timeout_the_harness_outlasts(self) -> None:
        config = e2e.isolated_machine_config(Path("/tmp/sb-test-store"), level=e2e.MODEL)
        minutes = config["curation"]["model_timeout_minutes"]

        step = datetime.timedelta(minutes=minutes, seconds=model.DEFAULT_GRACE_SECONDS)
        fetch = datetime.timedelta(seconds=DEFAULT_FETCH_TIMEOUT_SECONDS)
        bound = fetch + step * runner.MODEL_STEPS + runner.CODE_STEPS_MARGIN
        self.assertLess(bound.total_seconds(), e2e.MODEL_STEP_TIMEOUT_SECONDS)
        self.assertNotIn("curation", e2e.isolated_machine_config(Path("/tmp/sb-test-store")))


class AppleLevelTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        root = Path(self._temp.name)
        self.scenarios = root / "scenarios"
        self.drive = root / "drive"
        self.drive.mkdir()
        folder = self.scenarios / "sample"
        (folder / "given").mkdir(parents=True)
        (folder / "given" / "note.md").write_text("x\n", encoding="utf-8")
        config = "pathlib.Path(os.environ['M2B_HOME'], '.config/m2b/config.json')"
        probe = f"import json, os, pathlib; print(json.loads({config}.read_text())['store'])"
        _write_json(folder / "steps.json", {"steps": [{"run": [sys.executable, "-c", probe], "stdout": "icloud"}]})
        _write_json(folder / "expect.json", {"store_files": {"note.md": "x\n"}})
        self.environ = {"PATH": "/usr/bin:/bin", "M2B_HOME": str(root / "real-home"), "M2B_IT": "1"}

    def main(self, environ: dict[str, str], platform: str = "darwin") -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with (
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
            mock.patch.dict("os.environ", environ, clear=True),
            mock.patch("repo_tools.e2e.icloud_drive", return_value=self.drive),
            mock.patch("repo_tools.e2e.sys.platform", platform),
        ):
            code = e2e.main(["--level", "apple", "--scenarios", str(self.scenarios)])
        return code, out.getvalue(), err.getvalue()

    def test_the_apple_level_runs_the_stub_scenarios_on_an_icloud_store_in_a_test_folder_and_removes_it(self) -> None:
        code, out, err = self.main(self.environ)

        self.assertEqual(code, e2e.EXIT_PASSED, out + err)
        self.assertIn("e2e apple sample: passed", out)
        self.assertEqual(list(self.drive.iterdir()), [])

    def test_the_store_folder_lies_in_icloud_drive_and_starts_with_sb_test(self) -> None:
        location = e2e.scenario_store(e2e.APPLE, "E1-capture", Path("/tmp/sandbox"), self.drive)

        self.assertEqual(location.backend, "icloud")
        self.assertEqual(location.path.parent, self.drive)
        self.assertTrue(location.path.name.startswith("sb-test-e2e-E1-capture-"))
        self.assertEqual(
            e2e.scenario_store(e2e.STUB, "E1", Path("/tmp/sandbox"), self.drive).path, Path("/tmp/sandbox/store")
        )

    def test_without_m2b_it_or_off_macos_the_apple_level_refuses(self) -> None:
        for environ, platform in (({**self.environ, "M2B_IT": "0"}, "darwin"), (self.environ, "linux")):
            with self.subTest(platform=platform, it=environ["M2B_IT"]):
                code, _, err = self.main(environ, platform)
                self.assertEqual(code, e2e.EXIT_USAGE)
                self.assertIn("M2B_IT=1", err)
        self.assertEqual(list(self.drive.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
