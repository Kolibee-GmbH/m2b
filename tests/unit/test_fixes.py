"""A fix the owner keeps for a file Claude reads: kept in the store, applied by a session in its place."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from m2b import cli, fixes, paths
from m2b.config import machine
from m2b.fixes import APPLIED, DONE, DROPPED, GONE, WAITING, WAITS, Fix, FixRefusedError
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard

PORTAL = "github.com/acme/portal"
OLD_LINE = "- Run the whole proof before every commit."
NEW_WORDING = "- Run the checks the change touches; the whole proof only before a release."
WHY = "The whole proof takes twenty minutes and a small change does not need it."


def portal_fix(**changed: object) -> Fix:
    given: dict[str, object] = {
        "path": "CLAUDE.md",
        "repositories": (PORTAL,),
        "machine": None,
        "line": OLD_LINE,
        "wording": NEW_WORDING,
        "why": WHY,
        "kept": "2026-11-20",
    }
    given.update(changed)
    return fixes.new_fix(**given)  # type: ignore[arg-type]


class StoreFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="sb-test-fixes-")
        self.addCleanup(self._temp.cleanup)
        self.base = Path(self._temp.name)
        self.root = self.base / "sb-test-store"
        self.root.mkdir()
        self.store = FolderStore(self.root, self.base / "machine-tmp", DatalessGuard(False))

    def fix_files(self) -> list[str]:
        folder = self.root / fixes.FOLDER
        return sorted(path.name for path in folder.iterdir()) if folder.is_dir() else []


class KeepTest(StoreFixture):
    def test_a_kept_fix_is_one_new_file_named_by_what_it_changes(self) -> None:
        """Covers: B248"""
        fix = portal_fix()

        self.assertTrue(fixes.keep(self.store, fix))

        self.assertRegex(fix.name, r"\Afix-[0-9a-f]{12}\Z")
        self.assertEqual(self.fix_files(), [f"{fix.name}.json"])
        [kept] = fixes.read_all(self.store)
        self.assertEqual((kept.fix, kept.state), (fix, WAITING))

    def test_the_same_fix_kept_twice_stays_one_file(self) -> None:
        """Covers: B248"""
        self.assertTrue(fixes.keep(self.store, portal_fix()))
        self.assertFalse(fixes.keep(self.store, portal_fix(why="Said again.", kept="2026-11-21")))

        self.assertEqual(len(self.fix_files()), 1)

    def test_a_fix_without_wording_or_with_a_line_that_is_two_is_refused(self) -> None:
        """Covers: B248"""
        for changed in ({"wording": "  "}, {"line": "one\ntwo"}, {"why": ""}, {"kept": "today"}):
            with self.subTest(changed=changed), self.assertRaises(FixRefusedError):
                portal_fix(**changed)

    def test_a_path_out_of_its_folder_or_spelled_another_way_is_refused(self) -> None:
        """Covers: B248"""
        for path in ("../CLAUDE.md", "/etc/hosts", "docs//rules.md", "./CLAUDE.md", "docs/.", "a\\b", "CLAUDE.md\x00"):
            with self.subTest(path=path), self.assertRaises(FixRefusedError):
                portal_fix(path=path)
        for path in ("~/.claude/.", "~/.claude/../.ssh/config", "~/.claude/rules\x00.md", "~/notes.md"):
            with self.subTest(path=path), self.assertRaises(FixRefusedError):
                portal_fix(path=path, repositories=(), machine="sb-test-m1")

    def test_a_file_in_the_fixes_folder_that_is_no_fix_is_left_out(self) -> None:
        """Covers: B248"""
        fixes.keep(self.store, portal_fix())
        (self.root / fixes.FOLDER / "notes.txt").write_text("hello", encoding="utf-8")
        (self.root / fixes.FOLDER / "fix-0123456789ab.json").write_text("{not json", encoding="utf-8")

        self.assertEqual([kept.fix.name for kept in fixes.read_all(self.store)], [portal_fix().name])


class SettleTest(StoreFixture):
    def test_done_and_dropped_each_add_an_empty_file_beside_the_fix(self) -> None:
        """Covers: B250"""
        first, second, third = portal_fix(), portal_fix(path="docs/rules.md"), portal_fix(path="AGENTS.md")
        for fix in (first, second, third):
            fixes.keep(self.store, fix)

        fixes.settle(self.store, first.name, DONE)
        fixes.settle(self.store, second.name, DROPPED)

        states = {kept.fix.name: kept.state for kept in fixes.read_all(self.store)}
        self.assertEqual(states, {first.name: DONE, second.name: DROPPED, third.name: WAITING})
        self.assertEqual((self.root / fixes.FOLDER / f"{first.name}.done").read_bytes(), b"")

    def test_where_two_clients_settled_one_fix_differently_done_stands(self) -> None:
        """Covers: B250"""
        fix = portal_fix()
        fixes.keep(self.store, fix)
        for state in (DROPPED, DONE):
            (self.root / fixes.FOLDER / f"{fix.name}.{state}").write_bytes(b"")

        self.assertEqual(fixes.find(self.store, fix.name).state, DONE)

    def test_a_fix_settled_once_keeps_that_state(self) -> None:
        """Covers: B250"""
        fix = portal_fix()
        fixes.keep(self.store, fix)

        self.assertTrue(fixes.settle(self.store, fix.name, DONE))
        self.assertFalse(fixes.settle(self.store, fix.name, DROPPED))

        self.assertEqual(fixes.find(self.store, fix.name).state, DONE)

    def test_an_unknown_name_is_refused(self) -> None:
        """Covers: B250"""
        with self.assertRaises(fixes.UnknownFixError):
            fixes.settle(self.store, "fix-0123456789ab", DONE)
        with self.assertRaises(FixRefusedError):
            fixes.find(self.store, "../state")


class WaitingTest(StoreFixture):
    def test_a_repository_fix_waits_in_a_clone_of_that_repository_only(self) -> None:
        """Covers: B249"""
        fix = portal_fix()
        fixes.keep(self.store, fix)
        kept = fixes.read_all(self.store)

        self.assertEqual(fixes.waiting_for(kept, {PORTAL}, "sb-test-m1"), [fix])
        self.assertEqual(fixes.waiting_for(kept, {"github.com/acme/shop"}, "sb-test-m1"), [])

    def test_a_home_fix_waits_in_every_session_of_the_machine_it_was_kept_on(self) -> None:
        """Covers: B249"""
        fix = portal_fix(path="~/.claude/CLAUDE.md", repositories=(), machine="sb-test-m1")
        fixes.keep(self.store, fix)
        kept = fixes.read_all(self.store)

        self.assertEqual(fixes.waiting_for(kept, set(), "sb-test-m1"), [fix])
        self.assertEqual(fixes.waiting_for(kept, set(), "sb-test-m2"), [])

    def test_a_settled_fix_waits_no_longer(self) -> None:
        """Covers: B250"""
        fix = portal_fix()
        fixes.keep(self.store, fix)
        fixes.settle(self.store, fix.name, DONE)

        self.assertEqual(fixes.waiting_for(fixes.read_all(self.store), {PORTAL}, "sb-test-m1"), [])


class LookTest(StoreFixture):
    def file(self, text: str | None) -> Path:
        target = self.base / "clone" / "CLAUDE.md"
        target.parent.mkdir(exist_ok=True)
        if text is not None:
            target.write_text(text, encoding="utf-8")
        return target

    def test_a_file_that_still_holds_the_line_waits(self) -> None:
        """Covers: B249"""
        self.assertEqual(fixes.look(portal_fix(), self.file(f"# Portal\n{OLD_LINE}\n")), WAITS)

    def test_a_file_that_holds_the_new_wording_instead_is_applied(self) -> None:
        """Covers: B249"""
        self.assertEqual(fixes.look(portal_fix(), self.file(f"# Portal\n{NEW_WORDING}\n")), APPLIED)

    def test_a_path_the_file_system_refuses_holds_nothing(self) -> None:
        """Covers: B249"""
        self.assertEqual(fixes.look(portal_fix(), self.base / "clone" / "CLAUDE\x00.md"), GONE)

    def test_a_file_without_the_line_and_without_the_wording_is_gone(self) -> None:
        """Covers: B249"""
        self.assertEqual(fixes.look(portal_fix(), self.file("# Portal\n- Something else.\n")), GONE)
        self.assertEqual(fixes.look(portal_fix(), self.file(None)), GONE)

    def test_a_fix_that_only_adds_waits_until_its_wording_is_there(self) -> None:
        """Covers: B249"""
        adding = portal_fix(line=None)

        self.assertEqual(fixes.look(adding, self.file(None)), WAITS)
        self.assertEqual(fixes.look(adding, self.file("# Portal\n")), WAITS)
        self.assertEqual(fixes.look(adding, self.file(f"# Portal\n{NEW_WORDING}\n")), APPLIED)

    def test_white_space_at_the_ends_of_lines_does_not_hide_a_line(self) -> None:
        """Covers: B249"""
        self.assertEqual(fixes.look(portal_fix(), self.file(f"# Portal\r\n{OLD_LINE}  \r\n")), WAITS)


class CommandFixture(StoreFixture):
    def setUp(self) -> None:
        super().setUp()
        self.m2b_home = self.base / "m2b-home"
        self.machine = paths.MachinePaths(self.m2b_home)
        self.user_home = self.base / "user-home"
        self.user_home.mkdir()
        machine.save_machine_config(
            self.machine,
            {"version": 1, "machine_id": "sb-test-m1", "store": {"backend": "folder", "path": str(self.root)}},
        )
        self.environ = {
            "HOME": str(self.user_home),
            "M2B_HOME": str(self.m2b_home),
            "PATH": os.environ.get("PATH", ""),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
        }

    def clone(self, *remotes: str) -> Path:
        folder = self.base / "code" / "acme-portal"
        (folder / "docs").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(folder)], check=True, env=self.environ, capture_output=True)
        for number, remote in enumerate(remotes):
            subprocess.run(
                ["git", "-C", str(folder), "remote", "add", f"r{number}", remote],
                check=True,
                env=self.environ,
                capture_output=True,
            )
        (folder / "CLAUDE.md").write_text(f"# Portal\n{OLD_LINE}\n", encoding="utf-8")
        return folder

    def m2b(self, *arguments: str, stdin: str = "") -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        given = io.TextIOWrapper(io.BytesIO(stdin.encode("utf-8")), encoding="utf-8")
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), mock.patch("sys.stdin", given):
            code = cli.main(list(arguments), self.environ)
        return code, out.getvalue(), err.getvalue()

    def add(self, **given: object) -> tuple[int, str, str]:
        return self.m2b("fix", "add", stdin=json.dumps(given))


class AddCommandTest(CommandFixture):
    def test_a_fix_for_a_file_in_a_clone_is_kept_by_the_address_of_its_remote(self) -> None:
        """Covers: B248"""
        clone = self.clone("git@github.com:acme/portal.git")

        code, out, err = self.add(file=str(clone / "CLAUDE.md"), line=OLD_LINE, wording=NEW_WORDING, why=WHY)

        self.assertEqual((code, err), (0, ""))
        [kept] = fixes.read_all(self.store)
        self.assertEqual((kept.fix.path, kept.fix.repositories, kept.fix.machine), ("CLAUDE.md", (PORTAL,), None))
        self.assertEqual((kept.fix.line, kept.fix.wording, kept.fix.why), (OLD_LINE, NEW_WORDING, WHY))
        self.assertIn(kept.fix.name, out)
        self.assertIn(f"CLAUDE.md in {PORTAL}", out)

    def test_a_file_in_a_folder_of_the_clone_keeps_its_path_in_the_repository(self) -> None:
        """Covers: B248"""
        clone = self.clone("https://github.com/acme/portal")
        (clone / "docs" / "rules.md").write_text("- Old rule.\n", encoding="utf-8")

        code, _, _ = self.add(file=str(clone / "docs" / "rules.md"), line="- Old rule.", wording="- New.", why=WHY)

        self.assertEqual(code, 0)
        self.assertEqual(fixes.read_all(self.store)[0].fix.path, "docs/rules.md")

    def test_a_fix_for_the_global_claude_md_is_kept_for_this_machine(self) -> None:
        """Covers: B248"""
        claude = self.user_home / ".claude"
        claude.mkdir()
        (claude / "CLAUDE.md").write_text(f"{OLD_LINE}\n", encoding="utf-8")

        code, out, _ = self.add(file=str(claude / "CLAUDE.md"), line=OLD_LINE, wording=NEW_WORDING, why=WHY)

        self.assertEqual(code, 0)
        [kept] = fixes.read_all(self.store)
        self.assertEqual(
            (kept.fix.path, kept.fix.repositories, kept.fix.machine), ("~/.claude/CLAUDE.md", (), "sb-test-m1")
        )
        self.assertIn("~/.claude/CLAUDE.md", out)

    def test_a_file_in_a_folder_without_a_remote_is_refused_and_nothing_is_kept(self) -> None:
        """Covers: B248"""
        clone = self.clone()

        code, _, err = self.add(file=str(clone / "CLAUDE.md"), line=OLD_LINE, wording=NEW_WORDING, why=WHY)

        self.assertEqual(code, 2)
        self.assertIn("remote", err)
        self.assertEqual(self.fix_files(), [])

    def test_a_line_the_file_does_not_hold_is_refused(self) -> None:
        """Covers: B248"""
        clone = self.clone("git@github.com:acme/portal.git")

        code, _, err = self.add(file=str(clone / "CLAUDE.md"), line="- Not there.", wording=NEW_WORDING, why=WHY)

        self.assertEqual(code, 2)
        self.assertIn("does not hold", err)
        self.assertEqual(self.fix_files(), [])

    def test_the_claude_folder_itself_is_no_file_to_fix(self) -> None:
        """Covers: B248"""
        (self.user_home / ".claude").mkdir()

        code, _, _ = self.add(file=str(self.user_home / ".claude"), wording=NEW_WORDING, why=WHY)

        self.assertEqual((code, self.fix_files()), (2, []))

    def test_input_that_is_no_json_object_is_refused(self) -> None:
        """Covers: B248"""
        for given in ("", "[1]", "{not json"):
            with self.subTest(given=given):
                code, _, _ = self.m2b("fix", "add", stdin=given)
                self.assertEqual(code, 2)


class ShowListDoneTest(CommandFixture):
    def kept(self) -> Fix:
        fix = portal_fix()
        fixes.keep(self.store, fix)
        return fix

    def test_show_prints_the_fix_whole_by_its_name(self) -> None:
        """Covers: B249"""
        fix = self.kept()

        code, out, _ = self.m2b("fix", "show", fix.name)

        self.assertEqual(code, 0)
        for said in (f"CLAUDE.md in {PORTAL}", WHY, OLD_LINE, NEW_WORDING):
            self.assertIn(said, out)

    def test_done_and_drop_settle_a_fix_and_list_says_so(self) -> None:
        """Covers: B250"""
        fix = self.kept()

        self.assertEqual(self.m2b("fix", "done", fix.name)[0], 0)
        code, out, _ = self.m2b("fix", "list", "--json")

        self.assertEqual(code, 0)
        [listed] = json.loads(out)["fixes"]
        self.assertEqual((listed["name"], listed["state"]), (fix.name, DONE))

    def test_done_of_an_unknown_fix_ends_with_a_problem(self) -> None:
        """Covers: B250"""
        self.assertEqual(self.m2b("fix", "done", "fix-0123456789ab")[0], 1)

    def test_the_commands_write_no_file_outside_the_store(self) -> None:
        """Covers: B250"""
        clone = self.clone("git@github.com:acme/portal.git")
        before = (clone / "CLAUDE.md").read_bytes()

        self.add(file=str(clone / "CLAUDE.md"), line=OLD_LINE, wording=NEW_WORDING, why=WHY)
        [kept] = fixes.read_all(self.store)
        self.m2b("fix", "show", kept.fix.name)
        self.m2b("fix", "done", kept.fix.name)

        self.assertEqual((clone / "CLAUDE.md").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
