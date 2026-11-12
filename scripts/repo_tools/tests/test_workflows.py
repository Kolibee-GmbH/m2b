"""Only GitHub runs the workflows, so nothing here can start one. These tests hold what a reader of
the files relies on, and read them as text: the standard library has no YAML parser."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from repo_tools import e2e

REPO = Path(__file__).resolve().parents[3]
WORKFLOWS = REPO / ".github" / "workflows"
CLAUDE_CODE_PACKAGE = "@anthropic-ai/claude-code"
STEP_ENVIRONMENT_INDENT = 10

RECORD_END = "\x1e"
ARGUMENT_END = "\x1f"
# Stands in for the GitHub CLI: keeps every call with its arguments and answers the search for an
# open issue with the number the test gives it.
GH_STUB = """#!/bin/sh
for argument in "$@"; do
    printf '%s\\037' "$argument" >> "$GH_CALLS"
done
printf '\\036' >> "$GH_CALLS"
if [ "$1 $2" = "issue list" ]; then
    printf '%s' "$GH_OPEN_ISSUE"
fi
"""


def _text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def _script_blocks(text: str) -> list[str]:
    """The multi-line shell scripts of a workflow's steps, each without its indentation."""
    blocks = []
    lines = text.splitlines()
    for number, line in enumerate(lines):
        start = re.fullmatch(r"( *)run: \|", line)
        if start is None:
            continue
        body = []
        for following in lines[number + 1 :]:
            if following.strip() and len(following) - len(following.lstrip()) <= len(start.group(1)):
                break
            body.append(following)
        blocks.append(textwrap.dedent("\n".join(body)) + "\n")
    return blocks


class WorkflowCommandsTest(unittest.TestCase):
    def test_every_script_a_workflow_names_exists_and_can_be_run(self) -> None:
        for workflow in sorted(WORKFLOWS.glob("*.yml")):
            for script in re.findall(r"(?<![\w./-])scripts/[\w-]+", workflow.read_text(encoding="utf-8")):
                with self.subTest(workflow=workflow.name, script=script):
                    self.assertTrue((REPO / script).is_file())
                    self.assertTrue(os.access(REPO / script, os.X_OK))

    def test_every_level_a_workflow_asks_of_the_scenarios_is_one_the_runner_has(self) -> None:
        levels = re.findall(r"scripts/e2e --level (\S+)", _text("weekly.yml"))

        self.assertEqual(levels, [e2e.MODEL])

    def test_ci_installs_the_claude_code_version_the_readme_names_as_the_minimum(self) -> None:
        versions = re.findall(r"(?m)^  CLAUDE_CODE_VERSION: (\S+)$", _text("ci.yml"))

        self.assertEqual(len(versions), 1)
        self.assertIn(f"Claude Code {versions[0]} or newer", (REPO / "README.md").read_text(encoding="utf-8"))
        self.assertIn(f'"{CLAUDE_CODE_PACKAGE}@${{CLAUDE_CODE_VERSION}}"', _text("ci.yml"))


class PinnedActionsTest(unittest.TestCase):
    """A tag is moved by whoever controls an action's repository, a commit is not: the workflows
    hold an account's key and may write a release."""

    PINNED = re.compile(r" *- uses: [\w.-]+/[\w./-]+@[0-9a-f]{40} # v\d+\.\d+\.\d+")
    USES = re.compile(r"uses: (\S+?)@(.*)")

    def uses(self) -> dict[str, list[str]]:
        """The lines that name an action, per workflow file."""
        found = {}
        for workflow in sorted(WORKFLOWS.glob("*.yml")):
            found[workflow.name] = [line for line in _text(workflow.name).splitlines() if "uses:" in line]
        return found

    def test_every_action_is_named_by_its_commit_with_the_version_as_a_comment(self) -> None:
        for workflow, lines in self.uses().items():
            self.assertTrue(lines, workflow)
            for line in lines:
                with self.subTest(workflow=workflow, line=line.strip()):
                    self.assertRegex(line, f"^{self.PINNED.pattern}$")

    def test_an_action_is_the_same_commit_and_version_in_every_workflow(self) -> None:
        pins: dict[str, set[str]] = {}
        for lines in self.uses().values():
            for line in lines:
                found = self.USES.search(line)
                assert found is not None, line
                pins.setdefault(found.group(1), set()).add(found.group(2))

        self.assertEqual({action: len(named) for action, named in pins.items() if len(named) != 1}, {})
        self.assertGreaterEqual(len(pins), 4)


class WeeklyRunTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = _text("weekly.yml")

    def test_it_starts_once_a_week_and_by_hand(self) -> None:
        schedules = re.findall(r'(?m)^ +- cron: "([^"]+)"$', self.text)

        self.assertEqual(len(schedules), 1)
        minute, hour, day_of_month, month, day_of_week = schedules[0].split()
        self.assertTrue(minute.isdigit() and hour.isdigit(), schedules[0])
        self.assertEqual((day_of_month, month), ("*", "*"))
        self.assertRegex(day_of_week, r"^[0-6]$")
        self.assertIn("\n  workflow_dispatch:\n", self.text)

    def test_it_installs_the_newest_claude_code_and_holds_no_version(self) -> None:
        installs = [line for line in self.text.splitlines() if CLAUDE_CODE_PACKAGE in line]

        self.assertEqual(len(installs), 2)
        for line in installs:
            self.assertRegex(line, rf'^ +- run: npm install --global "{CLAUDE_CODE_PACKAGE}@latest"$')
        self.assertNotIn("CLAUDE_CODE_VERSION", self.text)

    def test_it_runs_the_whole_proof_and_the_model_level_scenarios(self) -> None:
        self.assertRegex(self.text, r"(?m)^ +- run: scripts/check$")
        self.assertRegex(self.text, r"(?m)^ +scripts/e2e --level model \$SCENARIOS$")

    def test_the_model_level_scenarios_run_only_where_an_account_is(self) -> None:
        self.assertIn("\n    needs: access\n    if: needs.access.outputs.granted == 'true'\n", self.text)

    def test_an_account_reaches_single_steps_and_never_a_whole_job(self) -> None:
        with_secret = [line for line in self.text.splitlines() if "secrets." in line]

        self.assertEqual(len(with_secret), 4)
        for line in with_secret:
            self.assertEqual(len(line) - len(line.lstrip()), STEP_ENVIRONMENT_INDENT, line)

    def test_only_the_job_that_reports_may_write_and_only_issues(self) -> None:
        self.assertIn("\npermissions:\n  contents: read\n", self.text)
        self.assertEqual(re.findall(r"(?m)^ *[\w-]+: write$", self.text), ["      issues: write"])

    def test_only_a_failed_scheduled_run_reports(self) -> None:
        self.assertIn("\n    if: failure() && github.event_name == 'schedule'\n", self.text)


@unittest.skipUnless(shutil.which("bash"), "needs bash, the shell GitHub runs a step's script with")
class WeeklyFailureReportTest(unittest.TestCase):
    TITLE = "The weekly run with the newest Claude Code failed"
    RUN_URL = "https://github.example/acme/m2b/actions/runs/7"

    def _report(self, open_issue: str = "", claude_code: str = "9.8.7 (Claude Code)") -> list[list[str]]:
        """Runs the script of the reporting step and returns the calls it made to the GitHub CLI."""
        (script,) = [block for block in _script_blocks(_text("weekly.yml")) if "gh issue" in block]
        with tempfile.TemporaryDirectory(prefix="sb-test-") as folder:
            stub = Path(folder) / "gh"
            stub.write_text(GH_STUB, encoding="utf-8")
            stub.chmod(0o755)
            calls = Path(folder) / "calls"
            subprocess.run(
                [shutil.which("bash") or "bash", "-e", "-c", script],
                env={
                    "PATH": folder,
                    "GH_CALLS": str(calls),
                    "GH_OPEN_ISSUE": open_issue,
                    "GITHUB_REPOSITORY": "acme/m2b",
                    "RUN_URL": self.RUN_URL,
                    "CLAUDE_CODE": claude_code,
                    "CHECK": "failure",
                    "MODEL_SCENARIOS": "skipped",
                },
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            records = calls.read_text(encoding="utf-8").split(RECORD_END)[:-1]
        return [record.split(ARGUMENT_END)[:-1] for record in records]

    def test_the_first_failure_opens_an_issue_with_the_run_the_version_and_what_failed(self) -> None:
        search, report = self._report()

        self.assertEqual(search[:6], ["issue", "list", "--repo", "acme/m2b", "--state", "open"])
        self.assertEqual(search[search.index("--search") + 1], f'in:title "{self.TITLE}"')
        self.assertEqual(report[:6], ["issue", "create", "--repo", "acme/m2b", "--title", self.TITLE])
        body = report[report.index("--body") + 1]
        self.assertIn(f"Claude Code 9.8.7 (Claude Code): {self.RUN_URL}", body)
        self.assertIn("- scripts/check: failure", body)
        self.assertIn("- the model-level scenarios: skipped", body)

    def test_a_failure_while_the_issue_is_open_adds_a_comment_and_opens_no_second_issue(self) -> None:
        _, report = self._report(open_issue="12")

        self.assertEqual(report[:5], ["issue", "comment", "12", "--repo", "acme/m2b"])
        self.assertIn(self.RUN_URL, report[report.index("--body") + 1])

    def test_a_run_that_never_installed_claude_code_says_the_version_is_unknown(self) -> None:
        _, report = self._report(claude_code="")

        self.assertIn("Claude Code (version unknown): ", report[report.index("--body") + 1])


if __name__ == "__main__":
    unittest.main()
