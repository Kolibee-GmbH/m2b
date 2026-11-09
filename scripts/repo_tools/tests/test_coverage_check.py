from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from repo_tools import coverage_check

SMALL_CATALOG = """\
# Behavior catalog

| ID | Behavior | Why |
|---|---|---|
| B1 | first | reason |
| B2 | second | reason |
| X1 | defect | fix |
| X15 | a rule about tests | review |
"""


class CatalogTest(unittest.TestCase):
    def test_reads_every_table_row_and_leaves_out_the_untestable_rule(self) -> None:
        self.assertEqual(coverage_check.catalogued_ids(SMALL_CATALOG), ["B1", "B2", "X1"])

    def test_the_real_catalog_is_read_with_every_testable_behavior(self) -> None:
        catalog = coverage_check.catalogued_ids(coverage_check.BEHAVIOR_CATALOG.read_text(encoding="utf-8"))

        self.assertEqual(len(catalog), 102)
        self.assertEqual(sum(i.startswith("B") for i in catalog), 81)
        self.assertNotIn("X15", catalog)
        self.assertEqual(len(set(catalog)), len(catalog))

    def test_a_text_without_any_catalog_row_is_an_error(self) -> None:
        with self.assertRaises(coverage_check.CatalogError):
            coverage_check.catalogued_ids("# Something else\n")


class CoversLineTest(unittest.TestCase):
    def test_reads_every_id_of_a_covers_line(self) -> None:
        text = '    """Writes the file.\n\n    Covers: B16, X6,B2\n    """\n'

        self.assertEqual(coverage_check.covered_ids(text), {"B16", "X6", "B2"})

    def test_text_without_a_covers_line_covers_nothing(self) -> None:
        self.assertEqual(coverage_check.covered_ids("B16 is mentioned in passing"), set())


class ReportTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.catalog = self.root / "catalog.md"
        self.catalog.write_text(SMALL_CATALOG, encoding="utf-8")
        self.tests = self.root / "plugins" / "core" / "tests"
        self.tests.mkdir(parents=True)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _run(self) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = coverage_check.main(["--catalog", str(self.catalog), str(self.root / "plugins")])
        return code, output.getvalue()

    def test_lists_every_behavior_without_a_test_and_still_passes(self) -> None:
        (self.tests / "test_capture.py").write_text('"""Covers: B1"""\n', encoding="utf-8")

        code, output = self._run()

        self.assertEqual(code, coverage_check.EXIT_REPORTED)
        self.assertIn("2 of 3 behaviors have no test: B2, X1", output)

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

    def test_a_catalog_without_its_section_is_a_configuration_error(self) -> None:
        self.catalog.write_text("# Renamed heading\n", encoding="utf-8")

        with contextlib.redirect_stderr(io.StringIO()):
            code, _ = self._run()

        self.assertEqual(code, coverage_check.EXIT_BAD_CATALOG)

    def test_citing_an_id_that_is_not_in_the_catalog_fails(self) -> None:
        (self.tests / "test_capture.py").write_text('"""Covers: B1, B77"""\n', encoding="utf-8")

        code, output = self._run()

        self.assertEqual(code, coverage_check.EXIT_UNKNOWN_IDS)
        self.assertIn("B77 is not in the catalog", output)


if __name__ == "__main__":
    unittest.main()
