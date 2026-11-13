"""Step reports: a model step's findings, kept per run on this machine until the run reads them."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from m2b import cli, paths
from m2b.curate import report


class RunFindingsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.machine = paths.MachinePaths(Path(self._temp.name))

    def test_findings_are_kept_in_order_for_the_run_that_opened_them(self) -> None:
        token = report.open_run(self.machine)
        other = report.open_run(self.machine)

        report.add_finding(self.machine, token, report.Finding("lint", "action", "two links point at one name"))
        report.add_finding(self.machine, token, report.Finding("lint", "info", "3 files evicted"))
        report.add_finding(self.machine, other, report.Finding("ingest", "info", "nothing in the inbox"))

        self.assertEqual(
            report.read_findings(self.machine, token),
            [
                report.Finding("lint", "action", "two links point at one name"),
                report.Finding("lint", "info", "3 files evicted"),
            ],
        )
        self.assertEqual(
            report.read_findings(self.machine, other), [report.Finding("ingest", "info", "nothing in the inbox")]
        )

    def test_a_token_is_long_random_hex_and_the_run_file_is_private(self) -> None:
        token = report.open_run(self.machine)

        self.assertRegex(token, r"^[0-9a-f]{32}$")
        self.assertNotEqual(token, report.open_run(self.machine))
        self.assertEqual(report.run_file(self.machine, token).stat().st_mode & 0o777, 0o600)

    def test_the_text_becomes_one_line(self) -> None:
        token = report.open_run(self.machine)

        report.add_finding(self.machine, token, report.Finding("lint", "info", "  first\n\n second\tline  "))

        self.assertEqual(report.read_findings(self.machine, token)[0].text, "first second line")

    def test_a_token_without_an_open_run_is_refused(self) -> None:
        for token in ("", "0" * 32, "../../etc/passwd", "ABCDEF" * 6):
            with self.subTest(token=token), self.assertRaises(report.NoRunError):
                report.add_finding(self.machine, token, report.Finding("lint", "info", "x"))

    def test_a_closed_run_takes_no_more_findings(self) -> None:
        token = report.open_run(self.machine)
        report.close_run(self.machine, token)

        with self.assertRaises(report.NoRunError):
            report.add_finding(self.machine, token, report.Finding("lint", "info", "late"))
        report.close_run(self.machine, token)

    def test_unknown_kinds_bad_step_names_and_empty_text_are_refused(self) -> None:
        token = report.open_run(self.machine)
        for finding in (
            report.Finding("lint", "warning", "x"),
            report.Finding("Lint step", "info", "x"),
            report.Finding("lint", "info", " \n "),
        ):
            with self.subTest(finding=finding), self.assertRaises(report.FindingError):
                report.add_finding(self.machine, token, finding)
        self.assertEqual(report.read_findings(self.machine, token), [])

    def test_a_long_text_is_cut(self) -> None:
        token = report.open_run(self.machine)

        report.add_finding(self.machine, token, report.Finding("lint", "info", "word " * 1000))

        text = report.read_findings(self.machine, token)[0].text
        self.assertLessEqual(len(text), report.MAX_TEXT_CHARACTERS)
        self.assertTrue(text.endswith("..."))

    def test_a_line_that_cannot_be_read_stays_visible_as_an_action(self) -> None:
        token = report.open_run(self.machine)
        report.add_finding(self.machine, token, report.Finding("lint", "info", "fine"))
        with report.run_file(self.machine, token).open("ab") as handle:
            handle.write(b'{"step": "lint", "kind": "inf')

        findings = report.read_findings(self.machine, token)

        self.assertEqual(findings[0], report.Finding("lint", "info", "fine"))
        self.assertEqual(findings[1].kind, "action")
        self.assertIn("could not be read", findings[1].text)


class ReportCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.home = Path(self._temp.name) / "home"
        self.machine = paths.MachinePaths(self.home)
        self.environ = {"HOME": str(self.home), "M2B_HOME": str(self.home)}

    def run_command(self, *arguments: str, stdin: str = "") -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with (
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
            mock.patch("sys.stdin", io.StringIO(stdin)),
        ):
            code = cli.main(list(arguments), self.environ)
        return code, out.getvalue(), err.getvalue()

    def test_with_a_run_token_the_finding_is_kept_for_the_run(self) -> None:
        token = report.open_run(self.machine)
        self.environ[report.RUN_TOKEN_VARIABLE] = token

        code, _, err = self.run_command(
            "curate", "report", "--step", "lint", "--kind", "action", "--text", "a broken link"
        )

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(report.read_findings(self.machine, token), [report.Finding("lint", "action", "a broken link")])

    def test_the_text_can_come_from_standard_input(self) -> None:
        token = report.open_run(self.machine)
        self.environ[report.RUN_TOKEN_VARIABLE] = token

        code, _, err = self.run_command(
            "curate", "report", "--step", "lint", "--kind", "info", "--text", "-", stdin='sizes: "memory" 3 KB\n'
        )

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(report.read_findings(self.machine, token)[0].text, 'sizes: "memory" 3 KB')

    def test_without_a_run_token_it_exits_2(self) -> None:
        code, _, err = self.run_command("curate", "report", "--step", "lint", "--kind", "info", "--text", "x")

        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertIn("curation run", err)

    def test_a_token_of_no_open_run_exits_2(self) -> None:
        self.environ[report.RUN_TOKEN_VARIABLE] = "0" * 32

        code, _, _ = self.run_command("curate", "report", "--step", "lint", "--kind", "info", "--text", "x")

        self.assertEqual(code, cli.EXIT_USAGE)

    def test_a_bad_kind_or_step_exits_2(self) -> None:
        self.environ[report.RUN_TOKEN_VARIABLE] = report.open_run(self.machine)

        self.assertEqual(self.run_command("curate", "report", "--step", "lint", "--kind", "note", "--text", "x")[0], 2)
        self.assertEqual(self.run_command("curate", "report", "--step", "LINT", "--kind", "info", "--text", "x")[0], 2)


if __name__ == "__main__":
    unittest.main()
