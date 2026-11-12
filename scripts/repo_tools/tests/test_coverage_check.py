from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from repo_tools import coverage_check

CORE_PART = """\
# Behavior: the core

## Behaviors m2b keeps

| ID | Behavior | Why |
|---|---|---|
| B1 | first | reason |
| B2 | second | reason |

## Defects m2b does not have

| ID | Defect | In the product |
|---|---|---|
| X1 | defect | fix |
| X15 | a rule about tests | review |
"""

WORKLOG_PART = """\
# Behavior: the worklog

| ID | Behavior | Why |
|---|---|---|
| B3 | third | reason |
"""


class CatalogFolderTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.catalog = self.root / "docs" / "behavior"
        self.catalog.mkdir(parents=True)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def write_part(self, name: str, text: str) -> None:
        (self.catalog / f"{name}.md").write_text(text, encoding="utf-8")


class RuleIdsTest(unittest.TestCase):
    def test_reads_the_id_of_every_table_row(self) -> None:
        self.assertEqual(coverage_check.rule_ids(CORE_PART), ["B1", "B2", "X1", "X15"])

    def test_a_text_without_a_rule_has_no_id(self) -> None:
        self.assertEqual(coverage_check.rule_ids("# Something else\n\n| ID | Behavior |\n|---|---|\n"), [])


class CatalogTest(CatalogFolderTestCase):
    def test_reads_every_part_and_says_which_part_a_rule_stands_in(self) -> None:
        self.write_part("worklog", WORKLOG_PART)
        self.write_part("core", CORE_PART)

        catalog = coverage_check.read_catalog(self.catalog)

        self.assertEqual(catalog, {"B1": "core", "B2": "core", "X1": "core", "B3": "worklog"})
        self.assertEqual(list(catalog), ["B1", "B2", "X1", "B3"])

    def test_leaves_out_the_rule_no_test_can_cover(self) -> None:
        self.write_part("core", CORE_PART)

        self.assertNotIn("X15", coverage_check.read_catalog(self.catalog))

    def test_only_markdown_files_are_parts(self) -> None:
        self.write_part("core", CORE_PART)
        (self.catalog / "notes.txt").write_text("| B9 | not a part | reason |\n", encoding="utf-8")

        self.assertNotIn("B9", coverage_check.read_catalog(self.catalog))

    def test_a_folder_without_a_part_is_an_error(self) -> None:
        with self.assertRaisesRegex(coverage_check.CatalogError, "no part"):
            coverage_check.read_catalog(self.catalog)

    def test_a_catalog_that_is_no_folder_is_an_error(self) -> None:
        with self.assertRaisesRegex(coverage_check.CatalogError, "no part"):
            coverage_check.read_catalog(self.root / "docs" / "missing")

    def test_a_part_without_a_rule_is_an_error_that_names_it(self) -> None:
        self.write_part("core", CORE_PART)
        self.write_part("band", "# Behavior: the band\n\n| ID | Behavior | Why |\n|---|---|---|\n")

        with self.assertRaisesRegex(coverage_check.CatalogError, r"band\.md"):
            coverage_check.read_catalog(self.catalog)

    def test_an_id_in_two_parts_is_an_error_that_names_both(self) -> None:
        self.write_part("core", CORE_PART)
        self.write_part("worklog", WORKLOG_PART + "| B2 | second, again | reason |\n")

        with self.assertRaisesRegex(coverage_check.CatalogError, r"B2 .*core\.md.*worklog\.md"):
            coverage_check.read_catalog(self.catalog)

    def test_an_id_twice_in_one_part_is_an_error(self) -> None:
        self.write_part("core", CORE_PART + "| X15 | the same rule about tests | review |\n")

        with self.assertRaisesRegex(coverage_check.CatalogError, r"X15 .*core\.md.*core\.md"):
            coverage_check.read_catalog(self.catalog)

    def test_the_real_catalog_is_read_with_every_testable_behavior(self) -> None:
        catalog = coverage_check.read_catalog(coverage_check.BEHAVIOR_CATALOG)

        self.assertEqual(len(catalog), 175)
        self.assertEqual(sum(i.startswith("B") for i in catalog), 154)
        self.assertNotIn("X15", catalog)
        self.assertEqual(set(catalog.values()), {"band", "core", "curation", "worklog"})


class CoversLineTest(unittest.TestCase):
    def test_reads_every_id_of_a_covers_line(self) -> None:
        text = '    """Writes the file.\n\n    Covers: B16, X6,B2\n    """\n'

        self.assertEqual(coverage_check.covered_ids(text), {"B16", "X6", "B2"})

    def test_text_without_a_covers_line_covers_nothing(self) -> None:
        self.assertEqual(coverage_check.covered_ids("B16 is mentioned in passing"), set())


class ReportTest(CatalogFolderTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.write_part("core", CORE_PART)
        self.tests = self.root / "plugins" / "core" / "tests"
        self.tests.mkdir(parents=True)

    def _run(self) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = coverage_check.main(["--catalog", str(self.catalog), str(self.root / "plugins")])
        return code, output.getvalue()

    def test_a_behavior_without_a_test_is_listed_and_fails(self) -> None:
        (self.tests / "test_capture.py").write_text('"""Covers: B1"""\n', encoding="utf-8")

        code, output = self._run()

        self.assertEqual(code, coverage_check.EXIT_FINDINGS)
        self.assertIn("2 of 3 behaviors have no test: B2, X1", output)

    def test_every_behavior_with_a_test_passes(self) -> None:
        (self.tests / "test_capture.py").write_text('"""Covers: B1, B2, X1"""\n', encoding="utf-8")

        code, output = self._run()

        self.assertEqual(code, coverage_check.EXIT_COVERED)
        self.assertEqual(output, "coverage: all 3 behaviors have a test\n")

    def test_scenario_files_count_as_tests(self) -> None:
        scenario = self.root / "plugins" / "core" / "tests" / "e2e" / "everyday"
        scenario.mkdir(parents=True)
        (scenario / "steps.json").write_text('{"description": "Covers: B1, B2, X1"}', encoding="utf-8")

        _, output = self._run()

        self.assertIn("all 3 behaviors have a test", output)

    def test_mod_tests_in_typescript_count_as_tests(self) -> None:
        band_tests = self.root / "plugins" / "band" / "tests"
        band_tests.mkdir(parents=True)
        (band_tests / "band.test.tsx").write_text("  // Covers: B1\n", encoding="utf-8")
        (band_tests / "status-line.test.ts").write_text("  // Covers: B2, X1\n", encoding="utf-8")

        _, output = self._run()

        self.assertIn("all 3 behaviors have a test", output)

    def test_files_outside_a_tests_folder_do_not_count(self) -> None:
        source = self.root / "plugins" / "core" / "src"
        source.mkdir()
        (source / "capture.py").write_text('"""Covers: B1"""\n', encoding="utf-8")

        _, output = self._run()

        self.assertIn("3 of 3 behaviors have no test", output)

    def test_a_catalog_without_a_rule_is_a_configuration_error(self) -> None:
        self.write_part("core", "# Renamed heading\n")

        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            code, _ = self._run()

        self.assertEqual(code, coverage_check.EXIT_BAD_CATALOG)
        self.assertIn("core.md", errors.getvalue())

    def test_citing_an_id_that_is_not_in_the_catalog_fails(self) -> None:
        (self.tests / "test_capture.py").write_text('"""Covers: B1, B2, X1, B77"""\n', encoding="utf-8")

        code, output = self._run()

        self.assertEqual(code, coverage_check.EXIT_FINDINGS)
        self.assertIn("B77 is not in the catalog", output)

    def test_citing_the_rule_no_test_can_cover_is_no_finding(self) -> None:
        (self.tests / "test_capture.py").write_text('"""Covers: B1, B2, X1, X15"""\n', encoding="utf-8")

        code, _ = self._run()

        self.assertEqual(code, coverage_check.EXIT_COVERED)


class AddonSuiteTest(CatalogFolderTestCase):
    """The part named like an add-on is covered by that add-on's suite, every other part outside the add-ons' suites."""

    def setUp(self) -> None:
        super().setUp()
        self.write_part("core", CORE_PART)
        self.write_part("worklog", WORKLOG_PART)
        self.core_tests = self.root / "plugins" / "m2b" / "tests"
        self.worklog_tests = self.core_tests / "addons" / "worklog"
        self.worklog_tests.mkdir(parents=True)

    def _run(self) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = coverage_check.main(["--catalog", str(self.catalog), str(self.root / "plugins")])
        return code, output.getvalue()

    def test_each_part_named_by_its_own_suite_passes(self) -> None:
        (self.core_tests / "test_capture.py").write_text('"""Covers: B1, B2, X1"""\n', encoding="utf-8")
        (self.worklog_tests / "test_daily.py").write_text('"""Covers: B3"""\n', encoding="utf-8")

        code, output = self._run()

        self.assertEqual(code, coverage_check.EXIT_COVERED)
        self.assertEqual(output, "coverage: all 4 behaviors have a test\n")

    def test_a_rule_of_an_addon_named_only_outside_its_suite_fails(self) -> None:
        (self.core_tests / "test_capture.py").write_text('"""Covers: B1, B2, X1, B3"""\n', encoding="utf-8")

        code, output = self._run()

        self.assertEqual(code, coverage_check.EXIT_FINDINGS)
        self.assertIn("B3 stands in the part of the worklog add-on, and no test of its suite names it", output)
        self.assertNotIn("have a test", output)

    def test_a_rule_of_no_addon_named_only_by_an_addons_suite_fails(self) -> None:
        (self.core_tests / "test_capture.py").write_text('"""Covers: B1, X1"""\n', encoding="utf-8")
        (self.worklog_tests / "test_daily.py").write_text('"""Covers: B2, B3"""\n', encoding="utf-8")

        code, output = self._run()

        self.assertEqual(code, coverage_check.EXIT_FINDINGS)
        self.assertIn("B2 stands in the part core, and only an add-on's tests name it", output)

    def test_a_rule_may_be_named_by_both_suites(self) -> None:
        (self.core_tests / "test_capture.py").write_text('"""Covers: B1, B2, X1, B3"""\n', encoding="utf-8")
        (self.worklog_tests / "test_daily.py").write_text('"""Covers: B2, B3"""\n', encoding="utf-8")

        code, _ = self._run()

        self.assertEqual(code, coverage_check.EXIT_COVERED)

    def test_a_folder_named_like_no_addon_is_no_addons_suite(self) -> None:
        other = self.core_tests / "addons" / "calendar"
        other.mkdir()
        (other / "test_events.py").write_text('"""Covers: B1, B2, X1"""\n', encoding="utf-8")
        (self.worklog_tests / "test_daily.py").write_text('"""Covers: B3"""\n', encoding="utf-8")

        code, _ = self._run()

        self.assertEqual(code, coverage_check.EXIT_COVERED)

    def test_the_real_addons_each_have_their_part(self) -> None:
        parts = set(coverage_check.read_catalog(coverage_check.BEHAVIOR_CATALOG).values())

        self.assertEqual(sorted(coverage_check.ADDON_NAMES - parts), [])


if __name__ == "__main__":
    unittest.main()
