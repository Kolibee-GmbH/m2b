"""Ingest, the deterministic half: inbox to corpus, every step keyed and restart-safe."""

from __future__ import annotations

import datetime
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import test_commands
from m2b import cli, ingest
from m2b.config import profile
from m2b.notes.frontmatter import Note
from m2b.notes.names import NoteName
from m2b.notes.trailer import MARKER_LINE, find_trailer
from m2b.store.base import StoreReadError
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard
from m2b.store.icloud import ICloudStore
from m2b.tasks import markers
from m2b.tasks.base import Due, TasksUnreachableError
from m2b.tasks.markdown import MarkdownTasks

MTIME = datetime.datetime(2026, 11, 6, 21, 30, 0).astimezone()
CAPTURE = "20261107T091500Z-cli-a1b2.md"
CAPTURED = "---\ncreated: 2026-11-07T10:15:00+01:00\nsource: cli\n---\nRenew the passport before the trip\n"


class IngestFixture(unittest.TestCase):
    store_class: Any = FolderStore

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        base = Path(self._temp.name)
        self.root = base / "sb-test-store"
        (self.root / "inbox").mkdir(parents=True)
        self.store = self.store_class(self.root, base / "machine-tmp", DatalessGuard(False))
        self.tasks = MarkdownTasks(self.store)
        self.converted: list[tuple[Path, Path]] = []

    def write(self, relative: str, data: str | bytes, mtime: datetime.datetime = MTIME) -> None:
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
        os.utime(target, (mtime.timestamp(), mtime.timestamp()))

    def read(self, relative: str) -> str:
        return (self.root / relative).read_text(encoding="utf-8")

    def inbox(self) -> list[str]:
        return sorted(p.name for p in (self.root / "inbox").iterdir())

    def convert(self, source: Path, destination: Path) -> None:
        self.converted.append((source, destination))
        destination.write_bytes(b"JPEG from " + source.read_bytes())

    def normalize(self) -> ingest.NormalizeReport:
        return ingest.normalize(self.store, convert=self.convert)


class NormalizeTextTest(IngestFixture):
    def test_a_foreign_text_file_gets_the_schema_name_created_source_and_its_name_in_the_trailer(self) -> None:
        """Covers: B18"""
        self.write("inbox/Shopping list.txt", "milk\nbread\n")

        report = self.normalize()

        (name,) = self.inbox()
        expected = NoteName.for_capture(MTIME, "cli", suffix=name[-7:-3])
        self.assertEqual(name, str(expected))
        self.assertEqual(report.renamed, [("inbox/Shopping list.txt", f"inbox/{name}")])
        note = Note.parse(self.read(f"inbox/{name}"))
        assert note.frontmatter is not None
        self.assertEqual(note.frontmatter.get("created"), MTIME.isoformat(timespec="seconds"))
        self.assertEqual(note.frontmatter.get("source"), "cli")
        self.assertTrue(note.frontmatter.get_flag("curated"))
        trailer = find_trailer(note)
        assert trailer is not None
        self.assertEqual(trailer.captured, "milk\nbread\n")
        self.assertIn("original name: Shopping list.txt", trailer.notes)

    def test_a_foreign_file_keeps_its_own_created_and_source(self) -> None:
        """Covers: B18"""
        self.write("inbox/from-phone.md", "---\ncreated: 2026-10-01T08:00:00+02:00\nsource: phone\n---\nCall Dana\n")

        self.normalize()

        (name,) = self.inbox()
        self.assertTrue(name.startswith("20261001T060000Z-phone-"), name)

    def test_a_schema_named_file_without_frontmatter_gets_created_and_its_source_from_the_name(self) -> None:
        """Covers: B18"""
        self.write("inbox/20261105T120000Z-worklog-beef.md", "Worked on the Acme export\n")

        report = self.normalize()

        self.assertEqual(self.inbox(), ["20261105T120000Z-worklog-beef.md"])
        note = Note.parse(self.read("inbox/20261105T120000Z-worklog-beef.md"))
        assert note.frontmatter is not None
        self.assertEqual(note.frontmatter.get("source"), "worklog")
        name_time = datetime.datetime(2026, 11, 5, 12, 0, tzinfo=datetime.timezone.utc).astimezone()
        self.assertEqual(note.frontmatter.get("created"), name_time.isoformat(timespec="seconds"))
        self.assertEqual(note.body, "Worked on the Acme export\n")
        self.assertEqual(report.completed, ["inbox/20261105T120000Z-worklog-beef.md"])

    def test_a_conforming_capture_is_left_byte_for_byte(self) -> None:
        self.write(f"inbox/{CAPTURE}", CAPTURED)

        report = self.normalize()

        self.assertEqual(self.read(f"inbox/{CAPTURE}"), CAPTURED)
        self.assertEqual((report.renamed, report.completed), ([], []))

    def test_markdown_with_the_long_extension_is_text(self) -> None:
        """Covers: X7"""
        self.write("inbox/Notes.markdown", "# Trip\nPorto in May\n")

        self.normalize()

        (name,) = self.inbox()
        self.assertTrue(name.endswith(".md"), name)

    def test_a_rename_interrupted_before_the_old_file_was_removed_is_completed_without_a_second_capture(
        self,
    ) -> None:
        """Covers: B16"""
        self.write("inbox/Shopping list.txt", "milk\n")
        with mock.patch.object(self.store, "delete", side_effect=OSError("crash")), self.assertRaises(OSError):
            self.normalize()
        self.assertEqual(len(self.inbox()), 2)

        self.normalize()

        (name,) = self.inbox()
        self.assertTrue(NoteName.parse(name))

    def test_a_rename_of_a_file_without_a_final_newline_is_completed_without_a_second_capture(self) -> None:
        """Covers: B16"""
        self.write("inbox/Shopping list.txt", "milk\nbread")
        with mock.patch.object(self.store, "delete", side_effect=OSError("crash")), self.assertRaises(OSError):
            self.normalize()

        self.normalize()

        self.assertEqual(len(self.inbox()), 1, self.inbox())

    def test_a_text_file_that_is_no_utf8_is_left_and_reported_and_the_others_go_on(self) -> None:
        self.write("inbox/Alte Liste.txt", "K\xe4se".encode("latin-1"))
        self.write("inbox/Shopping list.txt", "milk\n")

        report = self.normalize()

        self.assertIn("Alte Liste.txt", self.inbox())
        self.assertEqual(len(report.renamed), 1)
        self.assertEqual(len(report.problems), 1)
        self.assertIn("Alte Liste.txt", report.problems[0])

    def test_a_file_with_a_broken_created_is_reported_and_the_others_go_on(self) -> None:
        self.write("inbox/dated.md", "---\ncreated: 2026-11-07\n---\nA date without a time\n")
        self.write("inbox/Shopping list.txt", "milk\n")

        report = self.normalize()

        self.assertIn("dated.md", self.inbox())
        self.assertEqual(len(report.renamed), 1)
        self.assertIn("dated.md", report.problems[0])

    def test_a_second_foreign_file_with_the_same_name_but_other_text_is_its_own_capture(self) -> None:
        self.write("inbox/Shopping list.txt", "milk\n")
        self.normalize()
        self.write("inbox/Shopping list.txt", "eggs\n")

        self.normalize()

        self.assertEqual(len(self.inbox()), 2)


class NormalizeBinaryTest(IngestFixture):
    def test_a_photo_becomes_a_bundle_with_original_reading_copy_and_sidecar(self) -> None:
        """Covers: B20"""
        self.write("inbox/IMG_0042.HEIC", b"heic bytes")

        report = self.normalize()

        names = self.inbox()
        stem = names[0].rsplit(".", 1)[0]
        self.assertEqual(names, [f"{stem}.HEIC", f"{stem}.jpg", f"{stem}.md"])
        self.assertEqual((self.root / "inbox" / f"{stem}.jpg").read_bytes(), b"JPEG from heic bytes")
        sidecar = Note.parse(self.read(f"inbox/{stem}.md"))
        assert sidecar.frontmatter is not None
        self.assertEqual(sidecar.frontmatter.get("kind"), "sidecar")
        trailer = find_trailer(sidecar)
        assert trailer is not None
        self.assertIn("original name: IMG_0042.HEIC", trailer.notes)
        self.assertEqual(report.bundles, [f"inbox/{stem}.md"])

    def test_a_photo_the_model_can_read_gets_no_reading_copy(self) -> None:
        self.write("inbox/whiteboard.jpg", b"jpeg bytes")

        self.normalize()

        self.assertEqual([name.rsplit(".", 1)[1] for name in self.inbox()], ["jpg", "md"])
        self.assertEqual(self.converted, [])

    def test_without_a_converter_the_sidecar_says_there_is_no_reading_copy(self) -> None:
        self.write("inbox/IMG_0042.HEIC", b"heic bytes")

        ingest.normalize(self.store, convert=None)

        sidecar = next(name for name in self.inbox() if name.endswith(".md"))
        trailer = find_trailer(Note.parse(self.read(f"inbox/{sidecar}")))
        assert trailer is not None
        self.assertIn("no reading copy", trailer.notes)

    def test_a_bundle_interrupted_after_the_sidecar_is_completed_on_the_rerun(self) -> None:
        """Covers: B20"""
        self.write("inbox/IMG_0042.HEIC", b"heic bytes")
        real_create = self.store.create_exclusive

        def create_only_markdown(relative: str, data: bytes) -> None:
            if not relative.endswith(".md"):
                raise OSError("crash")
            real_create(relative, data)

        with mock.patch.object(self.store, "create_exclusive", create_only_markdown), self.assertRaises(OSError):
            self.normalize()

        self.normalize()

        names = self.inbox()
        self.assertEqual(len(names), 3, names)
        self.assertNotIn("IMG_0042.HEIC", names)
        self.assertEqual(len({name.rsplit(".", 1)[0] for name in names}), 1)

    def test_a_new_photo_named_like_an_unfinished_bundle_s_original_is_its_own_bundle(self) -> None:
        """Covers: B20"""
        self.write("inbox/image.jpg", b"first photo")
        self.normalize()
        self.write("inbox/image.jpg", b"second photo")

        self.normalize()

        photos = sorted((self.root / "inbox" / name).read_bytes() for name in self.inbox() if name.endswith(".jpg"))
        self.assertEqual(photos, [b"first photo", b"second photo"])

    def test_an_interrupted_second_bundle_of_the_same_name_is_completed_next_to_the_first(self) -> None:
        """Covers: B20"""
        self.write("inbox/image.jpg", b"first photo", mtime=MTIME)
        self.normalize()
        self.write("inbox/image.jpg", b"second photo", mtime=MTIME - datetime.timedelta(days=30))
        real_create = self.store.create_exclusive

        def create_only_markdown(relative: str, data: bytes) -> None:
            if not relative.endswith(".md"):
                raise OSError("crash")
            real_create(relative, data)

        with mock.patch.object(self.store, "create_exclusive", create_only_markdown), self.assertRaises(OSError):
            self.normalize()

        self.normalize()

        sidecars = [name for name in self.inbox() if name.endswith(".md")]
        photos = [name for name in self.inbox() if name.endswith(".jpg")]
        self.assertEqual(len(sidecars), 2, self.inbox())
        self.assertEqual(
            sorted(name.rsplit(".", 1)[0] for name in photos), sorted(n.rsplit(".", 1)[0] for n in sidecars)
        )

    def test_a_schema_named_capture_that_is_no_utf8_is_reported_and_the_others_go_on(self) -> None:
        self.write("inbox/20261105T120000Z-worklog-beef.md", "K\xe4se".encode("latin-1"))
        self.write("inbox/Shopping list.txt", "milk\n")

        report = self.normalize()

        self.assertEqual(len(report.renamed), 1)
        self.assertIn("20261105T120000Z-worklog-beef.md", report.problems[0])

    def test_a_new_photo_named_like_a_bundle_whose_photo_was_already_moved_is_its_own_bundle(self) -> None:
        self.write("inbox/image.jpg", b"first photo")
        self.normalize()
        stem = self.inbox()[0].rsplit(".", 1)[0]
        month = "corpus/" + datetime.datetime.strptime(stem[:8], "%Y%m%d").strftime("%Y/%m")
        self.write(f"{month}/{stem}.jpg", b"first photo")
        (self.root / "inbox" / f"{stem}.jpg").unlink()
        self.write("inbox/image.jpg", b"second photo")

        self.normalize()

        photos = [name for name in self.inbox() if name.endswith(".jpg")]
        self.assertEqual(len(photos), 1)
        self.assertNotEqual(photos[0].rsplit(".", 1)[0], stem)

    def test_an_extension_outside_the_schema_becomes_bin_and_a_rerun_changes_nothing(self) -> None:
        self.write("inbox/image.jpg_large", b"photo")

        self.normalize()
        second = self.normalize()

        self.assertEqual([name.rsplit(".", 1)[1] for name in self.inbox()], ["bin", "md"])
        self.assertEqual((second.renamed, second.bundles), ([], []))

    def test_a_schema_named_photo_gets_its_created_from_its_name(self) -> None:
        self.write("inbox/20261031T233000Z-phone-c0de.jpg", b"jpeg bytes")

        self.normalize()

        note = Note.parse(self.read("inbox/20261031T233000Z-phone-c0de.md"))
        assert note.frontmatter is not None
        name_time = datetime.datetime(2026, 10, 31, 23, 30, tzinfo=datetime.timezone.utc).astimezone()
        self.assertEqual(note.frontmatter.get("created"), name_time.isoformat(timespec="seconds"))

    def test_a_schema_named_photo_without_sidecar_gets_one(self) -> None:
        self.write("inbox/20261105T080000Z-phone-c0de.jpg", b"jpeg bytes")

        self.normalize()

        self.assertEqual(self.inbox(), ["20261105T080000Z-phone-c0de.jpg", "20261105T080000Z-phone-c0de.md"])


class ConflictCopyTest(IngestFixture):
    def setUp(self) -> None:
        super().setUp()
        self.store = ICloudStore(self.root, self.store.temp_dir, DatalessGuard(False), macos_release="14.6")

    def test_an_identical_conflict_copy_is_removed_and_a_different_one_names_its_original(self) -> None:
        self.write(f"inbox/{CAPTURE}", CAPTURED)
        self.write(f"inbox/{CAPTURE[:-3]} 2.md", CAPTURED)
        self.write("inbox/plan.md", "---\ncreated: 2026-11-01T10:00:00+01:00\nsource: cli\n---\nplan A\n")
        self.write("inbox/plan 2.md", "---\ncreated: 2026-11-01T10:00:00+01:00\nsource: cli\n---\nplan B\n")

        report = self.normalize()

        self.assertEqual(report.removed_copies, [f"inbox/{CAPTURE[:-3]} 2.md"])
        self.assertEqual(len(report.kept_copies), 1)
        names = self.inbox()
        self.assertEqual(len(names), 3, names)
        notes = [self.read(f"inbox/{name}") for name in names]
        self.assertTrue(any("plan B" in text and "conflict copy of plan.md" in text for text in notes))


class ConflictCopyInAFolderStoreTest(IngestFixture):
    def test_an_identical_syncthing_copy_is_removed_and_a_different_dropbox_copy_names_its_original(self) -> None:
        """Covers: B150"""
        syncthing_copy = f"{CAPTURE[:-3]}.sync-conflict-20261107-091600-ABCDEFG.md"
        self.write(f"inbox/{CAPTURE}", CAPTURED)
        self.write(f"inbox/{syncthing_copy}", CAPTURED)
        self.write("inbox/plan.md", "---\ncreated: 2026-11-01T10:00:00+01:00\nsource: cli\n---\nplan A\n")
        self.write(
            "inbox/plan (Dana's conflicted copy 2026-11-01).md",
            "---\ncreated: 2026-11-01T10:00:00+01:00\nsource: cli\n---\nplan B\n",
        )

        report = self.normalize()

        self.assertEqual(report.removed_copies, [f"inbox/{syncthing_copy}"])
        self.assertEqual(len(report.kept_copies), 1)
        names = self.inbox()
        self.assertEqual(len(names), 3, names)
        notes = [self.read(f"inbox/{name}") for name in names]
        self.assertTrue(any("plan B" in text and "conflict copy of plan.md" in text for text in notes))

    def test_a_differing_copy_that_is_not_utf8_is_reported_and_the_other_captures_go_on(self) -> None:
        """Covers: B150"""
        copy = "inbox/menu.sync-conflict-20261105-081500-ABCDEFG.txt"
        self.write("inbox/menu.txt", "caf\u00e9 at nine\n".encode("latin-1"))
        self.write(copy, "caf\u00e9 at ten\n".encode("latin-1"))
        self.write("inbox/Shopping list.txt", "milk\nbread\n")

        report = self.normalize()

        self.assertEqual(report.kept_copies, [copy])
        self.assertEqual(
            [problem.split(" is a text file", 1)[0] for problem in report.problems], [copy, "inbox/menu.txt"]
        )
        self.assertNotIn("Shopping list.txt", self.inbox())

    def test_a_differing_copy_whose_text_cannot_be_read_gets_no_line_and_stops_nothing(self) -> None:
        """Covers: B150"""
        copy = "inbox/plan (conflicted copy 2026-11-01).md"
        self.write("inbox/plan.md", "---\ncreated: 2026-11-01T10:00:00+01:00\nsource: cli\n---\nplan A\n")
        self.write(copy, "---\ncreated: 2026-11-01T10:00:00+01:00\nsource: cli\n---\nplan B\n")
        self.write("inbox/Shopping list.txt", "milk\nbread\n")
        real_read = self.store.read_text

        def read(relative: str) -> str:
            if relative == copy:
                raise StoreReadError(f"{relative} could not be read: Permission denied")
            return real_read(relative)

        with mock.patch.object(self.store, "read_text", side_effect=read):
            report = self.normalize()

        self.assertEqual(report.kept_copies, [copy])
        self.assertEqual([problem.split(" stays", 1)[0] for problem in report.problems], [copy])
        self.assertNotIn("Shopping list.txt", self.inbox())


class TaskTest(IngestFixture):
    def setUp(self) -> None:
        super().setUp()
        self.write(f"inbox/{CAPTURE}", CAPTURED)

    def test_a_task_is_created_with_the_capture_marker_and_recorded_in_the_capture(self) -> None:
        """Covers: B16"""
        task_id = ingest.add_task(
            self.store, self.tasks, CAPTURE, "passport", "Renew passport", datetime.date(2026, 11, 30)
        )

        (task,) = self.tasks.items()
        self.assertEqual(task.id, task_id)
        self.assertEqual(markers.marker_of(task.notes), (markers.CAPTURE, (CAPTURE, "passport")))
        note = Note.parse(self.read(f"inbox/{CAPTURE}"))
        assert note.frontmatter is not None
        self.assertEqual(note.frontmatter.get_list("tasks"), [task_id])
        self.assertEqual(note.body, "Renew the passport before the trip\n")

    def test_running_it_again_finds_the_task_by_its_marker_and_creates_nothing(self) -> None:
        """Covers: B16, B17"""
        first = ingest.add_task(self.store, self.tasks, CAPTURE, "passport", "Renew passport", None)
        second = ingest.add_task(self.store, self.tasks, CAPTURE, "passport", "Renew passport", None)

        self.assertEqual(first, second)
        self.assertEqual(len(self.tasks.items()), 1)

    def test_a_task_with_the_same_title_but_no_marker_is_never_adopted(self) -> None:
        """Covers: B17"""
        self.tasks.add("Renew passport")

        ingest.add_task(self.store, self.tasks, CAPTURE, "passport", "Renew passport", None)

        self.assertEqual(len(self.tasks.items()), 2)

    def test_a_completed_task_of_this_capture_is_found_too(self) -> None:
        """Covers: B16"""
        first = ingest.add_task(self.store, self.tasks, CAPTURE, "passport", "Renew passport", None)
        self.tasks.complete(first)

        self.assertEqual(ingest.add_task(self.store, self.tasks, CAPTURE, "passport", "Renew passport", None), first)

    def test_a_second_key_adds_a_second_task(self) -> None:
        ingest.add_task(self.store, self.tasks, CAPTURE, "passport", "Renew passport", None)
        ingest.add_task(self.store, self.tasks, CAPTURE, "photos", "Get passport photos", None)

        note = Note.parse(self.read(f"inbox/{CAPTURE}"))
        assert note.frontmatter is not None
        self.assertEqual(len(note.frontmatter.get_list("tasks")), 2)

    def test_a_follow_up_date_becomes_its_task_and_leaves_the_frontmatter(self) -> None:
        """Covers: B32"""
        self.write(
            f"inbox/{CAPTURE}",
            "---\ncreated: 2026-11-07T10:15:00+01:00\nsource: cli\nfollow_up: 2026-11-20\n---\n"
            "Call Dana about the shed\n",
        )

        task_id = ingest.add_follow_up_task(self.store, self.tasks, CAPTURE)

        (task,) = self.tasks.items()
        self.assertEqual(
            (task.id, task.title, task.due), (task_id, "Call Dana about the shed", datetime.date(2026, 11, 20))
        )
        self.assertEqual(markers.marker_of(task.notes), (markers.CAPTURE, (CAPTURE, "follow-up")))
        note = Note.parse(self.read(f"inbox/{CAPTURE}"))
        assert note.frontmatter is not None
        self.assertIsNone(note.frontmatter.get("follow_up"))
        self.assertEqual(note.frontmatter.get_list("tasks"), [task_id])

    def test_a_capture_without_follow_up_has_no_follow_up_task(self) -> None:
        self.assertIsNone(ingest.add_follow_up_task(self.store, self.tasks, CAPTURE))
        self.assertEqual(self.tasks.items(), [])

    def test_a_key_of_two_words_is_refused_before_the_task_list_is_asked(self) -> None:
        with self.assertRaises(ingest.IngestError):
            ingest.add_task(self.store, self.tasks, CAPTURE, "two words", "Title", None)
        self.assertEqual(self.tasks.items(), [])

    def test_a_file_that_is_not_in_the_inbox_is_refused(self) -> None:
        with self.assertRaises(ingest.NotInInboxError):
            ingest.add_task(self.store, self.tasks, "20261107T091500Z-cli-ffff.md", "k", "Title", None)


class RefNoteAndFactsTest(IngestFixture):
    def setUp(self) -> None:
        super().setUp()
        self.write(f"inbox/{CAPTURE}", CAPTURED)

    def frontmatter(self) -> Any:
        note = Note.parse(self.read(f"inbox/{CAPTURE}"))
        assert note.frontmatter is not None
        return note.frontmatter

    def test_refs_are_merged_and_never_doubled(self) -> None:
        ingest.add_ref(self.store, CAPTURE, "20261001T080000Z-cli-aaaa.md")
        ingest.add_ref(self.store, CAPTURE, "https://example.org/passport")
        ingest.add_ref(self.store, CAPTURE, "20261001T080000Z-cli-aaaa.md")

        self.assertEqual(
            self.frontmatter().get_list("refs"), ["20261001T080000Z-cli-aaaa.md", "https://example.org/passport"]
        )

    def test_a_note_goes_into_the_trailer_once_and_the_captured_text_stays(self) -> None:
        ingest.add_note(self.store, CAPTURE, "filed: passport task")
        ingest.add_note(self.store, CAPTURE, "filed: passport task")
        ingest.add_note(self.store, CAPTURE, "fact: dana.md")

        note = Note.parse(self.read(f"inbox/{CAPTURE}"))
        trailer = find_trailer(note)
        assert trailer is not None
        self.assertEqual(trailer.captured, "Renew the passport before the trip\n")
        self.assertEqual(trailer.notes.count("filed: passport task"), 1)
        self.assertIn("fact: dana.md", trailer.notes)
        self.assertTrue(self.frontmatter().get_flag("curated"))

    def test_a_marker_line_the_user_typed_is_text_and_the_curator_adds_its_own(self) -> None:
        self.write(f"inbox/{CAPTURE}", CAPTURED.replace("trip\n", f"trip\n{MARKER_LINE}\nmy own line\n"))

        ingest.add_note(self.store, CAPTURE, "filed")

        trailer = find_trailer(Note.parse(self.read(f"inbox/{CAPTURE}")))
        assert trailer is not None
        self.assertIn("my own line", trailer.captured)
        self.assertEqual(trailer.notes.strip(), "filed")

    def test_a_note_with_a_line_break_or_a_reserved_line_is_refused(self) -> None:
        for text in ("line one\nline two", MARKER_LINE, "original name: x.txt"):
            with self.subTest(text=text), self.assertRaises(ingest.IngestError):
                ingest.add_note(self.store, CAPTURE, text)

    def test_facts_filed_is_set(self) -> None:
        ingest.set_facts_filed(self.store, CAPTURE)
        ingest.set_facts_filed(self.store, CAPTURE)

        self.assertTrue(self.frontmatter().get_flag("facts_filed"))

    def test_facts_filed_is_cleared_and_clearing_twice_changes_nothing(self) -> None:
        ingest.set_facts_filed(self.store, CAPTURE)

        ingest.clear_facts_filed(self.store, CAPTURE)
        ingest.clear_facts_filed(self.store, CAPTURE)

        self.assertFalse(self.frontmatter().get_flag("facts_filed"))
        self.assertNotIn("facts_filed", self.read(f"inbox/{CAPTURE}"))


class FinishTest(IngestFixture):
    def test_a_capture_moves_to_the_month_of_its_created_time_in_utc(self) -> None:
        """Covers: B19"""
        name = "20261031T233000Z-cli-0001.md"
        self.write(f"inbox/{name}", "---\ncreated: 2026-11-01T00:30:00+01:00\nsource: cli\n---\nHalloween party\n")

        destinations = ingest.finish(self.store, self.tasks, name)

        self.assertEqual(destinations, [f"corpus/2026/10/{name}"])
        self.assertEqual(self.inbox(), [])
        self.assertIn("Halloween party", self.read(f"corpus/2026/10/{name}"))

    def test_an_existing_destination_with_other_bytes_is_refused_before_the_capture_is_touched(self) -> None:
        """Covers: X6"""
        self.write(f"inbox/{CAPTURE}", CAPTURED)
        self.write(f"corpus/2026/11/{CAPTURE}", "something else\n")

        with self.assertRaises(ingest.DestinationTakenError):
            ingest.finish(self.store, self.tasks, CAPTURE)

        self.assertEqual(self.read(f"inbox/{CAPTURE}"), CAPTURED)
        self.assertEqual(self.read(f"corpus/2026/11/{CAPTURE}"), "something else\n")

    def test_a_move_interrupted_before_the_inbox_copy_was_removed_is_completed(self) -> None:
        """Covers: B16"""
        self.write(f"inbox/{CAPTURE}", CAPTURED)
        with mock.patch.object(self.store, "delete", side_effect=OSError("crash")), self.assertRaises(OSError):
            ingest.finish(self.store, self.tasks, CAPTURE)

        self.assertEqual(ingest.finish(self.store, self.tasks, CAPTURE), [f"corpus/2026/11/{CAPTURE}"])
        self.assertEqual(self.inbox(), [])

    def test_finishing_a_capture_already_in_the_corpus_is_done_and_changes_nothing(self) -> None:
        """Covers: B16"""
        self.write(f"inbox/{CAPTURE}", CAPTURED)
        ingest.finish(self.store, self.tasks, CAPTURE)

        self.assertEqual(ingest.finish(self.store, self.tasks, CAPTURE), [f"corpus/2026/11/{CAPTURE}"])

    def test_a_pending_follow_up_gets_its_task_before_the_move(self) -> None:
        """Covers: B32"""
        self.write(
            f"inbox/{CAPTURE}",
            "---\ncreated: 2026-11-07T10:15:00+01:00\nsource: cli\nfollow_up: 2026-11-20\n---\nCall Dana\n",
        )

        ingest.finish(self.store, self.tasks, CAPTURE)

        (task,) = self.tasks.items()
        self.assertEqual(task.due, datetime.date(2026, 11, 20))
        self.assertNotIn("follow_up", self.read(f"corpus/2026/11/{CAPTURE}"))

    def test_with_tasks_unreachable_a_pending_follow_up_keeps_the_capture_in_the_inbox(self) -> None:
        """Covers: B32"""
        self.write(
            f"inbox/{CAPTURE}",
            "---\ncreated: 2026-11-07T10:15:00+01:00\nsource: cli\nfollow_up: 2026-11-20\n---\nCall Dana\n",
        )

        class Unreachable(MarkdownTasks):
            def items(self, marker: str | None = None, include_completed: bool = False) -> list[Any]:
                raise TasksUnreachableError("Reminders did not answer")

            def add(self, title: str, notes: str = "", due: Due | None = None) -> str:
                raise TasksUnreachableError("Reminders did not answer")

        with self.assertRaises(TasksUnreachableError):
            ingest.finish(self.store, Unreachable(self.store), CAPTURE)

        self.assertEqual(self.inbox(), [CAPTURE])

    def test_a_taken_destination_is_refused_before_a_pending_follow_up_creates_its_task(self) -> None:
        """Covers: X6"""
        pending = "---\ncreated: 2026-11-07T10:15:00+01:00\nsource: cli\nfollow_up: 2026-11-20\n---\nCall Dana\n"
        self.write(f"inbox/{CAPTURE}", pending)
        self.write(f"corpus/2026/11/{CAPTURE}", "other\n")

        with self.assertRaises(ingest.DestinationTakenError):
            ingest.finish(self.store, self.tasks, CAPTURE)

        self.assertEqual(self.tasks.items(), [])
        self.assertEqual(self.read(f"inbox/{CAPTURE}"), pending)

    def test_a_file_that_was_not_normalized_is_refused(self) -> None:
        self.write("inbox/Shopping list.txt", "milk\n")

        with self.assertRaises(ingest.IngestError):
            ingest.finish(self.store, self.tasks, "Shopping list.txt")

    def test_a_bundle_moves_with_its_sidecar_last_from_any_member(self) -> None:
        """Covers: B20"""
        self.write("inbox/IMG_0042.HEIC", b"heic bytes")
        self.normalize()
        stem = self.inbox()[0].rsplit(".", 1)[0]
        moved: list[str] = []
        real_create = self.store.create_exclusive

        def record(relative: str, data: bytes) -> None:
            moved.append(relative)
            real_create(relative, data)

        with mock.patch.object(self.store, "create_exclusive", record):
            destinations = ingest.finish(self.store, self.tasks, f"{stem}.jpg")

        self.assertEqual(self.inbox(), [])
        self.assertEqual(len(destinations), 3)
        self.assertTrue(moved[-1].endswith(f"{stem}.md"), moved)
        month = "corpus/" + datetime.datetime.strptime(stem[:8], "%Y%m%d").strftime("%Y/%m")
        self.assertTrue(all(path.startswith(month) for path in destinations), destinations)

    def test_a_bundle_interrupted_mid_move_is_completed_from_its_sidecar(self) -> None:
        """Covers: B20"""
        self.write("inbox/IMG_0042.HEIC", b"heic bytes")
        self.normalize()
        stem = self.inbox()[0].rsplit(".", 1)[0]
        real_create = self.store.create_exclusive
        calls = [0]

        def crash_on_second(relative: str, data: bytes) -> None:
            calls[0] += 1
            if calls[0] == 2:
                raise OSError("crash")
            real_create(relative, data)

        with mock.patch.object(self.store, "create_exclusive", crash_on_second), self.assertRaises(OSError):
            ingest.finish(self.store, self.tasks, f"{stem}.md")

        self.assertEqual(len(ingest.finish(self.store, self.tasks, f"{stem}.md")), 3)
        self.assertEqual(self.inbox(), [])


class PendingTest(IngestFixture):
    def test_schema_named_captures_are_listed_in_name_order_with_what_the_model_needs(self) -> None:
        """Covers: B36 (the code half: a filed capture says so before the model reads it; the skill skips
        its facts. The model half, one link per capture, was checked once with a real model run.)"""
        self.write(
            "inbox/20261107T101500Z-claude-b2c3.md",
            "---\ncreated: 2026-11-07T11:15:00+01:00\nsource: claude\nquiet: true\nfacts_filed: true\n---\nx\n",
        )
        self.write(f"inbox/{CAPTURE}", CAPTURED.replace("source: cli\n", "source: cli\nfollow_up: 2026-11-20\n"))

        report = ingest.pending(self.store)

        self.assertEqual(
            report.captures,
            [
                ingest.Pending(CAPTURE, "cli", None, facts_filed=False, quiet=False, follow_up="2026-11-20"),
                ingest.Pending("20261107T101500Z-claude-b2c3.md", "claude", None, facts_filed=True, quiet=True),
            ],
        )
        self.assertEqual(report.problems, [])

    def test_a_bundle_is_one_capture_its_sidecar_with_the_other_files_as_members(self) -> None:
        self.write("inbox/IMG_0042.HEIC", b"heic bytes")
        self.normalize()
        stem = self.inbox()[0].rsplit(".", 1)[0]

        (capture,) = ingest.pending(self.store).captures

        self.assertEqual(capture.file, f"{stem}.md")
        self.assertEqual(capture.kind, "sidecar")
        self.assertEqual(capture.members, (f"{stem}.HEIC", f"{stem}.jpg"))

    def test_files_normalize_has_not_handled_are_problems_not_captures(self) -> None:
        self.write("inbox/Shopping list.txt", "milk\n")
        self.write("inbox/20261107T091600Z-cli-c3d4.jpg", b"jpeg without sidecar")
        self.write("inbox/20261107T091700Z-cli-d4e5.md", "no frontmatter\n")
        self.write("inbox/.hidden-temp", "x")

        report = ingest.pending(self.store)

        self.assertEqual(report.captures, [])
        self.assertEqual(len(report.problems), 3)
        self.assertTrue(all("normalize" in problem for problem in report.problems), report.problems)
        self.assertEqual(
            report.stuck,
            ["inbox/20261107T091600Z-cli-c3d4.jpg", "inbox/20261107T091700Z-cli-d4e5.md", "inbox/Shopping list.txt"],
        )

    def test_a_schema_named_capture_in_a_subfolder_is_a_problem_finish_could_not_move(self) -> None:
        """Covers: B57"""
        self.write("inbox/later/20261107T091500Z-cli-a1b2.md", CAPTURED)

        report = ingest.pending(self.store)

        self.assertEqual(report.captures, [])
        self.assertEqual(report.stuck, ["inbox/later/20261107T091500Z-cli-a1b2.md"])
        self.assertIn("subfolder", report.problems[0])

    def test_a_bundle_whose_sidecar_is_evicted_is_only_named_as_evicted(self) -> None:
        stem = "20261107T091600Z-cli-c3d4"
        scan = mock.Mock(files=[f"inbox/{stem}.HEIC", f"inbox/{stem}.jpg"], evicted=[f"inbox/{stem}.md"])
        with mock.patch.object(self.store, "scan", return_value=scan):
            report = ingest.pending(self.store)

        self.assertEqual((report.captures, report.problems), ([], []))
        self.assertEqual(report.evicted, [f"inbox/{stem}.md"])

    def test_an_evicted_member_is_never_handed_to_the_model_to_read(self) -> None:
        """Covers: B6 (an evicted file is listed apart and never read), B79"""
        stem = "20261107T091600Z-cli-c3d4"
        self.write(
            f"inbox/{stem}.md", "---\ncreated: 2026-11-07T10:16:00+01:00\nsource: cli\nkind: sidecar\n---\nphoto\n"
        )
        scan = mock.Mock(files=[f"inbox/{stem}.HEIC", f"inbox/{stem}.md"], evicted=[f"inbox/{stem}.jpg"])
        with mock.patch.object(self.store, "scan", return_value=scan):
            report = ingest.pending(self.store)

        # The whole bundle waits: finishing it would read the member that is not downloaded.
        self.assertEqual((report.captures, report.problems, report.stuck), ([], [], []))
        self.assertEqual(report.evicted, [f"inbox/{stem}.jpg"])

    def test_an_evicted_capture_is_named_and_left_for_the_next_run(self) -> None:
        self.write(f"inbox/{CAPTURE}", CAPTURED)
        with mock.patch.object(self.store, "scan", return_value=mock.Mock(files=[], evicted=[f"inbox/{CAPTURE}"])):
            report = ingest.pending(self.store)

        self.assertEqual((report.captures, report.evicted), ([], [f"inbox/{CAPTURE}"]))


class IngestCommandTest(test_commands.CommandTest):
    def setUp(self) -> None:
        super().setUp()
        # The curation run calls these commands; outside it they are refused.
        self.environ["M2B_CURATION_RUN"] = "1"
        self.set_up(calendar="none")
        (self.store_root / "inbox").mkdir()

    def write(self, relative: str, text: str) -> None:
        target = self.store_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def test_normalize_reports_what_it_renamed(self) -> None:
        self.write("inbox/Shopping list.txt", "milk\n")

        answer = self.run_json("ingest", "normalize")

        (renamed,) = answer["renamed"]
        self.assertEqual(renamed["from"], "inbox/Shopping list.txt")
        self.assertTrue((self.store_root / renamed["to"]).is_file())

    def test_a_task_twice_prints_the_same_id_and_a_task_without_key_is_a_usage_error(self) -> None:
        self.write(f"inbox/{CAPTURE}", CAPTURED)

        first = self.run_json("ingest", "task", CAPTURE, "--key", "passport", "--title", "Renew passport")
        second = self.run_json("ingest", "task", f"inbox/{CAPTURE}", "--key", "passport", "--title", "Renew passport")
        code, _, err = self.run_command("ingest", "task", CAPTURE, "--title", "Renew passport")

        self.assertEqual(first, second)
        self.assertEqual(code, cli.EXIT_USAGE, err)

    def test_the_follow_up_task_comes_from_the_capture(self) -> None:
        self.write(
            f"inbox/{CAPTURE}",
            "---\ncreated: 2026-11-07T10:15:00+01:00\nsource: cli\nfollow_up: 2026-11-20\n---\nCall Dana\n",
        )

        answer = self.run_json("ingest", "task", CAPTURE, "--follow-up")
        tasks = self.run_json("tasks", "list")

        self.assertEqual([(task["id"], task["due"]) for task in tasks], [(answer["task_id"], "2026-11-20")])

    def test_ref_note_facts_filed_and_finish_carry_a_capture_into_the_corpus(self) -> None:
        self.write(f"inbox/{CAPTURE}", CAPTURED)

        for arguments in (
            ("ingest", "ref", CAPTURE, "https://example.org/passport"),
            ("ingest", "note", CAPTURE, "filed: passport task"),
            ("ingest", "facts-filed", CAPTURE),
        ):
            with self.subTest(arguments=arguments):
                code, _, err = self.run_command(*arguments)
                self.assertEqual(code, cli.EXIT_OK, err)
        answer = self.run_json("ingest", "finish", CAPTURE)

        self.assertEqual(answer["destinations"], [f"corpus/2026/11/{CAPTURE}"])
        text = (self.store_root / "corpus" / "2026" / "11" / CAPTURE).read_text(encoding="utf-8")
        for expected in ("refs: [https://example.org/passport]", "facts_filed: true", "filed: passport task"):
            self.assertIn(expected, text)

    def test_a_missing_capture_and_a_taken_destination_are_problems(self) -> None:
        """Covers: X6"""
        self.write(f"inbox/{CAPTURE}", CAPTURED)
        self.write(f"corpus/2026/11/{CAPTURE}", "other\n")

        for arguments in (("ingest", "note", "20261107T091500Z-cli-ffff.md", "x"), ("ingest", "finish", CAPTURE)):
            with self.subTest(arguments=arguments):
                code, _, err = self.run_command(*arguments)
                self.assertEqual(code, cli.EXIT_PROBLEM, err)
        self.assertTrue((self.store_root / "inbox" / CAPTURE).is_file())

    def test_list_names_the_owner_so_first_person_facts_join_their_file(self) -> None:
        self.write(f"inbox/{CAPTURE}", CAPTURED)
        profile.save_profile(self.store, {"version": 1, "owner": "Alex", "language": "en"})

        self.assertEqual(self.run_json("ingest", "list")["owner"], "Alex")

    def test_list_gives_the_model_the_store_its_language_and_the_captures(self) -> None:
        del self.environ["M2B_CURATION_RUN"]  # reading is open outside a run too
        self.write(f"inbox/{CAPTURE}", CAPTURED)
        profile.save_profile(self.store, {"version": 1, "owner": "Alex", "language": "de"})

        answer = self.run_json("ingest", "list")

        self.assertEqual(answer["store"], str(self.store_root))
        self.assertEqual(answer["language"], "de")
        self.assertFalse(answer["curation_run"])
        self.assertEqual(
            answer["captures"],
            [
                {
                    "file": CAPTURE,
                    "source": "cli",
                    "kind": None,
                    "facts_filed": False,
                    "quiet": False,
                    "follow_up": None,
                    "members": [],
                }
            ],
        )
        self.assertEqual((answer["evicted"], answer["problems"]), ([], []))

    def test_list_knows_when_it_runs_inside_a_curation_run(self) -> None:
        self.environ["M2B_CURATION_RUN"] = "1"

        self.assertTrue(self.run_json("ingest", "list")["curation_run"])

    def test_list_without_json_prints_one_line_per_capture_and_exits_1_on_problems(self) -> None:
        self.write(f"inbox/{CAPTURE}", CAPTURED)
        self.write("inbox/Shopping list.txt", "milk\n")

        code, out, err = self.run_command("ingest", "list")

        self.assertEqual(code, cli.EXIT_PROBLEM)
        self.assertEqual(out, f"{CAPTURE}\n")
        self.assertIn("Shopping list.txt", err)

    def test_unreachable_reminders_are_exit_3(self) -> None:
        self.set_up(tasks={"backend": "apple-reminders", "list": "sb-test-missing"}, calendar="none")
        self.write(f"inbox/{CAPTURE}", CAPTURED)

        code, _, err = self.run_command("ingest", "task", CAPTURE, "--key", "k", "--title", "T")

        self.assertEqual(code, cli.EXIT_UNREACHABLE, err)


if __name__ == "__main__":
    unittest.main()
