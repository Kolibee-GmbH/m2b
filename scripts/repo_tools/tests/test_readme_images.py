from __future__ import annotations

import datetime
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any
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

    def test_one_task_is_due_on_the_day_of_the_recording_and_one_is_overdue(self) -> None:
        environ = readme_images.demo_environment({"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"})

        readme_images.build_demo(environ)

        due = {task["title"]: task["overdue"] for task in self.band(environ)["tasks"]["due"]}
        self.assertEqual(due, {"Pick up the paint for the shed door": False, "Return Sam's ladder": True})

    def band(self, environ: dict[str, str]) -> dict[str, Any]:
        answer = subprocess.run(
            [str(readme_images.PLUGIN / "bin" / "m2b"), "band", "--json"],
            env=environ,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(answer.stdout)  # type: ignore[no-any-return]

    def test_the_store_after_a_run_shows_one_changed_fact_and_three_proposals_and_nothing_waits(self) -> None:
        environ = readme_images.demo_environment({"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"})

        readme_images.build_demo_after_a_run(environ)

        band = self.band(environ)
        (change,) = band["tasks"]["review"]["changes"]
        self.assertEqual((change["topic"], change["file"]), ("Sam", "sam.md"))
        changed = [(part["change"], part["text"]) for part in change["parts"] if part["change"] != "same"]
        self.assertEqual(changed, [("removed", "14"), ("added", "21")])
        waiting = band["proposals"]["proposals"]
        self.assertEqual(
            sorted((proposal["kind"], proposal["quote"]) for proposal in waiting),
            sorted((kind, quote) for kind, _, quote, _ in readme_images.PROPOSALS),
        )
        store = self.demo / "notes"
        self.assertEqual(list((store / "inbox").glob("*.md")), [])
        self.assertIn("on Saturday 21 November", (store / "memory" / "sam.md").read_text(encoding="utf-8"))

    def test_the_scripted_run_reads_the_demo_s_sessions_and_reading_is_off_before_a_session_starts(self) -> None:
        environ = readme_images.demo_environment(
            {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "CLAUDE_CONFIG_DIR": "/Users/someone/.claude"}
        )
        runs = []
        run_m2b = readme_images._m2b

        def noting_the_runs(given: dict[str, str], *arguments: str) -> None:
            if arguments[:1] == ("curate",):
                config = self.demo / "home" / ".config" / "m2b" / "config.json"
                reads = json.loads(config.read_text(encoding="utf-8"))["curation"].get("read_sessions", False)
                runs.append((reads, given.get("CLAUDE_CONFIG_DIR")))
            run_m2b(given, *arguments)

        with mock.patch.object(readme_images, "_m2b", noting_the_runs):
            readme_images.build_demo_after_a_run(environ)

        claude_code = self.demo / "claude-code"
        self.assertEqual(runs, [(True, str(claude_code))])
        (session,) = (claude_code / "projects").glob("*/*.jsonl")
        typed = [json.loads(line)["message"]["content"] for line in session.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(tuple(typed), readme_images.SESSION_PROMPTS)
        config = json.loads((self.demo / "home" / ".config" / "m2b" / "config.json").read_text(encoding="utf-8"))
        self.assertFalse(config["curation"].get("read_sessions", False))

    def test_each_proposal_stands_on_words_of_a_prompt_of_the_invented_session(self) -> None:
        for _, _, quote, _ in readme_images.PROPOSALS:
            with self.subTest(quote=quote):
                self.assertTrue(any(quote in prompt for prompt in readme_images.SESSION_PROMPTS))


class RecordTest(unittest.TestCase):
    def test_the_recording_holds_what_the_command_drew_and_typed_keys_reach_it(self) -> None:
        command = ["sh", "-c", "printf 'ready\\n'; read answer; printf 'got %s\\n' \"$answer\"; sleep 5"]

        drawn = readme_images.record(command, Path("/"), {"PATH": "/usr/bin:/bin"}, 10, [(0.5, "yes\r"), (0.5, "")])

        self.assertIn(b"ready", drawn)
        self.assertIn(b"got yes", drawn)

    def test_a_wait_ends_as_soon_as_what_it_waits_for_is_drawn_and_every_chunk_has_its_time(self) -> None:
        command = ["sh", "-c", "printf 'one\\n'; read answer; printf 'two\\n'; sleep 5"]
        waits = [readme_images.Wait(30, "go\r", until=b"one"), readme_images.Wait(30, until=b"two")]

        recording = readme_images.record_timed(command, Path("/"), {"PATH": "/usr/bin:/bin"}, 10, 40, waits)

        self.assertIn(b"two", b"".join(drawn for _, drawn in recording.chunks))
        self.assertEqual(len(recording.typed_at), 2)
        self.assertLess(recording.typed_at[1], 10)
        times = [at for at, _ in recording.chunks]
        self.assertEqual(times, sorted(times))
        self.assertLessEqual(times[-1], recording.typed_at[1])

    def test_a_wait_finds_a_prompt_behind_the_escape_sequence_a_shell_draws_before_it(self) -> None:
        command = ["sh", "-c", "printf 'done\\n\\033[?2004h$ '; sleep 5"]

        recording = readme_images.record_timed(
            command, Path("/"), {"PATH": "/usr/bin:/bin"}, 10, 40, [readme_images.Wait(3, until=b"\n$ ")]
        )

        self.assertEqual(len(recording.typed_at), 1)

    def test_a_wait_that_never_sees_what_it_waits_for_fails(self) -> None:
        command = ["sh", "-c", "printf 'one\\n'; sleep 5"]

        with self.assertRaisesRegex(readme_images.ImagesError, "did not draw b'two' within 0.5 seconds"):
            readme_images.record_timed(
                command, Path("/"), {"PATH": "/usr/bin:/bin"}, 10, 40, [readme_images.Wait(0.5, until=b"two")]
            )

    def test_a_shot_trusts_the_folder_then_asks_its_prompt(self) -> None:
        shot = readme_images.Shot("todos", 40, 40, "what's on my list?", False)

        keys = [keys for _, keys in readme_images.steps_for(shot)]

        self.assertEqual(keys, [readme_images.DOWN, readme_images.ENTER, "what's on my list?", readme_images.ENTER, ""])

    def test_the_capture_shot_names_a_weekday_a_few_days_ahead_and_never_the_day_of_the_recording(self) -> None:
        (capture,) = [shot for shot in readme_images.SHOTS if shot.name == "capture"]
        monday = datetime.date(2030, 1, 7)

        for offset, expected in enumerate(
            ("Thursday", "Friday", "Saturday", "Sunday", "Monday", "Tuesday", "Wednesday")
        ):
            today = monday + datetime.timedelta(days=offset)
            with self.subTest(today=readme_images.WEEKDAYS[today.weekday()]):
                prompt = readme_images.steps_for(capture, today)[2][1]
                self.assertIn(f"remind me on {expected} to buy them", prompt)
                self.assertNotIn(readme_images.WEEKDAYS[today.weekday()], prompt)


class ShotsTest(unittest.TestCase):
    def test_a_shot_on_the_store_another_left_is_recorded_after_that_one(self) -> None:
        self.assertEqual([shot.name for shot in readme_images.shots_for("todos")], ["capture", "todos"])
        self.assertEqual([shot.name for shot in readme_images.shots_for("capture")], ["capture"])
        self.assertEqual([shot.name for shot in readme_images.shots_for("proposals")], ["review", "proposals"])
        self.assertEqual(len(readme_images.shots_for(None)), len(readme_images.SHOTS))

    def test_each_shot_names_a_demo_store_the_script_can_build_and_the_first_on_a_store_builds_it(self) -> None:
        seen = set()
        for shot in readme_images.SHOTS:
            with self.subTest(shot=shot.name):
                self.assertIn(shot.store, readme_images.STORES)
                if shot.store not in seen:
                    self.assertTrue(shot.fresh_store)
                seen.add(shot.store)

    def test_the_shots_of_the_pane_type_a_command_of_the_band(self) -> None:
        commands = {shot.name: shot.prompt for shot in readme_images.SHOTS if shot.store == readme_images.AFTER_A_RUN}

        self.assertEqual(commands, {"review": "/m2b-review", "proposals": "/m2b-proposals"})


class ToolsTest(unittest.TestCase):
    def test_missing_tools_are_named(self) -> None:
        found = {"claude": "/bin/claude", "node": "/bin/node", "npm": "/bin/npm", "git": "/bin/git"}

        self.assertEqual(readme_images.missing_tools(found.get), ["magick"])
        self.assertEqual(readme_images.missing_tools(found.get, ("claude", "agg")), ["agg"])


if __name__ == "__main__":
    unittest.main()
