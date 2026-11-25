"""A lesson the owner keeps by hand: a file a client adds, which the run's harvest files in code."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from m2b import cli, harvest, kept_lessons, lessons, paths
from m2b.config import machine
from m2b.config.store_settings import save_store_settings
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard
from m2b.tasks.markdown import MarkdownTasks

PROOF = "Run the whole proof only when the change gives a reason."


class KeptLessonFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="sb-test-kept-lessons-")
        self.addCleanup(self._temp.cleanup)
        self.base = Path(self._temp.name)
        self.root = self.base / "sb-test-store"
        self.root.mkdir()
        self.store = FolderStore(self.root, self.base / "machine-tmp", DatalessGuard(False))
        self.machine = paths.MachinePaths(self.base / "m2b-home")
        machine.save_machine_config(
            self.machine,
            {"version": 1, "machine_id": "sb-test-m1", "store": {"backend": "folder", "path": str(self.root)}},
        )
        save_store_settings(
            self.store,
            {
                "format": 1,
                "tasks": {"backend": "markdown"},
                "curating_machine": "sb-test-m1",
                "journal_since": "2026-11-01",
            },
        )
        self.environ = {
            "HOME": str(self.base / "user-home"),
            "M2B_HOME": str(self.base / "m2b-home"),
            "PATH": os.environ["PATH"],
        }

    def add(self, **given: object) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        stdin = io.TextIOWrapper(io.BytesIO(json.dumps(given).encode("utf-8")), encoding="utf-8")
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), mock.patch("sys.stdin", stdin):
            code = cli.main(["lesson", "add", "-"], self.environ)
        return code, out.getvalue(), err.getvalue()

    def waiting(self) -> list[str]:
        folder = self.root / kept_lessons.FOLDER
        return sorted(path.name for path in folder.iterdir()) if folder.is_dir() else []


class AddAndFileTest(KeptLessonFixture):
    def test_the_owners_lesson_about_a_command_becomes_an_action_lesson_with_those_words(self) -> None:
        """Covers: B267"""
        code, out, err = self.add(
            text=PROOF, kind="action", title="The whole proof", words=["scripts/check"], unless=["--quick"]
        )
        self.assertEqual((code, err), (0, ""))
        self.assertIn("the next curation run files it", out)
        self.assertEqual(len(self.waiting()), 1)

        report = harvest.harvest(self.store, MarkdownTasks(self.store), "Memory candidate: ")

        [lesson] = lessons.read_all(self.store)
        self.assertEqual(
            (lesson.name, lesson.text, lesson.kind, lesson.target, lesson.words, lesson.unless),
            ("the-whole-proof.md", PROOF, lessons.ACTION, lessons.EVERY_PROJECT, ("scripts/check",), ("--quick",)),
        )
        self.assertEqual(report.lessons, ["the-whole-proof.md"])
        self.assertEqual(self.waiting(), [])

    def test_the_same_lesson_kept_twice_waits_once(self) -> None:
        """Covers: B267"""
        self.add(text=PROOF, kind="action", words=["scripts/check"])
        code, out, _ = self.add(text=PROOF, kind="action", words=["scripts/check"])

        self.assertEqual(code, 0)
        self.assertIn("Kept before", out)
        self.assertEqual(len(self.waiting()), 1)

    def test_an_action_lesson_without_words_or_a_lesson_of_two_lines_is_refused(self) -> None:
        """Covers: B267"""
        for given in (
            {"text": PROOF, "kind": "action"},
            {"text": "One.\nTwo.", "kind": "knowledge"},
            {"kind": "action"},
        ):
            with self.subTest(given=given):
                self.assertEqual(self.add(**given)[0], 2)
        self.assertEqual(self.waiting(), [])

    def test_a_lesson_for_this_project_in_a_folder_without_a_remote_is_refused(self) -> None:
        """Covers: B267"""
        folder = self.base / "notes"
        folder.mkdir()
        with mock.patch("os.getcwd", return_value=str(folder)):
            code, _, err = self.add(text=PROOF, kind="knowledge", **{"for": "this project"})

        self.assertEqual(code, 2)
        self.assertIn("names its repository by its remote", err)

    def test_the_same_lesson_kept_again_on_another_day_is_not_filed_twice(self) -> None:
        """Covers: B267"""
        self.add(text=PROOF, kind="action", words=["scripts/check"])
        harvest.harvest(self.store, MarkdownTasks(self.store), "Memory candidate: ")
        with mock.patch("m2b.commands.lesson.datetime") as clock:
            clock.date.today.return_value.isoformat.return_value = "2026-12-01"
            self.add(text=PROOF, kind="action", words=["scripts/check"])

        report = harvest.harvest(self.store, MarkdownTasks(self.store), "Memory candidate: ")

        self.assertEqual(len(lessons.read_all(self.store)), 1)
        self.assertEqual(report.lessons, [lessons.read_all(self.store)[0].name])
        self.assertEqual(self.waiting(), [])

    def test_a_lesson_whose_text_reads_as_a_heading_is_refused(self) -> None:
        """Covers: B267"""
        self.assertEqual(self.add(text="# Run the proof", kind="knowledge")[0], 2)

    def test_a_knowledge_lesson_for_one_project_is_refused_and_sent_to_a_fix(self) -> None:
        """Covers: B267"""
        clone = self.base / "code" / "acme-portal"
        clone.mkdir(parents=True)
        repository = mock.Mock(addresses=("github.com/acme/portal",))
        with (
            mock.patch("os.getcwd", return_value=str(clone)),
            mock.patch("m2b.session_remotes.repository_of", return_value=repository),
        ):
            code, _, err = self.add(text=PROOF, kind="knowledge", **{"for": "this project"})

        self.assertEqual(code, 2)
        self.assertIn("keep it as a fix", err)

    def test_a_lesson_with_a_character_that_hides_or_reorders_text_is_refused(self) -> None:
        """Covers: B267"""
        for given in (
            {"text": "Run the proof\u202e only with a reason.", "kind": "knowledge"},
            {"text": PROOF, "kind": "action", "words": ["scripts/\u200bcheck"]},
            {"text": PROOF, "kind": "action", "words": ["scripts/check\x1b[2J"]},
        ):
            with self.subTest(given=given):
                self.assertEqual(self.add(**given)[0], 2)
        self.assertEqual(self.waiting(), [])

    def test_a_second_lesson_with_the_same_title_gets_a_name_of_its_own(self) -> None:
        """Covers: B267"""
        self.add(text=PROOF, kind="knowledge", title="Checks")
        self.add(text="Say what ran and why the rest did not.", kind="knowledge", title="Checks")

        harvest.harvest(self.store, MarkdownTasks(self.store), "Memory candidate: ")

        self.assertEqual(sorted(lesson.name for lesson in lessons.read_all(self.store)), ["checks-2.md", "checks.md"])


class LessonFileNameTest(KeptLessonFixture):
    def filed_name(self, title: str) -> str:
        self.add(text=PROOF, kind="knowledge", title=title)
        report = harvest.harvest(self.store, MarkdownTasks(self.store), "Memory candidate: ")
        [name] = report.lessons
        return name

    def test_umlauts_and_sharp_s_are_written_out(self) -> None:
        """Covers: B316"""
        self.assertEqual(self.filed_name("Über Prüfungen, Ärger und Maße"), "ueber-pruefungen-aerger-und-masse.md")

    def test_an_umlaut_typed_as_letter_and_mark_is_written_out_too(self) -> None:
        """Covers: B316"""
        self.assertEqual(self.filed_name("Pru\u0308fungen"), "pruefungen.md")

    def test_a_letter_with_another_mark_loses_the_mark(self) -> None:
        """Covers: B316"""
        self.assertEqual(self.filed_name("Café crème à la Señora"), "cafe-creme-a-la-senora.md")

    def test_a_letter_with_a_stroke_or_a_ligature_is_written_as_plain_letters(self) -> None:
        """Covers: B316"""
        self.assertEqual(self.filed_name("Søren über Łódź, Æsir und Œuvre"), "soren-ueber-lodz-aesir-und-oeuvre.md")

    def test_a_long_title_ends_at_the_last_whole_word_before_forty_characters(self) -> None:
        """Covers: B316"""
        self.assertEqual(
            self.filed_name("Run the whole proof only when the changes give a reason"),
            "run-the-whole-proof-only-when-the.md",
        )

    def test_a_word_that_ends_at_the_limit_is_kept_whole(self) -> None:
        """Covers: B316"""
        self.assertEqual(
            self.filed_name("Run the whole proof only when the change gives a reason"),
            "run-the-whole-proof-only-when-the-change.md",
        )

    def test_one_word_longer_than_the_limit_is_cut_at_the_limit(self) -> None:
        """Covers: B316"""
        self.assertEqual(self.filed_name("x" * 50), "x" * 40 + ".md")

    def test_a_title_of_no_latin_letter_is_named_lesson(self) -> None:
        """Covers: B316"""
        self.assertEqual(self.filed_name("Проверка"), "lesson.md")

    def test_a_lesson_file_that_exists_keeps_its_name(self) -> None:
        """Covers: B316"""
        self.add(text=PROOF, kind="knowledge", title="Über Prüfungen")
        harvest.harvest(self.store, MarkdownTasks(self.store), "Memory candidate: ")
        folder = self.root / lessons.FOLDER
        (folder / "ueber-pruefungen.md").rename(folder / "ber-pr-fungen.md")

        self.add(text=PROOF, kind="knowledge", title="Über Prüfungen")
        report = harvest.harvest(self.store, MarkdownTasks(self.store), "Memory candidate: ")

        self.assertEqual(report.lessons, ["ber-pr-fungen.md"])
        self.assertEqual(sorted(path.name for path in folder.iterdir()), ["ber-pr-fungen.md"])

    def test_a_written_out_name_that_is_taken_draws_its_number(self) -> None:
        """Covers: B316"""
        self.add(text=PROOF, kind="knowledge", title="Prüfungen")
        self.add(text="Say what ran and why the rest did not.", kind="knowledge", title="Pruefungen")

        harvest.harvest(self.store, MarkdownTasks(self.store), "Memory candidate: ")

        self.assertEqual(
            sorted(lesson.name for lesson in lessons.read_all(self.store)), ["pruefungen-2.md", "pruefungen.md"]
        )


if __name__ == "__main__":
    unittest.main()
