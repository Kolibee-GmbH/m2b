from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from repo_tools import fenced_claude, trigger_check

# Answers like `claude -p --output-format stream-json`: the skill named after "skill:" in the
# prompt, nothing for "none", and a crash for "crash"; it records its arguments and environment.
FAKE_CLAUDE = """#!{python}
import json, os, sys
prompt = sys.argv[sys.argv.index("-p") + 1]
with open(os.environ["FAKE_CLAUDE_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps({{"argv": sys.argv[1:], "cwd": os.getcwd(), "m2b_home": os.environ.get("M2B_HOME")}}) + "\\n")
if prompt == "crash":
    print("boom", file=sys.stderr)
    sys.exit(1)
print(json.dumps({{"type": "system", "subtype": "init", "skills": ["m2b:capture", "m2b:search"]}}))
print(json.dumps({{"type": "assistant", "message": {{"content": [{{"type": "text", "text": "ok"}}]}}}}))
if prompt.startswith("skill:"):
    tool = {{"type": "tool_use", "name": "Skill", "input": {{"skill": prompt[len("skill:"):]}}}}
    print(json.dumps({{"type": "assistant", "message": {{"content": [tool]}}}}), flush=True)
print(json.dumps({{"type": "result", "subtype": "success"}}))
"""


class FencedClaudeTest(unittest.TestCase):
    def test_the_command_is_the_fenced_form(self) -> None:
        command = fenced_claude.fenced_command("note this", Path("/repo/plugins/m2b"), claude="claude")

        self.assertEqual(command[:3], ["claude", "-p", "note this"])
        for flag, value in (
            ("--setting-sources", "project"),
            ("--plugin-dir", "/repo/plugins/m2b"),
            ("--permission-mode", "dontAsk"),
            ("--output-format", "stream-json"),
        ):
            with self.subTest(flag=flag):
                self.assertEqual(command[command.index(flag) + 1], value)
        self.assertIn("--verbose", command)
        self.assertNotIn("--allowedTools", command)

    def test_the_first_skill_call_is_found_in_the_stream(self) -> None:
        lines = [
            json.dumps({"type": "system", "subtype": "init"}),
            "not json",
            json.dumps(
                {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {}}]}}
            ),
            json.dumps(
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": "m2b:todos"}}]},
                }
            ),
        ]

        self.assertEqual(fenced_claude.skill_in(lines[3]), "m2b:todos")
        self.assertEqual([fenced_claude.skill_in(line) for line in lines[:3]], [None, None, None])

    def test_the_skills_the_session_loaded_are_read_from_the_init_line(self) -> None:
        line = json.dumps({"type": "system", "subtype": "init", "skills": ["m2b:capture", "loop"]})

        self.assertEqual(fenced_claude.loaded_skills_in(line), ["m2b:capture", "loop"])
        self.assertIsNone(fenced_claude.loaded_skills_in(json.dumps({"type": "result"})))


class TriggerCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        self.claude = self.root / "claude"
        self.claude.write_text(FAKE_CLAUDE.format(python=sys.executable), encoding="utf-8")
        self.claude.chmod(0o755)
        self.log = self.root / "claude-log.jsonl"
        self.environ = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(self.root / "real-home"),
            "FAKE_CLAUDE_LOG": str(self.log),
        }

    def phrases(self, skills: dict[str, dict[str, list[str]]]) -> Path:
        path = self.root / "phrases.json"
        path.write_text(json.dumps({"skills": skills}), encoding="utf-8")
        return path

    def run_main(self, *arguments: str) -> tuple[int, str]:
        """Runs in a sandbox of its own, never in the folder a real check may be using right now."""
        work_root = () if "--work-root" in arguments else ("--work-root", str(self.root / "sandbox"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = trigger_check.main([*arguments, *work_root, "--claude", str(self.claude)], self.environ)
        return code, out.getvalue()

    def test_every_phrase_hitting_its_skill_passes(self) -> None:
        phrases = self.phrases({"m2b:capture": {"en": ["skill:m2b:capture"], "de": ["skill:m2b:capture"]}})

        code, out = self.run_main("--phrases", str(phrases), "--jobs", "2")

        self.assertEqual(code, trigger_check.EXIT_PASSED, out)
        self.assertIn("2 of 2 phrases triggered their skill", out)

    def test_a_wrong_skill_and_no_skill_are_misses_named_with_the_phrase(self) -> None:
        phrases = self.phrases({"m2b:search": {"en": ["skill:m2b:capture", "none"], "de": ["skill:m2b:search"]}})

        code, out = self.run_main("--phrases", str(phrases))

        self.assertEqual(code, trigger_check.EXIT_FAILED)
        self.assertIn("miss m2b:search en: 'skill:m2b:capture' -> m2b:capture", out)
        self.assertIn("miss m2b:search en: 'none' -> no skill", out)
        self.assertIn("1 of 3 phrases triggered their skill", out)

    def test_a_run_that_fails_is_an_error_not_a_miss(self) -> None:
        phrases = self.phrases({"m2b:todos": {"en": ["crash"], "de": []}})

        code, out = self.run_main("--phrases", str(phrases))

        self.assertEqual(code, trigger_check.EXIT_FAILED)
        self.assertIn("error m2b:todos en: 'crash'", out)
        self.assertIn("boom", out)

    def test_each_run_is_fenced_in_an_empty_folder_with_a_test_store(self) -> None:
        phrases = self.phrases({"m2b:capture": {"en": ["skill:m2b:capture"], "de": []}})

        self.run_main("--phrases", str(phrases))

        (call,) = [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(Path(call["cwd"]).resolve(), (self.root / "sandbox" / "work").resolve())
        self.assertIn("--setting-sources", call["argv"])
        self.assertEqual(os.listdir(call["cwd"]), [])
        config = json.loads((Path(call["m2b_home"]) / ".config" / "m2b" / "config.json").read_text(encoding="utf-8"))
        self.assertTrue(Path(config["store"]["path"]).name.startswith("sb-test-"))

    def test_one_skill_and_one_language_can_be_picked(self) -> None:
        phrases = self.phrases(
            {"m2b:capture": {"en": ["skill:m2b:capture"], "de": ["none"]}, "m2b:todos": {"en": ["none"], "de": []}}
        )

        code, out = self.run_main("--phrases", str(phrases), "--skill", "m2b:capture", "--language", "en")

        self.assertEqual(code, trigger_check.EXIT_PASSED, out)
        self.assertIn("1 of 1 phrases", out)

    def test_the_real_store_is_refused(self) -> None:
        real_config = Path(self.environ["HOME"]) / ".config" / "m2b" / "config.json"
        real_config.parent.mkdir(parents=True)
        real_config.write_text(
            json.dumps({"version": 1, "machine_id": "m", "store": {"backend": "folder", "path": str(self.root)}}),
            encoding="utf-8",
        )
        phrases = self.phrases({"m2b:capture": {"en": ["skill:m2b:capture"], "de": []}})

        code, out = self.run_main("--phrases", str(phrases), "--work-root", str(self.root / "sandbox"))

        self.assertEqual(code, trigger_check.EXIT_REFUSED, out)
        self.assertFalse(self.log.exists())

    def test_a_real_store_inside_the_work_folder_is_refused_and_kept(self) -> None:
        work_root = self.root / "sandbox"
        real_store = work_root / "notes"
        real_store.mkdir(parents=True)
        real_config = Path(self.environ["HOME"]) / ".config" / "m2b" / "config.json"
        real_config.parent.mkdir(parents=True)
        real_config.write_text(
            json.dumps({"version": 1, "machine_id": "m", "store": {"backend": "folder", "path": str(real_store)}}),
            encoding="utf-8",
        )
        phrases = self.phrases({"m2b:capture": {"en": ["skill:m2b:capture"], "de": []}})

        code, _ = self.run_main("--phrases", str(phrases), "--work-root", str(work_root))

        self.assertEqual(code, trigger_check.EXIT_REFUSED)
        self.assertTrue(real_store.is_dir())

    def test_a_skill_or_language_that_selects_no_phrase_is_a_usage_error(self) -> None:
        phrases = self.phrases({"m2b:capture": {"en": ["skill:m2b:capture"], "de": []}})

        for arguments in (("--skill", "capture"), ("--skill", "m2b:capture", "--language", "de")):
            with self.subTest(arguments=arguments):
                code, out = self.run_main("--phrases", str(phrases), *arguments)
                self.assertEqual(code, trigger_check.EXIT_USAGE, out)
                self.assertIn("no phrases", out)
        self.assertFalse(self.log.exists())


class PhraseFileTest(unittest.TestCase):
    def test_the_repository_phrases_hold_ten_per_language_for_each_client_skill(self) -> None:
        skills = json.loads(trigger_check.PHRASES.read_text(encoding="utf-8"))["skills"]

        self.assertEqual(sorted(skills), ["m2b:capture", "m2b:rediscover", "m2b:search", "m2b:todos"])
        for skill, languages in skills.items():
            for language in ("en", "de"):
                with self.subTest(skill=skill, language=language):
                    self.assertEqual(len(languages[language]), 10)
                    self.assertEqual(len(set(languages[language])), 10)


if __name__ == "__main__":
    unittest.main()
