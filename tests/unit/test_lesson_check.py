"""An action lesson that did not fire for a month goes to the owner as a question: still needed?"""

from __future__ import annotations

import datetime
import tempfile
import unittest
from pathlib import Path

from m2b import action_lessons, lesson_check, lesson_counts
from m2b.glean import Correction
from m2b.paths import MachinePaths
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard
from m2b.tasks import markers
from m2b.tasks.base import Task
from m2b.tasks.markdown import MarkdownTasks

PREFIX = "Still needed?"
TODAY = datetime.date(2026, 12, 21)
LIST = "markdown:"
PROOF = (
    "---\nkind: action\ntarget: every project\nkept: {kept}\nwords: [scripts/check]\n---\n"
    "# Proof\n\nRun the whole proof only with a reason.\n"
)
ONCE = "---\nkind: knowledge\ntarget: every project\nkept: {kept}\n---\n# Once\n\nSay it once.\n"


class LessonCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.root = base / "sb-test-store"
        self.store = FolderStore(self.root, base / "machine-tmp", DatalessGuard(False))
        (self.root / "memory" / "lessons").mkdir(parents=True)
        self.machine = MachinePaths(base / "home")
        self.machine.state_dir.mkdir(parents=True)
        self.tasks = MarkdownTasks(self.store)

    def lesson(self, name: str, text: str) -> None:
        (self.root / "memory" / "lessons" / name).write_text(text, encoding="utf-8")

    def fired_on(self, name: str, day: str) -> None:
        with (self.machine.state_dir / action_lessons.FIRED).open("a", encoding="utf-8") as log:
            log.write(f"{day}T12:00:00+00:00\t{name}\n")

    def questions(self) -> list[Task]:
        return self.tasks.items(marker=markers.LESSON, include_completed=True)

    def ask(self) -> list[str]:
        found = lesson_check.quiet(self.store, self.machine, TODAY, corrections_counted=True)
        return lesson_check.ask(self.store, self.tasks, found, PREFIX, task_list=LIST)

    def test_an_action_lesson_that_did_not_fire_for_a_month_is_asked_about_once(self) -> None:
        """Covers: B283"""
        self.lesson("proof.md", PROOF.format(kept="2026-11-01"))
        self.lesson("young.md", PROOF.format(kept="2026-12-01"))
        self.lesson("fires.md", PROOF.format(kept="2026-11-01"))
        self.fired_on("fires.md", "2026-12-20")
        # It fired once, a few days after it was kept, and never again since.
        self.lesson("once-fired.md", PROOF.format(kept="2026-11-01"))
        self.fired_on("once-fired.md", "2026-11-05")
        self.lesson("once.md", ONCE.format(kept="2026-11-01"))

        self.assertEqual(sorted(self.ask()), ["once-fired.md", "proof.md"])
        self.assertEqual(self.ask(), [])

        self.assertEqual(
            {question.title for question in self.questions()}, {"Still needed? Run the whole proof only with a reason."}
        )

    def test_a_knowledge_lesson_of_the_block_not_corrected_for_60_days_is_asked_about(self) -> None:
        """Covers: B292"""
        self.lesson("once.md", ONCE.format(kept="2026-10-01"))
        self.lesson("young.md", ONCE.format(kept="2026-11-01").replace("Say it once.", "Say it twice."))
        self.lesson("corrected.md", ONCE.format(kept="2026-10-01").replace("Say it once.", "Name the day."))
        lesson_counts.add(
            self.store,
            [Correction("corrected.md", "no, name the day again", "shed")],
            {"corrected.md": "2026-10-01"},
            datetime.date(2026, 11, 10),
        )
        stated = ONCE.format(kept="2026-10-01").replace(
            "kept: 2026-10-01\n", "kept: 2026-10-01\nkept_at: ~/.claude/CLAUDE.md\n"
        )
        self.lesson("stated.md", stated.replace("Say it once.", "Keep it short."))

        self.assertEqual(self.ask(), ["once.md"])
        self.assertEqual({question.title for question in self.questions()}, {"Still needed? Say it once."})

    def test_a_knowledge_lesson_said_to_still_hold_is_quiet_anew_for_60_days(self) -> None:
        """Covers: B292"""
        self.lesson("once.md", ONCE.format(kept="2026-10-01"))
        self.ask()
        (question,) = self.questions()
        self.tasks.complete(question.id)
        lesson_check.settle(self.store, self.tasks, TODAY, task_list=LIST)

        later = TODAY + datetime.timedelta(days=59)
        self.assertEqual(lesson_check.quiet(self.store, self.machine, later, corrections_counted=True), [])
        self.assertEqual(
            [
                lesson.name
                for lesson in lesson_check.quiet(
                    self.store, self.machine, later + datetime.timedelta(days=1), corrections_counted=True
                )
            ],
            ["once.md"],
        )

    def test_while_the_sessions_are_not_read_a_knowledge_lesson_is_not_asked_about(self) -> None:
        """Covers: B292"""
        self.lesson("once.md", ONCE.format(kept="2026-10-01"))
        self.assertEqual(lesson_check.quiet(self.store, self.machine, TODAY, corrections_counted=False), [])

    def test_without_the_counts_a_knowledge_lesson_is_not_asked_about(self) -> None:
        """Covers: B292"""
        self.lesson("once.md", ONCE.format(kept="2026-10-01"))
        (self.root / "state" / "core").mkdir(parents=True, exist_ok=True)
        (self.root / lesson_counts.COUNTS_FILE).write_text('{"format": 99, "lessons": {}}', encoding="utf-8")
        self.assertEqual(lesson_check.quiet(self.store, self.machine, TODAY, corrections_counted=True), [])

    def test_a_ticked_question_keeps_the_lesson_quiet_anew_from_that_day(self) -> None:
        """Covers: B283"""
        self.lesson("proof.md", PROOF.format(kept="2026-11-01"))
        self.ask()
        (question,) = self.questions()
        self.tasks.complete(question.id)

        removed = lesson_check.settle(self.store, self.tasks, TODAY, task_list=LIST)

        self.assertEqual(removed, [])
        self.assertTrue((self.root / "memory" / "lessons" / "proof.md").exists())
        self.assertEqual(self.questions(), [])
        self.assertEqual(
            lesson_check.quiet(self.store, self.machine, TODAY + datetime.timedelta(days=29), corrections_counted=True),
            [],
        )
        self.assertEqual(
            [
                each.name
                for each in lesson_check.quiet(
                    self.store, self.machine, TODAY + datetime.timedelta(days=30), corrections_counted=True
                )
            ],
            ["proof.md"],
        )

    def test_a_dropped_or_deleted_question_removes_the_lesson(self) -> None:
        """Covers: B283"""
        for how in ("drop", "delete"):
            with self.subTest(how):
                self.lesson("proof.md", PROOF.format(kept="2026-11-01"))
                self.ask()
                (question,) = [each for each in self.questions() if not each.completed]
                if how == "drop":
                    self.tasks.drop(question.id)
                else:
                    self.tasks.delete(question.id)

                removed = lesson_check.settle(self.store, self.tasks, TODAY, task_list=LIST)

                self.assertEqual(removed, ["proof.md"])
                self.assertFalse((self.root / "memory" / "lessons" / "proof.md").exists())

    def test_an_open_question_keeps_the_lesson_and_one_whose_lesson_is_gone_is_closed(self) -> None:
        """Covers: B283"""
        self.lesson("proof.md", PROOF.format(kept="2026-11-01"))
        self.ask()

        self.assertEqual(lesson_check.settle(self.store, self.tasks, TODAY, task_list=LIST), [])
        self.assertTrue((self.root / "memory" / "lessons" / "proof.md").exists())
        self.assertEqual(len(self.questions()), 1)

        # A lesson whose file is there but cannot be read now keeps its open question.
        (self.root / "memory" / "lessons" / "proof.md").write_text("not a lesson", encoding="utf-8")
        self.ask()
        self.assertEqual(len(self.questions()), 1)

        (self.root / "memory" / "lessons" / "proof.md").unlink()
        self.ask()
        self.assertEqual(self.questions(), [])


if __name__ == "__main__":
    unittest.main()
