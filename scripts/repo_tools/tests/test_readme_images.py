from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from repo_tools import readme_images


class DemoEnvironmentTest(unittest.TestCase):
    def test_the_running_session_s_variables_stay_out_and_the_demo_machine_s_go_in(self) -> None:
        environ = {
            "PATH": "/usr/bin",
            "CLAUDECODE": "1",
            "CLAUDE_CODE_CHILD_SESSION": "1",
            "HERDR_PANE_ID": "p1",
            "M2B_HOME": "/Users/someone",
            "CLAUDE_CONFIG_DIR": "/Users/someone/.claude-work",
        }

        demo = readme_images.demo_environment(environ)

        self.assertEqual(demo["PATH"], "/usr/bin")
        self.assertNotIn("CLAUDECODE", demo)
        self.assertNotIn("CLAUDE_CODE_CHILD_SESSION", demo)
        self.assertNotIn("HERDR_PANE_ID", demo)
        self.assertEqual(demo["CLAUDE_CONFIG_DIR"], "/Users/someone/.claude-work")
        self.assertEqual(demo["M2B_HOME"], str(readme_images.DEMO / "home"))
        self.assertEqual(demo["M2B_CORE_ROOT"], str(readme_images.PLUGIN))

    def test_the_demo_lives_in_a_test_folder(self) -> None:
        self.assertTrue(readme_images.DEMO.name.startswith("sb-test-"))


class BuildDemoTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.demo = Path(temp.name) / "sb-test-m2b-demo"
        for name, value in (("DEMO", self.demo), ("PROJECT", self.demo / "projects" / "invoice-tool")):
            patcher = mock.patch.object(readme_images, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_the_demo_store_holds_memory_tasks_a_question_captures_and_an_invented_machine_id(self) -> None:
        environ = readme_images.demo_environment({"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"})

        readme_images.build_demo(environ)

        store = self.demo / "notes"
        self.assertIn("Spare shed key", (store / "memory" / "MEMORY.md").read_text(encoding="utf-8"))
        tasks = [path.read_text(encoding="utf-8") for path in (store / "tasks").glob("*.md")]
        self.assertEqual(len(tasks), 4)
        # The band shows a question of the curation run, never a candidate: only `m2b tasks add --candidate` makes one.
        self.assertEqual([task for task in tasks if "m2b:candidate" in task], [])
        (question,) = [task for task in tasks if "m2b:current" in task]
        self.assertIn("Still current? Planning the trip to Porto in spring", question)
        self.assertEqual(len(list((store / "inbox").glob("*.md"))), 2)
        config = json.loads((self.demo / "home" / ".config" / "m2b" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["machine_id"], readme_images.MACHINE_ID)
        self.assertIn(readme_images.MACHINE_ID, (store / "store.json").read_text(encoding="utf-8"))
        self.assertTrue((self.demo / "projects" / "invoice-tool" / ".git").is_dir())


class RecordTest(unittest.TestCase):
    def test_the_recording_holds_what_the_command_drew_and_typed_keys_reach_it(self) -> None:
        command = ["sh", "-c", "printf 'ready\\n'; read answer; printf 'got %s\\n' \"$answer\"; sleep 5"]

        drawn = readme_images.record(command, Path("/"), {"PATH": "/usr/bin:/bin"}, 10, [(0.5, "yes\r"), (0.5, "")])

        self.assertIn(b"ready", drawn)
        self.assertIn(b"got yes", drawn)

    def test_a_shot_trusts_the_folder_then_asks_its_prompt(self) -> None:
        shot = readme_images.Shot("todos", 40, 40, "what's on my list?", False)

        keys = [keys for _, keys in readme_images.steps_for(shot)]

        self.assertEqual(keys, [readme_images.DOWN, readme_images.ENTER, "what's on my list?", readme_images.ENTER, ""])


class ShotsTest(unittest.TestCase):
    def test_a_shot_on_the_store_another_left_is_recorded_after_that_one(self) -> None:
        self.assertEqual([shot.name for shot in readme_images.shots_for("todos")], ["capture", "todos"])
        self.assertEqual([shot.name for shot in readme_images.shots_for("capture")], ["capture"])
        self.assertEqual(len(readme_images.shots_for(None)), len(readme_images.SHOTS))


class ToolsTest(unittest.TestCase):
    def test_missing_tools_are_named(self) -> None:
        found = {"claude": "/bin/claude", "node": "/bin/node", "npm": "/bin/npm", "git": "/bin/git"}

        self.assertEqual(readme_images.missing_tools(found.get), ["magick"])


if __name__ == "__main__":
    unittest.main()
