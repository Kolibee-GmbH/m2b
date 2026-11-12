"""Fenced model runs: the one way the core and its add-ons start the model."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

import test_commands
from m2b import cli, launcher
from m2b.config.machine import load_machine_config
from m2b.curate import model, report

FAKE_CLAUDE = test_commands.FAKES / "fake_claude.py"
STUB_STORE_VARIABLE = "M2B_STUB_STORE"
CORE_BIN = launcher.PLUGIN_ROOT / "bin"


class StoreRulesTest(unittest.TestCase):
    STORE = Path("/Users/alex/Library/Mobile Documents/com~apple~CloudDocs/Brain")

    def test_store_names_the_real_folder_in_file_rules(self) -> None:
        rules = model.store_rules(
            ["Bash(m2b ingest *)", "Read(<store>/inbox/**)", "Edit(<store>/memory/**)", "Read"], self.STORE
        )

        self.assertEqual(
            rules,
            [
                "Bash(m2b ingest *)",
                f"Read(/{self.STORE}/inbox/**)",
                f"Edit(/{self.STORE}/memory/**)",
                "Read",
            ],
        )
        self.assertTrue(rules[1].startswith("Read(//Users/alex/"))

    def test_rules_that_do_not_parse_are_refused(self) -> None:
        for rule in ("", "Read(", "Bash(m2b search *), Read", "read file", "Bash()"):
            with self.subTest(rule=rule), self.assertRaises(model.FenceError):
                model.store_rules([rule], self.STORE)

    def test_store_outside_a_read_or_edit_rule_is_refused(self) -> None:
        for rule in ("Bash(cat <store>/inbox/x.md)", "Glob(<store>/**)", "Grep(<store>/**)"):
            with self.subTest(rule=rule), self.assertRaises(model.FenceError):
                model.store_rules([rule], self.STORE)

    def test_a_write_path_rule_is_refused_because_claude_code_reads_only_edit_rules_for_writes(self) -> None:
        """Measured with Claude Code 2.1.319 on 2026-11-07: Write(//path/**) leaves Write denied."""
        for rule in ("Write(<store>/memory/**)", "Write(//tmp/x/**)"):
            with self.subTest(rule=rule), self.assertRaisesRegex(model.FenceError, "Edit"):
                model.store_rules([rule], self.STORE)
        self.assertEqual(model.store_rules(["Write"], self.STORE), ["Write"])

    def test_store_must_lead_the_file_rule(self) -> None:
        with self.assertRaises(model.FenceError):
            model.store_rules(["Read(/tmp/<store>/**)"], self.STORE)

    def test_a_store_path_a_rule_cannot_hold_is_refused(self) -> None:
        for store in ("relative/store", "/Users/alex/Brain, old", "/Users/alex/[Brain]", "/Users/alex/Brain (2)"):
            with self.subTest(store=store), self.assertRaises(model.FenceError):
                model.store_rules(["Read(<store>/**)"], Path(store))

    def test_a_store_path_is_fine_in_rules_without_it(self) -> None:
        self.assertEqual(
            model.store_rules(["Bash(m2b search *)"], Path("/Users/alex/Brain (2)")), ["Bash(m2b search *)"]
        )


class StepToolsTest(unittest.TestCase):
    def test_a_step_has_the_tools_its_rules_name_and_write_with_edit(self) -> None:
        """Covers: B147"""
        rules = ["Bash(m2b ingest *)", "Bash(m2b search *)", "Read(//store/inbox/**)", "Edit(//store/memory/**)"]

        self.assertEqual(model.step_tools(rules), ["Bash", "Read", "Edit", "Write"])

    def test_a_read_rule_brings_neither_glob_nor_grep_and_another_tool_only_itself(self) -> None:
        """Covers: B147"""
        self.assertEqual(model.step_tools(["Read(//store/memory/**)"]), ["Read"])
        self.assertEqual(
            model.step_tools(["Read", "Grep", "WebFetch(domain:example.com)"]), ["Read", "Grep", "WebFetch"]
        )
        self.assertEqual(model.step_tools([]), [])

    def test_a_rule_that_does_not_parse_is_refused(self) -> None:
        with self.assertRaises(model.FenceError):
            model.step_tools(["read everything"])


class FencedCommandTest(unittest.TestCase):
    def test_the_fenced_form(self) -> None:
        """Covers: B61, B147"""
        command = model.fenced_command(
            "/opt/claude",
            "m2b:worklog-verdict",
            ["Bash(m2b tasks list *)", "Read(//store/memory/**)"],
            [Path("/plugins/m2b")],
            "haiku",
            40,
        )

        self.assertEqual(
            command,
            [
                "/opt/claude",
                "-p",
                "/m2b:worklog-verdict",
                "--setting-sources",
                "project",
                "--model",
                "haiku",
                "--max-turns",
                "40",
                "--plugin-dir",
                "/plugins/m2b",
                "--tools",
                "Bash,Read",
                "--strict-mcp-config",
                "--disallowedTools",
                "mcp__*",
                "--no-session-persistence",
                "--permission-mode",
                "dontAsk",
                "--permission-prompts",
                "none",
                "--allowedTools",
                "Bash(m2b tasks list *)",
                "Read(//store/memory/**)",
                "--output-format",
                "stream-json",
                "--verbose",
            ],
        )


class ModelCommandFixture(test_commands.CommandTest):
    """``m2b curate model`` with the scripted model in ``claude``'s place; an add-on's suite uses it too."""

    def setUp(self) -> None:
        super().setUp()
        self.set_up()
        self.actions = self.bin.parent / "model.json"
        self.stub([])
        self.environ[model.MODEL_RUNNER_VARIABLE] = self.fake_program("claude", "fake_claude.py", self.actions)
        self.environ["PATH"] = os.pathsep.join([str(CORE_BIN), os.environ.get("PATH", "")])
        self.environ["M2B_PYTHON"] = sys.executable
        self.environ[STUB_STORE_VARIABLE] = str(self.store_root)

    def stub(self, actions: list[dict[str, Any]], outcome: str = "success", start: object = None) -> None:
        script = {"actions": actions, "outcome": outcome, **({} if start is None else {"start": start})}
        self.actions.write_text(json.dumps(script), encoding="utf-8")

    def calls(self) -> list[dict[str, Any]]:
        calls_file = Path(f"{self.actions}.calls")
        if not calls_file.exists():
            return []
        return [json.loads(line) for line in calls_file.read_text(encoding="utf-8").splitlines()]

    def curate_model(self, *arguments: str) -> tuple[int, str, str]:
        return self.run_command("curate", "model", *arguments)


class ModelCommandTest(ModelCommandFixture):
    def test_the_curation_model_and_turn_limit_come_from_the_config(self) -> None:
        raw = json.loads(self.machine.config_file.read_text(encoding="utf-8"))
        raw["curation"] = {"model": "sonnet", "max_turns": 2}
        self.machine.config_file.write_text(json.dumps(raw), encoding="utf-8")
        self.stub([{"tool": "Bash", "command": "m2b search a"}] * 3)

        code, _, err = self.curate_model("--skill", "m2b:search", "--allow", "Bash(m2b search *)")

        self.assertEqual(code, cli.EXIT_PROBLEM)
        self.assertIn("turn limit (curation.max_turns", err)
        arguments = self.calls()[0]["arguments"]
        self.assertEqual(arguments[arguments.index("--model") + 1], "sonnet")
        self.assertEqual(arguments[arguments.index("--max-turns") + 1], "2")
        self.assertNotIn("--max-budget-usd", arguments)

    def test_a_spending_cap_in_the_config_is_passed_to_the_run(self) -> None:
        raw = json.loads(self.machine.config_file.read_text(encoding="utf-8"))
        raw["curation"] = {"max_budget_usd": 0.5}
        self.machine.config_file.write_text(json.dumps(raw), encoding="utf-8")
        self.stub([])

        self.curate_model("--skill", "m2b:search", "--allow", "Bash(m2b search *)")

        arguments = self.calls()[0]["arguments"]
        self.assertEqual(arguments[arguments.index("--max-budget-usd") + 1], "0.5")

    def test_a_step_stopped_at_its_spending_cap_names_the_setting(self) -> None:
        self.stub([], outcome="over-budget")

        code, _, err = self.curate_model("--skill", "m2b:search", "--allow", "Read")

        self.assertEqual(code, cli.EXIT_PROBLEM)
        self.assertIn("spending cap (curation.max_budget_usd", err)

    def test_the_model_starts_fenced_from_an_empty_folder_with_the_store_rules(self) -> None:
        code, out, err = self.curate_model(
            "--skill", "m2b:search", "--allow", "Bash(m2b search *)", "--allow", "Read(<store>/corpus/**)"
        )

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertIn("m2b:search: done", out)
        (call,) = self.calls()
        self.assertEqual(
            call["arguments"],
            model.fenced_command(
                self.environ[model.MODEL_RUNNER_VARIABLE],
                "m2b:search",
                ["Bash(m2b search *)", f"Read(/{self.store_root}/corpus/**)"],
                [launcher.PLUGIN_ROOT],
                "haiku",
                100,
            )[1:],
        )
        self.assertEqual(call["cwd_entries"], [])
        self.assertFalse(Path(call["cwd"]).exists())
        self.assertNotIn(Path(call["cwd"]).resolve(), [Path.cwd().resolve(), self.store_root.resolve()])
        self.assertEqual(call["environment"]["M2B_CURATION_RUN"], "1")
        self.assertRegex(call["environment"]["M2B_RUN_TOKEN"], r"^[0-9a-f]{32}$")

    def test_the_step_reads_no_claude_md_and_no_memory_of_claude_code(self) -> None:
        """Covers: B147"""
        self.environ["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] = "0"

        self.curate_model("--skill", "m2b:search", "--allow", "Read")

        environment = self.calls()[0]["environment"]
        self.assertEqual(environment["CLAUDE_CODE_DISABLE_CLAUDE_MDS"], "1")
        self.assertEqual(environment["CLAUDE_CODE_DISABLE_AUTO_MEMORY"], "1")

    def test_a_session_that_starts_with_another_tool_is_stopped_before_it_acts(self) -> None:
        """Covers: B147"""
        (self.store_root / "memory").mkdir()
        write = {"tool": "Write", "file_path": "<store>/memory/notes.md", "content": "Dana likes tea\n"}
        started_with = {"tools": ["Read", "Edit", "Write", "SendMessage", "Agent"]}
        self.stub([{"sleep": 5}, write], start=started_with)

        started = time.monotonic()
        code, _, err = self.curate_model(
            "--skill", "m2b:search", "--allow", "Edit(<store>/memory/**)", "--allow", "Read"
        )

        self.assertEqual(code, cli.EXIT_PROBLEM)
        self.assertLess(time.monotonic() - started, 4)
        self.assertIn("Claude Code gave the model step the tools Agent, SendMessage, which its fence leaves out", err)
        self.assertFalse((self.store_root / "memory" / "notes.md").exists())

    def test_a_session_that_starts_with_an_mcp_server_is_stopped(self) -> None:
        """Covers: B147"""
        self.stub([], start={"mcp_servers": [{"name": "claude.ai Mail", "status": "pending"}]})

        code, _, err = self.curate_model("--skill", "m2b:search", "--allow", "Read")

        self.assertEqual(code, cli.EXIT_PROBLEM)
        self.assertIn("gave the model step the MCP server claude.ai-Mail, which its fence leaves out", err)

    def test_what_a_session_has_beyond_its_fence_is_named_briefly(self) -> None:
        """Covers: B147"""
        more = ["Agent", "CronCreate", "CronList", "ListAgents", "Monitor", "SendMessage", "Workflow"]
        self.stub([], start={"tools": ["Read", *reversed(more)], "mcp_servers": [{"status": "pending"}]})

        code, _, err = self.curate_model("--skill", "m2b:search", "--allow", "Read")

        self.assertEqual(code, cli.EXIT_PROBLEM)
        self.assertIn(
            "the tools Agent, CronCreate, CronList, ListAgents, Monitor and 2 more and the MCP server without a name, ",
            err,
        )

    def test_a_run_that_does_not_say_which_tools_it_had_fails(self) -> None:
        """Covers: B147"""
        for start in ("silent", {"tools": None}, {"mcp_servers": None}, {"mcp_servers": "none"}):
            with self.subTest(start=start):
                self.stub([], start=start)

                code, _, err = self.curate_model("--skill", "m2b:search", "--allow", "Read")

                self.assertEqual(code, cli.EXIT_PROBLEM)
                self.assertIn("did not say which tools and MCP servers it had", err)

    def test_a_run_without_a_login_still_says_so_when_it_did_not_say_its_tools(self) -> None:
        self.stub([], outcome="not-logged-in", start="silent")

        code, _, err = self.curate_model("--skill", "m2b:search", "--allow", "Read")

        self.assertEqual(code, cli.EXIT_PROBLEM)
        self.assertIn("Not logged in", err)
        self.assertNotIn("which tools", err)

    def test_a_call_of_a_tool_the_step_does_not_have_fails_it_like_a_denial(self) -> None:
        """Covers: B147"""
        self.stub(
            [
                {"tool": "WebFetch", "url": "https://example.com/a?b"},
                {"tool": "Grep", "pattern": "tea", "path": "<store>/corpus"},
                {"tool": "Read", "file_path": "<store>/corpus/x.md"},
            ]
        )

        code, out, err = self.curate_model("--skill", "m2b:search", "--allow", "Read(<store>/corpus/**)")

        self.assertEqual(code, cli.EXIT_PROBLEM)
        self.assertIn(
            'action: search: the model step m2b:search was denied WebFetch: {"url": "https://example.com/a?b"}', out
        )
        self.assertIn("action: search: the model step m2b:search was denied Grep: tea", out)
        self.assertNotIn("denied Read", out)
        self.assertIn("denied 2 tool call", err)

    def test_an_unknown_skill_or_one_of_a_plugin_not_loaded_exits_2(self) -> None:
        for skill in ("m2b:nothing-here", "worklog:verdict", "search", "m2b:../search"):
            with self.subTest(skill=skill):
                code, _, _ = self.curate_model("--skill", skill, "--allow", "Read")
                self.assertEqual(code, cli.EXIT_USAGE)
        self.assertEqual(self.calls(), [])

    def test_a_denied_tool_call_fails_the_step_and_is_reported(self) -> None:
        """E10 at unit level: the write outside the step's rules is denied and never happens. Covers: B61"""
        self.stub([{"tool": "Write", "file_path": "<store>/memory/notes.md", "content": "Dana likes tea\n"}])

        code, out, err = self.curate_model("--skill", "m2b:search", "--allow", "Read(<store>/**)")

        self.assertEqual(code, cli.EXIT_PROBLEM)
        self.assertFalse((self.store_root / "memory" / "notes.md").exists())
        self.assertIn("action: search: the model step m2b:search was denied Write", out)
        self.assertIn(f"{self.store_root}/memory/notes.md", out)
        self.assertIn("denied 1 tool call", err)

    def test_an_allowed_tool_call_is_carried_out(self) -> None:
        (self.store_root / "memory").mkdir()
        self.stub([{"tool": "Write", "file_path": "<store>/memory/notes.md", "content": "Dana likes tea\n"}])

        code, _, err = self.curate_model("--skill", "m2b:search", "--allow", "Edit(<store>/memory/**)")

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual((self.store_root / "memory" / "notes.md").read_text(encoding="utf-8"), "Dana likes tea\n")

    def test_a_read_outside_the_rules_is_denied_although_it_is_in_the_store(self) -> None:
        """Without --add-dir the store is not readable as a whole; only the step's Read rules open it."""
        self.stub([{"tool": "Read", "file_path": "<store>/store.json"}])

        code, out, _ = self.curate_model("--skill", "m2b:search", "--allow", "Read(<store>/corpus/**)")

        self.assertEqual(code, cli.EXIT_PROBLEM)
        self.assertIn("denied Read", out)

    def test_glob_and_grep_come_only_with_a_rule_of_their_own_which_allows_them_on_every_path(self) -> None:
        (self.store_root / "corpus").mkdir()
        self.stub(
            [
                {"tool": "Grep", "pattern": "tea", "path": "<store>/corpus"},
                {"tool": "Glob", "pattern": "**/*.md", "path": "<store>/corpus"},
            ]
        )

        code, _, err = self.curate_model("--skill", "m2b:search", "--allow", "Glob", "--allow", "Grep")

        self.assertEqual(code, cli.EXIT_OK, err)

    def test_an_edit_replaces_its_text_once_and_a_capture_placeholder_names_the_generated_file(self) -> None:
        (self.store_root / "memory").mkdir()
        (self.store_root / "memory" / "MEMORY.md").write_text("# Memory\n\n## Facts\n\n## Current\n", encoding="utf-8")
        (self.store_root / "inbox").mkdir()
        (self.store_root / "inbox" / "20261107T091500Z-cli-a1b2.md").write_text("x\n", encoding="utf-8")
        self.stub(
            [
                {
                    "tool": "Edit",
                    "file_path": "<store>/memory/MEMORY.md",
                    "old_string": "## Facts\n\n",
                    "new_string": "## Facts\n\n- From <capture:cli> (x.md)\n",
                },
                {"tool": "Edit", "file_path": "<store>/memory/MEMORY.md", "old_string": "absent", "new_string": "y"},
            ]
        )

        code, _, err = self.curate_model("--skill", "m2b:search", "--allow", "Edit(<store>/memory/**)")

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(
            (self.store_root / "memory" / "MEMORY.md").read_text(encoding="utf-8"),
            "# Memory\n\n## Facts\n\n- From 20261107T091500Z-cli-a1b2.md (x.md)\n## Current\n",
        )

    def test_the_model_step_reports_through_the_run_token_and_a_lone_run_prints_the_findings(self) -> None:
        self.stub(
            [{"tool": "Bash", "command": "m2b curate report --step search --kind info --text 'two notes skipped'"}]
        )

        code, out, err = self.curate_model("--skill", "m2b:search", "--allow", "Bash(m2b curate report *)")

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertIn("info: search: two notes skipped", out)
        self.assertEqual(list((self.machine.state_dir / "runs").iterdir()), [])

    def test_inside_a_run_the_findings_stay_with_the_run(self) -> None:
        token = report.open_run(self.machine)
        self.environ[report.RUN_TOKEN_VARIABLE] = token
        self.stub([{"tool": "Bash", "command": "cat <store>/store.json"}])

        code, out, _ = self.curate_model("--skill", "m2b:search", "--allow", "Bash(m2b search *)")

        self.assertEqual(code, cli.EXIT_PROBLEM)
        self.assertEqual(self.calls()[0]["environment"]["M2B_RUN_TOKEN"], token)
        (finding,) = report.read_findings(self.machine, token)
        self.assertEqual((finding.step, finding.kind), ("search", "action"))
        self.assertIn(f"denied Bash: cat {self.store_root}/store.json", finding.text)
        self.assertNotIn("denied Bash", out)

    def test_a_run_token_without_an_open_run_exits_2(self) -> None:
        self.environ[report.RUN_TOKEN_VARIABLE] = "0" * 32

        code, _, _ = self.curate_model("--skill", "m2b:search", "--allow", "Read")

        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertEqual(self.calls(), [])

    def test_a_run_that_ends_in_an_error_fails_the_step(self) -> None:
        for outcome, expected in (("error", "error_during_execution"), ("no-result", "fake claude: crashed")):
            with self.subTest(outcome=outcome):
                self.stub([], outcome=outcome)
                code, _, err = self.curate_model("--skill", "m2b:search", "--allow", "Read")
                self.assertEqual(code, cli.EXIT_PROBLEM)
                self.assertIn(expected, err)

    def test_a_run_without_a_login_says_so_and_what_to_do(self) -> None:
        self.stub([], outcome="not-logged-in")

        code, _, err = self.curate_model("--skill", "m2b:search", "--allow", "Read")

        self.assertEqual(code, cli.EXIT_PROBLEM)
        self.assertIn("Not logged in", err)
        self.assertIn("claude", err)
        self.assertIn("ANTHROPIC_API_KEY", err)
        self.assertNotIn("ended with success", err)

    def test_a_missing_claude_exits_3(self) -> None:
        self.environ[model.MODEL_RUNNER_VARIABLE] = str(self.bin / "no-such-claude")

        code, _, err = self.curate_model("--skill", "m2b:search", "--allow", "Read")

        self.assertEqual(code, cli.EXIT_UNREACHABLE)
        self.assertIn("no-such-claude", err)

    def test_claude_comes_from_the_config_without_the_runner_variable(self) -> None:
        runner = self.environ.pop(model.MODEL_RUNNER_VARIABLE)
        self.set_up(executables={"claude": runner})

        code, _, err = self.curate_model("--skill", "m2b:search", "--allow", "Read")

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(len(self.calls()), 1)


class TextCommandTest(unittest.TestCase):
    def test_the_run_without_tools_gives_the_model_nothing_to_call_and_keeps_no_session(self) -> None:
        """Covers: B61"""
        command = model.text_command("claude", "read this", "haiku")

        self.assertEqual(command[:3], ["claude", "-p", "read this"])
        for flag, value in (
            ("--model", "haiku"),
            ("--setting-sources", "project"),
            ("--tools", ""),
            ("--permission-mode", "dontAsk"),
            ("--max-turns", "1"),
            ("--output-format", "json"),
        ):
            with self.subTest(flag=flag):
                self.assertEqual(command[command.index(flag) + 1], value)
        for flag in ("--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"):
            with self.subTest(flag=flag):
                self.assertIn(flag, command)
        for flag in ("--plugin-dir", "--allowedTools", "--max-budget-usd"):
            with self.subTest(flag=flag):
                self.assertNotIn(flag, command)

    def test_a_spending_cap_is_passed_to_the_run(self) -> None:
        command = model.text_command("claude", "read this", "haiku", max_budget_usd=0.5)

        self.assertEqual(command[command.index("--max-budget-usd") + 1], "0.5")


class RunTextTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.actions = self.folder / "model.json"
        self.work = self.folder / "work"
        self.work.mkdir()

    def ask(self, script: dict[str, Any], text: str = "the input", timeout_seconds: float = 30) -> model.TextRun:
        self.actions.write_text(json.dumps(script), encoding="utf-8")
        command = model.text_command(sys.executable, "read this", "haiku")
        command[1:1] = [str(FAKE_CLAUDE), str(self.actions)]
        return model.run_text(command, text, self.work, dict(os.environ), timeout_seconds, grace_seconds=1)

    def given(self) -> str:
        lines = Path(f"{self.actions}.calls").read_text(encoding="utf-8").splitlines()
        return str(json.loads(lines[-1])["stdin"])

    def test_the_answer_comes_back_with_the_model_that_gave_it(self) -> None:
        run = self.ask({"answer": '{"proposals": []}'})

        self.assertEqual((run.answer, run.model, run.error, run.detail), ('{"proposals": []}', "fake-model", None, ""))

    def test_the_text_reaches_the_model_on_standard_input_whatever_its_size(self) -> None:
        text = "Dana runs IT at Northwind. " * 20000

        run = self.ask({"answer": "read"}, text)

        self.assertIsNone(run.error)
        self.assertEqual(self.given(), text)

    def test_half_a_character_in_the_text_does_not_stop_the_run(self) -> None:
        run = self.ask({"answer": "read"}, "half \ud83d of an emoji")

        self.assertIsNone(run.error)
        self.assertEqual(self.given(), "half ? of an emoji")

    def test_a_run_that_prints_no_result_is_an_error_with_no_answer(self) -> None:
        run = self.ask({"outcome": "no-result"})

        self.assertEqual((run.answer, run.error), (None, "exit 1 without a result"))
        self.assertIn("fake claude: crashed", run.detail)

    def test_a_run_that_ends_in_an_error_gives_no_answer_and_keeps_what_was_said_apart(self) -> None:
        run = self.ask({"outcome": "error"})

        self.assertEqual((run.answer, run.error), (None, "the model run failed (error_during_execution)"))
        self.assertEqual(run.detail, "the run broke")
        self.assertEqual(run.failure(), "the model run failed (error_during_execution): the run broke")

    def test_a_run_without_a_login_says_so_and_what_to_do(self) -> None:
        run = self.ask({"outcome": "not-logged-in"})

        self.assertEqual(
            (run.answer, run.error, run.detail), (None, "the model run failed", "Not logged in · Please run /login")
        )
        self.assertEqual(
            run.failure(),
            "the model run failed: Not logged in · Please run /login. Claude Code has no login for this run: "
            "run claude once and sign in with /login, or set ANTHROPIC_API_KEY, which bills the API instead "
            "of a subscription",
        )

    def test_a_result_that_is_not_text_is_no_answer(self) -> None:
        run = self.ask({"outcome": "not-text"})

        self.assertEqual((run.answer, run.error, run.failure()), (None, "the model run failed", "the model run failed"))

    def test_a_run_stopped_at_its_spending_cap_names_the_setting(self) -> None:
        run = self.ask({"outcome": "over-budget"})

        self.assertIn("curation.max_budget_usd", run.error or "")

    def test_a_run_past_its_timeout_is_stopped(self) -> None:
        started = time.monotonic()

        run = self.ask({"answer": "late", "sleep": 30}, timeout_seconds=1)

        self.assertLess(time.monotonic() - started, 10)
        self.assertEqual((run.answer, run.error), (None, "timed out after 1 seconds"))

    def test_a_command_that_cannot_be_started_is_a_model_out_of_reach(self) -> None:
        with self.assertRaises(model.ModelUnreachableError):
            model.run_text([str(self.folder / "no-such-claude")], "the input", self.work, dict(os.environ), 30)


class TextStepTest(test_commands.CommandTest):
    def setUp(self) -> None:
        super().setUp()
        self.actions = self.bin.parent / "model.json"
        self.actions.write_text(json.dumps({"answer": "an answer"}), encoding="utf-8")
        self.environ[model.MODEL_RUNNER_VARIABLE] = self.fake_program("claude", "fake_claude.py", self.actions)

    def call(self) -> dict[str, Any]:
        lines = Path(f"{self.actions}.calls").read_text(encoding="utf-8").splitlines()
        return dict(json.loads(lines[-1]))

    def test_the_step_asks_the_curation_model_from_an_empty_folder_inside_the_run(self) -> None:
        """Covers: B61"""
        self.set_up(curation={"model": "sonnet", "max_budget_usd": 0.5})
        config = load_machine_config(self.machine)

        run = model.text_step(config, self.machine, self.environ, "read this", "the input")

        self.assertEqual((run.answer, run.error), ("an answer", None))
        call = self.call()
        arguments = call["arguments"]
        self.assertEqual(arguments[:2], ["-p", "read this"])
        self.assertEqual(arguments[arguments.index("--model") + 1], "sonnet")
        self.assertEqual(arguments[arguments.index("--max-budget-usd") + 1], "0.5")
        self.assertEqual(call["stdin"], "the input")
        self.assertEqual(call["cwd_entries"], [])
        self.assertTrue(Path(call["cwd"]).resolve().is_relative_to(self.machine.temp_dir.resolve()))
        self.assertFalse(Path(call["cwd"]).exists())
        self.assertEqual(call["environment"]["M2B_CURATION_RUN"], "1")

    def test_the_step_reads_no_claude_md_and_no_memory_of_claude_code(self) -> None:
        """Covers: B147"""
        self.set_up()

        model.text_step(load_machine_config(self.machine), self.machine, self.environ, "read this", "x")

        environment = self.call()["environment"]
        self.assertEqual(environment["CLAUDE_CODE_DISABLE_CLAUDE_MDS"], "1")
        self.assertEqual(environment["CLAUDE_CODE_DISABLE_AUTO_MEMORY"], "1")

    def test_claude_comes_from_the_config_without_the_runner_variable(self) -> None:
        runner = self.environ.pop(model.MODEL_RUNNER_VARIABLE)
        self.set_up(executables={"claude": runner})

        run = model.text_step(load_machine_config(self.machine), self.machine, self.environ, "read this", "x")

        self.assertEqual(run.answer, "an answer")


class TimeoutTest(unittest.TestCase):
    def test_a_run_past_its_timeout_is_killed_with_its_children(self) -> None:
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        pid_file = folder / "child.pid"
        actions = folder / "model.json"
        actions.write_text(json.dumps({"actions": [{"hang": str(pid_file)}]}), encoding="utf-8")
        work = folder / "work"
        work.mkdir()

        started = time.monotonic()
        run = model.run_model(
            [sys.executable, str(FAKE_CLAUDE), str(actions)],
            [],
            work,
            dict(os.environ),
            timeout_seconds=1,
            grace_seconds=1,
        )

        self.assertLess(time.monotonic() - started, 10)
        self.assertIsNotNone(run.error)
        self.assertIn("timed out", run.error or "")
        child = int(pid_file.read_text(encoding="utf-8"))
        deadline = time.monotonic() + 5
        while _alive(child) and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertFalse(_alive(child))


class NestedStopTest(unittest.TestCase):
    def test_a_supervisor_stopped_by_sigterm_stops_the_group_it_supervises(self) -> None:
        """A module step that runs a model step: stopping the module must stop the model too."""
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        pid_file = folder / "child.pid"
        actions = folder / "model.json"
        actions.write_text(json.dumps({"actions": [{"hang": str(pid_file)}]}), encoding="utf-8")
        work = folder / "work"
        work.mkdir()
        inner = (
            "import os, sys; from pathlib import Path; from m2b.curate import model; "
            f"model.run_model([sys.executable, {str(FAKE_CLAUDE)!r}, {str(actions)!r}], [], Path({str(work)!r}), "
            "dict(os.environ), timeout_seconds=600)"
        )
        environ = {**os.environ, "PYTHONPATH": str(launcher.PLUGIN_ROOT / "src")}

        end = model.run_supervised([sys.executable, "-c", inner], work, environ, timeout_seconds=3, grace_seconds=5)

        self.assertTrue(end.timed_out)
        self.assertTrue(pid_file.exists(), "the inner model never started")
        child = int(pid_file.read_text(encoding="utf-8"))
        deadline = time.monotonic() + 5
        while _alive(child) and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertFalse(_alive(child))


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


if __name__ == "__main__":
    unittest.main()
