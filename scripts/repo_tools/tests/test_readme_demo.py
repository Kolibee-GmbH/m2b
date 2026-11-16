from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from m2b.config import catalog

from repo_tools import readme_demo, readme_images
from repo_tools.readme_demo import Beat, Picture
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


def keys_of(picture: Picture) -> str:
    (act,) = picture.acts(readme_images.demo_environment({"PATH": "/usr/bin"}))
    return "".join(beat.keys for beat in act.beats)


class PicturesTest(unittest.TestCase):
    def test_the_readme_s_picture_comes_first_and_the_two_of_the_pane_are_wide_enough_to_dock_it(self) -> None:
        sizes = {picture.name: (picture.columns, picture.rows) for picture in readme_demo.PICTURES}

        self.assertEqual(list(sizes), ["demo", "pane-answers", "settings-walk"])
        self.assertEqual(sizes["demo"], (readme_demo.COLUMNS, readme_demo.ROWS))
        self.assertEqual({sizes["pane-answers"][0], sizes["settings-walk"][0]}, {readme_images.WIDE})

    def test_a_picture_of_the_pane_is_one_session_in_the_full_screen_layout_that_asks_no_model(self) -> None:
        demo = readme_images.demo_environment({"PATH": "/usr/bin"})

        for picture in readme_demo.PICTURES[1:]:
            with self.subTest(picture=picture.name):
                (act,) = picture.acts(demo)
                self.assertEqual(act.environ, {**demo, "CLAUDE_CODE_NO_FLICKER": "1"})
                self.assertIn("M2B_MODEL_RUNNER", act.environ)
                self.assertEqual(act.cwd, readme_images.PROJECT)
                self.assertEqual(act.command, tuple(readme_images.claude_command()))
                self.assertIs(picture.build, readme_images.build_demo_after_a_run)

    def test_a_picture_of_the_pane_types_one_command_of_the_band_and_then_only_tab_and_enter(self) -> None:
        commands = {}
        for picture in readme_demo.PICTURES[1:]:
            trusted = readme_images.DOWN + readme_images.ENTER
            keys = keys_of(picture)
            self.assertTrue(keys.startswith(trusted))
            command, _, presses = keys[len(trusted) :].partition(readme_images.ENTER)
            commands[picture.name] = command
            self.assertEqual(
                set(presses.replace(readme_demo.SHIFT_TAB, "")), {readme_demo.TAB, readme_images.ENTER}, picture.name
            )

        self.assertEqual(commands, {"pane-answers": "/m2b-pane", "settings-walk": "/m2b-settings"})

    def test_only_the_second_press_is_given_the_five_seconds_after_which_it_is_written(self) -> None:
        # The key after the press that is written: the first step back to the start view, and Enter on the row
        # that opens what only informs.
        after_the_write = {
            "pane-answers": (readme_demo.answering_beats(), readme_demo.SHIFT_TAB, 0),
            "settings-walk": (readme_demo.settings_beats(), readme_images.ENTER, -1),
        }
        for name, (beats, key, which) in after_the_write.items():
            with self.subTest(picture=name):
                waited = [beat for beat in beats if beat.keys == key][which]
                self.assertGreater(waited.seconds, 5.0)
                self.assertIsNone(waited.shown)
                # Every other wait is short enough for the undo of the first press to come in time.
                others = [beat.seconds for beat in beats[3:] if beat is not waited]
                self.assertLess(max(others), 5.0)

    def test_the_way_to_the_model_of_curation_is_the_buttons_the_settings_draw_around_its_other_value(self) -> None:
        presses = keys_of(readme_demo.PICTURES[2]).partition("/m2b-settings" + readme_images.ENTER)[2]
        model = (catalog.MACHINE, "curation.model")
        in_sight = [held for group in catalog.groups() if not group.folded for held in group.holds]
        choices = {(setting.scope, setting.key): setting.choices for setting in catalog.settings()}

        def values_to_press(settings: list[tuple[str, str]]) -> int:
            """A switch draws a button for every value but the one in force; a setting that is no switch draws none."""
            return sum(max(len(choices[held]) - 1, 0) for held in settings)

        at = in_sight.index(model)
        tabs_of_the_pane = 3
        to_the_model = tabs_of_the_pane + values_to_press(in_sight[:at]) + 1
        # From the row of the folded group, the button after the last value.
        back_to_the_model = values_to_press(in_sight[at + 1 :]) + 1

        self.assertEqual(readme_demo.TABS_TO_THE_MODEL, to_the_model)
        self.assertEqual(readme_demo.BACK_TO_THE_MODEL, back_to_the_model)
        self.assertEqual(choices[model], ("haiku", readme_demo.KEPT_MODEL))
        self.assertTrue(catalog.groups()[-1].folded)
        # The model stands nearer to that row than to the tabs, so the focus rests on the row after undo.
        self.assertLess(len(in_sight) - at, at + 1)
        pressed_and_undone = readme_demo.TAB * to_the_model + readme_images.ENTER * 2
        pressed_again = readme_demo.SHIFT_TAB * back_to_the_model + readme_images.ENTER
        opened_the_rest = readme_images.ENTER
        self.assertEqual(presses, pressed_and_undone + pressed_again + opened_the_rest)

    def test_the_proposal_the_picture_keeps_is_one_of_the_demo_store(self) -> None:
        self.assertIn(readme_demo.KEPT_PROPOSAL, [text for _, text, _, _ in readme_images.PROPOSALS])


class WrittenTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.demo = Path(temp.name) / "sb-test-m2b-demo"
        for name, value in (("DEMO", self.demo), ("PROJECT", self.demo / "projects" / "invoice-tool")):
            patcher = mock.patch.object(readme_images, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.environ = readme_images.demo_environment({"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"})

    def m2b(self, *arguments: str, given: str | None = None) -> str:
        command = [str(readme_images.PLUGIN / "bin" / "m2b"), *arguments]
        done = subprocess.run(command, env=self.environ, input=given, capture_output=True, text=True, check=True)
        return done.stdout

    def waiting(self) -> dict[str, str]:
        proposals = json.loads(self.m2b("band", "--json"))["proposals"]["proposals"]
        return {proposal["text"]: proposal["id"] for proposal in proposals}

    def test_the_picture_of_the_answers_is_refused_until_the_first_proposal_is_kept(self) -> None:
        readme_images.build_demo_after_a_run(self.environ)

        before = readme_demo.kept_proposal_not_written(self.environ)
        waiting = self.waiting()
        self.m2b("proposals", "keep", waiting[readme_demo.KEPT_PROPOSAL])

        self.assertEqual(next(iter(waiting)), readme_demo.KEPT_PROPOSAL)
        self.assertIn("3 proposals wait on the demo machine, not all but 'Send Dana", before or "")
        self.assertIsNone(readme_demo.kept_proposal_not_written(self.environ))

    def test_the_picture_of_the_answers_is_refused_when_the_press_dropped_the_proposal(self) -> None:
        readme_images.build_demo_after_a_run(self.environ)

        self.m2b("proposals", "drop", self.waiting()[readme_demo.KEPT_PROPOSAL])

        self.assertEqual(
            readme_demo.kept_proposal_not_written(self.environ),
            "the demo machine holds .drop, not one keep: the press was no keep",
        )

    def test_the_picture_of_the_answers_is_refused_when_another_proposal_was_kept(self) -> None:
        readme_images.build_demo_after_a_run(self.environ)

        waiting = self.waiting()
        self.m2b("proposals", "keep", next(id for text, id in waiting.items() if text != readme_demo.KEPT_PROPOSAL))

        self.assertIn("it was not answered", readme_demo.kept_proposal_not_written(self.environ) or "")

    def test_the_picture_of_the_settings_is_refused_until_the_model_of_curation_is_set(self) -> None:
        readme_images.build_demo_after_a_run(self.environ)

        before = readme_demo.model_not_written(self.environ)
        self.m2b("config", "set", "curation.model", "opus")
        another = readme_demo.model_not_written(self.environ)
        self.m2b("settings", "set", "--", "curation.model", readme_demo.KEPT_MODEL)

        self.assertEqual(
            before, "the demo machine's curation.model is not set, not 'sonnet': the press was not written"
        )
        self.assertEqual(
            another, "the demo machine's curation.model is 'opus', not 'sonnet': the press was not written"
        )
        self.assertIsNone(readme_demo.model_not_written(self.environ))

    def test_a_demo_machine_that_cannot_be_asked_refuses_both(self) -> None:
        self.assertEqual(
            readme_demo.kept_proposal_not_written(self.environ),
            "m2b band --json did not say which proposals wait on the demo machine",
        )
        self.assertEqual(readme_demo.model_not_written(self.environ), "the demo machine's config could not be read")


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
        lines = readme_demo.cast([("Say it", [(0.0, b"a"), (2.0, b"b")]), ("Ask", [(0.5, b"c")])], 90, 22).splitlines()

        header = json.loads(lines[0])
        self.assertEqual((header["version"], header["width"], header["height"]), (2, 90, 22))
        events = [json.loads(line) for line in lines[1:]]
        self.assertIn("Say it", events[0][2])
        self.assertIn("1", events[0][2])
        self.assertEqual(events[1], [readme_demo.CARD_SECONDS, "o", readme_demo.RESET])
        second_card = readme_demo.CARD_SECONDS + 2.0 + readme_demo.HOLD_SECONDS
        self.assertEqual(events[4][0], second_card)
        self.assertIn("Ask", events[4][2])
        self.assertEqual(events[6], [round(second_card + readme_demo.CARD_SECONDS + 0.5, 3), "o", "c"])

    def test_a_picture_of_one_act_has_a_card_without_a_number_and_the_size_of_its_terminal(self) -> None:
        lines = readme_demo.cast([("Walk through", [(0.0, b"a")])], 130, 30).splitlines()

        header = json.loads(lines[0])
        self.assertEqual((header["width"], header["height"]), (130, 30))
        self.assertTrue(json.loads(lines[1])[2].endswith("\r\n\r\n   Walk through"))

    def test_a_character_cut_in_two_by_a_chunk_is_drawn_whole(self) -> None:
        arrow = "\u276f".encode()

        lines = readme_demo.cast([("Say it", [(0.0, arrow[:1]), (0.1, arrow[1:])])], 90, 22).splitlines()

        self.assertEqual([json.loads(line)[2] for line in lines[3:]], ["\u276f"])

    def test_a_no_break_space_is_drawn_as_a_space(self) -> None:
        lines = readme_demo.cast([("Say it", [(0.0, "\u276f\u00a0remember".encode())])], 90, 22).splitlines()

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
        self.assertEqual(command[command.index("--font-size") + 1], str(readme_demo.FONT_SIZE))

    def test_no_pause_a_picture_shows_as_recorded_is_cut(self) -> None:
        demo = readme_images.demo_environment({"PATH": "/usr/bin"})
        readme, answers, walk = (picture.acts(demo) for picture in readme_demo.PICTURES)

        self.assertEqual(readme_demo.longest_pause(readme), max(readme_demo.HOLD_SECONDS, readme_demo.CARD_SECONDS))
        for acts in (answers, walk):
            self.assertGreater(readme_demo.longest_pause(acts), readme_demo.PRESS_SECONDS)
        command = readme_demo.agg_command(Path("/tmp/pane.cast"), Path("/tmp/pane.gif"), 14, 8.0)
        self.assertEqual(command[command.index("--idle-time-limit") + 1], "9.0")

    def test_a_picture_s_letters_have_the_size_it_names(self) -> None:
        command = readme_demo.agg_command(Path("/tmp/pane.cast"), Path("/tmp/pane.gif"), 14)

        self.assertEqual(command[command.index("--font-size") + 1], "14")

    def test_each_act_is_recorded_in_its_folder_with_its_keys(self) -> None:
        seen = []

        def record(command, cwd, environ, rows, columns, waits):  # type: ignore[no-untyped-def]
            seen.append((command, cwd, rows, columns, "".join(wait.keys for wait in waits)))
            return Recording((), tuple(float(second) for second in range(len(waits))))

        acts = readme_demo.acts_for(readme_images.demo_environment({"PATH": "/usr/bin"}))
        readme_demo.record_acts(acts, readme_demo.COLUMNS, readme_demo.ROWS, record)

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
            readme_demo.record_acts(acts, readme_demo.COLUMNS, readme_demo.ROWS, record)


class MainTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.images = Path(temp.name)
        self.rendered: list[list[str]] = []
        self.built: list[str] = []
        self.sizes: list[tuple[int, int]] = []
        self.refusal: dict[str, str] = {}

        def render(command: list[str], environ: object) -> None:
            self.rendered.append(command)
            Path(command[-1]).write_bytes(b"GIF89a")

        def record_acts(acts: list[readme_demo.Act], columns: int, rows: int) -> list[Recording]:
            self.sizes.append((columns, rows))
            return [Recording(((0.5, self.drawn),), (1.0,))] * len(acts)

        self.drawn = b"Saved as inbox/note.md"
        self.patch(readme_demo, "PICTURES", (self.picture("demo", 90, 16, 3), self.picture("pane-answers", 130, 14, 1)))
        self.patch(readme_demo, "waiting_captures", lambda: [])
        self.patch(readme_demo, "IMAGES", self.images)
        self.patch(readme_demo, "REPO_ROOT", self.images)
        self.patch(readme_demo, "record_acts", record_acts)
        self.patch(readme_demo, "machine_names", lambda: MACHINE)
        self.patch(readme_images, "missing_tools", lambda tools: [])
        self.patch(readme_images, "run", render)

    def picture(self, name: str, columns: int, font_size: int, acts: int) -> Picture:
        # The picture of one act shows a wait of eight seconds as recorded, as a press in the pane does.
        beats = (Beat(1.0),) if acts > 1 else (Beat(8.0),)
        one = readme_demo.Act(f"Act of {name}", ("claude",), Path("/"), {}, beats)
        return Picture(
            name,
            columns,
            22,
            font_size,
            lambda environ: self.built.append(name),
            lambda environ: [one] * acts,
            lambda environ: self.refusal.get(name),
        )

    def patch(self, module: object, name: str, value: object) -> None:
        patcher = mock.patch.object(module, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def main(self, *arguments: str) -> tuple[int, str]:
        said = io.StringIO()
        with contextlib.redirect_stdout(said), contextlib.redirect_stderr(said):
            return readme_demo.main(list(arguments)), said.getvalue()

    def test_each_picture_is_recorded_on_its_demo_machine_in_its_size_and_rendered_to_its_file(self) -> None:
        status, said = self.main()

        self.assertEqual(status, 0)
        self.assertEqual(self.built, ["demo", "pane-answers"])
        self.assertEqual(self.sizes, [(90, 22), (130, 22)])
        self.assertEqual([Path(command[-1]).name for command in self.rendered], ["demo.gif", "pane-answers.gif"])
        self.assertEqual(sorted(path.name for path in self.images.iterdir()), ["demo.gif", "pane-answers.gif"])
        self.assertEqual([command[command.index("--font-size") + 1] for command in self.rendered], ["16", "14"])
        self.assertEqual(
            [command[command.index("--idle-time-limit") + 1] for command in self.rendered],
            [str(max(readme_demo.HOLD_SECONDS, readme_demo.CARD_SECONDS) + 1), "9.0"],
        )
        self.assertIn("demo.gif, 0 kB", said)
        self.assertIn("pane-answers.gif, 0 kB", said)

    def test_only_the_picture_asked_for_is_recorded(self) -> None:
        status, _ = self.main("--only", "pane-answers")

        self.assertEqual(status, 0)
        self.assertEqual(self.built, ["pane-answers"])
        self.assertEqual([path.name for path in self.images.iterdir()], ["pane-answers.gif"])

    def test_the_recording_is_kept_where_asked_and_only_for_one_picture(self) -> None:
        kept = self.images / "kept.cast"

        status, _ = self.main("--only", "pane-answers", "--cast", str(kept))

        self.assertEqual(status, 0)
        self.assertEqual(json.loads(kept.read_text(encoding="utf-8").splitlines()[0])["width"], 130)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            readme_demo.main(["--cast", str(kept)])

    def test_a_recording_that_names_this_machine_becomes_no_picture(self) -> None:
        self.drawn = b"cwd: /Users/someone/projects"

        status, said = self.main()

        self.assertEqual(status, 1)
        self.assertEqual(self.rendered, [])
        self.assertEqual(list(self.images.iterdir()), [])
        self.assertIn("demo: the terminal drew the home folder and the user name of this machine", said)

    def test_a_demo_machine_that_does_not_hold_what_the_picture_shows_becomes_no_picture(self) -> None:
        self.refusal["pane-answers"] = "the demo machine holds .drop, not one keep: the press was no keep"

        status, said = self.main()

        self.assertEqual(status, 1)
        self.assertEqual([path.name for path in self.images.iterdir()], ["demo.gif"])
        self.assertIn("pane-answers: the demo machine holds .drop, not one keep", said)
        self.assertIn("no picture written", said)

    def test_a_picture_that_fails_does_not_keep_the_ones_after_it_from_being_recorded(self) -> None:
        self.refusal["demo"] = "the run of the second act left a note in the inbox"

        status, said = self.main()

        self.assertEqual(status, 1)
        self.assertEqual(self.built, ["demo", "pane-answers"])
        self.assertEqual([path.name for path in self.images.iterdir()], ["pane-answers.gif"])
        self.assertIn("demo: the run of the second act left a note in the inbox; no picture written", said)

    def test_a_render_that_fails_leaves_the_picture_of_before_as_it_was(self) -> None:
        (self.images / "demo.gif").write_bytes(b"the picture of before")

        def failing_render(command: list[str], environ: object) -> None:
            Path(command[-1]).write_bytes(b"GIF8")
            raise readme_images.ImagesError("agg failed: out of memory")

        self.patch(readme_images, "run", failing_render)

        status, said = self.main("--only", "demo")

        self.assertEqual(status, 1)
        self.assertEqual((self.images / "demo.gif").read_bytes(), b"the picture of before")
        self.assertIn("agg failed", said)

    def test_a_note_the_run_left_in_the_inbox_refuses_the_readme_s_picture(self) -> None:
        self.patch(readme_demo, "waiting_captures", lambda: ["20300102T030405Z-claude-a1b2.md"])

        reason = readme_demo.note_left_in_the_inbox({})

        self.assertIn("left 20300102T030405Z-claude-a1b2.md in the inbox", reason or "")
        self.patch(readme_demo, "waiting_captures", lambda: [])
        self.assertIsNone(readme_demo.note_left_in_the_inbox({}))

    def test_a_missing_tool_is_named_and_nothing_is_recorded(self) -> None:
        self.patch(readme_images, "missing_tools", lambda tools: ["agg"])

        status, said = self.main()

        self.assertEqual(status, 1)
        self.assertEqual(self.built, [])
        self.assertIn("not found on PATH: agg", said)


if __name__ == "__main__":
    unittest.main()
