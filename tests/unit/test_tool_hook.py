"""The tool hook: before a Bash call, the action lessons whose words the command holds."""

from __future__ import annotations

import dataclasses
import datetime
import io
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from locations import PLUGIN_ROOT
from m2b import action_lessons, cli, paths, session_remotes, tool_hook
from m2b.config import machine
from m2b.lessons import ACTION, EVERY_PROJECT, KNOWLEDGE, Lesson

PROOF = Lesson(
    "proof.md",
    "Run the whole proof only when the change gives a reason.",
    ACTION,
    EVERY_PROJECT,
    "2026-11-20",
    words=("scripts/check",),
    unless=("--quick",),
)
PUSH = Lesson("push.md", "Never push to main.", ACTION, "github.com/acme/portal", "2026-11-20", words=("git push",))


class ToolHookFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="sb-test-tool-hook-")
        self.addCleanup(self._temp.cleanup)
        self.base = Path(self._temp.name)
        self.machine = paths.MachinePaths(self.base / "m2b-home")
        store = self.base / "sb-test-store"
        store.mkdir()
        machine.save_machine_config(
            self.machine, {"version": 1, "machine_id": "sb-test-m1", "store": {"backend": "folder", "path": str(store)}}
        )
        self.environ = {"HOME": str(self.base / "user-home"), "M2B_HOME": str(self.base / "m2b-home")}
        self.clone = self.base / "code" / "acme-portal"
        self.clone.mkdir(parents=True)

    def kept(self, *found: Lesson) -> None:
        action_lessons.note(self.machine, found)

    def noted_remote(self, folder: Path, remote: str) -> None:
        session_remotes.note(
            self.machine.state_dir / session_remotes.NOTES_FOLDER,
            str(folder),
            frozenset({remote}),
            datetime.datetime.now(datetime.timezone.utc),
            lambda path, text: path.write_text(text, encoding="utf-8"),
            top=str(folder),
        )

    def call(
        self,
        command: str,
        folder: Path | None = None,
        tool: str = "Bash",
        session: str | None = None,
        **environ: str,
    ) -> dict[str, object]:
        given: dict[str, object] = {
            "tool_name": tool,
            "tool_input": {"command": command},
            "cwd": str(folder or self.clone),
        }
        if session is not None:
            given["session_id"] = session
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            code = tool_hook.main({**self.environ, **environ}, io.StringIO(json.dumps(given)))
        self.assertEqual(code, 0)
        printed = out.getvalue()
        return json.loads(printed) if printed else {}


class RemindTest(ToolHookFixture):
    def test_a_lesson_for_every_project_comes_before_its_command_in_any_repository(self) -> None:
        """Covers: B263"""
        self.kept(PROOF)

        answer = self.call("scripts/check")

        output = answer["hookSpecificOutput"]
        assert isinstance(output, dict)
        self.assertEqual(output["hookEventName"], "PreToolUse")
        self.assertIn(PROOF.text, output["additionalContext"])
        self.assertIn("the owner corrected Claude on it and kept the correction", output["additionalContext"])
        self.assertNotIn("permissionDecision", output)

    def test_a_word_that_must_not_be_there_keeps_the_lesson_silent(self) -> None:
        """Covers: B263"""
        self.kept(PROOF)

        self.assertEqual(self.call("scripts/check --quick m2b"), {})

    def test_a_word_inside_a_longer_word_does_not_fire_or_silence(self) -> None:
        """Covers: B263"""
        self.kept(PROOF)

        self.assertEqual(self.call("myscripts/checker"), {})
        self.assertEqual(self.call("scripts/checkout.sh"), {})
        self.assertIn(PROOF.text, json.dumps(self.call("./scripts/check --quickly")))

    def test_the_session_folder_decides_the_repository_after_a_cd(self) -> None:
        """Covers: B263"""
        self.kept(PUSH)
        self.noted_remote(self.clone, "git@github.com:acme/portal.git")
        below = self.clone / "src"
        below.mkdir()

        self.assertIn(
            "Never push to main.", json.dumps(self.call("git push", below, CLAUDE_PROJECT_DIR=str(self.clone)))
        )

    def test_a_command_without_the_words_adds_nothing(self) -> None:
        """Covers: B263"""
        self.kept(PROOF)

        self.assertEqual(self.call("git status"), {})

    def test_a_lesson_for_one_project_comes_only_in_a_clone_of_it(self) -> None:
        """Covers: B263"""
        self.kept(PUSH)
        shop = self.base / "code" / "acme-shop"
        shop.mkdir()
        self.noted_remote(self.clone, "git@github.com:acme/portal.git")
        self.noted_remote(shop, "git@github.com:acme/shop.git")

        self.assertIn("Never push to main.", json.dumps(self.call("git push origin main", self.clone)))
        self.assertEqual(self.call("git push origin main", shop), {})

    def test_a_lesson_set_to_ask_has_claude_code_ask_the_owner(self) -> None:
        """Covers: B264"""
        asking = Lesson(PROOF.name, PROOF.text, ACTION, EVERY_PROJECT, PROOF.kept, words=PROOF.words, ask=True)
        self.kept(asking)

        output = self.call("scripts/check")["hookSpecificOutput"]
        assert isinstance(output, dict)

        self.assertEqual(output["permissionDecision"], "ask")
        self.assertIn(PROOF.text, output["permissionDecisionReason"])

    def test_a_knowledge_lesson_is_no_action_lesson(self) -> None:
        """Covers: B263"""
        self.kept(Lesson("k.md", "Say it once.", KNOWLEDGE, EVERY_PROJECT, "2026-11-20"))

        self.assertEqual(self.call("scripts/check"), {})

    def test_another_tool_adds_nothing(self) -> None:
        """Covers: B263"""
        self.kept(PROOF)

        self.assertEqual(self.call("scripts/check", tool="Read"), {})


class SilentTest(ToolHookFixture):
    def test_on_any_error_the_hook_adds_nothing_and_lets_the_call_run(self) -> None:
        """Covers: B265"""
        self.machine.state_dir.mkdir(parents=True, exist_ok=True)
        (self.machine.state_dir / action_lessons.FILE).write_text("{not json", encoding="utf-8")

        self.assertEqual(self.call("scripts/check"), {})

        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            self.assertEqual(tool_hook.main(self.environ, io.StringIO("not json")), 0)
        self.assertEqual(out.getvalue(), "")

    def test_inside_a_curation_run_it_adds_nothing(self) -> None:
        """Covers: B265"""
        self.kept(PROOF)

        self.assertEqual(self.call("scripts/check", M2B_CURATION_RUN="1"), {})

    def test_where_the_owner_turned_m2b_off_it_adds_nothing(self) -> None:
        """Covers: B265"""
        self.kept(PROOF)
        config = json.loads(self.machine.config_file.read_text(encoding="utf-8"))
        config["distillate"] = {"skip_under": [str(self.base / "code")]}
        self.machine.config_file.write_text(json.dumps(config), encoding="utf-8")

        self.assertEqual(self.call("scripts/check"), {})

    def test_the_hook_answers_from_its_own_small_command(self) -> None:
        """Covers: B265"""
        self.kept(PROOF)
        given = json.dumps({"tool_name": "Bash", "tool_input": {"command": "scripts/check"}, "cwd": str(self.clone)})
        command = [str(PLUGIN_ROOT / "bin" / "m2b-tool-hook")]
        subprocess.run(command, input=given, text=True, capture_output=True, env=self.environ, check=True)

        started = time.monotonic()
        result = subprocess.run(command, input=given, text=True, capture_output=True, env=self.environ, check=True)
        elapsed = time.monotonic() - started

        self.assertIn(PROOF.text, result.stdout)
        self.assertLess(elapsed, 0.5)


SESSION = "0a1b2c3d-1111-4222-8333-444455556666"
OTHER_SESSION = "9f8e7d6c-5555-4666-8777-888899990000"
ASKING = Lesson("deploy.md", "Ask before a deploy.", ACTION, EVERY_PROJECT, "2026-11-20", words=("deploy",), ask=True)


class StopFirstTest(ToolHookFixture):
    """The first call of a session that a lesson fires on is denied with the lesson, so Claude reads
    it before anything runs."""

    def output(self, command: str, session: str | None = SESSION) -> dict[str, object]:
        answer = self.call(command, session=session)
        output = answer.get("hookSpecificOutput", {})
        assert isinstance(output, dict)
        return output

    def test_the_first_call_is_denied_with_the_lesson_and_the_next_goes_through_with_it(self) -> None:
        """Covers: B288"""
        self.kept(PROOF)

        first = self.output("scripts/check")
        second = self.output("scripts/check")

        self.assertEqual(first["permissionDecision"], "deny")
        reason = first["permissionDecisionReason"]
        assert isinstance(reason, str)
        self.assertIn(tool_hook.LESSON_LINE + PROOF.text, reason)
        self.assertIn("the same call goes through", reason)
        self.assertNotIn("permissionDecision", second)
        self.assertIn(PROOF.text, second["additionalContext"])
        self.assertEqual(action_lessons.fired(self.machine), {"proof.md": 2})

    def test_a_lesson_whose_name_is_no_plain_file_name_is_not_listed(self) -> None:
        """Covers: B288"""
        self.kept(dataclasses.replace(PROOF, name="proof\nother.md"), dataclasses.replace(PROOF, name="proof two.md"))

        self.assertEqual([], action_lessons.read(self.machine))

    def test_another_session_is_stopped_once_too(self) -> None:
        """Covers: B288"""
        self.kept(PROOF)
        self.output("scripts/check")

        self.assertEqual(self.output("scripts/check", OTHER_SESSION)["permissionDecision"], "deny")

    def test_a_lesson_set_to_ask_asks_as_before(self) -> None:
        """Covers: B264, B288"""
        self.kept(ASKING)

        for _ in range(2):
            self.assertEqual(self.output("./deploy prod")["permissionDecision"], "ask")

    def test_a_denying_lesson_comes_before_one_that_asks_and_the_next_call_asks(self) -> None:
        """Covers: B288"""
        self.kept(PROOF, ASKING)

        first = self.output("scripts/check && ./deploy prod")
        second = self.output("scripts/check && ./deploy prod")

        self.assertEqual(first["permissionDecision"], "deny")
        self.assertEqual(second["permissionDecision"], "ask")

    def test_without_a_plain_session_id_nothing_is_denied(self) -> None:
        """Covers: B288"""
        self.kept(PROOF)

        for session in (None, "", "../../outside", "a" * 200):
            with self.subTest(session=session):
                self.assertNotIn("permissionDecision", self.output("scripts/check", session))
        self.assertEqual(list(self.base.glob("outside*")), [])

    def test_a_call_let_through_keeps_its_session_from_being_forgotten(self) -> None:
        """Covers: B288"""
        self.kept(PROOF)
        self.output("scripts/check")
        mark = self.machine.state_dir / action_lessons.DENIED_FOLDER / SESSION
        old = time.time() - 3 * 24 * 3600
        os.utime(mark, (old, old))

        self.output("scripts/check")
        self.output("scripts/check", OTHER_SESSION)

        self.assertNotIn("permissionDecision", self.output("scripts/check"))

    def test_where_the_mark_cannot_be_written_nothing_is_denied(self) -> None:
        """Covers: B265, B288"""
        self.kept(PROOF)
        (self.machine.state_dir / action_lessons.DENIED_FOLDER).write_text("a file, not a folder", encoding="utf-8")

        for _ in range(2):
            output = self.output("scripts/check")
            self.assertNotIn("permissionDecision", output)
            self.assertIn(PROOF.text, output["additionalContext"])

    def test_the_marks_of_sessions_older_than_two_days_go_when_a_new_session_is_marked(self) -> None:
        """Covers: B288"""
        self.kept(PROOF)
        self.output("scripts/check", OTHER_SESSION)
        folder = self.machine.state_dir / action_lessons.DENIED_FOLDER
        old = time.time() - 3 * 24 * 3600
        os.utime(folder / OTHER_SESSION, (old, old))

        self.output("scripts/check")

        self.assertEqual(sorted(path.name for path in folder.iterdir()), [SESSION])


class SessionStartTest(ToolHookFixture):
    def test_the_session_start_hands_the_tool_hook_the_action_lessons_of_the_store(self) -> None:
        """Covers: B263"""
        store = self.base / "sb-test-store"
        (store / "memory" / "lessons").mkdir(parents=True)
        (store / "memory" / "MEMORY.md").write_text("# Memory\n\n## Facts\n\n## Current\n", encoding="utf-8")
        (store / "memory" / "lessons" / "proof.md").write_text(
            "---\nkind: action\ntarget: every project\nkept: 2026-11-20\nwords: [scripts/check]\n---\n"
            "# The whole proof\n\nRun the whole proof only when the change gives a reason.\n",
            encoding="utf-8",
        )
        with mock.patch("sys.stdout", io.StringIO()):
            cli.main(["hook", "start-notes"], self.environ, stdin=io.StringIO("{}"))

        self.assertIn(
            "Run the whole proof only when the change gives a reason.", json.dumps(self.call("scripts/check"))
        )


class CountTest(ToolHookFixture):
    def test_each_firing_is_counted_per_lesson_in_machine_state(self) -> None:
        """Covers: B266"""
        self.kept(PROOF, PUSH)

        self.call("scripts/check")
        self.call("scripts/check -v")
        self.call("scripts/check --quick m2b")

        self.assertEqual(action_lessons.fired(self.machine), {"proof.md": 2})

    def test_each_call_is_counted_per_day_while_there_are_action_lessons_and_firings_count_from_a_day(self) -> None:
        """Covers: B281"""
        self.call("ls")
        self.kept(PROOF)

        self.call("scripts/check")
        self.call("git status")

        today = datetime.datetime.now(datetime.timezone.utc).date()
        self.assertEqual(action_lessons.calls(self.machine, today), 2)
        self.assertEqual(action_lessons.calls(self.machine, today + datetime.timedelta(days=1)), 0)
        self.assertEqual(action_lessons.fired(self.machine, today), {"proof.md": 1})
        self.assertEqual(action_lessons.fired(self.machine, today + datetime.timedelta(days=1)), {})


if __name__ == "__main__":
    unittest.main()
