"""Lessons the owner kept: read from the store, and brought into every session as kept corrections."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import test_lint
from m2b import lessons, lint
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard

CHECKS = (
    "---\nkind: knowledge\ntarget: every project\nkept: 2026-11-20\n---\n# The checks a change touches\n\n"
    "Run only the checks the change touches; the whole proof only when the change gives a reason.\n\n"
    "## Evidence\n\n- [[20261120T101500Z-claude-a1b2.md]]\n"
)
LOOK_FIRST = (
    "---\nkind: knowledge\ntarget: every project\nkept: 2026-11-21\n---\n# Look it up first\n\n"
    "Before asking the owner, look it up: the repository, its records, the second brain's search.\n"
)
CHECKS_SENTENCE = "Run only the checks the change touches; the whole proof only when the change gives a reason."
LOOK_SENTENCE = "Before asking the owner, look it up: the repository, its records, the second brain's search."


class StoreFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="sb-test-lessons-")
        self.addCleanup(self._temp.cleanup)
        base = Path(self._temp.name)
        self.root = base / "sb-test-store"
        (self.root / lessons.FOLDER).mkdir(parents=True)
        self.store = FolderStore(self.root, base / "machine-tmp", DatalessGuard(False))

    def write(self, name: str, text: str) -> None:
        (self.root / lessons.FOLDER / name).write_text(text, encoding="utf-8")


class ReadTest(StoreFixture):
    def test_a_lesson_file_gives_its_sentence_kind_target_and_day(self) -> None:
        """Covers: B257"""
        self.write("checks.md", CHECKS)

        [lesson] = lessons.read_all(self.store)

        self.assertEqual(
            (lesson.name, lesson.text, lesson.kind, lesson.target, lesson.kept, lesson.kept_at),
            ("checks.md", CHECKS_SENTENCE, lessons.KNOWLEDGE, lessons.EVERY_PROJECT, "2026-11-20", None),
        )

    def test_a_file_without_the_fields_of_a_lesson_is_no_lesson(self) -> None:
        """Covers: B257"""
        self.write("checks.md", CHECKS)
        self.write("note.md", "# A note\n\nSomething said once.\n")
        self.write("no-kind.md", CHECKS.replace("kind: knowledge\n", ""))
        self.write("no-day.md", CHECKS.replace("kept: 2026-11-20\n", ""))
        self.write("other-kind.md", CHECKS.replace("kind: knowledge", "kind: rumour"))

        self.assertEqual([lesson.name for lesson in lessons.read_all(self.store)], ["checks.md"])

    def test_a_file_with_a_title_and_evidence_but_no_sentence_is_no_lesson(self) -> None:
        """Covers: B257"""
        self.write("bare.md", CHECKS.replace(f"{CHECKS_SENTENCE}\n\n", ""))

        self.assertEqual(lessons.read_all(self.store), [])

    def test_no_lessons_folder_holds_no_lesson(self) -> None:
        """Covers: B257"""
        (self.root / lessons.FOLDER).rmdir()

        self.assertEqual(lessons.read_all(self.store), [])


PROOF = (
    "---\nkind: action\ntarget: every project\nkept: 2026-11-20\nwords: [scripts/check]\nunless: [--quick]\n---\n"
    "# The whole proof\n\nRun the whole proof only when the change gives a reason.\n"
)


class ActionLessonTest(StoreFixture):
    def test_an_action_lesson_gives_its_words_the_words_that_silence_it_and_whether_it_asks(self) -> None:
        """Covers: B262"""
        self.write("proof.md", PROOF.replace("unless: [--quick]\n", "unless: [--quick]\nask: true\n"))

        [lesson] = lessons.read_all(self.store)

        self.assertEqual((lesson.words, lesson.unless, lesson.ask), (("scripts/check",), ("--quick",), True))

    def test_an_action_lesson_without_words_is_no_lesson(self) -> None:
        """Covers: B262"""
        self.write("proof.md", PROOF.replace("words: [scripts/check]\n", ""))

        self.assertEqual(lessons.read_all(self.store), [])

    def test_a_lesson_written_by_render_reads_back_as_it_was(self) -> None:
        """Covers: B262"""
        kept = lessons.Lesson(
            "proof.md",
            "Run the whole proof only when the change gives a reason.",
            lessons.ACTION,
            lessons.EVERY_PROJECT,
            "2026-11-20",
            words=("scripts/check",),
            unless=("--quick",),
        )
        self.write("proof.md", lessons.render(kept, "The whole proof", ["20261120T101500Z-claude-a1b2.md"]))

        self.assertEqual(lessons.read_all(self.store), [kept])


class BlockTest(StoreFixture):
    def test_the_block_holds_every_knowledge_lesson_for_every_project_as_kept_corrections(self) -> None:
        """Covers: B257"""
        self.write("checks.md", CHECKS)
        self.write("look-first.md", LOOK_FIRST)

        block = lessons.block(lessons.read_all(self.store))

        self.assertEqual(block, f"{lessons.BLOCK_HEADER}\n- {CHECKS_SENTENCE}\n- {LOOK_SENTENCE}\n")
        self.assertIn("the owner corrected Claude on each of these and kept the correction", lessons.BLOCK_HEADER)

    def test_the_block_leaves_out_a_lesson_kept_at_its_source(self) -> None:
        """Covers: B258"""
        self.write(
            "checks.md", CHECKS.replace("kept: 2026-11-20\n", "kept: 2026-11-20\nkept_at: ~/.claude/CLAUDE.md\n")
        )
        self.write("look-first.md", LOOK_FIRST)

        all_lessons = lessons.read_all(self.store)

        self.assertEqual(lessons.block(all_lessons), f"{lessons.BLOCK_HEADER}\n- {LOOK_SENTENCE}\n")
        self.assertEqual([lesson.name for lesson in lessons.kept_at_source(all_lessons)], ["checks.md"])

    def test_the_block_leaves_out_action_lessons_and_lessons_for_one_project(self) -> None:
        """Covers: B257"""
        self.write("action.md", CHECKS.replace("kind: knowledge", "kind: action"))
        self.write("portal.md", CHECKS.replace("target: every project", "target: github.com/acme/portal"))

        self.assertEqual(lessons.block(lessons.read_all(self.store)), "")

    def test_a_lesson_with_characters_that_draw_nothing_loses_them(self) -> None:
        """Covers: B257"""
        self.write("checks.md", CHECKS.replace("Run only", "Run‮ only"))

        self.assertNotIn("‮", lessons.block(lessons.read_all(self.store)))

    def test_lessons_past_the_block_limit_are_left_out_with_a_line_saying_so(self) -> None:
        """Covers: B259"""
        for number in range(40):
            self.write(f"lesson-{number:02}.md", LOOK_FIRST.replace("Before asking", f"Lesson {number}: before asking"))

        block = lessons.block(lessons.read_all(self.store))

        carried, left = lessons.fitting(lessons.read_all(self.store))
        self.assertLessEqual(len(block), lessons.MAX_BLOCK_CHARACTERS)
        self.assertIn(f"({left} more lessons are kept in memory/lessons/)", block)
        self.assertEqual(block.count("\n- "), len(carried))
        self.assertEqual(len(carried) + left, 40)

    def test_a_last_lesson_that_fits_comes_without_a_line_for_more(self) -> None:
        """Covers: B259"""
        self.write("look-first.md", LOOK_FIRST)

        self.assertEqual(lessons.fitting(lessons.read_all(self.store)), (lessons.read_all(self.store), 0))


class LintTest(test_lint.LintFixture):
    def test_lessons_that_take_the_start_past_its_target_are_reported_with_both_sizes(self) -> None:
        """Covers: B260"""
        for number in range(25):
            self.write(f"memory/lessons/lesson-{number:02}.md", LOOK_FIRST.replace("Before", f"{number}: before"))

        [finding] = [finding for finding in lint.scan(self.store).findings if finding.code == "distillate-size"]

        self.assertRegex(
            finding.text,
            r"the part every session starts with is \d+ bytes, \d+ of the distillate and \d+ of the lessons in "
            r"memory/lessons/, over its 2 KB target",
        )

    def test_a_small_start_with_lessons_is_no_finding(self) -> None:
        """Covers: B260"""
        self.write("memory/lessons/look-first.md", LOOK_FIRST)

        self.assertNotIn("distillate-size", [finding.code for finding in lint.scan(self.store).findings])


if __name__ == "__main__":
    unittest.main()
