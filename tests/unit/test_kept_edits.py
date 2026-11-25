"""A kept edit of a fact file: put in place by the run's harvest step, before ingest, under three checks."""

from __future__ import annotations

import datetime
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

import test_runner
from m2b import ingest, kept_edits
from m2b.capture import capture
from m2b.fact_edit import content_hash
from m2b.notes import frontmatter as keys
from m2b.notes.frontmatter import Note
from m2b.run_record import SUCCEEDED
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard
from store_contract import FakeEviction

DANA = "# Dana\n\n- Lives in Zurich.\n\n## Evidence\n\n- [[20261003T080000Z-cli-d4e5.md]]\n"
EDITED = DANA.replace("Lives in Zurich.", "Lives in Basel since October.")
INDEX = "# Memory\n\n## Facts\n\n- Dana lives in Zurich (dana.md)\n\n## Current\n"
NOW = datetime.datetime(2026, 11, 7, 7, 0, tzinfo=datetime.timezone.utc)


def kept_edit(store: Any, text: str = EDITED, about: str = "dana.md", base: str | None = None) -> str:
    """The capture ``m2b store edit --keep`` writes, made from the fact file as it is now."""
    if base is None:
        base = content_hash(store.read_bytes("memory/dana.md"))
    return capture(store, text, "cli", kind=keys.KIND_EDIT, about=about, base=base, now=NOW).path


class PutInPlaceTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "sb-test-store"
        self.eviction = FakeEviction()
        self.store = FolderStore(
            self.root, Path(temp.name) / "machine-tmp", DatalessGuard(True, lstat=self.eviction.lstat)
        )
        self.write("memory/dana.md", DANA)
        self.write("memory/MEMORY.md", INDEX)
        self.write("memory/lessons/ask-first.md", "# Ask first\n")
        (self.root / "inbox").mkdir()

    def write(self, relative: str, text: str) -> None:
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def read(self, relative: str) -> str:
        return (self.root / relative).read_text(encoding="utf-8")

    def archived(self) -> list[str]:
        return sorted(path.name for path in (self.root / "corpus").rglob("*.md"))

    def test_an_edit_made_from_the_fact_file_as_it_stands_is_put_in_place_and_marked(self) -> None:
        """Covers: B309"""
        path = kept_edit(self.store)

        report = kept_edits.put_in_place(self.store)

        self.assertEqual(self.read("memory/dana.md"), EDITED)
        self.assertEqual(report.placed, [kept_edits.Placed(Path(path).name, "dana.md")])
        self.assertEqual((report.refused, report.waiting), ([], []))
        note = Note.parse(self.read(path))
        assert note.frontmatter is not None
        self.assertTrue(note.frontmatter.get_flag(keys.PLACED))
        self.assertEqual(note.body, EDITED)

    def test_a_fact_file_with_an_until_is_put_in_place(self) -> None:
        """Covers: B309"""
        dated = "---\nuntil: 2026-12-31\n---\n" + EDITED
        kept_edit(self.store, dated)

        kept_edits.put_in_place(self.store)

        self.assertEqual(self.read("memory/dana.md"), dated)

    def test_an_edit_that_fails_a_check_stays_out_and_goes_to_the_archive_with_its_reason(self) -> None:
        """Covers: B310"""
        cases = {
            "the fact file changed since": (EDITED, "dana.md", content_hash(b"# Dana\n\n- Lived somewhere.\n")),
            "no title": ("- Lives in Basel.\n", "dana.md", None),
            "a broken frontmatter": ("---\nuntil 2026-12-31\n# Dana\n\n- Lives in Basel.\n", "dana.md", None),
            "an until that is no day": ("---\nuntil: soon\n---\n# Dana\n\n- Lives in Basel.\n", "dana.md", None),
            "a key no fact file has": ("---\nsource: cli\n---\n# Dana\n\n- Lives in Basel.\n", "dana.md", None),
            "nothing but blank lines": ("\n\n", "dana.md", None),
            "a character that hides text": ("# Dana\n\n- Lives in Basel‮.\n", "dana.md", None),
            "the distillate": ("# Memory\n", "MEMORY.md", None),
            "a lesson": ("# Ask first\n", "lessons/ask-first.md", None),
            "no such fact file": ("# Kim\n", "kim.md", content_hash(b"")),
        }
        for case, (text, about, base) in cases.items():
            with self.subTest(case):
                for leftover in (self.root / "inbox").iterdir():
                    leftover.unlink()
                before = {name: self.read(f"memory/{name}") for name in ("dana.md", "MEMORY.md")}
                path = self._raw_edit(text, about, base)

                report = kept_edits.put_in_place(self.store)

                self.assertEqual({name: self.read(f"memory/{name}") for name in before}, before)
                self.assertEqual(self.read("memory/lessons/ask-first.md"), "# Ask first\n")
                self.assertEqual(report.placed, [])
                (refused,) = report.refused
                self.assertEqual(refused.capture, Path(path).name)
                self.assertIn(Path(path).name, self.archived())
                self.assertFalse((self.root / path).exists())
                self.assertNotIn("Basel", refused.reason)

    def test_the_review_names_a_hidden_character_by_its_code_point_and_a_changed_file_by_what_to_do(self) -> None:
        """Covers: B310"""
        self._raw_edit("# Dana\n\n- Lives in Basel‮.\n", "dana.md", None)
        (hidden,) = kept_edits.put_in_place(self.store).refused
        self.assertIn("U+202E", hidden.reason)
        self.assertNotIn("‮", hidden.reason)

        self._raw_edit(EDITED, "dana.md", content_hash(b"older"))
        (changed,) = kept_edits.put_in_place(self.store).refused
        self.assertEqual(changed.fact_file, "dana.md")
        self.assertIn("m2b store edit dana.md", changed.reason)

    def test_an_edit_put_in_place_before_is_not_put_in_place_again(self) -> None:
        """Covers: B309"""
        path = kept_edit(self.store)
        kept_edits.put_in_place(self.store)
        self.write("memory/dana.md", EDITED + "- Added by a later step.\n")

        report = kept_edits.put_in_place(self.store)

        self.assertEqual((report.placed, report.refused, report.waiting), ([], [], []))
        self.assertTrue((self.root / path).exists())
        self.assertIn("Added by a later step", self.read("memory/dana.md"))

    def test_an_edit_in_place_but_not_marked_yet_is_marked_and_not_refused(self) -> None:
        """Covers: B309"""
        path = kept_edit(self.store)
        self.write("memory/dana.md", EDITED)

        report = kept_edits.put_in_place(self.store)

        self.assertEqual(report.placed, [kept_edits.Placed(Path(path).name, "dana.md")])
        self.assertEqual(report.refused, [])
        note = Note.parse(self.read(path))
        assert note.frontmatter is not None
        self.assertTrue(note.frontmatter.get_flag(keys.PLACED))

    def test_an_edit_of_a_fact_file_that_is_not_downloaded_waits_in_the_inbox(self) -> None:
        """Covers: B309"""
        path = kept_edit(self.store)
        self.eviction.evicted.add(self.root / "memory/dana.md")

        report = kept_edits.put_in_place(self.store)

        self.assertEqual((report.placed, report.refused), ([], []))
        (waiting,) = report.waiting
        self.assertIn("dana.md", waiting)
        self.assertIn("not downloaded", waiting)
        self.assertTrue((self.root / path).exists())

    def test_a_refused_edit_that_cannot_be_archived_waits_and_the_next_edit_is_still_put_in_place(self) -> None:
        """Covers: B310"""
        broken = self._raw_edit(EDITED.replace("Basel", "Bern"), "dana.md", content_hash(b"older"))
        target = self.root / broken
        target.write_text(target.read_text(encoding="utf-8").replace("2026-11-07T08:00:00+01:00", "yesterday"))
        later = kept_edit(self.store)

        report = kept_edits.put_in_place(self.store)

        self.assertEqual(report.refused, [])
        (waiting,) = report.waiting
        self.assertIn(Path(broken).name, waiting)
        self.assertTrue(target.exists())
        self.assertEqual(report.placed, [kept_edits.Placed(Path(later).name, "dana.md")])

    def test_ingest_lists_an_edit_only_once_it_is_in_place_and_then_with_its_fact_file(self) -> None:
        """Covers: B311"""
        path = kept_edit(self.store)
        name = Path(path).name

        waiting = ingest.pending(self.store)
        self.assertEqual(waiting.captures, [])
        self.assertEqual(waiting.problems, [])
        self.assertEqual(waiting.stuck, [path])

        kept_edits.put_in_place(self.store)
        (listed,) = ingest.pending(self.store).captures
        self.assertEqual((listed.file, listed.kind, listed.about, listed.placed), (name, "edit", "dana.md", True))

    def _raw_edit(self, text: str, about: str, base: str | None) -> str:
        """A capture of kind edit as a hand or another machine may have written it: no check on the way in."""
        stamp = len(list((self.root / "corpus").rglob("*.md"))) if (self.root / "corpus").exists() else 0
        name = f"20261107T07{stamp:02d}00Z-cli-e{stamp:03d}.md"
        base = base or content_hash((self.root / "memory/dana.md").read_bytes())
        self.write(
            f"inbox/{name}",
            f"---\ncreated: 2026-11-07T08:00:00+01:00\nsource: cli\nkind: edit\nabout: {about}\nbase: {base}\n---\n"
            + text,
        )
        return f"inbox/{name}"


INGEST_BRINGS_THE_LINE_IN_STEP = [
    {"tool": "Bash", "command": "m2b ingest list --json"},
    {
        "tool": "Edit",
        "file_path": "<store>/memory/MEMORY.md",
        "old_string": "- Dana lives in Zurich (dana.md)",
        "new_string": "- Dana lives in Basel since October (dana.md)",
    },
    {"tool": "Bash", "command": "m2b ingest note <capture:cli> 'filed: edit of dana.md, line rewritten'"},
    {"tool": "Bash", "command": "m2b ingest finish <capture:cli>"},
]


class EditInARunTest(test_runner.RunnerTest):
    def setUp(self) -> None:
        super().setUp()
        self.curating()
        self.write("memory/MEMORY.md", INDEX)
        self.write("memory/dana.md", DANA)

    def memory_file(self, name: str) -> str:
        return (self.store_root / "memory" / name).read_text(encoding="utf-8")

    def test_a_run_puts_the_edit_in_place_before_ingest_which_brings_the_distillate_in_step(self) -> None:
        """Covers: B309, B311"""
        name = Path(kept_edit(self.store)).name
        self.model({"m2b:ingest": INGEST_BRINGS_THE_LINE_IN_STEP})

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.memory_file("dana.md"), EDITED)
        self.assertIn("- Dana lives in Basel since October (dana.md)", self.memory_file("MEMORY.md"))
        self.assertEqual(list((self.store_root / "inbox").iterdir()), [])
        (review,) = self.review_tasks()
        # That it is in place is no action for the owner; the rewritten line is.
        self.assertNotIn("your edit", review.notes)
        self.assertIn(name, review.notes)
        self.assertIn(
            'ingest: rewrote the facts line "- Dana lives in Zurich (dana.md)" as '
            '"- Dana lives in Basel since October (dana.md)"',
            review.notes,
        )
        # The copy of memory/ from before the run holds the fact file as it was before the edit.
        (saved,) = (self.machine.state_dir / "memory-before-run").iterdir()
        self.assertEqual((saved / "dana.md").read_text(encoding="utf-8"), DANA)
        self.assertIn(f"memory/ as it was before this run is in {saved}", review.notes)

    def test_an_edit_that_is_refused_is_named_in_the_review_without_its_text(self) -> None:
        """Covers: B310"""
        name = Path(kept_edit(self.store, base=content_hash(b"older"))).name
        self.model({"m2b:ingest": INGEST_BRINGS_THE_LINE_IN_STEP})

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.memory_file("dana.md"), DANA)
        (review,) = self.review_tasks()
        self.assertIn(f"harvest: your edit of dana.md was not put in place ({name})", review.notes)
        self.assertNotIn("Basel", review.notes)
        self.assertEqual(list((self.store_root / "inbox").iterdir()), [])
        self.assertEqual(len(list((self.store_root / "corpus").rglob(name))), 1)
        # Nothing waited for the ingest step, so its model never started.
        self.assertEqual([call for call in self.calls() if "ingest" in str(call)], [])

    def test_an_edit_that_waits_in_the_inbox_starts_no_ingest_model_by_itself(self) -> None:
        """Covers: B310"""
        base = content_hash(b"older")
        self.write(
            "inbox/20261107T070000Z-cli-e000.md",
            f"---\ncreated: yesterday\nsource: cli\nkind: edit\nabout: dana.md\nbase: {base}\n---\n{EDITED}",
        )
        self.model({"m2b:ingest": INGEST_BRINGS_THE_LINE_IN_STEP})

        self.run_curate()

        self.assertEqual(self.memory_file("dana.md"), DANA)
        self.assertEqual(len(list((self.store_root / "inbox").iterdir())), 1)
        self.assertEqual([call for call in self.calls() if "ingest" in str(call)], [])
        (review,) = self.review_tasks()
        self.assertIn("an edit that was not put in place", review.notes)

    def test_an_ingest_step_that_fails_leaves_the_edit_in_the_inbox_for_the_next_run_to_file(self) -> None:
        """Covers: B309, B311"""
        kept_edit(self.store)
        self.model({"m2b:ingest": [{"tool": "Bash", "command": "m2b ingest list --json"}]}, {"m2b:ingest": "error"})

        self.run_curate()

        self.assertEqual(self.memory_file("dana.md"), EDITED)
        self.assertEqual(len(list((self.store_root / "inbox").iterdir())), 1)
        # A later run changed the fact file; the edit is not put over that change, nor refused.
        self.write("memory/dana.md", EDITED + "- Likes old maps.\n")
        self.model({"m2b:ingest": INGEST_BRINGS_THE_LINE_IN_STEP})
        self.clock = test_runner.START + datetime.timedelta(hours=2)

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.memory_file("dana.md"), EDITED + "- Likes old maps.\n")
        self.assertEqual(list((self.store_root / "inbox").iterdir()), [])
        (review,) = self.review_tasks()
        self.assertNotIn("was not put in place", review.notes)

    def test_an_edit_the_guard_puts_back_after_ingest_filed_it_is_filed_again_by_the_next_run(self) -> None:
        """Covers: B311"""
        path = kept_edit(self.store)
        # A line with a character that hides text: the guard puts memory/ back as before the step.
        planted = {
            "tool": "Edit",
            "file_path": "<store>/memory/MEMORY.md",
            "old_string": "## Current\n",
            "new_string": "## Current\n\n- Planning a trip\u202e\n",
        }
        self.model({"m2b:ingest": [*INGEST_BRINGS_THE_LINE_IN_STEP, planted]})

        self.run_curate()

        self.assertEqual(self.memory_file("dana.md"), EDITED)
        self.assertIn("- Dana lives in Zurich (dana.md)", self.memory_file("MEMORY.md"))
        note = Note.parse((self.store_root / path).read_text(encoding="utf-8"))
        assert note.frontmatter is not None
        self.assertTrue(note.frontmatter.get_flag(keys.PLACED))
        self.assertFalse(note.frontmatter.get_flag(keys.FACTS_FILED))
        self.assertEqual(list((self.store_root / "corpus").rglob(Path(path).name)), [])

        self.model({"m2b:ingest": INGEST_BRINGS_THE_LINE_IN_STEP})
        self.clock = test_runner.START + datetime.timedelta(hours=2)
        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.memory_file("dana.md"), EDITED)
        self.assertIn("- Dana lives in Basel since October (dana.md)", self.memory_file("MEMORY.md"))
        self.assertEqual(list((self.store_root / "inbox").iterdir()), [])


@unittest.skipIf(shutil.which("git") is None, "git is not installed")
class EditInARepositoryTest(test_runner.RunnerTest):
    OWNER = ("-c", "user.name=Alex", "-c", "user.email=alex@example.com")

    def setUp(self) -> None:
        super().setUp()
        self.environ["GIT_CONFIG_GLOBAL"] = os.devnull
        self.environ["GIT_CONFIG_SYSTEM"] = os.devnull
        self.curating()
        self.write("memory/MEMORY.md", INDEX)
        self.write("memory/dana.md", DANA)
        self.git("init", "-q", "-b", "main")
        self.git("add", "--all")
        self.git("commit", "-q", "-m", "the store as Alex set it up")

    def git(self, *arguments: str) -> str:
        result = subprocess.run(
            ["git", *self.OWNER, *arguments],
            cwd=self.store_root,
            env=self.environ,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def paths_in(self, commit: str) -> list[str]:
        return sorted(self.git("show", "--name-only", "--format=", "--no-renames", commit).splitlines())

    def test_the_edit_is_in_the_commit_of_the_captures_and_its_change_in_the_runs_and_a_revert_undoes_it(self) -> None:
        """Covers: B312"""
        path = kept_edit(self.store)
        name = Path(path).name
        self.model({"m2b:ingest": INGEST_BRINGS_THE_LINE_IN_STEP})

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.paths_in("HEAD~1"), [path])
        self.assertIn("memory/dana.md", self.paths_in("HEAD"))
        self.assertIn(f"corpus/2026/11/{name}", self.paths_in("HEAD"))
        self.assertEqual(self.git("show", f"HEAD~1:{path}").split("---\n", 2)[2], EDITED)

        self.git("revert", "--no-edit", "HEAD")

        self.assertEqual((self.store_root / "memory/dana.md").read_text(encoding="utf-8"), DANA)
        self.assertTrue((self.store_root / path).exists())
        self.assertFalse((self.store_root / f"corpus/2026/11/{name}").exists())


if __name__ == "__main__":
    unittest.main()
