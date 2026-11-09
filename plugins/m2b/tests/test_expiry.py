"""Memory lines that are due: facts past their day, current items nothing has touched for a month."""

from __future__ import annotations

import contextlib
import datetime
import io
import json
import tempfile
import unittest
from pathlib import Path

from m2b import cli, paths
from m2b.config import machine
from m2b.expiry import DueFact, QuietCurrent, due, undated
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard
from store_contract import FakeEviction

TODAY = datetime.date(2026, 11, 20)
INDEX = """# Memory

## Facts

- Sam brings plywood for the shed roof on 14 November (sam.md)
- Dana's birthday is on 3 March (dana.md)

## Current

- Rebuilding the garden shed roof (since 2026-11-03)
- Planning the trip to Porto (since 2026-10-02)
- Reading Dune
"""


class DueTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.root = base / "sb-test-store"
        self.eviction = FakeEviction()
        self.store = FolderStore(self.root, base / "machine-tmp", DatalessGuard(True, lstat=self.eviction.lstat))
        self.write("memory/MEMORY.md", INDEX)
        self.write("memory/dana.md", "# Dana\n\n- Birthday on 3 March.\n")

    def write(self, relative: str, text: str) -> None:
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def test_a_fact_past_its_until_is_due_and_one_on_its_day_is_not(self) -> None:
        """Covers: B41"""
        self.write("memory/sam.md", "---\nuntil: 2026-11-14\n---\n# Sam\n")
        self.write("memory/plumber.md", "---\nuntil: 2026-11-20\n---\n# Plumber\n")

        found = due(self.store, TODAY)

        self.assertEqual(found.facts, [DueFact("memory/sam.md", "2026-11-14")])

    def test_a_current_item_untouched_for_more_than_30_days_is_quiet(self) -> None:
        """Covers: B41"""
        found = due(self.store, TODAY)

        self.assertEqual(found.current, [QuietCurrent("Planning the trip to Porto", "2026-10-02")])

    def test_exactly_30_days_is_not_quiet_yet(self) -> None:
        found = due(self.store, datetime.date(2026, 11, 1))

        self.assertEqual(found.current, [])

    def test_lines_without_a_date_or_with_a_wrong_one_are_never_due(self) -> None:
        self.write("memory/sam.md", "---\nuntil: next spring\n---\n# Sam\n")
        self.write("memory/robin.md", "# Robin\n")

        found = due(self.store, TODAY)

        self.assertEqual(found.facts, [])

    def test_an_evicted_fact_file_is_listed_apart_and_never_read(self) -> None:
        self.write("memory/sam.md", "---\nuntil: 2026-11-14\n---\n# Sam\n")
        self.eviction.evicted.add(self.root / "memory" / "sam.md")

        found = due(self.store, TODAY)

        self.assertEqual((found.facts, found.evicted), ([], ["memory/sam.md"]))

    def test_a_store_without_a_distillate_has_nothing_due(self) -> None:
        (self.root / "memory" / "MEMORY.md").unlink()

        found = due(self.store, TODAY)

        self.assertEqual((found.facts, found.current), ([], []))


class UndatedTest(DueTest):
    def test_lists_fact_files_without_until_and_current_items_without_since(self) -> None:
        """Covers: B43"""
        self.write("memory/sam.md", "---\nuntil: 2026-11-14\n---\n# Sam\n")
        self.write("memory/people/robin.md", "# Robin\n")

        found = undated(self.store)

        self.assertEqual((found.facts, found.current), (["memory/dana.md"], ["Reading Dune"]))

    def test_a_wrong_date_is_left_to_lint_and_an_evicted_file_is_listed_apart(self) -> None:
        self.write("memory/sam.md", "---\nuntil: next spring\n---\n# Sam\n")
        self.write("memory/MEMORY.md", "# Memory\n\n## Facts\n\n## Current\n\n- Reading Dune (since soon)\n")
        self.eviction.evicted.add(self.root / "memory" / "dana.md")

        found = undated(self.store)

        self.assertEqual((found.facts, found.current, found.evicted), ([], [], ["memory/dana.md"]))


class RefreshDueCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.home = base / "home"
        self.store_root = base / "sb-test-store"
        (self.store_root / "memory").mkdir(parents=True)
        (self.store_root / "memory" / "MEMORY.md").write_text(INDEX, encoding="utf-8")
        (self.store_root / "memory" / "sam.md").write_text("---\nuntil: 2026-11-14\n---\n# Sam\n", encoding="utf-8")
        self.environ = {"HOME": str(base / "user-home"), "M2B_HOME": str(self.home)}
        machine.save_machine_config(
            paths.MachinePaths(self.home),
            {"version": 1, "machine_id": "sb-test-m1", "store": {"backend": "folder", "path": str(self.store_root)}},
        )

    def run_command(self, *arguments: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(arguments), self.environ)
        return code, out.getvalue(), err.getvalue()

    def test_json_names_the_due_facts_and_quiet_items_for_the_refresh_skill(self) -> None:
        code, out, err = self.run_command("refresh", "due", "--json", "--today", "2026-11-20")

        self.assertEqual(code, cli.EXIT_OK, err)
        data = json.loads(out)
        self.assertEqual(data["today"], "2026-11-20")
        self.assertEqual(data["store"], str(self.store_root))
        self.assertEqual(data["facts"], [{"file": "sam.md", "path": "memory/sam.md", "until": "2026-11-14"}])
        self.assertEqual(data["current"], [{"text": "Planning the trip to Porto", "since": "2026-10-02"}])
        self.assertEqual(data["evicted"], [])

    def test_json_names_no_undated_lines_outside_a_refresh_all_run(self) -> None:
        _, out, _ = self.run_command("refresh", "due", "--json", "--today", "2026-11-20")

        data = json.loads(out)
        self.assertEqual((data["refresh_all"], "undated" in data), (False, False))

    def test_json_in_a_refresh_all_run_names_the_undated_lines_too(self) -> None:
        """Covers: B43"""
        batch = {"facts": ["memory/dana.md", "memory/sam.md"], "current": ["Reading Dune", "Gone meanwhile"]}
        self.environ["M2B_REFRESH_ALL"] = json.dumps(batch)
        (self.store_root / "memory" / "dana.md").write_text("# Dana\n", encoding="utf-8")

        _, out, _ = self.run_command("refresh", "due", "--json", "--today", "2026-11-20")

        data = json.loads(out)
        self.assertTrue(data["refresh_all"])
        self.assertEqual(
            data["undated"],
            {"facts": [{"file": "dana.md", "path": "memory/dana.md"}], "current": ["Reading Dune"]},
        )

    def test_a_variable_that_holds_no_batch_is_an_error(self) -> None:
        self.environ["M2B_REFRESH_ALL"] = "1"

        code, _, err = self.run_command("refresh", "due", "--json")

        self.assertNotEqual(code, cli.EXIT_OK)
        self.assertIn("no backfill batch", err)

    def test_text_says_when_nothing_is_due(self) -> None:
        code, out, _ = self.run_command("refresh", "due", "--today", "2026-11-14")

        self.assertEqual((code, out.splitlines()[0]), (cli.EXIT_OK, "No fact is past its day."))


if __name__ == "__main__":
    unittest.main()
