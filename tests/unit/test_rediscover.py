"""Rediscover: old corpus notes back into view, never a quiet one, always with its reason."""

from __future__ import annotations

import contextlib
import datetime
import io
import json
import random
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from locations import PLUGIN_ROOT
from m2b import cli, paths
from m2b.config import machine
from m2b.rediscover import FROM_PERIOD, RANDOM, SHARES_A_WORD, Months, rediscover
from m2b.store.base import StoreReadError
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard
from store_contract import FakeEviction

TODAY = datetime.date(2026, 11, 7)
MEMORY = (
    "# Memory\n\n## Facts\n\n- Dana likes old maps (dana.md)\n\n## Current\n\n- Building the garden shed with Alex\n"
)


class RediscoverFixture(unittest.TestCase):
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
        target.write_text(text, encoding="utf-8")

    def note(self, relative: str, body: str, *extra: str) -> None:
        lines = ["---", "created: 2026-05-12T08:15:00+02:00", "source: cli", *extra, "---"]
        self.write(relative, "\n".join(lines) + "\n" + body)

    def run_it(self, seed: int = 1, count: int = 3) -> Any:
        return rediscover(self.store, TODAY, random.Random(seed), count=count)


class RediscoverTest(RediscoverFixture):
    def test_a_random_pick_comes_from_a_past_month_and_says_so(self) -> None:
        """Covers: B5"""
        self.note("corpus/2026/05/20260512T061500Z-cli-a1b2.md", "Dana recommended a bakery in Porto.\n")
        self.note("corpus/2026/11/20261103T090000Z-cli-c3d4.md", "This month: a new note.\n")

        (pick,) = self.run_it().picks

        self.assertEqual(pick.path, "corpus/2026/05/20260512T061500Z-cli-a1b2.md")
        self.assertEqual(pick.why, RANDOM)
        self.assertEqual(pick.reason, "random pick from May 2026")
        self.assertEqual(pick.text, "Dana recommended a bakery in Porto.")

    def test_a_note_sharing_a_word_with_the_current_section_says_which_word_and_item(self) -> None:
        """Covers: B5"""
        self.write("memory/MEMORY.md", MEMORY)
        self.note("corpus/2026/03/20260310T100000Z-cli-aaaa.md", "The shed roof needs larch boards.\n")

        picks = self.run_it().picks

        shared = [pick for pick in picks if pick.why == SHARES_A_WORD]
        self.assertEqual([pick.path for pick in shared], ["corpus/2026/03/20260310T100000Z-cli-aaaa.md"])
        self.assertEqual(shared[0].word, "shed")
        self.assertEqual(shared[0].reason, "shares 'shed' with the current item 'Building the garden shed with Alex'")

    def test_a_quiet_note_is_never_returned(self) -> None:
        """Covers: B4"""
        self.write("memory/MEMORY.md", MEMORY)
        self.note("corpus/2026/03/20260310T100000Z-cli-aaaa.md", "The shed roof needs larch boards.\n", "quiet: true")

        for seed in range(20):
            with self.subTest(seed=seed):
                self.assertEqual(self.run_it(seed).picks, [])

    def test_the_word_quiet_in_the_body_is_no_rest_marker(self) -> None:
        """Covers: B4"""
        self.note("corpus/2026/03/20260310T100000Z-cli-aaaa.md", "quiet: true\nA quiet afternoon by the lake.\n")

        self.assertEqual(len(self.run_it().picks), 1)

    def test_files_with_a_kind_and_files_that_are_no_notes_are_skipped(self) -> None:
        self.note("corpus/2026/04/202604-done.md", "- Paid the shed invoice\n", "kind: journal")
        self.note("corpus/2026/04/20260402T090000Z-phone-bbbb.md", "Whiteboard photo\n", "kind: sidecar")
        self.note("corpus/2026/04/20260403T090000Z-worklog-cccc.md", "Worked on Acme\n", "kind: worklog")
        self.write("corpus/2026/04/20260402T090000Z-phone-bbbb.heic", "photo bytes")

        self.assertEqual(self.run_it().picks, [])

    def test_only_months_before_the_current_one_count(self) -> None:
        self.write("memory/MEMORY.md", MEMORY)
        self.note("corpus/2026/11/20261102T090000Z-cli-dddd.md", "Bought screws for the shed.\n")

        self.assertEqual(self.run_it().picks, [])

    def test_the_count_bounds_the_picks_and_no_note_comes_twice(self) -> None:
        self.write("memory/MEMORY.md", MEMORY)
        for month in range(1, 10):
            self.note(f"corpus/2026/{month:02d}/2026{month:02d}10T100000Z-cli-{month:04x}.md", "The shed again.\n")

        for count in (1, 2, 3):
            with self.subTest(count=count):
                picks = self.run_it(count=count).picks
                self.assertEqual(len(picks), count)
                self.assertEqual(len({pick.path for pick in picks}), count)

    def test_the_same_seed_gives_the_same_picks(self) -> None:
        for month in range(1, 10):
            self.note(f"corpus/2026/{month:02d}/2026{month:02d}10T100000Z-cli-{month:04x}.md", f"Note {month}\n")

        self.assertEqual(self.run_it(seed=7).picks, self.run_it(seed=7).picks)

    def test_common_short_words_are_no_shared_word(self) -> None:
        self.write("memory/MEMORY.md", "## Current\n\n- Talk with the bank about it\n")
        self.note("corpus/2026/03/20260310T100000Z-cli-aaaa.md", "Lunch with the team, then a walk.\n")

        picks = self.run_it().picks

        self.assertEqual([pick.why for pick in picks], [RANDOM])

    def test_the_curator_s_trailer_is_not_part_of_the_text(self) -> None:
        self.note(
            "corpus/2026/03/20260310T100000Z-cli-aaaa.md",
            "Alex lends us the ladder.\n<!-- m2b:curation -->\nfiled: alex.md\n",
            "curated: true",
        )

        (pick,) = self.run_it().picks

        self.assertEqual(pick.text, "Alex lends us the ladder.")

    def test_a_long_note_is_cut_and_says_so(self) -> None:
        self.note("corpus/2026/03/20260310T100000Z-cli-aaaa.md", "word " * 1000)

        (pick,) = self.run_it().picks

        self.assertTrue(pick.truncated)
        self.assertLessEqual(len(pick.text), 2000)

    def test_evicted_notes_are_never_read_and_listed_apart(self) -> None:
        self.write("memory/MEMORY.md", MEMORY)
        self.note("corpus/2026/03/20260310T100000Z-cli-aaaa.md", "The shed roof.\n")
        self.note("corpus/2026/04/20260410T100000Z-cli-bbbb.md", "The shed door.\n")
        self.evict("corpus/2026/04/20260410T100000Z-cli-bbbb.md")

        result = self.run_it()

        self.assertNotIn("corpus/2026/04/20260410T100000Z-cli-bbbb.md", [pick.path for pick in result.picks])
        self.assertEqual(result.evicted, ["corpus/2026/04/20260410T100000Z-cli-bbbb.md"])

    def test_an_evicted_memory_index_is_listed_and_the_random_pick_still_comes(self) -> None:
        self.write("memory/MEMORY.md", MEMORY)
        self.note("corpus/2026/03/20260310T100000Z-cli-aaaa.md", "The shed roof.\n")
        self.evict("memory/MEMORY.md")

        result = self.run_it()

        self.assertEqual([pick.why for pick in result.picks], [RANDOM])
        self.assertEqual(result.evicted, ["memory/MEMORY.md"])

    def test_a_memory_index_with_a_broken_byte_still_gives_its_current_items(self) -> None:
        (self.root / "memory").mkdir()
        (self.root / "memory" / "MEMORY.md").write_bytes(b"## Current\n\n- Building the shed caf\xe9\n")
        self.note("corpus/2026/03/20260310T100000Z-cli-aaaa.md", "The shed roof.\n")

        picks = self.run_it().picks

        self.assertEqual([pick.why for pick in picks], [SHARES_A_WORD])

    def test_only_evicted_paths_that_can_hold_an_old_note_are_listed(self) -> None:
        for relative in (
            "corpus/2026/04/20260410T100000Z-cli-bbbb.md",
            "corpus/2026/11/20261102T090000Z-cli-cccc.md",
            "corpus/2026/04/202604-done.md",
            "corpus/2026/03/20260310T100000Z-cli-aaaa.md",
            "corpus/2026/10/20261010T100000Z-cli-dddd.md",
            "corpus/2025/12/20251210T100000Z-cli-eeee.md",
        ):
            self.note(relative, "A note.\n")
        for evicted in (
            "corpus/2026/04/20260410T100000Z-cli-bbbb.md",
            "corpus/2026/11/20261102T090000Z-cli-cccc.md",
            "corpus/2026/04/202604-done.md",
            "corpus/2026/03",
            "corpus/2026/10",
            "corpus/2025",
        ):
            self.evict(evicted)

        result = self.run_it()

        self.assertEqual(
            result.evicted,
            ["corpus/2025", "corpus/2026/03", "corpus/2026/04/20260410T100000Z-cli-bbbb.md", "corpus/2026/10"],
        )

    def test_only_unreadable_files_that_can_hold_an_old_note_are_listed(self) -> None:
        for relative in (
            "corpus/2026/04/20260410T100000Z-cli-bbbb.md",
            "corpus/2026/11/20261102T090000Z-cli-cccc.md",
            "corpus/2026/04/202604-done.md",
        ):
            self.note(relative, "A note.\n")
        real_read = self.store.read_bytes

        def read_bytes(relative: str) -> bytes:
            if relative.startswith("corpus/"):
                raise StoreReadError(f"{relative} could not be read: permission denied")
            return real_read(relative)

        with mock.patch.object(self.store, "read_bytes", read_bytes):
            result = self.run_it()

        self.assertEqual([item.path for item in result.unreadable], ["corpus/2026/04/20260410T100000Z-cli-bbbb.md"])

    def test_an_evicted_corpus_is_listed_as_the_corpus(self) -> None:
        self.note("corpus/2026/03/20260310T100000Z-cli-aaaa.md", "A note.\n")
        self.evict("corpus")

        self.assertEqual(self.run_it().evicted, ["corpus"])

    def test_a_memory_index_that_cannot_be_read_is_listed_with_its_reason(self) -> None:
        self.write("memory/MEMORY.md", MEMORY)
        self.note("corpus/2026/03/20260310T100000Z-cli-aaaa.md", "The shed roof.\n")
        real_read = self.store.read_bytes

        def read_bytes(relative: str) -> bytes:
            if relative == "memory/MEMORY.md":
                raise StoreReadError("memory/MEMORY.md could not be read: permission denied")
            return real_read(relative)

        with mock.patch.object(self.store, "read_bytes", read_bytes):
            result = self.run_it()

        self.assertEqual([pick.why for pick in result.picks], [RANDOM])
        self.assertEqual([item.path for item in result.unreadable], ["memory/MEMORY.md"])

    def test_an_empty_corpus_gives_no_picks(self) -> None:
        result = self.run_it()

        self.assertEqual((result.picks, result.evicted), ([], []))

    def evict(self, relative: str) -> None:
        self.eviction.evicted.add(self.root / relative)


class PeriodTest(RediscoverFixture):
    """Notes from the months asked for ("what did I note last spring?"), each saying which month."""

    def run_period(self, text: str, seed: int = 1, count: int = 3) -> Any:
        return rediscover(self.store, TODAY, random.Random(seed), count=count, months=Months.parse(text))

    def test_a_month_brings_notes_from_that_month_only_and_says_so(self) -> None:
        self.note("corpus/2026/05/20260512T061500Z-cli-a1b2.md", "Dana recommended a bakery in Porto.\n")
        self.note("corpus/2026/03/20260310T100000Z-cli-aaaa.md", "The shed roof needs larch boards.\n")

        (pick,) = self.run_period("2026-05").picks

        self.assertEqual(pick.path, "corpus/2026/05/20260512T061500Z-cli-a1b2.md")
        self.assertEqual((pick.why, pick.reason), (FROM_PERIOD, "from May 2026"))

    def test_a_range_holds_its_first_and_last_month(self) -> None:
        for month in ("02", "03", "04", "05", "06"):
            self.note(f"corpus/2026/{month}/2026{month}10T100000Z-cli-aaaa.md", f"A note from month {month}.\n")

        picks = self.run_period("2026-03..2026-05", count=5).picks

        self.assertEqual(sorted(pick.path[12:14] for pick in picks), ["03", "04", "05"])

    def test_the_current_month_counts_when_it_is_asked_for(self) -> None:
        self.note("corpus/2026/11/20261103T090000Z-cli-c3d4.md", "This month: a new note.\n")

        self.assertEqual(len(self.run_period("2026-11").picks), 1)

    def test_a_period_does_not_look_for_shared_words(self) -> None:
        self.write("memory/MEMORY.md", MEMORY)
        self.note("corpus/2026/03/20260310T100000Z-cli-aaaa.md", "The shed roof needs larch boards.\n")

        self.assertEqual([pick.why for pick in self.run_period("2026-03").picks], [FROM_PERIOD])

    def test_only_evicted_paths_inside_the_period_are_listed(self) -> None:
        for relative in ("corpus/2026/03/20260310T100000Z-cli-aaaa.md", "corpus/2026/05/20260512T061500Z-cli-a1b2.md"):
            self.note(relative, "A note.\n")
        for evicted in ("corpus/2026/03", "corpus/2026/05", "corpus/2025"):
            self.eviction.evicted.add(self.root / evicted)

        self.assertEqual(self.run_period("2026-05").evicted, ["corpus/2026/05"])

    def test_a_period_is_a_month_or_two_months_in_order(self) -> None:
        self.assertEqual(Months.parse("2026-05"), Months((2026, 5), (2026, 5)))
        self.assertEqual(Months.parse("2025-12..2026-02"), Months((2025, 12), (2026, 2)))
        for text in ("2026-13", "2026-5", "May 2026", "2026-05..2026-03", "2026-05..", ""):
            with self.subTest(text=text), self.assertRaises(ValueError):
                Months.parse(text)


class RediscoverCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        base = Path(self._temp.name)
        self.home = base / "home"
        self.store_root = base / "sb-test-store"
        self.store_root.mkdir()
        self.environ = {"HOME": str(base / "user-home"), "M2B_HOME": str(self.home)}

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
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(arguments), self.environ)
        return code, out.getvalue(), err.getvalue()

    def test_json_carries_each_pick_with_its_reason_and_text(self) -> None:
        self.set_up()
        self.write("corpus/2026/05/20260512T061500Z-cli-a1b2.md", "---\nsource: cli\n---\nDana likes old maps.\n")

        code, out, err = self.run_command("rediscover", "--json", "--today", "2026-11-07")

        self.assertEqual(code, cli.EXIT_OK, err)
        data = json.loads(out)
        self.assertEqual(
            data["picks"],
            [
                {
                    "path": "corpus/2026/05/20260512T061500Z-cli-a1b2.md",
                    "why": "random",
                    "reason": "random pick from May 2026",
                    "word": None,
                    "current_item": None,
                    "text": "Dana likes old maps.",
                    "truncated": False,
                }
            ],
        )
        self.assertEqual(data["evicted"], [])

    def test_text_names_the_reason_before_the_note(self) -> None:
        self.set_up()
        self.write("corpus/2026/05/20260512T061500Z-cli-a1b2.md", "Dana likes old maps.\n")

        code, out, _ = self.run_command("rediscover", "--today", "2026-11-07")

        self.assertEqual(code, cli.EXIT_OK)
        self.assertEqual(
            out, "corpus/2026/05/20260512T061500Z-cli-a1b2.md (random pick from May 2026)\n  Dana likes old maps.\n"
        )

    def test_nothing_to_bring_back_is_said_in_words(self) -> None:
        self.set_up()

        code, out, _ = self.run_command("rediscover")

        self.assertEqual((code, out), (cli.EXIT_OK, "No old notes to bring back.\n"))

    def test_with_notes_left_unread_the_text_never_says_there_is_nothing(self) -> None:
        self.set_up()
        self.write("corpus/2026/05/20260512T061500Z-cli-a1b2.md", "Dana likes old maps.\n")
        eviction = FakeEviction()
        eviction.evicted.add(self.store_root / "corpus/2026/05")
        guard = DatalessGuard(True, lstat=eviction.lstat)

        with mock.patch("m2b.store.factory.guard_for_platform", return_value=guard):
            code, out, _ = self.run_command("rediscover", "--today", "2026-11-07")

        self.assertEqual(code, cli.EXIT_OK)
        self.assertTrue(out.startswith("No old notes to bring back among the notes that could be read.\n"), out)
        self.assertIn("m2b store fetch corpus/2026/05", out)

    def test_without_a_store_set_up_it_exits_2_and_a_missing_store_folder_3(self) -> None:
        code, out, _ = self.run_command("rediscover")
        self.assertEqual((code, out), (cli.EXIT_USAGE, ""))

        self.set_up()
        self.store_root.rmdir()
        code, out, _ = self.run_command("rediscover", "--json")
        self.assertEqual((code, out), (cli.EXIT_UNREACHABLE, ""))

    def test_month_brings_back_notes_from_that_month(self) -> None:
        self.set_up()
        self.write("corpus/2026/05/20260512T061500Z-cli-a1b2.md", "Dana likes old maps.\n")
        self.write("corpus/2026/03/20260310T100000Z-cli-aaaa.md", "The shed roof needs larch boards.\n")

        code, out, err = self.run_command("rediscover", "--json", "--month", "2026-05")

        self.assertEqual(code, cli.EXIT_OK, err)
        [pick] = json.loads(out)["picks"]
        self.assertEqual((pick["why"], pick["reason"]), ("period", "from May 2026"))

    def test_nothing_in_the_period_is_said_with_the_period(self) -> None:
        self.set_up()

        code, out, _ = self.run_command("rediscover", "--month", "2026-03..2026-05")

        self.assertEqual((code, out), (cli.EXIT_OK, "No notes from March 2026 to May 2026.\n"))

    def test_a_month_that_is_no_month_is_a_usage_error(self) -> None:
        self.set_up()

        for month in ("2026-13", ""):
            with self.subTest(month=month):
                code, _, err = self.run_command("rediscover", "--month", month)

                self.assertEqual(code, cli.EXIT_USAGE)
                self.assertIn("--month", err)

    def test_a_count_below_one_is_a_usage_error(self) -> None:
        self.set_up()

        code, _, err = self.run_command("rediscover", "--count", "0")

        self.assertEqual(code, cli.EXIT_USAGE, err)

    def test_the_random_source_is_the_system_one_without_a_seed(self) -> None:
        self.set_up()
        self.write("corpus/2026/05/20260512T061500Z-cli-a1b2.md", "Dana likes old maps.\n")

        with mock.patch("m2b.commands.rediscover.random.SystemRandom") as system_random:
            system_random.return_value = random.Random(3)
            code, _, _ = self.run_command("rediscover", "--today", "2026-11-07")

        self.assertEqual(code, cli.EXIT_OK)
        system_random.assert_called_once_with()


class RediscoverSkillTest(unittest.TestCase):
    """Structure only: the policy prose lives once, in the skill (X15)."""

    skill = PLUGIN_ROOT / "skills" / "rediscover" / "SKILL.md"

    def frontmatter(self) -> dict[str, str]:
        text = self.skill.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        block = text.split("\n---\n", 1)[0].split("\n")[1:]
        return dict(line.split(": ", 1) for line in block if ": " in line)

    def test_the_skill_may_only_run_the_rediscover_command(self) -> None:
        """Checks the skill's structure, not its prose."""
        fields = self.frontmatter()

        self.assertEqual(fields["name"], "rediscover")
        self.assertEqual(fields["allowed-tools"], "Bash(m2b rediscover *)")
        self.assertTrue(fields["description"])

    def test_the_skill_reads_the_json(self) -> None:
        self.assertIn("m2b rediscover --json", self.skill.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
