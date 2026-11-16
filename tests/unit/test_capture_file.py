"""A file from a session: copied into the inbox as a bundle, with the words given beside it."""

from __future__ import annotations

import contextlib
import datetime
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from m2b import cli, ingest, paths
from m2b.capture import NotSavedError
from m2b.capture_file import CaptureFileRefusedError, capture_file
from m2b.config import machine
from m2b.notes import frontmatter as keys
from m2b.notes.frontmatter import Note
from m2b.notes.trailer import find_trailer
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard
from store_contract import FakeEviction

PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n"
NOW = datetime.datetime(2026, 11, 16, 22, 5, tzinfo=datetime.timezone(datetime.timedelta(hours=1)))
MEGABYTE = 1024 * 1024


class CaptureFileFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.base = Path(self._temp.name)
        self.root = self.base / "sb-test-store"
        self.root.mkdir()
        self.store = FolderStore(self.root, self.base / "machine-tmp", DatalessGuard(True, lstat=FakeEviction().lstat))
        self.work = self.base / "sb-test-project"
        self.work.mkdir()

    def given(self, name: str, data: bytes = PDF_BYTES) -> Path:
        path = self.work / name
        path.write_bytes(data)
        return path

    def inbox(self) -> list[str]:
        folder = self.root / "inbox"
        return sorted(entry.name for entry in folder.iterdir()) if folder.exists() else []


class CopyTest(CaptureFileFixture):
    def test_the_file_and_a_note_beside_it_go_into_the_inbox_and_the_original_stays(self) -> None:
        """Covers: B233"""
        original = self.given("harbour-club-handbook.pdf")

        words = "Dana's club handbook, the fees are on page 4."

        captured = capture_file(self.store, original, words, "claude", 25, NOW)

        stem = captured.note.rsplit("/", 1)[1].rsplit(".", 1)[0]
        self.assertTrue(stem.startswith("20261116T210500Z-claude-"), stem)
        self.assertEqual(self.inbox(), [f"{stem}.md", f"{stem}.pdf"])
        self.assertEqual(captured.file, f"inbox/{stem}.pdf")
        self.assertEqual((self.root / captured.file).read_bytes(), PDF_BYTES)
        self.assertEqual(original.read_bytes(), PDF_BYTES)
        note = Note.parse((self.root / captured.note).read_text(encoding="utf-8"))
        assert note.frontmatter is not None
        self.assertEqual(note.frontmatter.get(keys.KIND), keys.KIND_SIDECAR)
        self.assertEqual(note.frontmatter.get(keys.SOURCE), "claude")
        trailer = find_trailer(note)
        assert trailer is not None
        self.assertIn(words, trailer.captured)
        self.assertIn(f"{ingest.ORIGINAL_NAME_PREFIX}harbour-club-handbook.pdf", trailer.notes)

    def test_a_curation_run_takes_the_bundle_as_it_is(self) -> None:
        """Covers: B233"""
        captured = capture_file(self.store, self.given("photo.HEIC", b"\x00\x00\x00\x18ftypheic"), "", "cli", 25, NOW)

        report = ingest.normalize(self.store, None)

        self.assertEqual((report.renamed, report.bundles, report.problems), ([], [], []))
        self.assertTrue(captured.file.endswith(".HEIC"), captured.file)
        self.assertEqual(len(self.inbox()), 2)

    def test_without_words_the_note_says_only_what_the_file_is(self) -> None:
        """Covers: B233"""
        captured = capture_file(self.store, self.given("scan.png", b"\x89PNG\r\n\x1a\n"), "  \n", "cli", 25, NOW)

        trailer = find_trailer(Note.parse((self.root / captured.note).read_text(encoding="utf-8")))
        assert trailer is not None
        self.assertEqual(trailer.captured.strip().splitlines(), [f"A png file, captured as {captured.file[6:]}."])

    def test_a_copy_that_fails_takes_its_note_with_it_and_says_not_saved(self) -> None:
        """Covers: B233"""
        write = self.store.create_exclusive

        def note_only(relative: str, data: bytes) -> None:
            if not relative.endswith(".md"):
                raise OSError(28, "No space left on device")
            write(relative, data)

        with (
            mock.patch.object(self.store, "create_exclusive", note_only),
            self.assertRaisesRegex(NotSavedError, "not captured: No space left on device"),
        ):
            capture_file(self.store, self.given("handbook.pdf"), "", "cli", 25, NOW)
        self.assertEqual(self.inbox(), [])


class RefusalTest(CaptureFileFixture):
    def test_over_the_limit_a_folder_a_link_a_text_file_or_no_file_is_refused_and_nothing_copied(self) -> None:
        """Covers: B234"""
        large = self.given("large.pdf", PDF_BYTES + bytes(2 * MEGABYTE))
        folder = self.work / "letters"
        folder.mkdir()
        link = self.work / "link.pdf"
        os.symlink(self.given("target.pdf"), link)
        cases = {
            "over": (large, "over the 1 MB"),
            "folder": (folder, "a folder"),
            "link": (link, "symbolic link"),
            "missing": (self.work / "gone.pdf", "no file"),
            "text": (self.given("notes.md", b"# Notes\n"), "m2b capture"),
            "dotfile": (self.given(".txt", b"words\n"), "m2b capture"),
            "dot md": (self.given(".md", b"words\n"), "m2b capture"),
            "name": (self.given("two\nlines.pdf"), "line"),
        }
        for case, (path, said) in cases.items():
            with self.subTest(case=case), self.assertRaisesRegex(CaptureFileRefusedError, said) as raised:
                capture_file(self.store, path, "", "cli", 1, NOW)
            self.assertEqual(len(str(raised.exception).splitlines()), 1)
        self.assertEqual(self.inbox(), [])

    def test_a_relative_path_is_refused(self) -> None:
        """Covers: B234"""
        with self.assertRaisesRegex(CaptureFileRefusedError, "absolute"):
            capture_file(self.store, Path("handbook.pdf"), "", "cli", 25, NOW)


class CommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        base = Path(self._temp.name)
        self.home = base / "home"
        self.store_root = base / "sb-test-store"
        self.store_root.mkdir()
        self.file = base / "handbook.pdf"
        self.file.write_bytes(PDF_BYTES)
        self.environ = {"HOME": str(base / "user-home"), "M2B_HOME": str(self.home)}
        machine.save_machine_config(
            paths.MachinePaths(self.home),
            {"version": 1, "machine_id": "sb-test-m1", "store": {"backend": "folder", "path": str(self.store_root)}},
        )

    def run_command(self, *arguments: str, stdin: str = "") -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with (
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
            mock.patch("sys.stdin", io.StringIO(stdin)),
        ):
            code = cli.main(list(arguments), self.environ)
        return code, out.getvalue(), err.getvalue()

    def test_the_command_prints_the_files_it_wrote_with_the_words_from_standard_input(self) -> None:
        """Covers: B233"""
        code, out, err = self.run_command(
            "capture-file", "--source", "claude", "--", str(self.file), "-", stdin="The handbook.\n"
        )

        self.assertEqual(code, cli.EXIT_OK, err)
        written = out.splitlines()
        self.assertEqual(len(written), 2)
        self.assertTrue(all(line.startswith("inbox/") for line in written), written)
        self.assertIn("The handbook.", (self.store_root / written[0]).read_text(encoding="utf-8"))

    def test_the_limit_is_a_setting_of_this_machine(self) -> None:
        """Covers: B234"""
        self.file.write_bytes(PDF_BYTES + bytes(2 * MEGABYTE))

        set_code, _, set_err = self.run_command("config", "set", "capture.file_limit_mb", "1")
        code, _, err = self.run_command("capture-file", "--", str(self.file))
        listed, settings, _ = self.run_command("settings")

        self.assertEqual(set_code, cli.EXIT_OK, set_err)
        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertEqual(len(err.strip().splitlines()), 1, err)
        self.assertIn("capture.file_limit_mb", err)
        self.assertFalse((self.store_root / "inbox").exists() and any((self.store_root / "inbox").iterdir()))
        self.assertEqual(listed, cli.EXIT_OK)
        self.assertIn("capture.file_limit_mb", settings)

    def test_the_default_limit_is_25_megabytes(self) -> None:
        """Covers: B234"""
        self.assertEqual(machine.DEFAULT_FILE_LIMIT_MB, 25)


if __name__ == "__main__":
    unittest.main()
