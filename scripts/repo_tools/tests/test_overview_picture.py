"""The overview picture's stories add up: every step inside the loop and in order, the dot on the
lines it travels, every animation off for reduced motion, and the README's alt text the script's. The
picture itself needs the typefaces and is looked at, not tested; these tests need neither."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from repo_tools import overview_picture as picture

README = Path(__file__).resolve().parents[3] / "README.md"


class Measured:
    """Type without typefaces: every letter as wide as the next, every text an empty group."""

    def width(self, text: str, style: str) -> float:
        return 6.0 * len(text)

    def draw(self, x: float, y: float, text: str, style: str, anchor: str = "start") -> str:
        return "<g/>"

    def defs(self) -> str:
        return ""

    def fit(self, text: str, style: str, room: float) -> None:
        return None


def in_order(windows: list[tuple[float, float]]) -> bool:
    ends = [0.0]
    for start, end in windows:
        if start < ends[-1] or end <= start:
            return False
        ends.append(end)
    return ends[-1] + picture.FADE <= picture.LOOP_SECONDS


class StoryTest(unittest.TestCase):
    def test_the_stories_and_the_rest_follow_each_other_inside_the_loop(self) -> None:
        self.assertTrue(in_order([*picture.STORIES, picture.REST]))

    def test_every_line_shows_inside_its_story_and_is_typed_while_it_shows(self) -> None:
        for line in picture.LINES:
            start, end = picture.STORIES[line.story - 1]
            with self.subTest(text=line.text):
                self.assertTrue(start <= line.shows < end)
                if line.typed:
                    self.assertEqual(line.typed[0], line.shows)
                    self.assertLess(line.typed[1], end)

    def test_the_lines_of_a_terminal_in_one_story_take_its_rows_in_order(self) -> None:
        for terminal in ("said", "known"):
            for story in range(1, len(picture.STORIES) + 1):
                lines = [line for line in picture.LINES if line.terminal == terminal and line.story == story]
                with self.subTest(terminal=terminal, story=story):
                    self.assertEqual([line.row for line in lines], list(range(len(lines))))
                    self.assertEqual([line.shows for line in lines], sorted(line.shows for line in lines))

    def test_each_glow_and_the_bands_texts_show_inside_the_loop_in_order(self) -> None:
        for name, windows in picture.GLOWS.items():
            with self.subTest(glow=name):
                self.assertTrue(in_order(windows))
        for text, _, windows in picture.BAND:
            with self.subTest(band=text):
                self.assertTrue(in_order(windows))


class DotTest(unittest.TestCase):
    def test_the_dot_moves_forward_in_time_inside_the_loop(self) -> None:
        seconds = [frame[0] for frame in picture.dot_frames()]
        self.assertEqual(seconds, sorted(seconds))
        self.assertEqual(len(seconds), len(set(seconds)))
        self.assertGreater(seconds[0], 0)
        self.assertLess(seconds[-1], picture.LOOP_SECONDS)

    def test_the_dot_shows_only_on_a_drawn_line(self) -> None:
        for seconds, x, y, opacity in picture.dot_frames():
            if opacity:
                with self.subTest(seconds=seconds):
                    self.assertTrue(picture.on_a_way((x, y)), (x, y))


class StillTest(unittest.TestCase):
    def test_every_animation_stops_for_reduced_motion(self) -> None:
        text = picture.svg(picture.THEMES["light"], Measured())
        names = set(re.findall(r"@keyframes ([\w-]+)\{", text))
        self.assertTrue(names)
        self.assertIn("@media (prefers-reduced-motion:reduce){.anim{animation:none}}", text)
        for classes in re.findall(r'class="([^"]*)"', text):
            if names & set(classes.split()):
                self.assertIn("anim", classes.split(), classes)

    def test_without_motion_the_picture_is_the_first_storys_last_frame(self) -> None:
        text = picture.svg(picture.THEMES["light"], Measured())
        self.assertIn(".story-later,.cover,.cursor,.dot{opacity:0}", text)
        first = [line for line in picture.LINES if line.story == 1]
        self.assertEqual(text.count('class="story-one anim line-'), len(first))


class ReadmeTest(unittest.TestCase):
    def test_both_pictures_in_the_readme_carry_the_scripts_alt_text(self) -> None:
        readme = README.read_text(encoding="utf-8")
        alt = 'alt="' + picture.ALT.replace('"', "&quot;") + '"'
        for theme in ("light", "dark"):
            with self.subTest(theme=theme):
                tag = next(line for line in readme.splitlines() if f"overview-{theme}.svg" in line)
                self.assertIn(alt, tag)


if __name__ == "__main__":
    unittest.main()
