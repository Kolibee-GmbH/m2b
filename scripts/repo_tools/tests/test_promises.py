"""The regression of m2b's promises: the catalog, the runs of each case and the report."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from unittest import mock

from repo_tools import e2e, promises
from repo_tools.promises import Case, Run

CATALOG = """# Promises

Some prose.

| # | Promise | Against Claude Code alone | Cases | Checked in part by |
|---|---|---|---|---|
| 1 | Say it once, every project knows it | compared | `E1-recall` | `recall` |
| 2 | A sentence becomes a task | not compared | open | |
| 7 | Nothing from another project | not compared | `no-leak`, `leak-a` / `leak-b` / `leak-c` | |

More prose.
"""
PASS, FAIL = Run(True), Run(False, "the answer did not name the pot")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class Tree:
    """A repository of invented scenarios and eval cases for one test."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.catalog = root / "docs" / "promises.md"
        self.scenarios = root / "tests" / "e2e"
        self.evals = root / "evals"
        self.catalog.parent.mkdir(parents=True)
        self.catalog.write_text(CATALOG, encoding="utf-8")
        _write_json(self.scenarios / "E1-recall" / "model.json", {"steps": [], "invariants": []})
        for name in ("recall", "no-leak", "leak-a", "leak-b", "leak-c"):
            (self.evals / name).mkdir(parents=True)
            (self.evals / name / "prompt.md").write_text("---\nname: x\n---\nQ?\n", encoding="utf-8")

    def read(self) -> list[promises.Promise]:
        return promises.read_catalog(self.catalog, self.scenarios, [self.evals])


class CatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.tree = Tree(Path(self._temp.name))

    def test_each_row_of_the_table_is_a_promise_with_its_cases_and_whether_it_is_compared(self) -> None:
        read = self.tree.read()

        self.assertEqual([promise.number for promise in read], [1, 2, 7])
        self.assertEqual(read[0].text, "Say it once, every project knows it")
        self.assertTrue(read[0].compared)
        self.assertEqual(read[0].cases, (Case(("E1-recall",), promises.SCENARIO),))
        self.assertEqual(read[1].cases, ())
        self.assertFalse(read[2].compared)
        self.assertEqual(
            read[2].cases,
            (Case(("no-leak",), promises.EVAL), Case(("leak-a", "leak-b", "leak-c"), promises.EVAL)),
        )

    def test_the_page_lists_the_eight_promises_each_with_cases_that_exist(self) -> None:
        page = promises.read_catalog(promises.CATALOG, e2e.SCENARIO_ROOT, [promises.EVALS, promises.WORDING_EVALS])

        self.assertEqual([promise.number for promise in page], list(range(1, 9)))
        self.assertEqual([promise.number for promise in page if not promise.cases], [])

    def test_a_case_that_names_neither_a_scenario_nor_an_eval_is_an_error(self) -> None:
        self.tree.catalog.write_text(CATALOG.replace("`E1-recall`", "`E9-nothing`"), encoding="utf-8")

        with self.assertRaisesRegex(promises.CatalogError, "E9-nothing"):
            self.tree.read()

    def test_a_scenario_without_a_model_file_is_no_case(self) -> None:
        (self.tree.scenarios / "E1-recall" / "model.json").unlink()

        with self.assertRaisesRegex(promises.CatalogError, "E1-recall"):
            self.tree.read()

    def test_a_case_of_two_evals_is_an_error_three_are_the_three_wordings(self) -> None:
        self.tree.catalog.write_text(CATALOG.replace("`leak-a` / `leak-b` / `leak-c`", "`leak-a` / `leak-b`"))

        with self.assertRaisesRegex(promises.CatalogError, "three"):
            self.tree.read()

    def test_a_page_without_the_table_is_an_error(self) -> None:
        self.tree.catalog.write_text("# Promises\n\nNothing here.\n", encoding="utf-8")

        with self.assertRaisesRegex(promises.CatalogError, "table"):
            self.tree.read()


class VerdictTest(unittest.TestCase):
    def result(
        self, with_m2b: Sequence[Run], without: Sequence[Run] = (), problem: str | None = None
    ) -> promises.CaseResult:
        return promises.CaseResult(Case(("E1-recall",), promises.SCENARIO), list(with_m2b), list(without), problem)

    def test_a_case_holds_when_all_three_runs_with_m2b_pass(self) -> None:
        self.assertEqual(self.result([PASS] * 3).verdict(compared=False), promises.HELD)

    def test_a_case_that_passes_once_or_twice_is_unsteady_and_never_passes_is_broken(self) -> None:
        self.assertEqual(self.result([PASS, FAIL, PASS]).verdict(compared=False), promises.UNSTEADY)
        self.assertEqual(self.result([FAIL] * 3).verdict(compared=False), promises.BROKEN)

    def test_a_compared_case_may_pass_without_m2b_at_most_once(self) -> None:
        self.assertEqual(self.result([PASS] * 3, [PASS, FAIL, FAIL]).verdict(compared=True), promises.HELD)
        self.assertEqual(self.result([PASS] * 3, [PASS, PASS, FAIL]).verdict(compared=True), promises.NO_DIFFERENCE)

    def test_a_case_whose_wordings_do_not_hold_a_promise_does_not_hold(self) -> None:
        self.assertEqual(self.result([PASS] * 3, problem="one wording").verdict(compared=False), promises.WORDINGS)

    def test_a_promise_without_a_case_is_open_and_one_holds_only_when_every_case_does(self) -> None:
        promise = promises.Promise(1, "x", False, ())
        self.assertEqual(promises.promise_verdict(promise, []), promises.OPEN)
        held, broken = self.result([PASS] * 3), self.result([FAIL] * 3)
        promise = promises.Promise(1, "x", False, (held.case, broken.case))
        self.assertEqual(promises.promise_verdict(promise, [held, held]), promises.HELD)
        self.assertEqual(promises.promise_verdict(promise, [held, broken]), promises.BROKEN)


class RunCaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.calls: list[tuple[str, int, str]] = []

    def scenario(self, folder: Path, wording: int, arm: str) -> Run:
        self.calls.append((folder.name, wording, arm))
        return PASS if arm == e2e.WITH else FAIL

    def evals(self, name: str, runs: int, compared: bool) -> tuple[list[Run], list[Run]]:
        self.calls.append((name, runs, str(compared)))
        return [PASS] * runs, ([FAIL] * runs if compared else [])

    def run_case(self, case: Case, compared: bool, deadline: float | None = None) -> promises.CaseResult:
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / case.names[0]
            wordings = [{"say": "a"}, {"say": "b", "language": "de"}, {"say": "c"}]
            _write_json(folder / "model.json", {"wordings": wordings, "steps": [{"session": [], "turns": ["{say}"]}]})
            runners = promises.Runners(self.scenario, self.evals)
            return promises.run_case(case, compared, Path(root), runners, deadline)

    def test_a_scenario_runs_in_each_of_its_three_wordings_with_m2b_and_without_where_compared(self) -> None:
        result = self.run_case(Case(("E1-recall",), promises.SCENARIO), compared=True)

        expected = [("E1-recall", k, arm) for arm in (e2e.WITH, e2e.WITHOUT) for k in range(3)]
        self.assertEqual(self.calls, expected)
        self.assertEqual(result.verdict(compared=True), promises.HELD)

    def test_a_promise_that_is_not_compared_runs_no_arm_without_m2b(self) -> None:
        result = self.run_case(Case(("E1-recall",), promises.SCENARIO), compared=False)

        self.assertEqual({arm for _, _, arm in self.calls}, {e2e.WITH})
        self.assertEqual(result.without_m2b, [])

    def test_an_eval_case_alone_runs_three_times_and_is_one_wording(self) -> None:
        result = self.run_case(Case(("no-leak",), promises.EVAL), compared=False)

        self.assertEqual(self.calls, [("no-leak", 3, "False")])
        self.assertEqual(result.verdict(compared=False), promises.WORDINGS)

    def test_three_eval_cases_run_once_each_one_per_wording(self) -> None:
        result = self.run_case(Case(("leak-a", "leak-b", "leak-c"), promises.EVAL), compared=True)

        self.assertEqual([call[:2] for call in self.calls], [("leak-a", 1), ("leak-b", 1), ("leak-c", 1)])
        self.assertEqual(len(result.with_m2b), 3)
        self.assertEqual(result.verdict(compared=True), promises.HELD)

    def test_a_run_that_would_start_after_the_deadline_is_not_run_and_does_not_pass(self) -> None:
        result = self.run_case(Case(("E1-recall",), promises.SCENARIO), compared=False, deadline=0.0)

        self.assertEqual(self.calls, [])
        self.assertEqual(result.verdict(compared=False), promises.INCOMPLETE)
        self.assertIn("time", result.with_m2b[0].evidence)

    def test_a_case_whose_runs_without_m2b_show_nothing_does_not_hold(self) -> None:
        ran = [PASS] * 3
        result = promises.CaseResult(Case(("E1-recall",), promises.SCENARIO), ran, [promises._out_of_time()] * 3, None)

        self.assertEqual(result.verdict(compared=True), promises.INCOMPLETE)


class ControlTest(unittest.TestCase):
    """A run against Claude Code alone counts only once its control shows Claude Code did its part."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        self.environ = {"PATH": "/usr/bin:/bin", "M2B_HOME": str(self.root / "real-home")}
        self.environ["CLAUDE_CONFIG_DIR"] = str(self.root / "real-claude")

    def run_without_m2b(self, control_exit: int) -> Run:
        steps = [
            {"run": [sys.executable, "-c", f"raise SystemExit({control_exit})"], "arm": "without", "control": True},
            {"run": [sys.executable, "-c", "raise SystemExit(1)"]},
        ]
        _write_json(self.root / "E1" / "model.json", {"steps": steps, "invariants": []})
        runner = promises.scenario_runner(self.environ, {e2e.TOKEN_VARIABLE: "sb-test"}, self.root / "sandboxes")
        return runner(self.root / "E1", 0, e2e.WITHOUT)

    def test_a_run_whose_control_fails_shows_nothing(self) -> None:
        run = self.run_without_m2b(control_exit=1)

        self.assertFalse(run.shows)
        self.assertIn("control", run.evidence)

    def test_a_run_whose_control_passes_counts_its_failure_as_claude_code_alone_failing(self) -> None:
        run = self.run_without_m2b(control_exit=0)

        self.assertTrue(run.shows)
        self.assertFalse(run.passed)


class ReportTest(unittest.TestCase):
    def test_the_report_names_each_promise_each_run_what_broke_and_the_versions(self) -> None:
        recall = promises.Promise(1, "Say it once", True, (Case(("E1-recall",), promises.SCENARIO),))
        task = promises.Promise(2, "A sentence becomes a task", False, ())
        result = promises.CaseResult(recall.cases[0], [PASS, FAIL, PASS], [FAIL, FAIL, FAIL], None)
        versions = promises.Versions("2.1.330 (Claude Code)", ("claude-haiku-5-5",), "abc1234")

        text = promises.report([(recall, [result]), (task, [])], versions)

        self.assertIn("1 unsteady", text)
        self.assertIn("2 open", text)
        self.assertIn("with ✓✗✓", text)
        self.assertIn("without ✗✗✗", text)
        self.assertIn("E1-recall with m2b, run 2 (wording 2): the answer did not name the pot", text)
        self.assertIn("2.1.330", text)
        self.assertIn("claude-haiku-5-5", text)
        self.assertIn("abc1234", text)
        self.assertIn("0 of 2 promises held", text)

    def test_a_run_without_m2b_that_shows_nothing_is_marked_apart_and_says_why(self) -> None:
        recall = promises.Promise(1, "Say it once", True, (Case(("E1-recall",), promises.SCENARIO),))
        blind = Run(False, "its control did not pass", shows=False)
        result = promises.CaseResult(recall.cases[0], [PASS] * 3, [FAIL, blind, FAIL], None)

        text = promises.report([(recall, [result])], promises.Versions("x", (), "y"))

        self.assertIn("without \u2717\u25cb\u2717", text)
        self.assertIn("E1-recall without m2b, run 2 (wording 2): its control did not pass", text)
        self.assertNotIn("without m2b, run 1", text)


class CommandTest(unittest.TestCase):
    """``scripts/promises`` end to end, against invented cases and a stand-in for ``claude``."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        self.tree = Tree(self.root)
        self.real_claude = self.root / "real-claude"
        self.environ = {
            "PATH": "/usr/bin:/bin",
            "M2B_HOME": str(self.root / "real-home"),
            "CLAUDE_CONFIG_DIR": str(self.real_claude),
            e2e.TOKEN_VARIABLE: "sb-test-token-value",
        }

    def given_scenario(self, script: dict[str, Any]) -> None:
        _write_json(self.tree.scenarios / "E1-recall" / "model.json", script)

    def run_command(self, *arguments: str, versions: promises.Versions | None = None) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()

        def evals(name: str, runs: int, compared: bool) -> tuple[list[Run], list[Run]]:
            return [PASS] * runs, [FAIL] * runs if compared else []

        with (
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
            mock.patch.dict("os.environ", self.environ, clear=True),
            mock.patch.object(e2e, "keychain_token", return_value=None),
            mock.patch.object(promises, "versions", return_value=versions or promises.Versions("x", (), "y")),
        ):
            code = promises.main(
                [
                    "--catalog",
                    str(self.tree.catalog),
                    "--scenarios",
                    str(self.tree.scenarios),
                    "--evals",
                    str(self.tree.evals),
                    "--sandbox-root",
                    str(self.root / "sandboxes"),
                    *arguments,
                ],
                eval_runner=evals,
            )
        return code, out.getvalue(), err.getvalue()

    def test_the_other_scenarios_are_the_model_scenarios_no_promise_names_and_need_no_account(self) -> None:
        _write_json(self.tree.scenarios / "E9-fence" / "model.json", {"steps": [], "invariants": []})
        _write_json(self.tree.scenarios / "E3-stub-only" / "steps.json", {"steps": []})
        del self.environ[e2e.TOKEN_VARIABLE]

        code, out, err = self.run_command("--other-scenarios")

        self.assertEqual((code, out, err), (promises.EXIT_HELD, "E9-fence\n", ""))

    def test_each_run_plays_its_wording_from_a_fresh_start_and_the_run_without_m2b_has_no_plugin(self) -> None:
        # The step passes when the wording reached it and a store of the run's own is empty at its
        # start; the stand-in for claude passes only with --plugin-dir, as m2b would answer.
        fresh = (
            "import os, sys; inbox = os.path.join(sys.argv[2], 'inbox'); "
            "assert not os.path.exists(inbox); os.makedirs(inbox); print(sys.argv[1])"
        )
        wordings = [{"say": "one"}, {"say": "zwei", "language": "de"}, {"say": "three"}]
        claude = self.root / "bin" / "claude"
        claude.parent.mkdir()
        claude.write_text('#!/bin/sh\ncase "$*" in *--plugin-dir*) exit 0;; esac\nexit 1\n', encoding="utf-8")
        claude.chmod(0o755)
        self.environ["PATH"] = f"{claude.parent}:/usr/bin:/bin"
        self.given_scenario(
            {
                "wordings": wordings,
                "steps": [
                    {"run": [sys.executable, "-c", fresh, "{say}", "{store}"], "stdout": "^{say}$"},
                    {"run": ["claude", "-p", "{say}", "--plugin-dir", "{core_plugin}"]},
                ],
                "invariants": [],
            }
        )

        code, out, _ = self.run_command("1")

        self.assertEqual(code, promises.EXIT_HELD, out)
        self.assertIn("1 held", out)
        self.assertIn("with ✓✓✓", out)
        self.assertIn("without ✗✗✗", out)
        self.assertNotIn("7 ", out)

    def test_a_promise_that_does_not_hold_fails_the_command_and_the_token_never_shows(self) -> None:
        leaky = "import os, sys; sys.exit('broke ' + os.environ['CLAUDE_CODE_OAUTH_TOKEN'])"
        wordings = [{"say": "a"}, {"say": "b", "language": "de"}, {"say": "c"}]
        self.given_scenario({"wordings": wordings, "steps": [{"run": [sys.executable, "-c", leaky]}], "invariants": []})

        code, out, err = self.run_command()

        self.assertEqual(code, promises.EXIT_NOT_HELD)
        self.assertIn("1 broken", out)
        self.assertIn("2 open", out)
        self.assertIn("7 too few wordings", out)
        self.assertNotIn("sb-test-token-value", out + err)
        self.assertIn("<token>", out)

    def test_without_an_account_the_command_stops_before_any_run(self) -> None:
        del self.environ[e2e.TOKEN_VARIABLE]

        code, out, err = self.run_command()

        self.assertEqual(code, promises.EXIT_USAGE)
        self.assertIn("claude setup-token", err)
        self.assertEqual(out, "")

    def test_a_number_the_catalog_does_not_have_is_a_usage_error(self) -> None:
        code, _, err = self.run_command("9")

        self.assertEqual(code, promises.EXIT_USAGE)
        self.assertIn("9", err)


# The one way a rewording checks more than its case: a leak in German would call the shed "Schuppen".
WORDING_GRADER_CHANGES = {"no-leak-de": {"no-names.md": ('|shed"', '|shed|Schuppen"')}}


def _graders(case: Path, changes: dict[str, tuple[str, str]] | None = None) -> dict[str, str]:
    """Each grader of an eval case by its name, with ``changes`` made: a name and (old, new)."""
    graders = {path.name: path.read_text(encoding="utf-8") for path in sorted((case / "graders").glob("*.md"))}
    for name, (old, new) in (changes or {}).items():
        graders[name] = graders[name].replace(old, new)
    return graders


class WordingEvalsTest(unittest.TestCase):
    """The second and third wording of a suite case run apart from the suite."""

    def test_each_wording_case_starts_as_the_case_it_rewords_and_checks_the_same(self) -> None:
        for folder in sorted(case.parent for case in promises.WORDING_EVALS.glob("*/case.yaml")):
            original = promises.EVALS / folder.name.rsplit("-", 1)[0]
            with self.subTest(case=folder.name):
                self.assertTrue(original.is_dir())
                self.assertIn(
                    f"evals/{original.name}/scaffold.sh", (folder / "scaffold.sh").read_text(encoding="utf-8")
                )
                self.assertEqual(_graders(folder), _graders(original, WORDING_GRADER_CHANGES.get(folder.name, {})))
                self.assertIn(f"name: {folder.name}\n", (folder / "prompt.md").read_text(encoding="utf-8"))

    def test_every_wording_case_is_one_of_the_three_wordings_of_a_case_of_the_catalog(self) -> None:
        catalog = promises.read_catalog(promises.CATALOG, e2e.SCENARIO_ROOT, [promises.EVALS, promises.WORDING_EVALS])
        named = {name for promise in catalog for case in promise.cases if len(case.names) == 3 for name in case.names}

        cases = {case.parent.name for case in promises.WORDING_EVALS.glob("*/case.yaml")}

        self.assertTrue(cases)
        self.assertLessEqual(cases, named)


class EvalRunnerTest(unittest.TestCase):
    """The eval cases run through ``claude plugin eval``, whose report says per arm which run passed."""

    def test_the_runs_of_each_arm_are_read_from_the_eval_report_with_their_models(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            trace = root / "trace.jsonl"
            trace.write_text(json.dumps({"type": "system", "subtype": "init", "model": "claude-haiku-5-5"}) + "\n")
            run = {"passed": True, "tracePath": str(trace)}
            report = {
                "schemaVersion": 1,
                "cases": [{"name": "no-leak", "arms": {"with": [run, {"passed": False}], "without": [run]}}],
            }
            _write_json(root / "out" / "aggregate-result.json", report)

            with_m2b, without = promises.runs_in_eval_report(root / "out", "no-leak")

        self.assertEqual([item.passed for item in with_m2b], [True, False])
        self.assertEqual(with_m2b[0].models, ("claude-haiku-5-5",))
        self.assertEqual([item.passed for item in without], [True])

    def test_the_eval_command_runs_the_case_with_the_tools_it_needs_and_both_arms_only_where_compared(self) -> None:
        both = promises.eval_command("no-leak", 1, True, Path("/tmp/sb-test-out"))
        one = promises.eval_command("no-leak", 3, False, Path("/tmp/sb-test-out"))

        self.assertIn("with-without", both)
        self.assertIn("none", one)
        for argument in ("--case", "no-leak", "--scaffold", "--trust-plugin", "--no-publish", "--keep-temp"):
            self.assertIn(argument, one)
        self.assertEqual(one[one.index("--runs") + 1], "3")
        self.assertEqual(one[one.index("--eval-dir") + 1], "evals")
        wording = promises.eval_command("no-leak-de", 1, False, Path("/tmp/sb-test-out"), "evals-wordings")
        self.assertEqual(wording[wording.index("--eval-dir") + 1], "evals-wordings")
        self.assertIn("mcp__m2b__note", one)


if __name__ == "__main__":
    unittest.main()
