"""One source behind a fact: a fact file or a note, read by its name under the guard."""

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
from m2b.source import (
    DOCUMENT,
    NOTE,
    PICTURE,
    Evidence,
    FactFile,
    NoteSource,
    NotRead,
    SourceNotFoundError,
    SourceRefusedError,
    fact_file_named,
    read_source,
)
from m2b.store.base import Scan
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard
from store_contract import FakeEviction

DANA = "memory/dana.md"
DANA_NOTE = "corpus/2026/10/20261012T081500Z-claude-3f2a.md"
HANDBOOK = "corpus/2026/11/20261116T165634Z-cli-7198"
PHOTO = "corpus/2026/09/20260903T100000Z-phone-c3d4"

FACT_FILE = """---
until: 2027-03-31
---
# Dana

My sister. Birthday on 3 March.

## Presents

- Would love a good fountain pen.

## Earlier

- Lived in Zurich (until 2026-11-07)

## Evidence

- [[20261012T081500Z-claude-3f2a.md]]
- [[20261116T165634Z-cli-7198.pdf]]
- [[20260903T100000Z-phone-c3d4.md]]
- [[20260101T000000Z-cli-0000.md]]
"""

OWNER_NOTE = """---
created: 2026-10-12T10:15:00+02:00
source: claude
curated: true
---
Dana, my sister, birthday on 3 March.
She would love a good fountain pen.
<!-- m2b:curation -->
filed: fact dana.md
"""

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
pp. 3-5: membership and fees 240 a year, due 31 January
outline: pages 1-60 of 75
filed: fact harbour-rowing-club.md
"""

PHOTO_NOTE = """---
kind: sidecar
created: 2026-09-03T12:00:00+02:00
source: phone
curated: true
---
A heic file, captured as 20260903T100000Z-phone-c3d4.heic.
<!-- m2b:curation -->
filed: fact dana.md
"""


class SourceFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        base = Path(self._temp.name)
        self.root = base / "sb-test-store"
        self.root.mkdir()
        self.eviction = FakeEviction()
        self.store = FolderStore(self.root, base / "machine-tmp", DatalessGuard(True, lstat=self.eviction.lstat))

    def write(self, relative: str, text: str | bytes) -> None:
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)

    def evict(self, relative: str) -> None:
        self.eviction.evicted.add(self.root / relative)

    def write_dana(self) -> None:
        self.write(DANA, FACT_FILE)
        self.write(DANA_NOTE, OWNER_NOTE)
        self.write(f"{HANDBOOK}.md", DOCUMENT_NOTE)
        self.write(f"{HANDBOOK}.pdf", b"%PDF-1.4")
        self.write(f"{PHOTO}.md", PHOTO_NOTE)
        self.write(f"{PHOTO}.heic", b"heic")
        self.write(f"{PHOTO}.jpg", b"jpeg")


class FactFileTest(SourceFixture):
    def test_a_fact_file_answers_its_title_lines_last_day_earlier_values_and_evidence(self) -> None:
        """Covers: B218"""
        self.write_dana()

        source = read_source(self.store, "dana.md")

        assert isinstance(source, FactFile)
        self.assertEqual(source.path, DANA)
        self.assertEqual(source.title, "Dana")
        self.assertEqual(
            source.lines, ["My sister. Birthday on 3 March.", "## Presents", "- Would love a good fountain pen."]
        )
        self.assertEqual(source.until, "2027-03-31")
        self.assertEqual(source.earlier, ["- Lived in Zurich (until 2026-11-07)"])
        self.assertEqual(
            source.evidence,
            [
                Evidence(
                    "20261012T081500Z-claude-3f2a.md",
                    "read",
                    "2026-10-12",
                    NOTE,
                    None,
                    "Dana, my sister, birthday on 3 March.",
                    DANA_NOTE,
                ),
                Evidence(
                    "20261116T165634Z-cli-7198.pdf",
                    "read",
                    "2026-11-16",
                    DOCUMENT,
                    "harbour-rowing-club-handbook.pdf",
                    "p. 1: club name, handbook 2026",
                    f"{HANDBOOK}.md",
                ),
                Evidence("20260903T100000Z-phone-c3d4.md", "read", "2026-09-03", PICTURE, None, None, f"{PHOTO}.md"),
                Evidence("20260101T000000Z-cli-0000.md", "missing", "2026-01-01", NOTE),
            ],
        )

    def test_a_fact_file_without_a_last_day_or_earlier_values_answers_none_of_them(self) -> None:
        """Covers: B218"""
        self.write("memory/house.md", "# House\n\nSpare key under the blue pot.\n")
        real_scan = self.store.scan
        listed: list[str] = []

        def scan(folder: str) -> Scan:
            listed.append(folder)
            return real_scan(folder)

        with mock.patch.object(self.store, "scan", side_effect=scan):
            source = read_source(self.store, "house.md")

        self.assertEqual(listed, ["memory"], "a fact file without evidence leaves the archive unlisted")

        assert isinstance(source, FactFile)
        self.assertEqual((source.until, source.earlier, source.evidence), (None, [], []))
        self.assertEqual(source.lines, ["Spare key under the blue pot."])

    def test_evidence_that_is_not_on_this_machine_is_named_with_its_path_and_not_read(self) -> None:
        """Covers: B219"""
        self.write_dana()
        self.evict(DANA_NOTE)
        self.evict("corpus/2026/09")

        source = read_source(self.store, "dana.md")

        assert isinstance(source, FactFile)
        self.assertEqual(
            [(item.state, item.path) for item in source.evidence[:3]],
            [("evicted", DANA_NOTE), ("read", f"{HANDBOOK}.md"), ("evicted", "corpus/2026/09")],
        )
        self.assertIsNone(source.evidence[0].first_line)


class NoteTest(SourceFixture):
    def test_a_note_answers_the_captured_words_and_what_the_run_added(self) -> None:
        """Covers: B218"""
        self.write_dana()

        source = read_source(self.store, "20261012T081500Z-claude-3f2a.md")

        self.assertEqual(
            source,
            NoteSource(
                DANA_NOTE,
                NOTE,
                "2026-10-12",
                "Dana, my sister, birthday on 3 March.\nShe would love a good fountain pen.\n",
                ["filed: fact dana.md"],
            ),
        )

    def test_a_documents_note_answers_its_original_name_kind_outline_and_whether_the_file_is_here(self) -> None:
        """Covers: B218"""
        self.write_dana()

        by_note = read_source(self.store, "20261116T165634Z-cli-7198.md")
        by_document = read_source(self.store, "20261116T165634Z-cli-7198.pdf")

        assert isinstance(by_note, NoteSource)
        self.assertEqual(by_document, by_note)
        self.assertEqual(by_note.kind, DOCUMENT)
        self.assertEqual(by_note.original_name, "harbour-rowing-club-handbook.pdf")
        self.assertEqual(
            by_note.outline,
            [
                "p. 1: club name, handbook 2026",
                "pp. 3-5: membership and fees 240 a year, due 31 January",
                "outline: pages 1-60 of 75",
            ],
        )
        self.assertEqual(by_note.added, ["filed: fact harbour-rowing-club.md"])
        self.assertEqual((by_note.original, by_note.original_here), (f"{HANDBOOK}.pdf", True))

    def test_a_document_that_is_not_downloaded_is_named_so_and_its_note_is_still_read(self) -> None:
        """Covers: B218"""
        self.write_dana()
        self.evict(f"{HANDBOOK}.pdf")

        source = read_source(self.store, "20261116T165634Z-cli-7198.pdf")

        assert isinstance(source, NoteSource)
        self.assertEqual((source.original, source.original_here), (f"{HANDBOOK}.pdf", False))
        self.assertEqual(len(source.outline), 3)

    def test_a_picture_is_the_original_and_not_its_reading_copy(self) -> None:
        self.write_dana()

        source = read_source(self.store, "20260903T100000Z-phone-c3d4.md")

        assert isinstance(source, NoteSource)
        self.assertEqual((source.kind, source.original), (PICTURE, f"{PHOTO}.heic"))

    def test_a_note_outside_the_month_its_name_says_is_found(self) -> None:
        self.write("corpus/2026/08/20261012T081500Z-claude-3f2a.md", OWNER_NOTE)

        source = read_source(self.store, "20261012T081500Z-claude-3f2a.md")

        assert isinstance(source, NoteSource)
        self.assertEqual(source.path, "corpus/2026/08/20261012T081500Z-claude-3f2a.md")

    def test_a_note_in_the_inbox_is_no_source(self) -> None:
        self.write("inbox/20261109T080000Z-cli-aaaa.md", "Dana called\n")

        with self.assertRaises(SourceNotFoundError):
            read_source(self.store, "20261109T080000Z-cli-aaaa.md")


class FactFileNamedTest(SourceFixture):
    def test_a_fact_file_not_downloaded_is_named_and_a_symbolic_link_is_refused(self) -> None:
        """Covers: B303"""
        self.write(DANA, FACT_FILE)
        self.evict(DANA)
        self.assertEqual(fact_file_named(self.store, "dana.md"), DANA)

        (self.root / "memory" / "sam.md").symlink_to(self.root / DANA)
        with self.assertRaisesRegex(SourceRefusedError, "symbolic link"):
            fact_file_named(self.store, "sam.md")


class RefusalTest(SourceFixture):
    def test_a_path_a_separator_or_a_name_of_no_source_is_refused_and_nothing_is_read(self) -> None:
        """Covers: B219"""
        self.write("profile.json", "{}")
        self.write(DANA, FACT_FILE)
        refused = [
            "memory/dana.md",
            "../dana.md",
            "/etc/passwd",
            "corpus\\2026\\dana.md",
            "dana\n.md",
            "dana.md\u2028",
            "",
            "  ",
            "..",
            ".hidden.md",
            "profile.json",
            "store.json",
            "MEMORY.md",
            "dana",
        ]
        with (
            mock.patch.object(self.store, "scan", side_effect=AssertionError("listed")),
            mock.patch.object(self.store, "read_bytes", side_effect=AssertionError("read")),
        ):
            for name in refused:
                with self.subTest(name=name), self.assertRaises(SourceRefusedError) as raised:
                    read_source(self.store, name)
                self.assertNotIn("\n", str(raised.exception))

    def test_a_name_nothing_has_is_not_found(self) -> None:
        with self.assertRaises(SourceNotFoundError):
            read_source(self.store, "nobody.md")
        with self.assertRaises(SourceNotFoundError):
            read_source(self.store, "20260101T000000Z-cli-0000.md")


class NotReadTest(SourceFixture):
    def test_a_fact_file_that_lives_only_in_the_cloud_is_named_and_not_read(self) -> None:
        """Covers: B219"""
        self.write(DANA, FACT_FILE)
        self.evict(DANA)

        with mock.patch.object(self.store, "read_bytes", side_effect=AssertionError("read")):
            self.assertEqual(read_source(self.store, "dana.md"), NotRead(DANA, evicted=True))

    def test_a_month_that_lives_only_in_the_cloud_is_named_as_the_folder(self) -> None:
        """Covers: B219"""
        self.write(DANA_NOTE, OWNER_NOTE)
        self.evict("corpus/2026/10")

        self.assertEqual(
            read_source(self.store, "20261012T081500Z-claude-3f2a.md"), NotRead("corpus/2026/10", evicted=True)
        )

    def test_a_fact_file_that_is_a_symbolic_link_is_not_followed(self) -> None:
        outside = Path(self._temp.name) / "secret.md"
        outside.write_text("# Secret\n", encoding="utf-8")
        (self.root / "memory").mkdir()
        os.symlink(outside, self.root / DANA)

        source = read_source(self.store, "dana.md")

        assert isinstance(source, NotRead)
        self.assertFalse(source.evicted)
        self.assertIn("symbolic link", source.reason)


class SourceCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        base = Path(self._temp.name)
        self.home = base / "home"
        self.store_root = base / "sb-test-store"
        self.store_root.mkdir()
        self.environ = {"HOME": str(base / "user-home"), "M2B_HOME": str(self.home)}
        self.eviction = FakeEviction()
        machine.save_machine_config(
            paths.MachinePaths(self.home),
            {"version": 1, "machine_id": "sb-test-m1", "store": {"backend": "folder", "path": str(self.store_root)}},
        )

    def write(self, relative: str, text: str | bytes) -> None:
        target = self.store_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)

    def run_command(self, *arguments: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        guard = DatalessGuard(True, lstat=self.eviction.lstat)
        with (
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
            mock.patch("m2b.store.factory.guard_for_platform", return_value=guard),
        ):
            code = cli.main(list(arguments), self.environ)
        return code, out.getvalue(), err.getvalue()

    def test_a_fact_file_prints_its_lines_and_evidence(self) -> None:
        """Covers: B218"""
        self.write(DANA, FACT_FILE)
        self.write(DANA_NOTE, OWNER_NOTE)
        self.write(f"{HANDBOOK}.md", DOCUMENT_NOTE)
        self.write(f"{HANDBOOK}.pdf", b"%PDF-1.4")

        code, out, err = self.run_command("source", "dana.md")

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(
            out.splitlines(),
            [
                "Fact file memory/dana.md: Dana",
                "True until 2027-03-31.",
                "",
                "My sister. Birthday on 3 March.",
                "## Presents",
                "- Would love a good fountain pen.",
                "",
                "Earlier:",
                "  - Lived in Zurich (until 2026-11-07)",
                "",
                "Evidence:",
                "  2026-10-12  a note: Dana, my sister, birthday on 3 March. (20261012T081500Z-claude-3f2a.md)",
                "  2026-11-16  a document, harbour-rowing-club-handbook.pdf: p. 1: club name, handbook 2026"
                " (20261116T165634Z-cli-7198.pdf)",
                "  20260903T100000Z-phone-c3d4.md: no note of the archive has this name",
                "  20260101T000000Z-cli-0000.md: no note of the archive has this name",
            ],
        )

    def test_with_viewer_a_fact_file_names_the_corrections_that_wait_for_it(self) -> None:
        """Covers: B304"""
        self.write(DANA, FACT_FILE)
        waiting = "20261124T180000Z-cli-a1b2.md"
        self.write(
            f"inbox/{waiting}",
            "---\ncreated: 2026-11-24T19:00:00+01:00\nsource: cli\nabout: dana.md\n---\n"
            "Dana lives in Bern since October.\nShe moved for the new job.\n",
        )
        self.write(
            "inbox/20261124T181000Z-cli-c3d4.md",
            "---\ncreated: 2026-11-24T19:10:00+01:00\nsource: cli\nabout: sam.md\n---\nSam has a new boat.\n",
        )
        self.write(
            "inbox/20261124T182000Z-cli-e5f6.md",
            "---\ncreated: 2026-11-24T19:20:00+01:00\nsource: cli\n---\nDana called.\n",
        )

        code, out, err = self.run_command("source", "--json", "--viewer", "dana.md")

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(
            json.loads(out)["corrections"], [{"capture": waiting, "first_line": "Dana lives in Bern since October."}]
        )
        code, out, err = self.run_command("source", "--json", "dana.md")
        self.assertNotIn("corrections", json.loads(out))

    def test_a_documents_note_as_json(self) -> None:
        """Covers: B218"""
        self.write(f"{HANDBOOK}.md", DOCUMENT_NOTE)
        self.write(f"{HANDBOOK}.pdf", b"%PDF-1.4")

        code, out, err = self.run_command("source", "--json", "20261116T165634Z-cli-7198.pdf")

        self.assertEqual(code, cli.EXIT_OK, err)
        answer = json.loads(out)
        self.assertEqual(
            {key: answer[key] for key in ("name", "kind", "path", "day", "original_name", "original", "original_here")},
            {
                "name": "20261116T165634Z-cli-7198.pdf",
                "kind": "document",
                "path": f"{HANDBOOK}.md",
                "day": "2026-11-16",
                "original_name": "harbour-rowing-club-handbook.pdf",
                "original": f"{HANDBOOK}.pdf",
                "original_here": True,
            },
        )
        self.assertEqual(len(answer["outline"]), 3)

    def test_a_source_that_is_not_downloaded_answers_the_command_that_fetches_it(self) -> None:
        """Covers: B219"""
        self.write(DANA, FACT_FILE)
        self.eviction.evicted.add(self.store_root / DANA)

        code, out, _ = self.run_command("source", "--json", "dana.md")
        _, text, _ = self.run_command("source", "dana.md")

        self.assertEqual(code, cli.EXIT_OK)
        self.assertEqual(
            json.loads(out),
            {
                "name": "dana.md",
                "kind": "not read",
                "path": DANA,
                "evicted": True,
                "fetch": "m2b store fetch memory/dana.md",
                "reason": None,
            },
        )
        self.assertEqual(
            text.splitlines(),
            [
                "Not read, because not downloaded to this machine; fetch it, then ask again:",
                "  m2b store fetch memory/dana.md",
            ],
        )

    def test_a_path_is_refused_in_one_line_with_exit_2_and_a_missing_name_ends_with_exit_1(self) -> None:
        """Covers: B219"""
        code, out, err = self.run_command("source", "--", "../profile.json")
        self.assertEqual((code, out), (cli.EXIT_USAGE, ""))
        self.assertEqual(len(err.strip().splitlines()), 1)
        self.assertIn("never a path", err)

        code, out, err = self.run_command("source", "nobody.md")
        self.assertEqual((code, out), (cli.EXIT_PROBLEM, ""))
        self.assertIn("no fact file or note is named nobody.md", err)

    def test_text_from_the_store_prints_without_the_characters_that_draw_nothing(self) -> None:
        self.write("memory/sam.md", "---\nuntil: 2027-03-31​\n---\n# Sam​\n\nBrings\U000e0041 the plywood.\n")

        _, out, _ = self.run_command("source", "--json", "sam.md")
        _, text, _ = self.run_command("source", "sam.md")

        answer = json.loads(out)
        self.assertEqual((answer["title"], answer["lines"]), ("Sam", ["Brings the plywood."]))
        self.assertEqual(answer["until"], "2027-03-31")
        self.assertIn("True until 2027-03-31.\n", text)


if __name__ == "__main__":
    unittest.main()
