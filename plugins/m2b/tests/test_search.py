"""Search: full text over corpus, memory and inbox, read under the guard."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from m2b import cli, paths
from m2b.config import machine
from m2b.search import Hit, search
from m2b.store.base import EvictedFileError, StoreReadError
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard
from store_contract import FakeEviction


class SearchFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        base = Path(self._temp.name)
        self.root = base / "sb-test-store"
        self.root.mkdir()
        self.eviction = FakeEviction()
        self.store = FolderStore(self.root, base / "machine-tmp", DatalessGuard(True, lstat=self.eviction.lstat))

    def write(self, relative: str, text: str) -> None:
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))

    def evict(self, relative: str) -> None:
        self.eviction.evicted.add(self.root / relative)


class SearchTest(SearchFixture):
    def test_hits_come_with_file_and_line_and_the_evicted_file_is_listed_apart(self) -> None:
        """Covers: B6"""
        self.write("corpus/2026/10/20261012T081500Z-cli-a1b2.md", "---\nsource: cli\n---\nDana likes old maps.\n")
        self.write("corpus/2026/09/20260903T100000Z-cli-c3d4.md", "Dana moved to Lisbon.\n")
        self.evict("corpus/2026/09/20260903T100000Z-cli-c3d4.md")

        result = search(self.store, "dana")

        self.assertEqual(result.hits, [Hit("corpus/2026/10/20261012T081500Z-cli-a1b2.md", 4, "Dana likes old maps.")])
        self.assertEqual(result.evicted, ["corpus/2026/09/20260903T100000Z-cli-c3d4.md"])

    def test_corpus_memory_and_inbox_are_searched_and_nothing_else(self) -> None:
        for relative in (
            "corpus/2026/11/a.md",
            "memory/MEMORY.md",
            "memory/dana.md",
            "inbox/b.md",
            "tasks/c.md",
            "state/core/run.json",
            "STORE.md",
            "inbox/.hidden.md",
        ):
            self.write(relative, "Acme order\n")

        found = [hit.path for hit in search(self.store, "acme").hits]

        self.assertEqual(found, ["memory/MEMORY.md", "memory/dana.md", "corpus/2026/11/a.md", "inbox/b.md"])

    def test_a_note_filed_from_the_inbox_into_the_corpus_during_the_search_is_still_found(self) -> None:
        self.write("inbox/20261105T080000Z-cli-abcd.md", "Dana\n")
        real_scan = self.store.scan

        def scan(folder: str) -> Any:
            result = real_scan(folder)
            if folder == "inbox":
                target = self.root / "corpus/2026/11"
                target.mkdir(parents=True)
                (self.root / "inbox/20261105T080000Z-cli-abcd.md").rename(target / "20261105T080000Z-cli-abcd.md")
            return result

        with mock.patch.object(self.store, "scan", scan):
            result = search(self.store, "dana")

        self.assertEqual([hit.path for hit in result.hits], ["corpus/2026/11/20261105T080000Z-cli-abcd.md"])

    def test_the_match_ignores_case_and_finds_parts_of_words(self) -> None:
        self.write("inbox/a.md", "Steady TEA, every morning\nStraße 4\n")

        self.assertEqual([hit.line for hit in search(self.store, "tea").hits], [1])
        self.assertEqual([hit.line for hit in search(self.store, "STRASSE").hits], [2])

    def test_whole_words_leaves_out_matches_inside_a_word(self) -> None:
        self.write("inbox/a.md", "steady pace\nGreen tea, please\nteapot\n")

        hits = search(self.store, "Tea", whole_words=True).hits

        self.assertEqual([hit.line for hit in hits], [2])

    def test_several_terms_find_every_line_that_holds_one_of_them_once(self) -> None:
        """Covers: B68"""
        self.write("inbox/a.md", "Akku für den Rasenmäher bestellt\nnew battery for the lawn mower\nlawn chairs\n")
        self.write("memory/b.md", "Rasenmäher: lawn mower, both words in one line\n")

        hits = search(self.store, "lawn mower", "Rasenmäher").hits

        self.assertEqual(
            [(hit.path, hit.line) for hit in hits], [("memory/b.md", 1), ("inbox/a.md", 1), ("inbox/a.md", 2)]
        )

    def test_whole_words_holds_for_each_term(self) -> None:
        """Covers: B68"""
        self.write("inbox/a.md", "teapot\ngreen tea\nTee am Morgen\nTeekanne\n")

        hits = search(self.store, "tea", "Tee", whole_words=True).hits

        self.assertEqual([hit.line for hit in hits], [2, 3])

    def test_an_empty_term_among_several_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            search(self.store, "dana", " ")

    def test_lines_are_split_at_newlines_only_and_lose_a_carriage_return(self) -> None:
        self.write("inbox/a.md", "first\u2028still first\r\nsecond with Alex\r\n")

        self.assertEqual(search(self.store, "alex").hits, [Hit("inbox/a.md", 2, "second with Alex")])

    def test_every_hit_in_a_file_is_reported_in_line_order(self) -> None:
        self.write("memory/alex.md", "Alex\nnothing\nalex again\n")

        self.assertEqual([hit.line for hit in search(self.store, "alex").hits], [1, 3])

    def test_only_text_notes_are_read_so_a_photo_is_found_through_its_sidecar(self) -> None:
        self.write("inbox/20261101T090000Z-phone-aaaa.heic", "Acme in the bytes")
        self.write("inbox/20261101T090000Z-phone-aaaa.md", "---\nkind: sidecar\n---\nAcme whiteboard\n")
        self.write("inbox/plain.txt", "Acme in a text file\n")

        found = [hit.path for hit in search(self.store, "acme").hits]

        self.assertEqual(found, ["inbox/20261101T090000Z-phone-aaaa.md", "inbox/plain.txt"])

    def test_an_evicted_photo_is_not_listed_because_a_search_would_skip_it_anyway(self) -> None:
        self.write("inbox/20261101T090000Z-phone-aaaa.heic", "photo bytes")
        self.write("inbox/20261101T090000Z-phone-aaaa.md", "---\nkind: sidecar\n---\nAcme whiteboard\n")
        self.write("corpus/2026/08/a.md", "Acme\n")
        self.evict("inbox/20261101T090000Z-phone-aaaa.heic")
        self.evict("corpus/2026/08")

        result = search(self.store, "acme")

        self.assertEqual(result.evicted, ["corpus/2026/08"])
        self.assertEqual([hit.path for hit in result.hits], ["inbox/20261101T090000Z-phone-aaaa.md"])

    def test_bytes_that_are_no_utf8_do_not_stop_the_search(self) -> None:
        (self.root / "inbox").mkdir()
        (self.root / "inbox" / "a.md").write_bytes(b"caf\xe9 with Dana\n")

        self.assertEqual([hit.line for hit in search(self.store, "dana").hits], [1])

    def test_an_evicted_folder_is_listed_as_the_folder_and_the_rest_is_still_searched(self) -> None:
        self.write("corpus/2026/08/a.md", "Dana\n")
        self.write("corpus/2026/09/b.md", "Dana\n")
        self.evict("corpus/2026/08")

        result = search(self.store, "dana")

        self.assertEqual([hit.path for hit in result.hits], ["corpus/2026/09/b.md"])
        self.assertEqual(result.evicted, ["corpus/2026/08"])

    def test_a_file_evicted_between_the_check_and_the_read_is_listed_not_read(self) -> None:
        """Covers: B6"""
        self.write("inbox/a.md", "Dana\n")
        self.write("inbox/b.md", "Dana\n")
        real_read = self.store.read_bytes

        def read_bytes(relative: str) -> bytes:
            if relative == "inbox/a.md":
                raise EvictedFileError(relative)
            return real_read(relative)

        with mock.patch.object(self.store, "read_bytes", read_bytes):
            result = search(self.store, "dana")

        self.assertEqual([hit.path for hit in result.hits], ["inbox/b.md"])
        self.assertEqual(result.evicted, ["inbox/a.md"])

    def test_a_file_that_cannot_be_read_is_listed_apart_with_its_reason(self) -> None:
        self.write("inbox/a.md", "Dana\n")
        self.write("inbox/b.md", "Dana\n")
        real_read = self.store.read_bytes

        def read_bytes(relative: str) -> bytes:
            if relative == "inbox/a.md":
                raise StoreReadError("inbox/a.md could not be read: permission denied")
            return real_read(relative)

        with mock.patch.object(self.store, "read_bytes", read_bytes):
            result = search(self.store, "dana")

        self.assertEqual([hit.path for hit in result.hits], ["inbox/b.md"])
        self.assertEqual([item.path for item in result.unreadable], ["inbox/a.md"])
        self.assertIn("permission denied", result.unreadable[0].reason)

    def test_a_file_moved_away_during_the_search_is_skipped(self) -> None:
        self.write("inbox/a.md", "Dana\n")
        self.write("inbox/b.md", "Dana\n")
        real_read = self.store.read_bytes

        def read_bytes(relative: str) -> bytes:
            if relative == "inbox/a.md":
                raise FileNotFoundError(relative)
            return real_read(relative)

        with mock.patch.object(self.store, "read_bytes", read_bytes):
            result = search(self.store, "dana")

        self.assertEqual([hit.path for hit in result.hits], ["inbox/b.md"])
        self.assertEqual((result.evicted, result.unreadable), ([], []))

    def test_an_empty_store_has_no_hits_and_nothing_left_out(self) -> None:
        result = search(self.store, "dana")

        self.assertEqual((result.hits, result.evicted, result.unreadable), ([], [], []))

    def test_an_empty_term_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            search(self.store, "  ")

    def test_the_fetch_command_quotes_a_path_with_spaces(self) -> None:
        self.write("inbox/plan for Acme.md", "Acme\n")
        self.evict("inbox/plan for Acme.md")

        result = search(self.store, "acme")

        self.assertEqual(result.fetch_commands(), ["m2b store fetch 'inbox/plan for Acme.md'"])


class SearchOrderTest(SearchFixture):
    def paths_found(self) -> list[str]:
        return [hit.path for hit in search(self.store, "dana").hits]

    def test_hits_come_from_memory_then_the_archive_then_the_inbox(self) -> None:
        """Covers: B142"""
        self.write("inbox/20261109T080000Z-cli-aaaa.md", "Dana called\n")
        self.write("corpus/2026/10/20261012T081500Z-cli-bbbb.md", "Dana likes old maps.\n")
        self.write("memory/dana.md", "# Dana\n")

        self.assertEqual(
            self.paths_found(),
            ["memory/dana.md", "corpus/2026/10/20261012T081500Z-cli-bbbb.md", "inbox/20261109T080000Z-cli-aaaa.md"],
        )

    def test_the_distillate_comes_before_the_fact_files_and_those_come_by_name(self) -> None:
        """Covers: B142"""
        for name in ("dana.md", "MEMORY.md", "Acme.md", "2026-plans.md", "alex.md", "old/MEMORY.md"):
            self.write(f"memory/{name}", "Dana\n")

        self.assertEqual(
            self.paths_found(),
            [
                "memory/MEMORY.md",
                "memory/2026-plans.md",
                "memory/Acme.md",
                "memory/alex.md",
                "memory/dana.md",
                "memory/old/MEMORY.md",
            ],
        )

    def test_in_the_archive_and_the_inbox_the_newest_note_comes_first_by_the_time_in_its_name(self) -> None:
        """Covers: B142"""
        newest_first = [
            "corpus/2026/11/20261103T120001Z-cli-dddd.md",
            "corpus/2026/11/20261103T120000Z-cli-aaaa.md",
            "corpus/2026/11/20261103T120000Z-phone-bbbb.md",
            "corpus/2026/10/20261012T081500Z-cli-eeee.md",
            "corpus/2025/12/20251224T180000Z-cli-cccc.md",
            "inbox/20261109T070000Z-cli-ffff.md",
            "inbox/20261108T070000Z-cli-9999.md",
        ]
        for position, relative in enumerate(newest_first):
            self.write(relative, "Dana\n")
            # A synced folder gives a file the time it arrived: here the newest note changed first.
            changed = 1_700_000_000 + position * 86_400
            os.utime(self.root / relative, (changed, changed))

        self.assertEqual(self.paths_found(), newest_first)

    def test_the_time_in_the_name_decides_not_the_month_folder_a_note_lies_in(self) -> None:
        """Covers: B142"""
        self.write("corpus/2026/11/20261031T233000Z-cli-aaaa.md", "Dana\n")
        self.write("corpus/2026/10/20261031T234500Z-cli-bbbb.md", "Dana\n")

        self.assertEqual(
            self.paths_found(),
            ["corpus/2026/10/20261031T234500Z-cli-bbbb.md", "corpus/2026/11/20261031T233000Z-cli-aaaa.md"],
        )

    def test_a_months_journal_comes_after_the_notes_of_its_month_and_before_older_notes(self) -> None:
        """Covers: B142"""
        self.write("corpus/2026/10/202610-done.md", "- write to Dana\n")
        self.write("corpus/2026/10/20261031T220000Z-cli-bbbb.md", "Dana\n")
        self.write("corpus/2026/11/202611-done.md", "- call Dana\n")
        self.write("corpus/2026/11/20261101T000500Z-cli-aaaa.md", "Dana\n")
        self.write("corpus/2026/11/20261101T000000Z-cli-cccc.md", "Dana\n")

        self.assertEqual(
            self.paths_found(),
            [
                "corpus/2026/11/20261101T000500Z-cli-aaaa.md",
                "corpus/2026/11/20261101T000000Z-cli-cccc.md",
                "corpus/2026/11/202611-done.md",
                "corpus/2026/10/20261031T220000Z-cli-bbbb.md",
                "corpus/2026/10/202610-done.md",
            ],
        )

    def test_a_file_without_a_time_in_its_name_comes_after_every_dated_one_by_path(self) -> None:
        """Covers: B142"""
        for relative in (
            "corpus/2026/11/readme.md",
            "corpus/0000/01/000001-done.md",
            "corpus/2019/01/20190105T070000Z-cli-bbbb.md",
            "corpus/1969/07/19690720T201700Z-cli-dddd.md",
            "inbox/shopping list.md",
            "inbox/Notes.txt",
            "inbox/20261340T250000Z-cli-cccc.md",
            "inbox/20261109T070000Z-cli-aaaa 2.md",
            "inbox/20261109T070000Z-cli-aaaa.md",
        ):
            self.write(relative, "Dana\n")

        self.assertEqual(
            self.paths_found(),
            [
                "corpus/2019/01/20190105T070000Z-cli-bbbb.md",
                "corpus/1969/07/19690720T201700Z-cli-dddd.md",
                "corpus/0000/01/000001-done.md",
                "corpus/2026/11/readme.md",
                "inbox/20261109T070000Z-cli-aaaa.md",
                "inbox/20261109T070000Z-cli-aaaa 2.md",
                "inbox/20261340T250000Z-cli-cccc.md",
                "inbox/Notes.txt",
                "inbox/shopping list.md",
            ],
        )

    def test_the_hits_of_one_file_stay_together_in_line_order(self) -> None:
        """Covers: B142"""
        self.write("inbox/20261109T070000Z-cli-aaaa.md", "Dana called\nno name here\nDana again\n")
        self.write("memory/dana.md", "# Dana\nBirthday: 3 March\nDana likes old maps.\n")

        self.assertEqual(
            [(hit.path, hit.line) for hit in search(self.store, "dana").hits],
            [
                ("memory/dana.md", 1),
                ("memory/dana.md", 3),
                ("inbox/20261109T070000Z-cli-aaaa.md", 1),
                ("inbox/20261109T070000Z-cli-aaaa.md", 3),
            ],
        )

    def test_the_files_left_out_are_listed_as_they_were_read_not_in_the_order_of_the_hits(self) -> None:
        for relative in ("inbox/a.md", "inbox/b.md", "corpus/2026/11/c.md", "corpus/2026/11/d.md", "memory/e.md"):
            self.write(relative, "Dana\n")
        self.write("memory/f.md", "Dana\n")
        for relative in ("inbox/a.md", "corpus/2026/11/c.md", "memory/e.md"):
            self.evict(relative)
        real_read = self.store.read_bytes

        def read_bytes(relative: str) -> bytes:
            if relative in ("inbox/b.md", "corpus/2026/11/d.md"):
                raise StoreReadError(f"{relative} could not be read: permission denied")
            return real_read(relative)

        with mock.patch.object(self.store, "read_bytes", read_bytes):
            result = search(self.store, "dana")

        self.assertEqual([hit.path for hit in result.hits], ["memory/f.md"])
        self.assertEqual(result.evicted, ["corpus/2026/11/c.md", "inbox/a.md", "memory/e.md"])
        self.assertEqual([item.path for item in result.unreadable], ["inbox/b.md", "corpus/2026/11/d.md"])


class SearchCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        base = Path(self._temp.name)
        self.home = base / "home"
        self.store_root = base / "sb-test-store"
        self.store_root.mkdir()
        self.environ = {"HOME": str(base / "user-home"), "M2B_HOME": str(self.home)}
        self.eviction = FakeEviction()

    def set_up(self) -> None:
        machine.save_machine_config(
            paths.MachinePaths(self.home),
            {"version": 1, "machine_id": "sb-test-m1", "store": {"backend": "folder", "path": str(self.store_root)}},
        )

    def write(self, relative: str, text: str) -> None:
        target = self.store_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

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

    def test_hits_print_as_path_line_and_text(self) -> None:
        self.set_up()
        self.write("memory/dana.md", "# Dana\nBirthday: 3 March\n")

        code, out, err = self.run_command("search", "birthday")

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(out, "memory/dana.md:2: Birthday: 3 March\n")

    def test_hits_print_curated_first_then_the_archive_and_the_inbox_newest_first(self) -> None:
        """Covers: B142"""
        self.set_up()
        self.write("inbox/20261109T080000Z-cli-aaaa.md", "Dana called\n")
        self.write("corpus/2026/10/20261012T081500Z-cli-bbbb.md", "Dana likes old maps.\n")
        self.write("corpus/2026/11/20261103T120000Z-cli-cccc.md", "Dana moved to Lisbon.\n")
        self.write("memory/dana.md", "# Dana\n")
        in_order = [
            "memory/dana.md",
            "corpus/2026/11/20261103T120000Z-cli-cccc.md",
            "corpus/2026/10/20261012T081500Z-cli-bbbb.md",
            "inbox/20261109T080000Z-cli-aaaa.md",
        ]

        _, text, _ = self.run_command("search", "dana")
        _, answer, _ = self.run_command("search", "--json", "dana")

        self.assertEqual([line.split(":")[0] for line in text.splitlines()], in_order)
        self.assertEqual([hit["path"] for hit in json.loads(answer)["hits"]], in_order)

    def test_a_hit_prints_without_the_characters_that_draw_nothing(self) -> None:
        """Covers: B143"""
        self.set_up()
        coder = "\U0001f469‍\U0001f4bb"
        self.write("memory/dana.md", f"Dana​ likes\U000e0041 old­ maps️ ‮{coder}\n")

        _, text, _ = self.run_command("search", "dana")
        _, answer, _ = self.run_command("search", "--json", "dana")

        self.assertEqual(text, f"memory/dana.md:1: Dana likes old maps {coder}\n")
        self.assertEqual(
            json.loads(answer)["hits"], [{"path": "memory/dana.md", "line": 1, "text": f"Dana likes old maps {coder}"}]
        )

    def test_a_character_that_draws_nothing_in_a_file_name_is_written_out(self) -> None:
        """Covers: B143"""
        self.set_up()
        self.write("inbox/da​na.md", "Dana called\n")
        self.write("inbox/ki‍m.md", "Dana wrote\n")
        self.eviction.evicted.add(self.store_root / "inbox/ki‍m.md")
        fetch = "m2b store fetch 'inbox/ki<U+200D>m.md'"

        _, text, _ = self.run_command("search", "dana")
        _, answer, _ = self.run_command("search", "--json", "dana")

        self.assertEqual(text.splitlines()[0], "inbox/da<U+200B>na.md:1: Dana called")
        self.assertEqual(text.splitlines()[-1], f"  {fetch}")
        data = json.loads(answer)
        self.assertEqual(data["hits"], [{"path": "inbox/da<U+200B>na.md", "line": 1, "text": "Dana called"}])
        self.assertEqual(data["evicted"], [{"path": "inbox/ki<U+200D>m.md", "fetch": fetch}])

    def test_why_a_file_could_not_be_read_is_said_without_a_character_that_draws_nothing(self) -> None:
        """Covers: B143"""
        self.set_up()
        self.write("inbox/da​na.md", "Dana called\n")

        def unreadable(store: Any, relative: str) -> bytes:
            raise StoreReadError(f"{relative} could not be read: permission denied")

        with mock.patch("m2b.store.folder.FolderStore.read_bytes", unreadable):
            _, text, _ = self.run_command("search", "dana")
            _, answer, _ = self.run_command("search", "--json", "dana")

        reason = "inbox/da<U+200B>na.md could not be read: permission denied"
        self.assertEqual(text.splitlines()[-1], f"  {reason}")
        self.assertEqual(json.loads(answer)["unreadable"], [{"path": "inbox/da<U+200B>na.md", "reason": reason}])

    def test_several_words_are_searched_as_one_phrase(self) -> None:
        """Covers: B68"""
        self.set_up()
        self.write("inbox/a.md", "old maps\nmaps, old ones\n")

        code, out, _ = self.run_command("search", "old", "maps")

        self.assertEqual((code, out), (cli.EXIT_OK, "inbox/a.md:1: old maps\n"))

    def test_any_searches_each_term_on_its_own(self) -> None:
        """Covers: B68"""
        self.set_up()
        self.write("inbox/a.md", "old maps\nalte Karten\nmaps, old ones\n")

        code, out, _ = self.run_command("search", "--any", "--", "old maps", "alte Karten")

        self.assertEqual((code, out), (cli.EXIT_OK, "inbox/a.md:1: old maps\ninbox/a.md:2: alte Karten\n"))

    def test_no_hits_for_several_terms_names_each_of_them(self) -> None:
        self.set_up()
        self.write("inbox/a.md", "Alex\n")

        code, out, _ = self.run_command("search", "--any", "dana", "Dani")

        self.assertEqual((code, out), (cli.EXIT_OK, "No hits for 'dana' or 'Dani'.\n"))

    def test_no_hits_is_said_in_words_never_as_empty_output(self) -> None:
        self.set_up()
        self.write("inbox/a.md", "Alex\n")

        code, out, _ = self.run_command("search", "dana")

        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("No hits", out)

    def test_evicted_files_are_listed_with_the_command_that_fetches_them(self) -> None:
        """Covers: B6"""
        self.set_up()
        self.write("corpus/2026/09/a.md", "Dana\n")
        self.eviction.evicted.add(self.store_root / "corpus/2026/09/a.md")

        code, out, _ = self.run_command("search", "dana")

        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("No hits in the files that could be searched", out)
        self.assertIn("m2b store fetch corpus/2026/09/a.md", out)

    def test_json_carries_hits_evicted_files_and_unreadable_files(self) -> None:
        self.set_up()
        self.write("inbox/a.md", "Dana\n")
        self.write("inbox/b.md", "Dana\n")
        self.eviction.evicted.add(self.store_root / "inbox/b.md")

        code, out, err = self.run_command("search", "--json", "--word", "dana")

        self.assertEqual(code, cli.EXIT_OK, err)
        data: Any = json.loads(out)
        self.assertEqual(
            data,
            {
                "terms": ["dana"],
                "whole_words": True,
                "hits": [{"path": "inbox/a.md", "line": 1, "text": "Dana"}],
                "evicted": [{"path": "inbox/b.md", "fetch": "m2b store fetch inbox/b.md"}],
                "unreadable": [],
            },
        )

    def test_json_lists_each_term_searched(self) -> None:
        self.set_up()

        for arguments, terms in ((("old", "maps"), ["old maps"]), (("--any", "old", "maps"), ["old", "maps"])):
            with self.subTest(arguments=arguments):
                code, out, err = self.run_command("search", "--json", *arguments)
                self.assertEqual(code, cli.EXIT_OK, err)
                self.assertEqual(json.loads(out)["terms"], terms)

    def test_without_a_store_set_up_it_exits_2_and_a_missing_store_folder_3_never_an_empty_list(self) -> None:
        code, out, err = self.run_command("search", "dana")
        self.assertEqual((code, out), (cli.EXIT_USAGE, ""), err)

        self.set_up()
        self.store_root.rmdir()
        code, out, err = self.run_command("search", "--json", "dana")
        self.assertEqual((code, out), (cli.EXIT_UNREACHABLE, ""), err)

    def test_a_store_folder_that_cannot_be_listed_exits_3(self) -> None:
        self.set_up()
        self.write("inbox/a.md", "Dana\n")

        with mock.patch(
            "m2b.store.base.Store.scan", side_effect=StoreReadError("the store could not be listed: permission denied")
        ):
            code, out, err = self.run_command("search", "dana")

        self.assertEqual((code, out), (cli.EXIT_UNREACHABLE, ""))
        self.assertIn("permission denied", err)

    def test_a_term_after_a_double_dash_may_start_with_a_dash(self) -> None:
        self.set_up()
        self.write("inbox/a.md", "use --force with care\n")

        code, out, err = self.run_command("search", "--json", "--", "--force")

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual([hit["line"] for hit in json.loads(out)["hits"]], [1])

    def test_an_empty_term_is_a_usage_error(self) -> None:
        self.set_up()

        code, _, err = self.run_command("search", " ")

        self.assertEqual(code, cli.EXIT_USAGE, err)


class SearchSkillTest(unittest.TestCase):
    """Structure only: the policy prose lives once, in the skill (X15)."""

    skill = Path(__file__).resolve().parents[1] / "skills" / "search" / "SKILL.md"

    def frontmatter(self) -> dict[str, str]:
        text = self.skill.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        block = text.split("\n---\n", 1)[0].split("\n")[1:]
        return dict(line.split(": ", 1) for line in block if ": " in line)

    def test_the_skill_may_only_run_the_search_command(self) -> None:
        """Checks the skill's structure, not its prose."""
        fields = self.frontmatter()

        self.assertEqual(fields["name"], "search")
        self.assertEqual(fields["allowed-tools"], "Bash(m2b search *)")
        self.assertTrue(fields["description"])

    def test_the_skill_searches_with_json_and_names_the_fetch_command(self) -> None:
        body = self.skill.read_text(encoding="utf-8")

        self.assertIn("m2b search --json -- ", body)
        self.assertIn("m2b search --json --any -- ", body)
        self.assertIn("m2b store fetch", body)


if __name__ == "__main__":
    unittest.main()
