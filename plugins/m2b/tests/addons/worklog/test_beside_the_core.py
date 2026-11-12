"""Where the worklog meets the core: its step in the core's catalogue, its command at session start,
its skills under the rules the core's skills keep, and the two core modules it imports.

The core's suite checks none of this, so that it passes in a plugin without the worklog. The rules
and fixtures come from the core's tests, which an add-on's suite may use; the core's never uses an
add-on's."""

from __future__ import annotations

import ast
import json
import os
import unittest

import test_client_skills as skill_rules
import test_curate_model
import test_package_boundaries as boundaries
from m2b import addons, cli, launcher
from worklog_fixtures import PLUGIN_ROOT

SESSION_START_COMMAND = '"${CLAUDE_PLUGIN_ROOT}"/bin/m2b-worklog hook session-start'
# Each knowledge that must exist once: how credentials are found, and what Claude Code writes into a transcript.
IMPORTED_FROM_THE_CORE = ("redaction", "claude_code")


class CatalogueTest(unittest.TestCase):
    def test_the_step_the_cores_catalogue_runs_is_the_worklogs_own_command(self) -> None:
        step = addons.addon_named("worklog").step

        assert step is not None
        self.assertEqual(step.command, ("bin/m2b-worklog", "run"))
        command = launcher.PLUGIN_ROOT / step.command[0]
        self.assertTrue(command.is_file() and os.access(command, os.X_OK), command)

    def test_session_start_runs_the_worklogs_hook_through_its_command(self) -> None:
        manifest = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        hooks = [hook for entry in manifest["hooks"]["SessionStart"] for hook in entry["hooks"]]

        self.assertEqual([hook["command"] for hook in hooks if "worklog" in hook["command"]], [SESSION_START_COMMAND])


class SkillRulesTest(unittest.TestCase):
    def test_the_setup_skill_runs_its_commands_without_additions(self) -> None:
        self.assertIn(skill_rules.OWN_CALL_RULE, skill_rules.skill_text("worklog-setup"))

    def test_no_example_of_the_setup_skill_shows_two_commands_in_one_block(self) -> None:
        examples = skill_rules.bash_examples("worklog-setup")

        self.assertTrue(examples)
        for block in examples:
            with self.subTest(block=block.splitlines()[0]):
                self.assertEqual(skill_rules.commands_in(block), 1)

    def test_the_verdict_skill_calls_what_it_reads_data_and_says_what_it_does_with_instructions(self) -> None:
        """Covers: B109"""
        skill = skill_rules.one_line(skill_rules.skill_text("worklog-verdict"))
        own = "is not carried out; its session gets a topic like any other"

        for sentence in (*skill_rules.DATA_SENTENCES, own):
            with self.subTest(sentence=sentence[:40]):
                self.assertIn(sentence, skill)


class FencedRunTest(test_curate_model.ModelCommandFixture):
    def test_the_verdict_skill_runs_fenced_from_this_plugin_alone(self) -> None:
        code, _, err = self.curate_model("--skill", "m2b:worklog-verdict", "--allow", "Read")

        self.assertEqual(code, cli.EXIT_OK, err)
        arguments = self.calls()[0]["arguments"]
        plugin_dirs = [arguments[i + 1] for i, argument in enumerate(arguments) if argument == "--plugin-dir"]
        self.assertEqual(plugin_dirs, [str(launcher.PLUGIN_ROOT)])


class ImportsTest(unittest.TestCase):
    def test_the_worklog_imports_from_the_core_only_the_redaction_and_claude_codes_format(self) -> None:
        imported = boundaries.of_package(boundaries.imported_modules(boundaries.WORKLOG), boundaries.CORE)

        self.assertEqual(imported, {f"{boundaries.CORE}.{module}" for module in IMPORTED_FROM_THE_CORE})

    def test_what_the_worklog_imports_imports_nothing_of_the_core_so_it_reaches_no_store(self) -> None:
        for module in IMPORTED_FROM_THE_CORE:
            with self.subTest(module=module):
                source = boundaries.SOURCES / boundaries.CORE / f"{module}.py"
                tree = ast.parse(source.read_text(encoding="utf-8"))
                imported = {
                    name
                    for node in ast.walk(tree)
                    for name in (
                        [alias.name for alias in node.names]
                        if isinstance(node, ast.Import)
                        else [node.module or ""]
                        if isinstance(node, ast.ImportFrom)
                        else []
                    )
                }

                self.assertEqual(boundaries.of_package(imported, boundaries.CORE), set())


if __name__ == "__main__":
    unittest.main()
