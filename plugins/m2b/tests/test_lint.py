"""Lint: findings about the store, and the only two fixes that are safe to make without the owner."""

from __future__ import annotations

import datetime
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import test_commands
from m2b import cli, lint
from m2b.config import profile
from m2b.curate import report
from m2b.store.folder import FolderStore
from m2b.store.guard import SF_DATALESS, DatalessGuard
from m2b.store.icloud import ICloudStore
from m2b.tasks.base import Tasks
from m2b.tasks.markdown import MarkdownTasks

NOW = datetime.datetime(2026, 11, 7, 3, 0, tzinfo=datetime.timezone.utc)
CAPTURE = "20261103T081200Z-cli-c3d4.md"
NOTE = "---\ncreated: 2026-11-03T09:12:00+01:00\nsource: cli\ncurated: true\n---\nThe office opens at eight\n"
INDEX = "# Memory\n\n## Facts\n\n- Dana's birthday is on 3 March (dana.md)\n\n## Current\n\n- Planning the trip\n"
DANA = f"# Dana\n\n- Birthday on 3 March.\n\n## Evidence\n\n- [[{CAPTURE}]]\n"
TASK = "tasks/a1b2c3d4e5f6.md"
OPEN_TASK = "---\nstatus: open\n---\nCall Dana\n"
DONE_TASK = "---\nstatus: done\ndone: 2026-11-05T08:15:00+01:00\n---\nCall Dana\n"


class LintFixture(unittest.TestCase):
    store_class: Any = FolderStore

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        base = Path(self._temp.name)
        self.root = base / "sb-test-store"
        self.root.mkdir()
        self.evicted: set[str] = set()
        guard = DatalessGuard(True, lstat=self._lstat)
        self.store = self.store_class(self.root, base / "machine-tmp", guard)
        self.write(f"corpus/2026/11/{CAPTURE}", NOTE)
        self.write("memory/MEMORY.md", INDEX)
        self.write("memory/dana.md", DANA)

    def _lstat(self, path: str | os.PathLike[str]) -> Any:
        result = os.lstat(path)
        relative = Path(path).relative_to(self.root).as_posix() if Path(path).is_relative_to(self.root) else ""
        return mock.Mock(st_flags=SF_DATALESS if relative in self.evicted else 0, st_mode=result.st_mode)

    def write(self, relative: str, data: str | bytes) -> None:
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)

    def findings(self, **options: Any) -> list[lint.Finding]:
        return lint.scan(self.store, **options).findings

    def codes(self, **options: Any) -> list[tuple[str, str, str]]:
        return [(finding.code, finding.kind, finding.path) for finding in self.findings(**options)]


class CleanStoreTest(LintFixture):
    def test_a_clean_store_has_no_findings(self) -> None:
        self.assertEqual(self.findings(), [])

    def test_binaries_waiting_in_the_inbox_are_not_findings(self) -> None:
        """Covers: X12"""
        self.write("inbox/IMG_0042.HEIC", b"heic")
        self.write("inbox/20261107T091600Z-cli-c3d4.jpg", b"jpeg")

        self.assertEqual(self.findings(), [])

    def test_an_excel_lock_file_beside_the_worklog_export_is_no_finding_and_stays(self) -> None:
        """Excel writes ~$<name> while the owner has the worklog's export open."""
        self.write("state/addons/worklog/ledger.xlsx", b"xlsx")
        self.write("state/addons/worklog/~$ledger.xlsx", b"lock")
        old = (NOW - datetime.timedelta(days=2)).timestamp()
        os.utime(self.root / "state/addons/worklog/~$ledger.xlsx", (old, old))

        self.assertEqual(self.findings(), [])
        self.assertEqual(lint.fix(self.store, now=NOW), [])
        self.assertTrue((self.root / "state/addons/worklog/~$ledger.xlsx").exists())


class CorpusSchemaTest(LintFixture):
    def test_names_outside_the_schema_are_actions_and_the_month_journal_is_fine(self) -> None:
        """Covers: B21"""
        self.write("corpus/2026/11/plan 2026.md", NOTE)
        self.write(
            "corpus/2026/11/202611-done.md",
            "---\ncreated: 2026-11-30T23:00:00+01:00\nsource: journal\nkind: journal\n---\n",
        )

        self.assertEqual(self.codes(), [("name", "action", "corpus/2026/11/plan 2026.md")])

    def test_a_note_without_frontmatter_created_or_source_is_an_action(self) -> None:
        self.write("corpus/2026/11/20261103T090000Z-cli-0001.md", "no frontmatter\n")
        self.write("corpus/2026/11/20261103T090000Z-cli-0002.md", "---\nsource: cli\n---\nx\n")
        self.write("corpus/2026/11/20261103T090000Z-cli-0003.md", "---\ncreated: 2026-11-03T10:00:00+01:00\n---\nx\n")

        self.assertEqual([(code, kind) for code, kind, _ in self.codes()], [("frontmatter", "action")] * 3)

    def test_created_without_offset_is_tolerated_with_an_info(self) -> None:
        """Covers: X5"""
        self.write(
            "corpus/2026/11/20261103T090000Z-cli-0001.md", "---\ncreated: 2026-11-03T10:00:00\nsource: cli\n---\nx\n"
        )

        self.assertEqual(self.codes(), [("created-offset", "info", "corpus/2026/11/20261103T090000Z-cli-0001.md")])

    def test_a_note_in_the_wrong_month_folder_is_an_action(self) -> None:
        self.write("corpus/2026/10/20261103T090000Z-cli-0001.md", NOTE)

        self.assertEqual(self.codes(), [("month", "action", "corpus/2026/10/20261103T090000Z-cli-0001.md")])

    def test_a_ref_to_a_corpus_file_that_does_not_exist_is_an_action_and_urls_are_not_checked(self) -> None:
        self.write(
            "corpus/2026/11/20261103T090000Z-cli-0001.md",
            "---\ncreated: 2026-11-03T10:00:00+01:00\nsource: cli\n"
            f"refs: [{CAPTURE}, 20260101T000000Z-cli-ffff.md, https://example.org/x]\n---\nx\n",
        )

        self.assertEqual(self.codes(), [("broken-ref", "action", "corpus/2026/11/20261103T090000Z-cli-0001.md")])
        self.assertIn("20260101T000000Z-cli-ffff.md", self.findings()[0].text)


class MalformedTest(LintFixture):
    def test_a_refs_value_that_is_no_list_is_a_finding_and_the_scan_goes_on(self) -> None:
        self.write(
            "corpus/2026/11/20261103T090000Z-cli-0001.md",
            "---\ncreated: 2026-11-03T10:00:00+01:00\nsource: cli\nrefs: x.md\n---\nx\n",
        )
        self.write("corpus/2026/11/plan.md", NOTE)

        self.assertEqual(
            [(code, path) for code, _, path in self.codes()],
            [("frontmatter", "corpus/2026/11/20261103T090000Z-cli-0001.md"), ("name", "corpus/2026/11/plan.md")],
        )

    def test_a_task_file_that_cannot_be_parsed_is_named_and_the_other_tasks_are_checked(self) -> None:
        """Covers: B59"""
        self.write("tasks/0123456789ab.md", "---\nstatus: someday\n---\nCall Dana\n")
        self.write("tasks/aaaaaaaaaaaa.md", "---\nstatus: open\n---\nCall Kim\nm2b:capture gone.md call\n")

        self.assertEqual(
            self.codes(tasks=MarkdownTasks(self.store)),
            [("task-file", "action", "tasks/0123456789ab.md"), ("task-without-capture", "info", "tasks")],
        )

    def test_a_task_folder_another_backend_left_behind_is_not_read(self) -> None:
        """Covers: B59"""
        self.write("tasks/0123456789ab.md", "---\nstatus: someday\n---\nCall Dana\n")
        reminders = mock.Mock(spec=Tasks)
        reminders.items.return_value = []
        reminders.unreadable.return_value = []
        reminders.conflict_copies.return_value = []

        self.assertEqual(self.codes(tasks=reminders), [])


class BundleTest(LintFixture):
    SIDECAR = "---\ncreated: 2026-11-03T10:00:00+01:00\nsource: cli\nkind: sidecar\n---\nphoto\n"

    def test_a_sidecar_without_its_file_and_a_file_without_its_sidecar_are_actions(self) -> None:
        self.write("corpus/2026/11/20261103T090000Z-cli-0001.md", self.SIDECAR)
        self.write("corpus/2026/11/20261103T090000Z-cli-0002.jpg", b"jpeg")

        self.assertEqual(
            self.codes(),
            [
                ("orphaned-sidecar", "action", "corpus/2026/11/20261103T090000Z-cli-0001.md"),
                ("orphaned-member", "action", "corpus/2026/11/20261103T090000Z-cli-0002.jpg"),
                ("binary-volume", "info", "corpus"),
            ],
        )

    def test_a_complete_bundle_only_counts_towards_the_binary_volume(self) -> None:
        self.write("corpus/2026/11/20261103T090000Z-cli-0001.md", self.SIDECAR)
        self.write("corpus/2026/11/20261103T090000Z-cli-0001.heic", b"h" * 2048)
        self.write("corpus/2026/11/20261103T090000Z-cli-0001.jpg", b"j" * 1024)

        (finding,) = self.findings()
        self.assertEqual((finding.code, finding.kind), ("binary-volume", "info"))
        self.assertIn("2 binary files", finding.text)
        self.assertIn("3.0 KB", finding.text)


class EvictedBundleTest(LintFixture):
    store_class = ICloudStore

    def test_an_evicted_member_or_sidecar_is_no_orphan(self) -> None:
        self.write("corpus/2026/11/20261103T090000Z-cli-0001.md", BundleTest.SIDECAR)
        self.write("corpus/2026/11/20261103T090000Z-cli-0001.pdf", b"pdf")
        self.write("corpus/2026/11/20261103T090000Z-cli-0002.md", BundleTest.SIDECAR)
        self.write("corpus/2026/11/20261103T090000Z-cli-0002.pdf", b"pdf")
        self.evicted |= {"corpus/2026/11/20261103T090000Z-cli-0001.pdf", "corpus/2026/11/20261103T090000Z-cli-0002.md"}

        self.assertEqual([code for code, _, _ in self.codes()], ["evicted", "binary-volume"])


class MemoryTest(LintFixture):
    def test_a_fact_file_no_facts_line_points_to_is_an_action_even_if_a_longer_name_is_indexed(self) -> None:
        """Covers: X13"""
        self.write("memory/MEMORY.md", INDEX.replace("(dana.md)", "(dana.md)\n- A friend of Alex (friend-alex.md)"))
        self.write("memory/friend-alex.md", f"# Friend\n\n## Evidence\n\n- [[{CAPTURE}]]\n")
        self.write("memory/alex.md", f"# Alex\n\n## Evidence\n\n- [[{CAPTURE}]]\n")

        self.assertEqual(self.codes(), [("unindexed-fact", "action", "memory/alex.md")])

    def test_a_facts_line_without_its_file_and_an_unparsed_facts_line_are_actions(self) -> None:
        self.write(
            "memory/MEMORY.md", INDEX.replace("(dana.md)", "(dana.md)\n- Robin lives in Lyon (robin.md)\n- loose line")
        )

        self.assertEqual(
            self.codes(),
            [("missing-fact-file", "action", "memory/MEMORY.md"), ("index-line", "action", "memory/MEMORY.md")],
        )

    def test_a_distillate_over_2_kb_is_an_info_and_a_missing_one_an_action(self) -> None:
        self.write("memory/MEMORY.md", INDEX + "- " + "x" * 2100 + "\n")
        self.assertEqual(self.codes(), [("distillate-size", "info", "memory/MEMORY.md")])

        (self.root / "memory" / "MEMORY.md").unlink()
        self.assertIn(("no-distillate", "action", "memory/MEMORY.md"), self.codes())


class TopicTest(LintFixture):
    """A topic's heading decides when its facts come into a session, so a broken one is an action."""

    def index_with(self, heading: str) -> str:
        return INDEX.replace("- Dana's birthday", f"{heading}\n- Dana's birthday")

    def test_a_well_formed_topic_is_fine(self) -> None:
        self.write("memory/MEMORY.md", self.index_with("### Dana (Dana Berg, Berg family)"))

        self.assertEqual(self.codes(), [])

    def test_a_well_formed_topic_under_current_is_fine(self) -> None:
        """Covers: B48"""
        self.write(
            "memory/MEMORY.md", INDEX.replace("- Planning the trip", "### Trip (Porto, Lisbon)\n- Planning the trip")
        )

        self.assertEqual(self.codes(), [])

    def test_a_heading_without_words_is_an_action_in_either_section(self) -> None:
        """Covers: B48"""
        text = self.index_with("### Dana").replace("- Planning the trip", "### Trip\n- Planning the trip")
        self.write("memory/MEMORY.md", text)

        self.assertEqual(
            self.codes(),
            [("topic-heading", "action", "memory/MEMORY.md"), ("topic-heading", "action", "memory/MEMORY.md")],
        )

    def test_a_topic_under_current_follows_the_rules_for_its_words_too(self) -> None:
        """Covers: B48"""
        self.write("memory/MEMORY.md", INDEX.replace("- Planning the trip", "### Trip (Porto)\n- Planning the trip"))

        self.assertEqual(self.codes(), [("topic-words", "action", "memory/MEMORY.md")])

    def test_the_size_of_a_topic_counts_its_current_items(self) -> None:
        """Covers: B48"""
        items = "".join(f"- Planning stage {number} of the trip to Porto and Lisbon\n" for number in range(60))
        self.write("memory/MEMORY.md", INDEX + f"\n### Trip (Porto, Lisbon)\n{items}")

        self.assertEqual(self.codes(), [("distillate-size", "info", "memory/MEMORY.md")])

    def test_words_that_would_match_too_much_or_never_are_actions(self) -> None:
        """Covers: B48"""
        for heading in (
            "### Dana (Dana Berg)",
            "### Dana (Dana Berg, Berg family, Bergs, Dana B., Berg clan, Berg house)",
            "### Dana (Dana Berg, DB)",
            "### Dana (Dana Berg, " + "x" * 41 + ")",
            "### " + "D" * 61 + " (Dana Berg, Berg family)",
        ):
            with self.subTest(heading=heading):
                self.write("memory/MEMORY.md", self.index_with(heading))
                self.assertEqual(self.codes(), [("topic-words", "action", "memory/MEMORY.md")])

    def test_size_counts_per_view(self) -> None:
        """Covers: B48"""
        big_topic = "### Dana (Dana Berg, Berg family)\n" + "".join(
            f"- Fact {n} {'x' * 60} (dana.md)\n" for n in range(40)
        )
        self.write("memory/MEMORY.md", INDEX.replace("- Dana's birthday is on 3 March (dana.md)\n", big_topic))

        findings = [finding for finding in self.findings() if finding.code == "distillate-size"]

        self.assertEqual(len(findings), 1)
        self.assertIn("topic Dana", findings[0].text)


class ExpiryTest(LintFixture):
    def test_an_until_or_since_that_is_no_date_is_an_action(self) -> None:
        """Covers: B40"""
        self.write("memory/MEMORY.md", INDEX.replace("- Planning the trip\n", "- Planning the trip (since soon)\n"))
        self.write("memory/dana.md", "---\nuntil: next spring\n---\n" + DANA)

        self.assertEqual(
            self.codes(),
            [("invalid-since", "action", "memory/MEMORY.md"), ("invalid-until", "action", "memory/dana.md")],
        )

    def test_valid_dates_are_no_finding(self) -> None:
        current = "- Planning the trip (since 2026-10-02)\n"
        self.write("memory/MEMORY.md", INDEX.replace("- Planning the trip\n", current))
        self.write("memory/dana.md", "---\nuntil: 2026-11-14\n---\n" + DANA)

        self.assertEqual(self.codes(), [])


class EarlierTest(LintFixture):
    def earlier(self, lines: str) -> str:
        return DANA.replace("\n## Evidence", f"\n## Earlier\n\n{lines}\n## Evidence")

    def test_an_earlier_value_with_the_day_it_stopped_is_no_finding(self) -> None:
        """Covers: B74"""
        self.write("memory/MEMORY.md", INDEX)
        self.write("memory/dana.md", self.earlier("- Lived in Zurich (until 2026-11-07)\n"))

        self.assertEqual(self.codes(), [])

    def test_a_heading_with_a_windows_line_end_is_still_checked(self) -> None:
        """Covers: B74"""
        self.write("memory/MEMORY.md", INDEX)
        self.write("memory/dana.md", self.earlier("- Lived in Zurich\n").replace("\n", "\r\n"))

        self.assertEqual(self.codes(), [("invalid-earlier", "action", "memory/dana.md")])

    def test_an_earlier_value_without_its_day_is_an_action(self) -> None:
        """Covers: B74"""
        self.write("memory/MEMORY.md", INDEX)
        for line in (
            "- Lived in Zurich\n",
            "- Lived in Zurich (until last year)\n",
            "Lived in Zurich (until 2026-11-07)\n",
            "- Lived in Zurich (until 2026-02-30)\n",
        ):
            with self.subTest(line=line):
                self.write("memory/dana.md", self.earlier(line))
                self.assertEqual(self.codes(), [("invalid-earlier", "action", "memory/dana.md")])


class EvictedMemoryTest(LintFixture):
    def test_an_evicted_memory_folder_is_no_missing_distillate(self) -> None:
        self.evicted.add("memory")

        self.assertEqual(self.codes(), [("evicted", "info", "memory")])

    def test_links_are_checked_when_only_the_distillate_is_evicted(self) -> None:
        self.write("memory/dana.md", DANA + "- [[nothing.md]]\n")
        self.evicted.add("memory/MEMORY.md")

        self.assertEqual(self.codes(), [("evicted", "info", "memory"), ("broken-link", "action", "memory/dana.md")])


class LinkTest(LintFixture):
    def test_links_without_extension_into_the_inbox_or_to_nothing_are_broken_with_their_candidates(self) -> None:
        """Covers: B22"""
        stem = CAPTURE.removesuffix(".md")
        self.write(
            "memory/dana.md",
            DANA + f"- [[{stem}]]\n- [[inbox/{CAPTURE}]]\n- [[20260101T000000Z-cli-ffff.md]]\n- [[{CAPTURE}]]\n",
        )

        broken = self.findings()

        self.assertEqual([(f.code, f.kind, f.path) for f in broken], [("broken-link", "action", "memory/dana.md")] * 3)
        self.assertEqual([f.link for f in broken], [stem, f"inbox/{CAPTURE}", "20260101T000000Z-cli-ffff.md"])
        self.assertEqual([f.candidates for f in broken], [(CAPTURE,), (CAPTURE,), ()])

    def test_a_link_into_an_evicted_corpus_folder_is_not_called_broken(self) -> None:
        self.write("memory/dana.md", DANA + "- [[20261001T000000Z-cli-eeee.md]]\n")
        self.write("corpus/2026/10/x.md", "x")
        self.evicted.add("corpus/2026/10")

        self.assertEqual(self.codes(), [("evicted", "info", "corpus")])


class EvictedTest(LintFixture):
    store_class = ICloudStore

    def test_evicted_files_are_one_info_per_folder_with_the_fetch_command(self) -> None:
        """Covers: B6"""
        self.write("corpus/2026/11/20261103T090000Z-cli-0001.md", NOTE)
        self.write("corpus/2026/11/20261103T090000Z-cli-0002.md", NOTE)
        self.evicted |= {"corpus/2026/11/20261103T090000Z-cli-0001.md", "corpus/2026/11/20261103T090000Z-cli-0002.md"}

        (finding,) = self.findings()

        self.assertEqual((finding.code, finding.kind, finding.path), ("evicted", "info", "corpus"))
        self.assertIn("2 files", finding.text)
        self.assertIn("m2b store fetch corpus", finding.text)


class ConflictCopyInAFolderStoreTest(LintFixture):
    def test_a_dropbox_or_syncthing_copy_is_a_finding_and_removed_only_when_it_equals_its_original(self) -> None:
        """Covers: B150, B21"""
        identical = f"corpus/2026/11/{CAPTURE.replace('.md', ' (conflicted copy 2026-11-07).md')}"
        different = f"corpus/2026/11/{CAPTURE.replace('.md', '.sync-conflict-20261107-091600-ABCDEFG.md')}"
        self.write(identical, NOTE)
        self.write(different, NOTE + "changed\n")

        self.assertEqual(self.codes(), [("conflict-copy", "info", identical), ("conflict-copy", "action", different)])
        self.assertEqual(lint.fix(self.store, now=NOW), [identical])
        self.assertTrue(self.store.exists(different))
        self.assertFalse(self.store.exists(identical))

    def test_a_copy_that_cannot_be_read_is_one_finding_and_the_other_findings_stay(self) -> None:
        """Covers: B150"""
        copy = f"corpus/2026/11/{CAPTURE.replace('.md', '.sync-conflict-20261107-091600-ABCDEFG.md')}"
        self.write(copy, NOTE)
        self.write("corpus/2026/11/holiday.md", NOTE)
        real_read = self.store.read_bytes

        def read(relative: str) -> bytes:
            if relative == copy:
                raise lint.StoreError(f"{relative} could not be read: Permission denied")
            return real_read(relative)

        with mock.patch.object(self.store, "read_bytes", side_effect=read):
            codes = self.codes()
            removed = lint.fix(self.store, now=NOW)

        self.assertEqual(codes, [("name", "action", "corpus/2026/11/holiday.md"), ("conflict-copy", "info", copy)])
        self.assertEqual(removed, [])


class ConflictCopyTest(LintFixture):
    store_class = ICloudStore

    def test_identical_copies_are_info_for_fix_and_differing_ones_actions(self) -> None:
        """Covers: B21 (conflict copies)"""
        self.write(f"corpus/2026/11/{CAPTURE.replace('.md', ' 2.md')}", NOTE)
        self.write(f"corpus/2026/11/{CAPTURE.replace('.md', ' 3.md')}", NOTE + "changed\n")

        self.assertEqual(
            [(code, kind) for code, kind, _ in self.codes()],
            [("conflict-copy", "info"), ("conflict-copy", "action")],
        )

    def test_an_evicted_corpus_folder_that_cannot_be_listed_is_reported_not_fatal(self) -> None:
        self.write(f"corpus/2026/11/{CAPTURE.replace('.md', ' 2.md')}", NOTE)
        self.write("corpus/2025/03/20250301T090000Z-cli-0001.md", NOTE)
        self.evicted.add("corpus/2025/03")
        real_entries = self.store._visible_entries

        def entries(relative: str) -> list[Path]:
            if relative == "corpus/2025/03":
                raise lint.StoreError("Resource deadlock avoided")
            return real_entries(relative)

        with mock.patch.object(self.store, "_visible_entries", side_effect=entries):
            codes = [(code, kind) for code, kind, _ in self.codes()]
            removed = lint.fix(self.store, now=NOW)

        self.assertEqual(codes, [("evicted", "info"), ("conflict-copy", "info")])
        self.assertEqual(removed, [f"corpus/2026/11/{CAPTURE.replace('.md', ' 2.md')}"])

    def test_an_evicted_copy_is_still_a_copy_and_never_compared(self) -> None:
        copy = f"corpus/2026/11/{CAPTURE.replace('.md', ' 2.md')}"
        self.write(copy, NOTE)
        self.evicted.add(copy)

        self.assertEqual([c.path for c in self.store.conflict_copies("corpus")], [copy])
        self.assertEqual(
            [(code, kind) for code, kind, _ in self.codes()], [("evicted", "info"), ("conflict-copy", "info")]
        )
        self.assertEqual(lint.fix(self.store, now=NOW), [])

    def test_fix_removes_only_the_identical_copy_and_old_own_temp_files(self) -> None:
        """Covers: B21, X22"""
        identical = f"corpus/2026/11/{CAPTURE.replace('.md', ' 2.md')}"
        differing = f"corpus/2026/11/{CAPTURE.replace('.md', ' 3.md')}"
        self.write(identical, NOTE)
        self.write(differing, NOTE + "changed\n")
        self.write("plan.md", "the owner's own file\n")
        self.write("plan 2.md", "the owner's own file\n")
        old_temp, new_temp, foreign = "memory/.sb-tmp-old", "memory/.sb-tmp-new", "memory/.other-hidden"
        for relative in (old_temp, new_temp, foreign):
            self.write(relative, "x")
        two_days_ago = (NOW - datetime.timedelta(days=2)).timestamp()
        for relative in (old_temp, foreign):
            os.utime(self.root / relative, (two_days_ago, two_days_ago))

        removed = lint.fix(self.store, now=NOW)

        self.assertEqual(sorted(removed), sorted([identical, old_temp]))
        for kept in (differing, "plan 2.md", new_temp, foreign, f"corpus/2026/11/{CAPTURE}"):
            self.assertTrue((self.root / kept).exists(), kept)


class TaskConflictCopies:
    """Holds the tests so that discovery runs them only with a backend and its names for a copy."""

    class Tests(LintFixture):
        identical: str
        differing: str
        copy_of_differing: str

        def setUp(self) -> None:
            super().setUp()
            self.write(TASK, OPEN_TASK)
            self.tasks = MarkdownTasks(self.store)

        def task_states(self) -> list[tuple[str, bool]]:
            return [(task.id, task.completed) for task in self.tasks.items(include_completed=True)]

        def test_a_copy_of_a_task_file_is_a_finding_that_says_whether_it_equals_the_task(self) -> None:
            """Covers: B157"""
            self.write(self.identical, OPEN_TASK)
            self.write(self.differing, DONE_TASK)

            self.assertEqual(
                [(finding.kind, finding.path, finding.text) for finding in self.findings(tasks=self.tasks)],
                [
                    ("info", self.identical, f"{self.identical} equals {TASK}; lint fix removes it"),
                    ("action", self.differing, f"{self.differing} differs from {TASK}; keep one of them"),
                ],
            )

        def test_fix_removes_only_the_copy_that_equals_the_task_and_the_task_stays_as_it_is(self) -> None:
            """Covers: B157"""
            self.write(self.identical, OPEN_TASK)
            self.write(self.differing, DONE_TASK)

            removed = lint.fix(self.store, self.tasks, now=NOW)

            self.assertEqual(removed, [self.identical])
            self.assertFalse(self.store.exists(self.identical))
            self.assertEqual(self.store.read_text(self.differing), DONE_TASK)
            self.assertEqual(self.store.read_text(TASK), OPEN_TASK)
            self.assertEqual(self.task_states(), [("a1b2c3d4e5f6", False)])

        def test_a_copy_that_cannot_be_read_is_named_as_not_compared_and_stays(self) -> None:
            """Covers: B157"""
            self.write(self.identical, OPEN_TASK)
            real_read = self.store.read_bytes

            def read(relative: str) -> bytes:
                if relative == self.identical:
                    raise lint.StoreError(f"{relative} could not be read: Permission denied")
                return real_read(relative)

            with mock.patch.object(self.store, "read_bytes", side_effect=read):
                findings = self.findings(tasks=self.tasks)
                removed = lint.fix(self.store, self.tasks, now=NOW)

            self.assertEqual(
                [(finding.kind, finding.text) for finding in findings],
                [("info", f"{self.identical} or {TASK} is not downloaded or cannot be read; not compared")],
            )
            self.assertEqual(removed, [])
            self.assertTrue(self.store.exists(self.identical))

        def test_a_copy_of_a_copy_is_named_against_the_copy_it_was_made_of(self) -> None:
            """Covers: B157"""
            self.write(self.differing, DONE_TASK)
            self.write(self.copy_of_differing, DONE_TASK)

            self.assertCountEqual(
                [(finding.kind, finding.text) for finding in self.findings(tasks=self.tasks)],
                [
                    ("action", f"{self.differing} differs from {TASK}; keep one of them"),
                    ("info", f"{self.copy_of_differing} equals {self.differing}; lint fix removes it"),
                ],
            )
            self.assertEqual(lint.fix(self.store, self.tasks, now=NOW), [self.copy_of_differing])
            self.assertEqual(self.store.read_text(self.differing), DONE_TASK)
            self.assertEqual(self.task_states(), [("a1b2c3d4e5f6", False)])

        def test_a_copy_in_a_subfolder_of_the_task_folder_is_not_named_and_stays(self) -> None:
            """Covers: B157"""
            copy = self.identical.replace("tasks/", "tasks/old/")
            self.write("tasks/old/a1b2c3d4e5f6.md", OPEN_TASK)
            self.write(copy, OPEN_TASK)

            self.assertEqual(self.codes(tasks=self.tasks), [])
            self.assertEqual(lint.fix(self.store, self.tasks, now=NOW), [])
            self.assertTrue(self.store.exists(copy))


class TaskConflictCopyInAFolderStoreTest(TaskConflictCopies.Tests):
    identical = "tasks/a1b2c3d4e5f6 (Dana's conflicted copy 2026-11-05).md"
    differing = "tasks/a1b2c3d4e5f6.sync-conflict-20261105-081500-ABCDEFG.md"
    copy_of_differing = "tasks/a1b2c3d4e5f6.sync-conflict-20261105-081500-ABCDEFG (conflicted copy 2026-11-06).md"

    def test_a_task_folder_another_backend_left_behind_keeps_its_copies_without_a_finding(self) -> None:
        """Covers: B157"""
        self.write(self.identical, OPEN_TASK)
        reminders = mock.Mock(spec=Tasks)
        reminders.items.return_value = []
        reminders.unreadable.return_value = []
        reminders.conflict_copies.return_value = []

        self.assertEqual(self.codes(tasks=reminders), [])
        self.assertEqual(lint.fix(self.store, reminders, now=NOW), [])
        self.assertEqual(self.codes(), [])
        self.assertEqual(lint.fix(self.store, now=NOW), [])
        self.assertTrue(self.store.exists(self.identical))

    def test_a_task_folder_that_cannot_be_read_is_one_finding_and_stops_no_other_fix(self) -> None:
        """Covers: B157"""
        copy_in_the_archive = f"corpus/2026/11/{CAPTURE.replace('.md', ' (conflicted copy 2026-11-07).md')}"
        self.write(copy_in_the_archive, NOTE)
        self.write(self.identical, OPEN_TASK)
        unreachable = lint.TasksError("the task folder could not be read: Permission denied")

        with mock.patch.object(self.tasks, "conflict_copies", side_effect=unreachable):
            codes = self.codes(tasks=self.tasks)
            removed = lint.fix(self.store, self.tasks, now=NOW)

        self.assertEqual(codes, [("conflict-copy", "info", copy_in_the_archive), ("tasks-unreadable", "info", "tasks")])
        self.assertEqual(removed, [copy_in_the_archive])
        self.assertTrue(self.store.exists(self.identical))


class TaskConflictCopyInAnICloudStoreTest(TaskConflictCopies.Tests):
    store_class = ICloudStore
    identical = "tasks/a1b2c3d4e5f6 2.md"
    differing = "tasks/a1b2c3d4e5f6 3.md"
    copy_of_differing = "tasks/a1b2c3d4e5f6 3 2.md"

    def test_an_evicted_copy_is_named_as_not_compared_and_stays(self) -> None:
        """Covers: B157"""
        self.write(self.identical, OPEN_TASK)
        self.evicted.add(self.identical)

        self.assertEqual(self.codes(tasks=self.tasks), [("conflict-copy", "info", self.identical)])
        self.assertEqual(lint.fix(self.store, self.tasks, now=NOW), [])
        self.assertEqual(self.task_states(), [("a1b2c3d4e5f6", False)])

    def test_a_copy_whose_task_is_evicted_is_named_as_not_compared_though_the_tasks_cannot_be_read(self) -> None:
        """Covers: B157"""
        self.write(self.identical, OPEN_TASK)
        self.evicted.add(TASK)

        findings = self.findings(tasks=self.tasks)

        self.assertEqual(
            [(finding.code, finding.kind, finding.path) for finding in findings],
            [("conflict-copy", "info", self.identical), ("tasks-unreadable", "info", "tasks")],
        )
        self.assertEqual(
            findings[0].text, f"{self.identical} or {TASK} is not downloaded or cannot be read; not compared"
        )
        self.assertEqual(lint.fix(self.store, self.tasks, now=NOW), [])
        self.assertTrue(self.store.exists(self.identical))


class TaskWithoutCaptureTest(LintFixture):
    def test_a_capture_task_whose_capture_is_gone_is_an_info_and_unreachable_tasks_say_so(self) -> None:
        tasks = MarkdownTasks(self.store)
        tasks.add("Call Dana", notes=f"m2b:capture {CAPTURE} call")
        tasks.add("Renew passport", notes="m2b:capture 20260101T000000Z-cli-ffff.md passport")

        self.assertEqual(self.codes(tasks=tasks), [("task-without-capture", "info", "tasks")])
        self.assertIn("Renew passport", self.findings(tasks=tasks)[0].text)

        broken = mock.Mock()
        broken.unreadable.return_value = []
        broken.conflict_copies.return_value = []
        broken.items.side_effect = lint.TasksError("Reminders did not answer")
        self.assertEqual(self.codes(tasks=broken), [("tasks-unreadable", "info", "tasks")])


class LintCommandTest(test_commands.CommandTest):
    def setUp(self) -> None:
        super().setUp()
        # The curation run calls these commands; outside it they are refused.
        self.environ["M2B_CURATION_RUN"] = "1"
        self.set_up(calendar="none")
        profile.save_profile(self.store, {"version": 1, "owner": "Alex", "language": "en"})
        (self.store_root / "memory").mkdir()
        (self.store_root / "memory" / "MEMORY.md").write_text(INDEX, encoding="utf-8")
        (self.store_root / "memory" / "dana.md").write_text(DANA + "- [[nothing.md]]\n", encoding="utf-8")
        (self.store_root / "corpus" / "2026" / "11").mkdir(parents=True)
        (self.store_root / "corpus" / "2026" / "11" / CAPTURE).write_text(NOTE, encoding="utf-8")

    def test_scan_gives_the_model_the_store_and_the_findings(self) -> None:
        del self.environ["M2B_CURATION_RUN"]  # reading is open outside a run too
        code, out, _ = self.run_command("lint", "scan", "--json")

        self.assertEqual(code, cli.EXIT_PROBLEM)
        answer = test_commands.json.loads(out)
        self.assertEqual(answer["store"], str(self.store_root))
        self.assertFalse(answer["curation_run"])
        self.assertEqual(
            answer["findings"],
            [
                {
                    "code": "broken-link",
                    "kind": "action",
                    "path": "memory/dana.md",
                    "text": "memory/dana.md links [[nothing.md]], which is no corpus file",
                    "link": "nothing.md",
                    "candidates": [],
                }
            ],
        )

    def test_scan_report_hands_every_finding_to_the_run(self) -> None:
        token = report.open_run(self.machine)
        self.environ[report.RUN_TOKEN_VARIABLE] = token

        code, _, err = self.run_command("lint", "scan", "--report")

        self.assertEqual(code, cli.EXIT_OK, err)
        (finding,) = report.read_findings(self.machine, token)
        self.assertEqual((finding.step, finding.kind), ("lint", "action"))
        self.assertIn("[[nothing.md]]", finding.text)

    def test_scan_report_outside_a_run_exits_2(self) -> None:
        self.assertEqual(self.run_command("lint", "scan", "--report")[0], cli.EXIT_USAGE)

    def test_fix_prints_what_it_removed(self) -> None:
        (self.store_root / "memory" / ".sb-tmp-old").write_text("x", encoding="utf-8")
        old = (datetime.datetime.now() - datetime.timedelta(days=2)).timestamp()
        os.utime(self.store_root / "memory" / ".sb-tmp-old", (old, old))

        code, out, err = self.run_command("lint", "fix")

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(out, "removed memory/.sb-tmp-old\n")

    def test_fix_removes_a_copy_of_a_task_file_that_equals_the_task(self) -> None:
        """Covers: B157"""
        copy = "a1b2c3d4e5f6 (conflicted copy 2026-11-05).md"
        (self.store_root / "tasks").mkdir()
        (self.store_root / TASK).write_text(OPEN_TASK, encoding="utf-8")
        (self.store_root / "tasks" / copy).write_text(OPEN_TASK, encoding="utf-8")

        code, out, err = self.run_command("lint", "fix")

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(out, f"removed tasks/{copy}\n")
        self.assertEqual(sorted(path.name for path in (self.store_root / "tasks").iterdir()), ["a1b2c3d4e5f6.md"])


if __name__ == "__main__":
    unittest.main()
