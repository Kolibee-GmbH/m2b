from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from typing import Any

from repo_tools import evals_page

PAGE = f"""\
# Evals

Written by hand, above the results.

{evals_page.BLOCK_START}

| Case | With m2b | Without m2b |
|---|---|---|
| `recall` | 0.00 (0 of 3 runs) | 0.00 (0 of 3 runs) |

{evals_page.BLOCK_END}

Written by hand, below the results.
"""


class ReportFolder:
    """An invented eval report with the trace of every run, in a temporary folder."""

    def __init__(self, test: unittest.TestCase) -> None:
        folder = tempfile.TemporaryDirectory(prefix="sb-test-evals-page-")
        test.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self._traces = 0

    def trace(self, model: str = "claude-test-1") -> str:
        self._traces += 1
        path = self.root / "runs" / f"e-{self._traces}" / "out" / "trace.jsonl"
        path.parent.mkdir(parents=True)
        lines = [
            {"type": "system", "subtype": "hook_started", "hook_name": "SessionStart"},
            {"type": "system", "subtype": "init", "model": model, "claude_code_version": "9.8.7"},
            {"type": "assistant", "message": {"model": model}},
        ]
        path.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
        return str(path)

    def run(self, score: float = 1, *, model: str = "claude-test-1", error: str | None = None) -> dict[str, Any]:
        return {"score": score, "passed": score >= 1, "error": error, "tracePath": self.trace(model)}

    def case(self, name: str, with_m2b: list[dict[str, Any]], without_m2b: list[dict[str, Any]]) -> dict[str, Any]:
        def mean(runs: list[dict[str, Any]]) -> float:
            return float(sum(run["score"] for run in runs)) / len(runs)

        return {
            "name": name,
            "arms": {"with": with_m2b, "without": without_m2b},
            "aggregates": {"score": mean(with_m2b), "scoreWithout": mean(without_m2b)},
        }

    def report(self, cases: list[dict[str, Any]], *, started: str = "2026-03-04T23:10:00.000Z") -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "claudeVersion": "9.8.7",
            "startedAt": started,
            "partial": False,
            "suite": {"ablation": "with-without", "plugins": [{"name": "m2b", "version": "1.2.3"}]},
            "cases": cases,
        }

    def two_cases(self) -> dict[str, Any]:
        return self.report(
            [
                self.case("note", [self.run(), self.run(), self.run()], [self.run(0), self.run(0), self.run(0)]),
                self.case("recall", [self.run(), self.run(0.5), self.run()], [self.run(), self.run(), self.run()]),
            ]
        )

    def write(self, report: object, folder: str = "2026-03-04T23-10-00-000Z") -> Path:
        path = self.root / "evals" / "results" / folder / evals_page.REPORT_NAME
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(report), encoding="utf-8")
        return path

    def suite(self, *names: str, prompt: str = "---\nname: a case\nruns: 3\n---\nA prompt.\n") -> Path:
        evals = self.root / "evals"
        for name in names:
            (evals / name).mkdir(parents=True, exist_ok=True)
            (evals / name / "case.yaml").write_text(f"name: {name}\n", encoding="utf-8")
            (evals / name / "prompt.md").write_text(prompt, encoding="utf-8")
        return evals


class ReadRunTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = ReportFolder(self)

    def _refusal(self, report: object, suite: tuple[str, ...] = ("note", "recall")) -> str:
        with self.assertRaises(evals_page.EvalsPageError) as refused:
            evals_page.read_run(self.folder.write(report), dict.fromkeys(suite, 1))
        return str(refused.exception)

    def test_reads_each_case_with_and_without_m2b_and_the_facts_of_the_run(self) -> None:
        run = evals_page.read_run(self.folder.write(self.folder.two_cases()), {"note": 3, "recall": 3})

        self.assertEqual(run.day, date(2026, 3, 4))
        self.assertEqual((run.m2b_version, run.claude_code_version), ("1.2.3", "9.8.7"))
        self.assertEqual(run.models, ("claude-test-1",))
        self.assertEqual([case.name for case in run.cases], ["note", "recall"])
        note, recall = run.cases
        self.assertEqual(note.with_m2b, evals_page.Arm(score=1.0, passed=3, runs=3, errors=0))
        self.assertEqual(note.without_m2b, evals_page.Arm(score=0.0, passed=0, runs=3, errors=0))
        self.assertAlmostEqual(recall.with_m2b.score, 2.5 / 3)
        self.assertEqual((recall.with_m2b.passed, recall.with_m2b.runs), (2, 3))

    def test_the_score_is_the_one_the_report_gives_not_one_worked_out_again(self) -> None:
        report = self.folder.two_cases()
        report["cases"][0]["aggregates"]["score"] = 0.25

        run = evals_page.read_run(self.folder.write(report), {"note": 3, "recall": 3})

        self.assertEqual(run.cases[0].with_m2b.score, 0.25)

    def test_every_model_a_run_was_answered_by_is_named(self) -> None:
        report = self.folder.report(
            [self.folder.case("note", [self.folder.run(model="claude-test-2")], [self.folder.run()])]
        )

        run = evals_page.read_run(self.folder.write(report), {"note": 1})

        self.assertEqual(run.models, ("claude-test-1", "claude-test-2"))

    def test_a_run_that_ended_in_an_error_is_counted_and_needs_no_trace(self) -> None:
        failed = {"score": 0, "passed": False, "error": "timed out", "tracePath": str(self.folder.root / "gone")}
        report = self.folder.report([self.folder.case("note", [self.folder.run(), failed], [self.folder.run(0)])])

        run = evals_page.read_run(self.folder.write(report), {"note": 1})

        self.assertEqual(run.cases[0].with_m2b, evals_page.Arm(score=0.5, passed=1, runs=2, errors=1))
        self.assertEqual(run.models, ("claude-test-1",))

    def test_a_run_whose_trace_is_gone_is_refused_with_the_flag_that_keeps_it(self) -> None:
        report = self.folder.two_cases()
        Path(report["cases"][1]["arms"]["without"][2]["tracePath"]).unlink()

        refusal = self._refusal(report)

        self.assertIn("--keep-temp", refusal)
        self.assertIn("recall", refusal)

    def test_a_trace_without_a_session_start_names_no_model_and_is_refused(self) -> None:
        report = self.folder.two_cases()
        Path(report["cases"][0]["arms"]["with"][0]["tracePath"]).write_text(
            '{"type": "assistant"}\nnot json\n', encoding="utf-8"
        )

        self.assertIn("--keep-temp", self._refusal(report))

    def test_a_run_that_stopped_early_is_refused(self) -> None:
        report = self.folder.two_cases()
        report["partial"] = True

        self.assertIn("stopped early", self._refusal(report))

    def test_a_run_without_the_arm_without_m2b_is_refused(self) -> None:
        report = self.folder.two_cases()
        report["suite"]["ablation"] = "none"

        self.assertIn("with-without", self._refusal(report))

    def test_a_run_of_some_cases_only_is_refused_and_the_missing_ones_are_named(self) -> None:
        refusal = self._refusal(self.folder.two_cases(), suite=("coding", "note", "recall", "topic"))

        self.assertIn("coding, topic", refusal)

    def test_a_case_the_suite_does_not_have_is_refused(self) -> None:
        self.assertIn("recall", self._refusal(self.folder.two_cases(), suite=("note",)))

    def test_a_case_without_runs_in_an_arm_is_refused(self) -> None:
        report = self.folder.two_cases()
        report["cases"][0]["arms"]["without"] = []

        self.assertIn("note", self._refusal(report))

    def test_a_case_with_fewer_runs_than_it_asks_for_is_refused_as_a_try_out(self) -> None:
        with self.assertRaises(evals_page.EvalsPageError) as refused:
            evals_page.read_run(self.folder.write(self.folder.two_cases()), {"note": 3, "recall": 5})

        self.assertIn("recall has 3 runs with m2b and asks for 5", str(refused.exception))
        self.assertIn("--runs", str(refused.exception))

    def test_more_runs_than_a_case_asks_for_are_taken(self) -> None:
        run = evals_page.read_run(self.folder.write(self.folder.two_cases()), {"note": 2, "recall": 1})

        self.assertEqual([case.with_m2b.runs for case in run.cases], [3, 3])

    def test_another_schema_version_is_refused(self) -> None:
        report = self.folder.two_cases()
        report["schemaVersion"] = 2

        self.assertIn("schema version 1", self._refusal(report))

    def test_a_report_without_m2b_among_its_plugins_is_refused(self) -> None:
        report = self.folder.two_cases()
        report["suite"]["plugins"] = [{"name": "other", "version": "0.1.0"}]

        self.assertIn("m2b", self._refusal(report))

    def test_a_file_that_is_no_report_is_refused_instead_of_raising_something_else(self) -> None:
        for content in ("not json", "[]", '{"schemaVersion": 1, "partial": false}', '{"schemaVersion": 1}'):
            with self.subTest(content=content):
                path = self.folder.root / "broken.json"
                path.write_text(content, encoding="utf-8")

                with self.assertRaises(evals_page.EvalsPageError):
                    evals_page.read_run(path, {"note": 1})

    def test_a_field_of_the_wrong_kind_is_refused_and_named(self) -> None:
        report = self.folder.two_cases()
        report["cases"][0]["aggregates"]["score"] = "high"

        self.assertIn("score", self._refusal(report))


class SuiteCasesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = ReportFolder(self)

    def test_every_case_folder_is_a_case_with_the_runs_its_prompt_asks_for(self) -> None:
        self.folder.suite("recall", prompt="---\nname: recall\nruns: 5\nmax_turns: 4\n---\nA prompt.\n")
        evals = self.folder.suite("note")
        (evals / "results").mkdir()

        self.assertEqual(evals_page.suite_cases(evals), {"note": 3, "recall": 5})

    def test_a_case_that_names_no_number_runs_as_often_as_the_eval_tool_runs_it(self) -> None:
        evals = self.folder.suite(
            "note", prompt="---\nname: note\n---\nThe prompt says runs: 9 in its text.\nruns: 9\n"
        )

        self.assertEqual(evals_page.suite_cases(evals), {"note": 3})

    def test_the_real_suite_asks_for_at_least_one_run_of_every_case(self) -> None:
        asked = evals_page.suite_cases(evals_page.EVALS)

        self.assertGreater(len(asked), 0)
        self.assertEqual([case for case, runs in asked.items() if runs < 1], [])


class ResultsBlockTest(unittest.TestCase):
    def _run(self, **changes: Any) -> evals_page.EvalRun:
        arm = evals_page.Arm(score=1.0, passed=3, runs=3, errors=0)
        values: dict[str, Any] = {
            "day": date(2026, 3, 4),
            "m2b_version": "1.2.3",
            "claude_code_version": "9.8.7",
            "models": ("claude-test-1",),
            "cases": (evals_page.Case("note", arm, evals_page.Arm(score=0.0, passed=0, runs=3, errors=0)),),
        }
        return evals_page.EvalRun(**{**values, **changes})

    def test_the_block_names_the_run_and_has_one_row_per_case(self) -> None:
        self.assertEqual(
            evals_page.results_block(self._run()),
            f"{evals_page.BLOCK_START}\n\n"
            "| | |\n"
            "|---|---|\n"
            "| Day | 2026-03-04 |\n"
            "| m2b | 1.2.3 |\n"
            "| Claude Code | 9.8.7 |\n"
            "| Model | `claude-test-1` |\n"
            "| Runs | 6 |\n\n"
            "| Case | With m2b | Without m2b |\n"
            "|---|---|---|\n"
            "| `note` | 1.00 (3 of 3 runs) | 0.00 (0 of 3 runs) |\n\n"
            f"{evals_page.BLOCK_END}",
        )

    def test_a_case_below_one_stands_there_with_its_score(self) -> None:
        low = evals_page.Arm(score=2 / 3, passed=2, runs=3, errors=0)

        block = evals_page.results_block(self._run(cases=(evals_page.Case("recall", low, low),)))

        self.assertIn("| `recall` | 0.67 (2 of 3 runs) | 0.67 (2 of 3 runs) |", block)

    def test_runs_that_ended_in_an_error_are_counted_on_the_page(self) -> None:
        broken = evals_page.Arm(score=0.5, passed=1, runs=2, errors=1)

        block = evals_page.results_block(self._run(cases=(evals_page.Case("note", broken, broken),)))

        self.assertIn("| Runs | 4, of which 2 ended in an error and count as failed |", block)

    def test_several_models_are_all_named(self) -> None:
        block = evals_page.results_block(self._run(models=("claude-test-1", "claude-test-2")))

        self.assertIn("| Model | `claude-test-1`, `claude-test-2` |", block)


class ReplaceResultsTest(unittest.TestCase):
    def test_only_the_block_between_the_markers_changes(self) -> None:
        block = f"{evals_page.BLOCK_START}\n\nnew\n\n{evals_page.BLOCK_END}"

        replaced = evals_page.replace_results(PAGE, block)

        before, _, rest = PAGE.partition(evals_page.BLOCK_START)
        after = rest.partition(evals_page.BLOCK_END)[2]
        self.assertEqual(replaced, before + block + after)

    def test_writing_the_same_block_twice_changes_nothing(self) -> None:
        block = f"{evals_page.BLOCK_START}\n\nnew\n\n{evals_page.BLOCK_END}"

        once = evals_page.replace_results(PAGE, block)

        self.assertEqual(evals_page.replace_results(once, block), once)

    def test_a_page_without_both_markers_in_order_is_refused(self) -> None:
        start, end = evals_page.BLOCK_START, evals_page.BLOCK_END
        for page in ("# Evals\n", f"{start}\n", f"{end}\n{start}\n", f"{start}\n{end}\n{start}\n{end}\n"):
            with self.subTest(page=page), self.assertRaises(evals_page.EvalsPageError):
                evals_page.replace_results(page, "block")


class MainTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = ReportFolder(self)
        self.evals = self.folder.suite("note", "recall")
        self.page = self.folder.root / "evals.md"
        self.page.write_text(PAGE, encoding="utf-8")

    def _main(self, *arguments: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = evals_page.main(list(arguments), evals=self.evals, page=self.page)
        return status, out.getvalue(), err.getvalue()

    def test_without_an_argument_the_newest_report_goes_on_the_page(self) -> None:
        old = self.folder.report([self.folder.case("note", [self.folder.run(0)], [self.folder.run(0)])])
        self.folder.write(old, "2026-03-01T08-00-00-000Z")
        self.folder.write(self.folder.two_cases(), "2026-03-04T23-10-00-000Z")

        status, out, err = self._main()

        self.assertEqual((status, err), (0, ""))
        page = self.page.read_text(encoding="utf-8")
        self.assertIn("| `note` | 1.00 (3 of 3 runs) | 0.00 (0 of 3 runs) |", page)
        self.assertIn("| `recall` | 0.83 (2 of 3 runs) | 1.00 (3 of 3 runs) |", page)
        self.assertIn("Written by hand, above the results.", page)
        self.assertIn("Written by hand, below the results.", page)
        self.assertIn("2026-03-04T23-10-00-000Z", out)

    def test_a_case_below_one_with_m2b_is_said_out_loud(self) -> None:
        self.folder.write(self.folder.two_cases())

        _, out, _ = self._main()

        self.assertIn("recall scores 0.83 with m2b", out)
        self.assertNotIn("note scores", out)

    def test_a_named_report_is_taken_by_its_file_or_its_folder(self) -> None:
        self.folder.write(self.folder.two_cases(), "2026-03-09T08-00-00-000Z")
        named = self.folder.write(self.folder.two_cases(), "2026-03-04T23-10-00-000Z")

        for argument in (str(named), str(named.parent)):
            with self.subTest(argument=argument):
                status, out, _ = self._main(argument)

                self.assertEqual(status, 0)
                self.assertIn("2026-03-04T23-10-00-000Z", out)

    def test_a_refused_report_leaves_the_page_as_it_was(self) -> None:
        report = self.folder.two_cases()
        report["partial"] = True
        self.folder.write(report)

        status, out, err = self._main()

        self.assertEqual((status, out), (2, ""))
        self.assertIn("evals-page: ", err)
        self.assertEqual(self.page.read_text(encoding="utf-8"), PAGE)

    def test_no_report_at_all_says_to_run_the_evals_first(self) -> None:
        status, _, err = self._main()

        self.assertEqual(status, 2)
        self.assertIn("run the evals first", err)

    def test_a_missing_page_is_refused(self) -> None:
        self.folder.write(self.folder.two_cases())
        self.page.unlink()

        status, _, err = self._main()

        self.assertEqual(status, 2)
        self.assertIn("evals.md", err)


if __name__ == "__main__":
    unittest.main()
