from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from repo_tools import readme_demo, readme_images
from repo_tools.readme_demo import Beat
from repo_tools.readme_images import Recording


class BeatsTest(unittest.TestCase):
    def test_a_session_starts_unseen_types_its_prompt_key_by_key_and_waits_for_the_answer(self) -> None:
        beats = readme_demo.session_beats("hi!", 30)

        self.assertEqual([beat.shown for beat in beats[:3]], [0, 0, 0])
        self.assertEqual("".join(beat.keys for beat in beats[3:]), "hi!" + readme_images.ENTER)
        self.assertEqual(
            (beats[-1].seconds, beats[-1].shown, beats[-1].settles), (30, readme_demo.ANSWER_SECONDS, True)
        )

    def test_the_session_whose_start_begins_the_run_types_nothing_and_waits_past_two_looks_of_the_status_line(
        self,
    ) -> None:
        beats = readme_demo.start_beats()

        self.assertEqual(beats[:3], readme_demo.session_beats("hi!", 30)[:3])
        self.assertEqual("".join(beat.keys for beat in beats[3:]), "")
        self.assertGreater(sum(beat.seconds for beat in beats), 2 * 60)
        self.assertEqual((beats[-1].shown, beats[-1].settles), (readme_demo.RUN_SECONDS, False))


class RealModelTest(unittest.TestCase):
    def test_the_session_that_begins_the_run_has_the_demo_machine_without_the_stand_in_for_the_model(self) -> None:
        demo = readme_images.demo_environment({"PATH": "/usr/bin"})

        real = readme_demo.with_the_real_model(demo)

        self.assertIn("M2B_MODEL_RUNNER", demo)
        self.assertEqual(real, {key: value for key, value in demo.items() if key != "M2B_MODEL_RUNNER"})


class BuildFirstNoteDemoTest(unittest.TestCase):
    def test_the_store_holds_nothing_yet_and_both_projects_are_repositories(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        demo = Path(temp.name) / "sb-test-m2b-demo"
        patcher = mock.patch.object(readme_images, "DEMO", demo)
        patcher.start()
        self.addCleanup(patcher.stop)
        environ = readme_images.demo_environment({"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"})

        readme_demo.build_first_note_demo(environ)

        self.assertEqual(list((demo / "notes" / "inbox").glob("*.md")), [])
        self.assertNotIn("Dana", (demo / "notes" / "memory" / "MEMORY.md").read_text(encoding="utf-8"))
        for act in readme_demo.acts_for(environ):
            self.assertTrue(act.cwd.is_dir(), act.cwd)
        self.assertEqual(sorted(path.name for path in (demo / "projects").iterdir()), ["garden-site", "invoice-tool"])
        self.assertTrue((demo / "projects" / "garden-site" / ".git").is_dir())


class WaitingCapturesTest(unittest.TestCase):
    def test_the_notes_left_in_the_demo_inbox_are_named_in_order(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        demo = Path(temp.name) / "sb-test-m2b-demo"
        inbox = demo / "notes" / "inbox"
        inbox.mkdir(parents=True)
        for name in ("b.md", "a.md", "c.txt"):
            (inbox / name).write_text("x", encoding="utf-8")

        with mock.patch.object(readme_images, "DEMO", demo):
            self.assertEqual(readme_demo.waiting_captures(), ["a.md", "b.md"])


class RetimedTest(unittest.TestCase):
    def test_a_hidden_wait_takes_no_time_and_a_plain_one_its_own(self) -> None:
        recording = Recording(((1.0, b"start"), (9.5, b"ready"), (10.2, b"k")), (10.0, 10.5))

        events = readme_demo.retimed(recording, [Beat(10, "k", shown=0), Beat(0.5)])

        self.assertEqual([at for at, _ in events[:2]], [0.0, 0.0])
        self.assertAlmostEqual(events[2][0], 0.2)

    def test_a_long_wait_is_shortened_to_what_it_may_take_and_keeps_its_order(self) -> None:
        recording = Recording(((0.0, b"go"), (10.0, b"half"), (20.0, b"done")), (20.0, 21.0))

        events = readme_demo.retimed(recording, [Beat(60, until=b"done", shown=3.0), Beat(1)])

        self.assertEqual(
            [(round(at, 3), drawn) for at, drawn in events], [(0.0, b"go"), (1.5, b"half"), (3.0, b"done")]
        )

    def test_a_wait_that_settles_and_is_shown_as_recorded_keeps_what_came_after_the_quiet_in_its_place(self) -> None:
        recording = Recording(((0.0, b"answer"), (8.0, b"1 in inbox")), (10.0,))

        events = readme_demo.retimed(recording, [Beat(10, settles=True)])

        self.assertEqual(events, [(0.0, b"answer"), (8.0, b"1 in inbox")])

    def test_a_short_wait_is_never_stretched(self) -> None:
        recording = Recording(((0.5, b"quick"),), (1.0,))

        self.assertEqual(readme_demo.retimed(recording, [Beat(60, shown=3.0)]), [(0.5, b"quick")])

    def test_a_wait_that_settles_is_shortened_up_to_the_quiet_and_what_comes_later_follows_soon(self) -> None:
        # An answer drawn for eight seconds, then quiet, then the band's status line 20 seconds later.
        chunks = (*((second / 2, b"spin") for second in range(17)), (28.0, b"1 in inbox"))
        recording = Recording(chunks, (30.0,))

        events = readme_demo.retimed(recording, [Beat(30, shown=4.0, settles=True)])

        self.assertAlmostEqual(events[16][0], 4.0)
        self.assertGreater(events[17][0], 4.0)
        self.assertLessEqual(events[17][0], 4.0 + readme_demo.TAIL_SECONDS)


class CastTest(unittest.TestCase):
    def test_each_act_follows_a_card_with_its_number_and_title_on_a_cleared_screen(self) -> None:
        lines = readme_demo.cast([("Say it", [(0.0, b"a"), (2.0, b"b")]), ("Ask", [(0.5, b"c")])]).splitlines()

        header = json.loads(lines[0])
        self.assertEqual(
            (header["version"], header["width"], header["height"]), (2, readme_demo.COLUMNS, readme_demo.ROWS)
        )
        events = [json.loads(line) for line in lines[1:]]
        self.assertIn("Say it", events[0][2])
        self.assertIn("1", events[0][2])
        self.assertEqual(events[1], [readme_demo.CARD_SECONDS, "o", readme_demo.RESET])
        second_card = readme_demo.CARD_SECONDS + 2.0 + readme_demo.HOLD_SECONDS
        self.assertEqual(events[4][0], second_card)
        self.assertIn("Ask", events[4][2])
        self.assertEqual(events[6], [round(second_card + readme_demo.CARD_SECONDS + 0.5, 3), "o", "c"])

    def test_a_character_cut_in_two_by_a_chunk_is_drawn_whole(self) -> None:
        arrow = "\u276f".encode()

        lines = readme_demo.cast([("Say it", [(0.0, arrow[:1]), (0.1, arrow[1:])])]).splitlines()

        self.assertEqual([json.loads(line)[2] for line in lines[3:]], ["\u276f"])

    def test_a_no_break_space_is_drawn_as_a_space(self) -> None:
        lines = readme_demo.cast([("Say it", [(0.0, "\u276f\u00a0remember".encode())])]).splitlines()

        self.assertEqual(json.loads(lines[3])[2], "\u276f remember")


MACHINE = {"the home folder": "/Users/someone", "the user name": "someone", "the host name": "Someones-MacBook"}


class LeaksTest(unittest.TestCase):
    def test_a_name_of_this_machine_is_found_through_colors(self) -> None:
        drawn = b"\x1b[2m/Users/\x1b[0msomeone/projects \x1b]0;title\x07 on someones-macbook"

        self.assertEqual(readme_demo.leaks(drawn, MACHINE), ["the home folder", "the user name", "the host name"])

    def test_the_demo_machine_s_own_text_passes(self) -> None:
        drawn = b"/private/tmp/sb-test-m2b-demo/projects/invoice-tool \x1b[1mAlex\x1b[0m handsomeone"

        self.assertEqual(readme_demo.leaks(drawn, MACHINE), [])


class RenderTest(unittest.TestCase):
    def test_agg_gets_the_recording_the_picture_and_a_pause_longer_than_any_hold(self) -> None:
        command = readme_demo.agg_command(Path("/tmp/demo.cast"), Path("/tmp/demo.gif"))

        self.assertEqual((command[0], command[-2], command[-1]), ("agg", "/tmp/demo.cast", "/tmp/demo.gif"))
        idle = float(command[command.index("--idle-time-limit") + 1])
        self.assertGreater(idle, max(readme_demo.HOLD_SECONDS, readme_demo.CARD_SECONDS))
        self.assertEqual(command[command.index("--emoji-font-family") + 1], readme_demo.FONTS)

    def test_each_act_is_recorded_in_its_folder_with_its_keys(self) -> None:
        seen = []

        def record(command, cwd, environ, rows, columns, waits):  # type: ignore[no-untyped-def]
            seen.append((command, cwd, rows, columns, "".join(wait.keys for wait in waits)))
            return Recording((), tuple(float(second) for second in range(len(waits))))

        acts = readme_demo.acts_for(readme_images.demo_environment({"PATH": "/usr/bin"}))
        readme_demo.record_acts(acts, record)

        self.assertEqual([entry[1].name for entry in seen], ["invoice-tool", "invoice-tool", "garden-site"])
        self.assertEqual({entry[0] for entry in seen}, {tuple(readme_images.claude_command())})
        self.assertIn(readme_demo.SENTENCE, seen[0][4])
        self.assertEqual(seen[1][4], readme_images.DOWN + readme_images.ENTER)
        self.assertIn(readme_demo.QUESTION, seen[2][4])
        self.assertEqual(["M2B_MODEL_RUNNER" in act.environ for act in acts], [True, False, True])
        self.assertEqual({entry[2:4] for entry in seen}, {(readme_demo.ROWS, readme_demo.COLUMNS)})

    def test_an_act_whose_command_ended_early_fails_with_what_it_drew_last(self) -> None:
        def record(*arguments: object) -> Recording:
            return Recording(((0.2, b"\x1b[31mNot logged in\x1b[0m\r\n"),), (8.0,))

        acts = readme_demo.acts_for(readme_images.demo_environment({"PATH": "/usr/bin"}))

        with self.assertRaisesRegex(
            readme_images.ImagesError, r"act 1 \(claude\) ended after 1 of \d+ waits.*Not logged in"
        ):
            readme_demo.record_acts(acts, record)


class MainTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.gif = Path(temp.name) / "demo.gif"
        self.rendered: list[list[str]] = []

        def render(command: list[str], environ: object) -> None:
            self.rendered.append(command)
            self.gif.write_bytes(b"GIF89a")

        self.patch(readme_demo, "GIF", self.gif)
        self.patch(readme_demo, "IMAGES", self.gif.parent)
        self.patch(readme_demo, "REPO_ROOT", self.gif.parent)
        self.patch(readme_demo, "build_first_note_demo", lambda environ: None)
        self.patch(readme_demo, "machine_names", lambda: MACHINE)
        self.patch(readme_demo, "waiting_captures", lambda: [])
        self.patch(readme_images, "missing_tools", lambda tools: [])
        self.patch(readme_images, "run", render)

    def patch(self, module: object, name: str, value: object) -> None:
        patcher = mock.patch.object(module, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def main_after_recording(self, drawn: bytes) -> tuple[int, str]:
        recordings = [Recording(((0.5, drawn),), (1.0,))] * 3
        self.patch(readme_demo, "record_acts", lambda acts: recordings)
        said = io.StringIO()
        with contextlib.redirect_stdout(said), contextlib.redirect_stderr(said):
            return readme_demo.main([]), said.getvalue()

    def test_the_three_acts_become_one_picture(self) -> None:
        status, said = self.main_after_recording(b"Saved as inbox/note.md")

        self.assertEqual(status, 0)
        (command,) = self.rendered
        self.assertEqual(command[-1], str(self.gif))
        self.assertIn("demo.gif, 0 kB", said)

    def test_a_recording_that_names_this_machine_becomes_no_picture(self) -> None:
        status, said = self.main_after_recording(b"cwd: /Users/someone/projects")

        self.assertEqual(status, 1)
        self.assertEqual(self.rendered, [])
        self.assertFalse(self.gif.exists())
        self.assertIn("the terminal drew the home folder and the user name of this machine", said)

    def test_a_note_the_run_left_in_the_inbox_becomes_no_picture(self) -> None:
        self.patch(readme_demo, "waiting_captures", lambda: ["20300102T030405Z-claude-a1b2.md"])

        status, said = self.main_after_recording(b"Saved as inbox/note.md")

        self.assertEqual(status, 1)
        self.assertEqual(self.rendered, [])
        self.assertIn("left 20300102T030405Z-claude-a1b2.md in the inbox", said)

    def test_a_missing_tool_is_named_and_nothing_is_recorded(self) -> None:
        self.patch(readme_images, "missing_tools", lambda tools: ["agg"])

        status, said = self.main_after_recording(b"")

        self.assertEqual(status, 1)
        self.assertEqual(self.rendered, [])
        self.assertIn("not found on PATH: agg", said)


if __name__ == "__main__":
    unittest.main()
