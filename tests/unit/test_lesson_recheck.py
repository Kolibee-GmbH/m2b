"""Every reading checks again whether a file every session loads now states a lesson of the block."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from m2b import lessons
from m2b.lesson_recheck import RecheckError, recheck, step_input
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard

GERMAN = lessons.Lesson(
    "answer-in-german.md", "Answer in German in the chat.", lessons.KNOWLEDGE, lessons.EVERY_PROJECT, "2026-11-10"
)
SHORT = lessons.Lesson(
    "short-commits.md",
    "Keep commit subjects under 60 characters.",
    lessons.KNOWLEDGE,
    lessons.EVERY_PROJECT,
    "2026-11-12",
)
PUSH = lessons.Lesson(
    "never-push.md", "Never push to main.", lessons.ACTION, lessons.EVERY_PROJECT, "2026-11-11", words=("git", "push")
)
CLAUDE_MD = "# Conventions\n\nCommits in English.\n\nAnswer in German in the chat.\n"


class Model:
    """Stands in for the model: answers with the verdicts given, and keeps what it was asked."""

    def __init__(self, *verdicts: dict[str, object]) -> None:
        self.verdicts = list(verdicts)
        self.asked: list[str] = []

    def __call__(self, instruction: str, text: str) -> str:
        self.asked.append(text)
        return json.dumps({"verdicts": self.verdicts})


class RecheckTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.home = base / "home"
        self.claude = self.home / ".claude"
        self.claude.mkdir(parents=True)
        (self.claude / "CLAUDE.md").write_text(CLAUDE_MD, encoding="utf-8")
        self.environ = {"HOME": str(self.home)}
        self.state = base / "machine-state"
        self.state.mkdir()
        self.root = base / "sb-test-store"
        self.store = FolderStore(self.root, base / "machine-tmp", DatalessGuard(False))
        (self.root / "memory" / "lessons").mkdir(parents=True)

    def keep(self, *found: lessons.Lesson) -> None:
        for lesson in found:
            text = lessons.render(lesson, lesson.text[:40], ["20261110T090000Z-cli-a1b2.md"])
            (self.root / lessons.FOLDER / lesson.name).write_text(text, encoding="utf-8")

    def run_recheck(self, model: Model) -> list[tuple[str, str]]:
        return list(recheck(self.store, self.environ, self.state, model).kept_at_source)

    def test_a_lesson_a_source_states_leaves_the_block_and_is_kept_at_it(self) -> None:
        """Covers: B291"""
        self.keep(GERMAN, SHORT)
        model = Model({"lesson": 1, "verdict": "right", "source": 1, "line": 5}, {"lesson": 2, "verdict": "none"})

        self.assertEqual([("answer-in-german.md", "~/.claude/CLAUDE.md")], self.run_recheck(model))

        standing = {lesson.name: lesson for lesson in lessons.read_all(self.store)}
        self.assertEqual("~/.claude/CLAUDE.md", standing["answer-in-german.md"].kept_at)
        self.assertFalse(standing["answer-in-german.md"].in_the_block)
        self.assertTrue(standing["short-commits.md"].in_the_block)
        text = (self.root / lessons.FOLDER / "answer-in-german.md").read_text(encoding="utf-8")
        self.assertIn("## Evidence\n\n- [[20261110T090000Z-cli-a1b2.md]]\n", text)

    def test_the_model_sees_only_the_lessons_of_the_block_and_the_files_every_session_loads(self) -> None:
        """Covers: B291"""
        stated = lessons.Lesson(
            "stated.md", "Say the date.", lessons.KNOWLEDGE, lessons.EVERY_PROJECT, "2026-11-01", "~/.claude/CLAUDE.md"
        )
        one_project = lessons.Lesson(
            "portal.md", "Use the portal's staging.", lessons.KNOWLEDGE, "github.com/acme/portal", "2026-11-01"
        )
        self.keep(GERMAN, PUSH, stated, one_project)
        (self.claude / "rules").mkdir()
        (self.claude / "rules" / "style.md").write_text("Write short sentences.\n", encoding="utf-8")
        (self.claude / "rules" / "tests.md").write_text(
            "---\npaths: tests/**\n---\nName each test.\n", encoding="utf-8"
        )
        (self.home / "CLAUDE.md").write_text("Only in the home folder.\n", encoding="utf-8")
        memory = self.claude / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(self.home)) / "memory"
        memory.mkdir(parents=True)
        (memory / "MEMORY.md").write_text("A memory of one project.\n", encoding="utf-8")
        model = Model({"lesson": 1, "verdict": "none"})

        self.run_recheck(model)

        (asked,) = model.asked
        document = json.loads(asked)
        self.assertEqual([{"lesson": 1, "text": "Answer in German in the chat."}], document["lessons"])
        self.assertEqual(
            ["~/.claude/CLAUDE.md", "~/.claude/rules/style.md"], [each["file"] for each in document["sources"]]
        )
        self.assertEqual("5: Answer in German in the chat.", document["sources"][0]["lines"][4])

    def test_nothing_changed_since_the_last_check_asks_no_model(self) -> None:
        """Covers: B291"""
        self.keep(GERMAN)
        self.run_recheck(Model({"lesson": 1, "verdict": "none"}))

        again = Model()
        result = recheck(self.store, self.environ, self.state, again)

        self.assertEqual([], again.asked)
        self.assertEqual("the lessons and the files every session loads are as at the last check", result.skipped)

    def test_after_a_lesson_left_the_block_an_unchanged_block_asks_no_model(self) -> None:
        """Covers: B291"""
        self.keep(GERMAN, SHORT)
        self.run_recheck(
            Model({"lesson": 1, "verdict": "right", "source": 1, "line": 5}, {"lesson": 2, "verdict": "none"})
        )
        again = Model()
        self.assertEqual(
            "the lessons and the files every session loads are as at the last check",
            recheck(self.store, self.environ, self.state, again).skipped,
        )
        self.assertEqual([], again.asked)

    def test_a_lesson_file_that_is_no_utf8_stays_in_the_block(self) -> None:
        """Covers: B291"""
        self.keep(GERMAN)
        path = self.root / lessons.FOLDER / GERMAN.name
        path.write_bytes(path.read_bytes().replace(b"# Answer", b"# Answer \xe9"))
        before = path.read_bytes()

        self.assertEqual([], self.run_recheck(Model({"lesson": 1, "verdict": "right", "source": 1, "line": 5})))
        self.assertEqual(before, path.read_bytes())

    def test_a_changed_source_or_a_new_lesson_is_checked_again(self) -> None:
        """Covers: B291"""
        self.keep(GERMAN)
        self.run_recheck(Model({"lesson": 1, "verdict": "none"}))
        (self.claude / "CLAUDE.md").write_text(
            CLAUDE_MD + "Keep commit subjects under 60 characters.\n", encoding="utf-8"
        )
        changed = Model({"lesson": 1, "verdict": "none"})
        self.run_recheck(changed)
        self.assertEqual(1, len(changed.asked))
        self.keep(SHORT)
        added = Model({"lesson": 1, "verdict": "none"}, {"lesson": 2, "verdict": "right", "source": 1, "line": 6})
        self.assertEqual([("short-commits.md", "~/.claude/CLAUDE.md")], self.run_recheck(added))

    def test_without_a_lesson_in_the_block_or_a_source_no_model_is_asked(self) -> None:
        """Covers: B291"""
        self.keep(PUSH)
        model = Model()
        self.assertEqual("no lesson in the block", recheck(self.store, self.environ, self.state, model).skipped)
        self.keep(GERMAN)
        (self.claude / "CLAUDE.md").unlink()
        self.assertEqual("no file every session loads", recheck(self.store, self.environ, self.state, model).skipped)
        self.assertEqual([], model.asked)

    def test_a_verdict_code_cannot_hold_to_a_line_keeps_the_lesson_in_the_block(self) -> None:
        """Covers: B291"""
        self.keep(GERMAN)
        for verdict in (
            {"lesson": 1, "verdict": "right", "source": 1, "line": 2},
            {"lesson": 1, "verdict": "right", "source": 1, "line": 99},
            {"lesson": 1, "verdict": "right", "source": 2, "line": 5},
            {"lesson": 1, "verdict": "right", "source": 1},
            {"lesson": 1, "verdict": "wrong", "source": 1, "line": 5},
            {"lesson": 7, "verdict": "right", "source": 1, "line": 5},
        ):
            with self.subTest(verdict=verdict):
                (self.state / "lesson-sources-checked.json").unlink(missing_ok=True)
                self.assertEqual([], self.run_recheck(Model(verdict)))
                self.assertTrue(lessons.read_all(self.store)[0].in_the_block)

    def test_an_answer_that_cannot_be_read_changes_nothing_and_is_asked_again(self) -> None:
        """Covers: B291"""
        self.keep(GERMAN)

        def unreadable(instruction: str, text: str) -> str:
            return "I cannot say."

        with self.assertRaises(RecheckError):
            recheck(self.store, self.environ, self.state, unreadable)
        self.assertTrue(lessons.read_all(self.store)[0].in_the_block)
        again = Model({"lesson": 1, "verdict": "none"})
        self.run_recheck(again)
        self.assertEqual(1, len(again.asked))

    def test_a_line_that_holds_a_credential_is_never_kept_as_the_source(self) -> None:
        """Covers: B291"""
        (self.claude / "CLAUDE.md").write_text("Answer in German, token ghp_" + "a1" * 18 + "\n", encoding="utf-8")
        self.keep(GERMAN)
        self.assertEqual([], self.run_recheck(Model({"lesson": 1, "verdict": "right", "source": 1, "line": 1})))


class StepInputTest(unittest.TestCase):
    def test_the_document_numbers_lessons_and_lines(self) -> None:
        """Covers: B291"""
        from m2b.lesson_sources import Source

        document = json.loads(
            step_input([GERMAN], [Source("~/.claude/CLAUDE.md", ("a", "b"), "~/.claude/CLAUDE.md", ())])
        )
        self.assertEqual(
            {"source": 1, "file": "~/.claude/CLAUDE.md", "lines": ["1: a", "2: b"]}, document["sources"][0]
        )


if __name__ == "__main__":
    unittest.main()
