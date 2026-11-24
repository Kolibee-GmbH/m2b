"""An editing copy of a fact file: made, opened, kept as a capture or discarded, never written to memory/."""

from __future__ import annotations

import contextlib
import io
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from m2b import cli, fact_edit, paths, viewer
from m2b.config import machine
from m2b.notes.frontmatter import Note
from m2b.store.guard import DatalessGuard
from store_contract import FakeEviction

MAC = "darwin"
DANA = "# Dana\n\n- Lives in Zurich.\n\n## Evidence\n\n- [[20261003T080000Z-cli-d4e5.md]]\n"
EDITED = DANA.replace("Lives in Zurich.", "Lives in Basel since October.")


class Launcher:
    """Stands in for the system's text editor: notes each command and answers an exit."""

    def __init__(self, exit_code: int | None = 0) -> None:
        self.exit_code = exit_code
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str]) -> int | None:
        self.commands.append(command)
        return self.exit_code


class StoreEditTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        base = Path(self._temp.name)
        self.home = base / "home"
        self.store_root = base / "sb-test-store"
        self.store_root.mkdir()
        self.environ = {"HOME": str(base / "user-home"), "M2B_HOME": str(self.home)}
        self.launcher = Launcher()
        self.eviction = FakeEviction()
        self.machine = paths.MachinePaths(self.home)
        machine.save_machine_config(
            self.machine,
            {"version": 1, "machine_id": "sb-test-m1", "store": {"backend": "folder", "path": str(self.store_root)}},
        )
        self.write("memory/dana.md", DANA)
        self.write("memory/MEMORY.md", "# Memory\n\n## Facts\n\n- Dana lives in Zurich (dana.md)\n")
        (self.store_root / "inbox").mkdir()

    def write(self, relative: str, text: str) -> None:
        target = self.store_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def memory(self) -> dict[str, bytes]:
        return {
            str(path): path.read_bytes() for path in sorted((self.store_root / "memory").rglob("*")) if path.is_file()
        }

    def inbox(self) -> list[Path]:
        return sorted((self.store_root / "inbox").iterdir())

    def run_command(self, *arguments: str, environ: dict[str, str] | None = None) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        guard = DatalessGuard(True, lstat=self.eviction.lstat)
        with (
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
            mock.patch("m2b.viewer.sys.platform", MAC),
            mock.patch("m2b.viewer.launch", self.launcher),
            mock.patch("m2b.store.factory.guard_for_platform", return_value=guard),
        ):
            code = cli.main(list(arguments), environ or self.environ)
        return code, out.getvalue(), err.getvalue()

    def edit_json(self, *arguments: str) -> dict[str, object]:
        code, out, err = self.run_command("store", "edit", "--json", *arguments)
        self.assertEqual(code, cli.EXIT_OK, err)
        answer: dict[str, object] = json.loads(out)
        return answer

    def viewer_edit(self) -> dict[str, object]:
        code, out, err = self.run_command("source", "--json", "--viewer", "dana.md")
        self.assertEqual(code, cli.EXIT_OK, err)
        edit: dict[str, object] = json.loads(out)["edit"]
        return edit

    def test_edit_makes_a_private_copy_outside_the_store_and_opens_it_in_the_text_editor(self) -> None:
        """Covers: B306"""
        before = self.memory()

        answer = self.edit_json("dana.md")

        copy = fact_edit.copy_path(self.machine, "dana.md")
        self.assertEqual(answer, {"copy": str(copy), "opened": True, "not_opened": None})
        self.assertEqual(copy.read_text(encoding="utf-8"), DANA)
        self.assertEqual(stat.S_IMODE(copy.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(copy.parent.stat().st_mode), 0o700)
        self.assertFalse(str(copy).startswith(str(self.store_root)))
        self.assertEqual(self.launcher.commands, [["/usr/bin/open", "-t", str(copy)]])
        self.assertEqual(self.memory(), before)

    def test_an_existing_copy_is_opened_again_as_it_is(self) -> None:
        """Covers: B306"""
        self.edit_json("dana.md")
        copy = fact_edit.copy_path(self.machine, "dana.md")
        copy.write_text(EDITED, encoding="utf-8")

        self.edit_json("dana.md")

        self.assertEqual(copy.read_text(encoding="utf-8"), EDITED)
        self.assertEqual(len(self.launcher.commands), 2)

    def test_over_ssh_the_copy_is_named_and_nothing_opens(self) -> None:
        """Covers: B306"""
        code, out, err = self.run_command(
            "store", "edit", "dana.md", environ={**self.environ, "SSH_TTY": "/dev/ttys001"}
        )

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertIn(str(fact_edit.copy_path(self.machine, "dana.md")), out)
        self.assertIn("not opened", out)
        self.assertEqual(self.launcher.commands, [])

    def test_what_is_no_fact_file_a_file_not_downloaded_and_a_run_under_way_make_no_copy(self) -> None:
        """Covers: B306"""
        self.write("memory/lessons/run-only-the-touched-checks.md", "# Lesson\n")
        self.write("memory/sam.md", "# Sam\n")
        self.eviction.evicted.add(self.store_root / "memory" / "sam.md")
        refused = {
            "MEMORY.md": cli.EXIT_USAGE,
            "lessons/run-only-the-touched-checks.md": cli.EXIT_USAGE,
            "memory/dana.md": cli.EXIT_USAGE,
            "kim.md": cli.EXIT_PROBLEM,
            "sam.md": cli.EXIT_PROBLEM,
        }
        for name, exit_code in refused.items():
            with self.subTest(name=name):
                code, _, err = self.run_command("store", "edit", name)
                self.assertEqual(code, exit_code, err)
        with mock.patch("m2b.commands.store.lock_is_held", return_value=True):
            code, _, err = self.run_command("store", "edit", "dana.md")
        self.assertEqual(code, cli.EXIT_PROBLEM, err)
        self.assertIn("a curation run is under way", err)
        self.assertFalse((self.home / ".local" / "state" / "m2b" / fact_edit.EDITS_FOLDER).exists())
        self.assertEqual(self.launcher.commands, [])

    def test_keep_writes_one_edit_capture_with_about_and_base_and_removes_the_copy(self) -> None:
        """Covers: B307"""
        self.edit_json("dana.md")
        copy = fact_edit.copy_path(self.machine, "dana.md")
        copy.write_text(EDITED, encoding="utf-8")
        before = self.memory()

        answer = self.edit_json("--keep", "dana.md")

        (kept,) = self.inbox()
        self.assertEqual(answer, {"kept": f"inbox/{kept.name}"})
        note = Note.parse(kept.read_text(encoding="utf-8"))
        assert note.frontmatter is not None
        self.assertEqual(
            (note.frontmatter.get("kind"), note.frontmatter.get("about"), note.frontmatter.get("base")),
            ("edit", "dana.md", fact_edit.content_hash(DANA.encode("utf-8"))),
        )
        self.assertEqual(note.body, EDITED)
        self.assertFalse(copy.exists())
        self.assertEqual(self.memory(), before)

    def test_keep_of_an_unchanged_copy_and_discard_write_nothing_and_remove_the_copy(self) -> None:
        """Covers: B307"""
        copy = fact_edit.copy_path(self.machine, "dana.md")
        self.edit_json("dana.md")
        self.assertEqual(self.edit_json("--keep", "dana.md"), {"kept": None})
        self.assertFalse(copy.exists())

        self.edit_json("dana.md")
        copy.write_text(EDITED, encoding="utf-8")
        self.assertEqual(self.edit_json("--discard", "dana.md"), {"discarded": True})

        self.assertFalse(copy.exists())
        self.assertEqual(self.inbox(), [])
        code, _, err = self.run_command("store", "edit", "--keep", "dana.md")
        self.assertEqual(code, cli.EXIT_PROBLEM, err)

    def test_viewer_and_band_say_where_the_copy_stands(self) -> None:
        """Covers: B308"""
        self.assertEqual(self.viewer_edit(), {"copy": None, "differs": False, "fact_file_changed": False, "kept": []})
        self.edit_json("dana.md")
        copy = fact_edit.copy_path(self.machine, "dana.md")
        copy.write_text(EDITED, encoding="utf-8")
        self.write("memory/dana.md", DANA + "- One more line.\n")

        self.assertEqual(
            self.viewer_edit(), {"copy": str(copy), "differs": True, "fact_file_changed": True, "kept": []}
        )
        self.assertEqual(fact_edit.differing_copies(self.machine), 1)

        self.edit_json("--keep", "dana.md")
        (kept,) = self.inbox()
        edit = self.viewer_edit()
        self.assertEqual((edit["copy"], edit["kept"]), (None, [kept.name]))
        code, out, err = self.run_command("source", "--json", "--viewer", "dana.md")
        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(json.loads(out)["corrections"], [])
        self.assertEqual(fact_edit.differing_copies(self.machine), 0)

    def test_a_left_over_base_or_a_copy_without_its_base_is_no_copy_and_a_new_one_is_made(self) -> None:
        """Covers: B306"""
        self.edit_json("dana.md")
        copy = fact_edit.copy_path(self.machine, "dana.md")
        base = copy.with_name("dana.md.base")
        copy.unlink()
        self.write("memory/dana.md", EDITED)

        self.edit_json("dana.md")

        self.assertEqual(base.read_text(encoding="ascii"), fact_edit.content_hash(EDITED.encode("utf-8")))
        base.unlink()
        self.assertEqual(self.viewer_edit()["copy"], None)
        self.edit_json("dana.md")
        self.assertTrue(base.is_file())

    def test_a_failed_start_of_the_editor_names_the_copy_and_does_not_fail_the_command(self) -> None:
        """Covers: B306"""

        def failing(command: list[str]) -> int | None:
            raise viewer.NotOpenedError("could not start /usr/bin/open: Permission denied")

        self.launcher = failing  # type: ignore[assignment]

        answer = self.edit_json("dana.md")

        self.assertEqual(
            (answer["opened"], answer["not_opened"]), (False, "could not start /usr/bin/open: Permission denied")
        )
        self.assertTrue(fact_edit.copy_path(self.machine, "dana.md").is_file())

    def test_an_emptied_copy_is_not_kept_and_stays_for_a_discard(self) -> None:
        """Covers: B307"""
        self.edit_json("dana.md")
        copy = fact_edit.copy_path(self.machine, "dana.md")
        copy.write_text("\n  \n", encoding="utf-8")

        code, _, err = self.run_command("store", "edit", "--keep", "dana.md")

        self.assertEqual(code, cli.EXIT_PROBLEM, err)
        self.assertIn("is empty", err)
        self.assertEqual(self.inbox(), [])
        self.assertTrue(copy.exists())

    def test_discard_drops_a_copy_whose_fact_file_is_gone(self) -> None:
        """Covers: B307"""
        self.edit_json("dana.md")
        (self.store_root / "memory" / "dana.md").unlink()

        self.assertEqual(self.edit_json("--discard", "dana.md"), {"discarded": True})
        self.assertFalse(fact_edit.copy_path(self.machine, "dana.md").exists())
        code, _, err = self.run_command("store", "edit", "--discard", "memory/dana.md")
        self.assertEqual(code, cli.EXIT_USAGE, err)


if __name__ == "__main__":
    unittest.main()
