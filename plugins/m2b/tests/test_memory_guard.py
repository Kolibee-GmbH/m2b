"""The check after a model step: what it did to ``memory/``, compared in code."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from m2b.curate.memory_guard import (
    REWROTE,
    FactChange,
    Snapshot,
    fact_change_list,
    fact_changes,
    refresh_problem,
    unsafe_line,
)
from m2b.notes.characters import strip_unsafe, unsafe_characters
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard

INDEX = "memory/MEMORY.md"
MEMORY = (
    "# Memory\n\n## Facts\n\n"
    "- Dana likes old maps (dana.md)\n"
    "- Sam brings plywood on 14 January (sam.md)\n\n"
    "### Acme Ltd (Acme, Kim Lee)\n- Kim Lee leads Acme's IT (kim-lee.md)\n\n"
    "## Current\n\n- Rebuilding the shed roof\n- Planning the trip to Porto (since 2099-01-01)\n"
)
SAM = "---\nuntil: 2026-01-14\n---\n# Sam\n\n- Brings plywood on 14 January.\n"


def memory(text: str = MEMORY, **fact_files: str) -> Snapshot:
    files = {INDEX: text.encode(), "memory/dana.md": b"# Dana\n\n- Likes old maps.\n", "memory/sam.md": SAM.encode()}
    files.update({f"memory/{name}.md": content.encode() for name, content in fact_files.items()})
    return Snapshot(files)


class CharactersTest(unittest.TestCase):
    def test_bidi_controls_zero_width_space_word_joiner_bom_and_tags_are_unsafe(self) -> None:
        """Covers: B56"""
        for character in ("‮", "⁦", "​", "⁠", "﻿", "\U000e0041", "᠎"):
            with self.subTest(code=f"U+{ord(character):04X}"):
                self.assertEqual(unsafe_characters(f"Dana{character} likes maps"), [f"U+{ord(character):04X}"])
                self.assertEqual(strip_unsafe(f"Dana{character} likes maps"), "Dana likes maps")

    def test_joiners_marks_and_emoji_stay_because_scripts_and_emoji_need_them(self) -> None:
        """Covers: B56"""
        for text in ("Dana \U0001f469‍\U0001f4bb codes", "می‌خواهم", "a‎b"):
            with self.subTest(text=text):
                self.assertEqual(unsafe_characters(text), [])
                self.assertEqual(strip_unsafe(text), text)

    def test_each_unsafe_character_is_named_once_in_the_order_it_comes(self) -> None:
        self.assertEqual(unsafe_characters("‮x​y‮"), ["U+202E", "U+200B"])


class UnsafeLineTest(unittest.TestCase):
    def test_a_new_or_changed_line_with_an_unsafe_character_is_found(self) -> None:
        """Covers: B56"""
        planted = MEMORY.replace("- Dana likes old maps", "- Dana likes old maps\U000e0049\U000e0047")
        problem = unsafe_line(memory(), memory(planted))

        self.assertIsNotNone(problem)
        assert problem is not None
        self.assertIn("memory/MEMORY.md", problem)
        self.assertIn("U+E0049", problem)

    def test_a_new_fact_file_with_one_is_found_too(self) -> None:
        problem = unsafe_line(memory(), memory(robin="# Robin\n\n- Visits‮ soon.\n"))

        self.assertIsNotNone(problem)
        assert problem is not None
        self.assertIn("memory/robin.md", problem)

    def test_a_line_that_already_held_one_before_the_step_is_not_the_steps(self) -> None:
        old = MEMORY.replace("old maps", "old​ maps")
        self.assertIsNone(unsafe_line(memory(old), memory(old + "- Another line\n")))


class RefreshProblemTest(unittest.TestCase):
    def test_the_due_files_line_and_file_may_change(self) -> None:
        """Covers: B54"""
        after = memory(
            MEMORY.replace("Sam brings plywood on", "Sam brought the plywood on"), sam="# Sam\n\n- Brought.\n"
        )

        self.assertIsNone(refresh_problem(memory(), after, files=["memory/sam.md"], current=[]))

    def test_another_line_of_the_distillate_may_not(self) -> None:
        """Covers: B54"""
        after = memory(MEMORY.replace("- Dana likes old maps (dana.md)\n", ""))

        problem = refresh_problem(memory(), after, files=["memory/sam.md"], current=[])

        self.assertIsNotNone(problem)
        assert problem is not None
        self.assertIn("memory/MEMORY.md", problem)
        self.assertIn("Dana likes old maps", problem)

    def test_a_line_under_current_may_not_unless_the_backfill_gave_it(self) -> None:
        """Covers: B54"""
        dated = MEMORY.replace("- Rebuilding the shed roof\n", "- Rebuilding the shed roof (since 2026-01-03)\n")

        self.assertIsNotNone(refresh_problem(memory(), memory(dated), files=[], current=[]))
        self.assertIsNone(refresh_problem(memory(), memory(dated), files=[], current=["Rebuilding the shed roof"]))

    def test_a_backfilled_current_line_must_keep_its_text(self) -> None:
        reworded = MEMORY.replace("- Rebuilding the shed roof\n", "- Rebuilt the shed roof (since 2026-01-03)\n")

        self.assertIsNotNone(
            refresh_problem(memory(), memory(reworded), files=[], current=["Rebuilding the shed roof"])
        )

    def test_a_second_line_for_a_due_file_is_more_than_rewriting_it(self) -> None:
        doubled = MEMORY.replace("(sam.md)\n", "(sam.md)\n- Sam is a carpenter (sam.md)\n")

        self.assertIsNotNone(refresh_problem(memory(), memory(doubled), files=["memory/sam.md"], current=[]))

    def test_another_fact_file_may_not_change_appear_or_go(self) -> None:
        """Covers: B54"""
        cases = {
            "changed": memory(dana="# Dana\n\n- Hates maps.\n"),
            "new": memory(robin="# Robin\n"),
            "gone": Snapshot({path: data for path, data in memory().files.items() if path != "memory/dana.md"}),
            "due file gone": Snapshot({path: data for path, data in memory().files.items() if path != "memory/sam.md"}),
        }
        for name, after in cases.items():
            with self.subTest(name):
                self.assertIsNotNone(refresh_problem(memory(), after, files=["memory/sam.md"], current=[]))

    def test_blank_lines_at_the_end_of_the_distillate_do_not_count(self) -> None:
        self.assertIsNone(refresh_problem(memory(), memory(MEMORY + "\n\n"), files=[], current=[]))


class FactChangesTest(unittest.TestCase):
    def test_a_change_keeps_the_whole_lines_and_the_review_text_stays_cut(self) -> None:
        """Covers: B106"""
        long_before = (
            "- Kim Lee leads Acme's IT, " + "with a long list of systems, " * 6 + "and the help desk (kim-lee.md)"
        )
        long_after = long_before.replace("and the help desk", "and the new help desk")
        before = memory(MEMORY.replace("- Kim Lee leads Acme's IT (kim-lee.md)", long_before))
        after = memory(MEMORY.replace("- Kim Lee leads Acme's IT (kim-lee.md)", long_after))

        [change] = fact_change_list(before, after)

        self.assertEqual(change, FactChange(REWROTE, "kim-lee.md", long_before, long_after))
        self.assertEqual(fact_changes(before, after), [change.described()])
        self.assertIn("...", change.described())

    def test_a_new_facts_line_or_one_moved_into_a_topic_is_no_change(self) -> None:
        """Covers: B55"""
        moved = MEMORY.replace("- Dana likes old maps (dana.md)\n", "").replace(
            "- Kim Lee leads", "- Dana likes old maps (dana.md)\n- Kim Lee leads"
        )
        added = MEMORY.replace("(dana.md)\n", "(dana.md)\n- Robin visits in May (robin.md)\n")

        self.assertEqual(fact_changes(memory(), memory(moved)), [])
        self.assertEqual(fact_changes(memory(), memory(added, robin="# Robin\n")), [])

    def test_a_removed_and_a_rewritten_facts_line_are_each_one_change(self) -> None:
        """Covers: B55"""
        after = MEMORY.replace("- Dana likes old maps (dana.md)\n", "").replace(
            "Kim Lee leads Acme's IT", "Kim Lee left Acme"
        )

        changes = fact_changes(memory(), memory(after))

        self.assertEqual(
            changes,
            [
                'removed the facts line "- Dana likes old maps (dana.md)"',
                'rewrote the facts line "- Kim Lee leads Acme\'s IT (kim-lee.md)" '
                'as "- Kim Lee left Acme (kim-lee.md)"',
            ],
        )

    def test_a_current_line_is_no_facts_line(self) -> None:
        after = MEMORY.replace("- Rebuilding the shed roof\n", "")

        self.assertEqual(fact_changes(memory(), memory(after)), [])

    def test_an_emptied_or_removed_fact_file_is_a_change(self) -> None:
        """Covers: B55"""
        emptied = memory(dana="\n")
        removed = Snapshot({path: data for path, data in memory().files.items() if path != "memory/sam.md"})

        self.assertEqual(fact_changes(memory(), emptied), ["emptied memory/dana.md"])
        self.assertEqual(fact_changes(memory(), removed), ["removed memory/sam.md"])


class SnapshotTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base / "sb-test-store"
        self.store = FolderStore(self.root, self.base / "machine-tmp", DatalessGuard(False))
        self.store.replace(INDEX, MEMORY.encode())
        self.store.replace("memory/dana.md", b"# Dana\n")
        self.store.replace("memory/people/old.md", b"# Old\n")
        self.store.replace("inbox/note.md", b"not memory\n")

    def test_it_holds_every_file_below_memory_and_nothing_else(self) -> None:
        taken = Snapshot.take(self.store)

        self.assertEqual(sorted(taken.files), ["memory/MEMORY.md", "memory/dana.md", "memory/people/old.md"])

    def test_restore_puts_changed_and_removed_files_back_and_removes_new_ones(self) -> None:
        before = Snapshot.take(self.store)
        self.store.replace("memory/dana.md", b"# Dana changed\n")
        self.store.delete("memory/people/old.md")
        self.store.replace("memory/robin.md", b"# Robin\n")

        before.restore(self.store)

        self.assertEqual(Snapshot.take(self.store), before)

    def test_save_writes_a_copy_that_replaces_the_one_before(self) -> None:
        folder = self.base / "state" / "memory-before-run"
        Snapshot({"memory/stale.md": b"old run\n"}).save(folder)

        Snapshot.take(self.store).save(folder)

        saved = sorted(path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file())
        self.assertEqual(saved, ["MEMORY.md", "dana.md", "people/old.md"])
        self.assertEqual((folder / "dana.md").read_bytes(), b"# Dana\n")


if __name__ == "__main__":
    unittest.main()
