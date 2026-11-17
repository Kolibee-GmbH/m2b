"""A PDF or a picture of the archive, opened in the system's viewer for the pane's `open the file`."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from m2b import cli, paths
from m2b.config import machine
from m2b.source import PICTURE_EXTENSIONS, SourceNotFoundError
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard
from m2b.viewer import (
    VIEWABLE_EXTENSIONS,
    NoScreenError,
    NotOpenedError,
    OpenRefusedError,
    open_original,
    screen_command,
    why_not_opened,
)
from store_contract import FakeEviction

HANDBOOK = "corpus/2026/11/20261116T165634Z-cli-7198"
PHOTO = "corpus/2026/09/20260903T100000Z-phone-c3d4"
PAGE = "corpus/2026/10/20261020T090000Z-cli-5e6f"
PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n"
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"
HEIC_BYTES = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00"
HTML_BYTES = b"<!doctype html><script>alert(1)</script>"
MAC = "darwin"
LINUX = "linux"
DESKTOP: dict[str, str] = {"HOME": "/home/sb-test"}

DOCUMENT_NOTE = """---
kind: sidecar
created: 2026-11-16T17:56:34+01:00
source: cli
curated: true
---
A pdf file, captured as 20261116T165634Z-cli-7198.pdf.
<!-- m2b:curation -->
original name: harbour-rowing-club-handbook.pdf
p. 1: club name, handbook 2026
"""


class Launcher:
    """Stands in for the system's viewer: notes each command and answers an exit, None while it runs."""

    def __init__(self, exit_code: int | None = 0) -> None:
        self.exit_code = exit_code
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str]) -> int | None:
        self.commands.append(command)
        return self.exit_code


class ViewerFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.base = Path(self._temp.name)
        self.root = self.base / "sb-test-store"
        self.root.mkdir()
        self.eviction = FakeEviction()
        self.store = FolderStore(self.root, self.base / "machine-tmp", DatalessGuard(True, lstat=self.eviction.lstat))
        self.launcher = Launcher()

    def write(self, relative: str, data: bytes) -> None:
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def open_on_mac(self, name: str, environ: dict[str, str] | None = None) -> str:
        return open_original(self.store, name, environ or DESKTOP, MAC, self.launcher)


class OpenTest(ViewerFixture):
    def test_a_pdf_of_the_archive_opens_in_the_viewer_on_a_mac(self) -> None:
        """Covers: B228"""
        self.write(f"{HANDBOOK}.pdf", PDF_BYTES)

        opened = self.open_on_mac("20261116T165634Z-cli-7198.pdf")

        self.assertEqual(opened, f"{HANDBOOK}.pdf")
        self.assertEqual(self.launcher.commands, [["/usr/bin/open", str(self.root / f"{HANDBOOK}.pdf")]])

    def test_a_picture_opens_and_a_viewer_still_running_is_opened(self) -> None:
        """Covers: B228"""
        self.write(f"{PHOTO}.heic", HEIC_BYTES)
        self.write(f"{PHOTO}.jpg", JPEG_BYTES)
        self.launcher.exit_code = None

        self.open_on_mac("20260903T100000Z-phone-c3d4.heic")
        self.open_on_mac("20260903T100000Z-phone-c3d4.jpg")

        self.assertEqual(len(self.launcher.commands), 2)

    def test_any_other_kind_or_a_name_that_is_no_file_of_the_archive_is_refused_before_anything_is_read(self) -> None:
        """Covers: B228"""
        self.write(f"{PAGE}.html", HTML_BYTES)
        self.write(f"{PAGE}.svg", b"<svg onload='x'/>")
        for name in (
            "20261020T090000Z-cli-5e6f.html",
            "20261020T090000Z-cli-5e6f.svg",
            "20261020T090000Z-cli-5e6f.md",
            "handbook.pdf",
            "../20261116T165634Z-cli-7198.pdf",
            f"{HANDBOOK}.pdf",
            "",
        ):
            with self.subTest(name=name), self.assertRaises(OpenRefusedError):
                self.open_on_mac(name)
        self.assertEqual(self.launcher.commands, [])

    def test_a_file_whose_bytes_are_not_of_its_kind_is_not_opened(self) -> None:
        """Covers: B228"""
        for extension, data in (
            ("pdf", HTML_BYTES),
            ("pdf", b"<!doctype html><!--%PDF-1.4--><script>alert(1)</script>"),
            ("bmp", b"BM<!doctype html><script>alert(1)</script>"),
        ):
            with self.subTest(extension=extension, data=data[:20]):
                self.write(f"{HANDBOOK}.{extension}", data)

                with self.assertRaisesRegex(NotOpenedError, f"not a {extension}"):
                    self.open_on_mac(f"20261116T165634Z-cli-7198.{extension}")
        self.assertEqual(self.launcher.commands, [])

    def test_a_bitmap_with_a_header_of_its_kind_opens(self) -> None:
        """Covers: B228"""
        self.write(f"{PHOTO}.bmp", b"BM" + bytes(12) + (40).to_bytes(4, "little") + bytes(16))

        self.open_on_mac("20260903T100000Z-phone-c3d4.bmp")

        self.assertEqual(len(self.launcher.commands), 1)

    def test_a_file_not_on_this_machine_is_named_with_the_command_that_fetches_it(self) -> None:
        """Covers: B228"""
        self.write(f"{HANDBOOK}.pdf", PDF_BYTES)
        self.eviction.evicted.add(self.root / f"{HANDBOOK}.pdf")

        with self.assertRaisesRegex(NotOpenedError, "m2b store fetch"):
            self.open_on_mac("20261116T165634Z-cli-7198.pdf")
        self.assertEqual(self.launcher.commands, [])

    def test_a_symbolic_link_is_not_followed(self) -> None:
        """Covers: B228"""
        outside = self.base / "elsewhere.pdf"
        outside.write_bytes(PDF_BYTES)
        (self.root / HANDBOOK).parent.mkdir(parents=True)
        os.symlink(outside, self.root / f"{HANDBOOK}.pdf")

        with self.assertRaisesRegex(NotOpenedError, "symbolic link"):
            self.open_on_mac("20261116T165634Z-cli-7198.pdf")
        self.assertEqual(self.launcher.commands, [])

    def test_a_name_nothing_has_is_not_found(self) -> None:
        """Covers: B228"""
        with self.assertRaises(SourceNotFoundError):
            self.open_on_mac("20261116T165634Z-cli-7198.pdf")

    def test_a_month_that_lives_only_in_the_cloud_is_named_with_the_command_that_fetches_it(self) -> None:
        """Covers: B228"""
        self.write(f"{HANDBOOK}.pdf", PDF_BYTES)
        self.eviction.evicted.add(self.root / "corpus/2026/11")

        with self.assertRaisesRegex(NotOpenedError, "corpus/2026/11"):
            self.open_on_mac("20261116T165634Z-cli-7198.pdf")

    def test_a_viewer_that_fails_is_said(self) -> None:
        """Covers: B228"""
        self.write(f"{HANDBOOK}.pdf", PDF_BYTES)
        self.launcher.exit_code = 1

        with self.assertRaisesRegex(NotOpenedError, "exit 1"):
            self.open_on_mac("20261116T165634Z-cli-7198.pdf")


class ScreenTest(ViewerFixture):
    def test_a_mac_session_over_ssh_has_no_screen_to_open_on(self) -> None:
        """Covers: B228"""
        self.write(f"{HANDBOOK}.pdf", PDF_BYTES)

        over_ssh = {**DESKTOP, "SSH_CONNECTION": "10.0.0.2 50000 10.0.0.1 22"}

        with self.assertRaisesRegex(NoScreenError, "SSH"):
            self.open_on_mac("20261116T165634Z-cli-7198.pdf", over_ssh)
        self.assertEqual(self.launcher.commands, [])

    def test_linux_opens_with_xdg_open_only_where_there_is_a_display(self) -> None:
        """Covers: B228"""
        tools = self.base / "bin"
        tools.mkdir()
        xdg_open = tools / "xdg-open"
        xdg_open.write_text("#!/bin/sh\n")
        xdg_open.chmod(0o755)

        self.assertEqual(screen_command({"PATH": str(tools), "WAYLAND_DISPLAY": "wayland-0"}, LINUX), [str(xdg_open)])
        with self.assertRaisesRegex(NoScreenError, "no screen"):
            screen_command({"PATH": str(tools)}, LINUX)
        with self.assertRaisesRegex(NoScreenError, "xdg-open"):
            screen_command({"PATH": str(self.base), "DISPLAY": ":0"}, LINUX)
        with self.assertRaisesRegex(NoScreenError, "macOS and Linux"):
            screen_command(DESKTOP, "win32")


class WhyNotTest(unittest.TestCase):
    def test_why_a_file_does_not_open_is_its_kind_that_it_is_not_here_or_the_screen(self) -> None:
        """Covers: B229"""
        self.assertEqual(VIEWABLE_EXTENSIONS, PICTURE_EXTENSIONS | {".pdf"})
        self.assertIsNone(why_not_opened(f"{HANDBOOK}.pdf", True, DESKTOP, MAC))
        self.assertIsNone(why_not_opened(f"{PHOTO}.HEIC", True, DESKTOP, MAC))
        self.assertIn("only a PDF or a picture", why_not_opened(f"{PAGE}.html", True, DESKTOP, MAC) or "")
        self.assertIn("m2b store fetch", why_not_opened(f"{HANDBOOK}.pdf", False, DESKTOP, MAC) or "")
        self.assertIn("SSH", why_not_opened(f"{HANDBOOK}.pdf", True, {"SSH_TTY": "/dev/ttys001"}, MAC) or "")


class StoreOpenCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        base = Path(self._temp.name)
        self.home = base / "home"
        self.store_root = base / "sb-test-store"
        self.store_root.mkdir()
        self.environ = {"HOME": str(base / "user-home"), "M2B_HOME": str(self.home)}
        self.launcher = Launcher()
        machine.save_machine_config(
            paths.MachinePaths(self.home),
            {"version": 1, "machine_id": "sb-test-m1", "store": {"backend": "folder", "path": str(self.store_root)}},
        )

    def write(self, relative: str, data: bytes) -> None:
        target = self.store_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def run_command(self, *arguments: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with (
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
            mock.patch("m2b.viewer.sys.platform", MAC),
            mock.patch("m2b.viewer.launch", self.launcher),
        ):
            code = cli.main(list(arguments), self.environ)
        return code, out.getvalue(), err.getvalue()

    def test_the_command_opens_the_file_and_says_so_in_one_line(self) -> None:
        """Covers: B228"""
        self.write(f"{HANDBOOK}.pdf", PDF_BYTES)

        code, out, err = self.run_command("store", "open", "--", "20261116T165634Z-cli-7198.pdf")

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(out.splitlines(), [f"opened {HANDBOOK}.pdf in the system's viewer"])
        self.assertEqual(len(self.launcher.commands), 1)

    def test_a_refused_name_ends_with_exit_2_and_a_file_that_does_not_open_with_exit_1(self) -> None:
        """Covers: B228"""
        self.write(f"{PAGE}.html", HTML_BYTES)
        self.write(f"{HANDBOOK}.pdf", HTML_BYTES)

        refused, _, refusal = self.run_command("store", "open", "--", "20261020T090000Z-cli-5e6f.html")
        failed, _, failure = self.run_command("store", "open", "--", "20261116T165634Z-cli-7198.pdf")
        missing, _, _ = self.run_command("store", "open", "--", "20261116T165634Z-cli-0000.pdf")

        self.assertEqual((refused, failed, missing), (cli.EXIT_USAGE, cli.EXIT_PROBLEM, cli.EXIT_PROBLEM))
        self.assertEqual(len(refusal.strip().splitlines()), 1, refusal)
        self.assertIn("not a pdf", failure)
        self.assertEqual(self.launcher.commands, [])

    def test_source_json_says_whether_a_documents_file_opens_and_where_it_lies(self) -> None:
        """Covers: B229"""
        self.write(f"{HANDBOOK}.md", DOCUMENT_NOTE.encode())
        self.write(f"{HANDBOOK}.pdf", PDF_BYTES)
        self.write(f"{PAGE}.md", DOCUMENT_NOTE.replace("pdf file", "html file").encode())
        self.write(f"{PAGE}.html", HTML_BYTES)

        _, document, _ = self.run_command("source", "--json", "--viewer", "20261116T165634Z-cli-7198.pdf")
        _, page, _ = self.run_command("source", "--json", "--viewer", "20261020T090000Z-cli-5e6f.md")

        self.assertEqual(
            {key: json.loads(document)[key] for key in ("opens", "not_opened", "file")},
            {"opens": True, "not_opened": None, "file": str(self.store_root / f"{HANDBOOK}.pdf")},
        )
        answer = json.loads(page)
        self.assertFalse(answer["opens"])
        self.assertIn("only a PDF or a picture", answer["not_opened"])
        self.assertEqual(answer["file"], str(self.store_root / f"{PAGE}.html"))

    def test_source_json_of_a_note_without_a_file_opens_nothing(self) -> None:
        """Covers: B229"""
        self.write("corpus/2026/10/20261012T081500Z-claude-3f2a.md", b"Dana, my sister.\n")

        _, out, _ = self.run_command("source", "--json", "--viewer", "20261012T081500Z-claude-3f2a.md")

        answer = json.loads(out)
        self.assertEqual((answer["opens"], answer["not_opened"], answer["file"]), (False, None, None))

    def test_without_viewer_the_json_a_session_may_read_names_no_path_on_the_machine(self) -> None:
        """Covers: B229"""
        self.write(f"{HANDBOOK}.md", DOCUMENT_NOTE.encode())
        self.write(f"{HANDBOOK}.pdf", PDF_BYTES)

        _, out, _ = self.run_command("source", "--json", "20261116T165634Z-cli-7198.pdf")

        self.assertFalse({"opens", "not_opened", "file"} & set(json.loads(out)))
        self.assertNotIn(str(self.store_root), out)


if __name__ == "__main__":
    unittest.main()
