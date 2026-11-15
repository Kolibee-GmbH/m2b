from __future__ import annotations

import datetime
import tempfile
import unittest
from pathlib import Path

from m2b import folders_left_out, session_remotes
from m2b.config.machine import DistillateSettings
from m2b.folders_left_out import LeftOutRule

NOW = datetime.datetime(2026, 3, 4, 12, tzinfo=datetime.timezone.utc)
GLOBEX = "https://git.globex.example/globex-ag/portal.git"
OWN = "git@github.com:alex/shed.git"


class LeftOutRuleTest(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory(prefix="sb-test-left-out-")
        self.addCleanup(folder.cleanup)
        self.home = Path(folder.name).resolve()
        self.notes = self.home / "notes"
        self.remotes: dict[Path, frozenset[str] | None] = {}
        self.asked: list[Path] = []

    def ask(self, folder: Path) -> frozenset[str] | None:
        self.asked.append(folder)
        return self.remotes.get(folder)

    def rule(self, *named: Path, parts: tuple[str, ...] = (), no_distillate: tuple[Path, ...] = ()) -> LeftOutRule:
        by_remote = session_remotes.RemoteRule(parts, self.notes, NOW, self.ask)
        return LeftOutRule(named, DistillateSettings(skip_under=no_distillate), by_remote, self.home)

    def folder(self, name: str, remote: str | None = None, in_a_repository: bool = True) -> Path:
        """A folder that is there; git names ``remote`` for it, no remote, or cannot say."""
        path = self.home / name
        path.mkdir(parents=True)
        self.remotes[path] = (frozenset({remote}) if remote else frozenset()) if in_a_repository else None
        return path

    def test_a_folder_the_profile_names_and_one_below_it_are_left_out(self) -> None:
        customers = self.home / "customers"
        rule = self.rule(customers)
        self.assertEqual(rule.reason(str(customers)), folders_left_out.IN_A_FOLDER_LEFT_OUT)
        self.assertEqual(rule.reason(str(customers / "acme" / "docs")), folders_left_out.IN_A_FOLDER_LEFT_OUT)
        self.assertIsNone(rule.reason(str(self.home / "projects" / "shed")))
        self.assertEqual(self.asked, [])

    def test_a_folder_without_the_distillate_and_one_that_is_not_absolute_are_left_out(self) -> None:
        quiet = self.folder("quiet")
        rule = self.rule(no_distillate=(quiet,))
        self.assertEqual(rule.reason(str(quiet / "below")), folders_left_out.IN_A_FOLDER_LEFT_OUT)
        self.assertEqual(rule.reason("projects/shed"), folders_left_out.IN_A_FOLDER_LEFT_OUT)

    def test_a_folder_is_left_out_by_its_repository_and_also_when_nothing_is_known_of_it(self) -> None:
        portal, shed = self.folder("portal", GLOBEX), self.folder("shed", OWN)
        gone = self.folder("gone", in_a_repository=False)
        rule = self.rule(parts=("globex-ag/",))
        self.assertEqual(rule.reason(str(portal)), folders_left_out.OF_A_REPOSITORY_LEFT_OUT)
        self.assertIsNone(rule.reason(str(shed)))
        self.assertEqual(rule.reason(str(gone)), folders_left_out.OF_NO_KNOWN_REPOSITORY)

    def test_a_session_folder_is_compared_as_written_with_no_look_at_the_disk(self) -> None:
        customers = self.folder("customers")
        (self.home / "link").symlink_to(customers)
        rule = self.rule(customers)
        self.assertIsNone(rule.reason(str(self.home / "link" / "acme")))

    def test_a_path_in_a_folder_that_is_left_out_is_not_taken(self) -> None:
        customers = self.home / "customers"
        quiet = self.folder("quiet")
        rule = self.rule(customers, no_distillate=(quiet,))
        self.assertEqual(
            rule.reason_for_a_path(str(customers / "acme" / "contract.md")), folders_left_out.IN_A_FOLDER_LEFT_OUT
        )
        self.assertEqual(rule.reason_for_a_path(str(quiet / "notes.md")), folders_left_out.IN_A_FOLDER_LEFT_OUT)
        self.assertEqual(rule.reason_for_a_path("notes.md"), folders_left_out.IN_A_FOLDER_LEFT_OUT)
        self.assertIsNone(rule.reason_for_a_path(str(self.folder("projects/shed") / "notes.md")))

    def test_a_path_is_read_as_the_disk_has_it(self) -> None:
        """Covers: B176"""
        customers, shed = self.folder("customers"), self.folder("projects/shed")
        (customers / "acme").mkdir()
        (shed / "link").symlink_to(customers / "acme")
        rule = self.rule(customers)
        written = (
            f"{shed}/../../customers/acme/contract.md",
            f"{shed}/link/contract.md",
            f"{shed}/link/../secret.md",
            f"{shed}/link/..",
            f"/{customers}/acme/contract.md",
            f"{customers}/./acme/new/folder/x.md",
        )
        for path in written:
            with self.subTest(path=path):
                self.assertEqual(rule.reason_for_a_path(path), folders_left_out.IN_A_FOLDER_LEFT_OUT)

    def test_a_folder_named_in_other_case_is_the_folder_where_the_disk_takes_both_as_one(self) -> None:
        """Covers: B176"""
        customers = self.folder("customers")
        (customers / "acme").mkdir()
        if not (self.home / "CUSTOMERS").exists():
            self.skipTest("this file system tells names in other case apart")
        rule = self.rule(customers)
        self.assertEqual(
            rule.reason_for_a_path(str(self.home / "CUSTOMERS" / "acme" / "x.md")),
            folders_left_out.IN_A_FOLDER_LEFT_OUT,
        )

    def test_a_path_without_the_distillate_reached_through_a_link_is_not_taken(self) -> None:
        quiet, shed = self.folder("quiet"), self.folder("projects/shed")
        (shed / "link").symlink_to(quiet)
        rule = self.rule(no_distillate=(quiet,))
        self.assertEqual(rule.reason_for_a_path(f"{shed}/link/notes.md"), folders_left_out.IN_A_FOLDER_LEFT_OUT)

    def test_a_file_is_judged_by_the_repository_of_the_nearest_folder_that_is_there(self) -> None:
        portal, shed = self.folder("portal", GLOBEX), self.folder("shed", OWN)
        (portal / "contract.md").write_text("terms", encoding="utf-8")
        rule = self.rule(parts=("globex-ag/",))
        self.assertEqual(rule.reason_for_a_path(str(portal / "contract.md")), folders_left_out.OF_A_REPOSITORY_LEFT_OUT)
        self.assertEqual(
            rule.reason_for_a_path(str(portal / "src" / "new" / "module.py")), folders_left_out.OF_A_REPOSITORY_LEFT_OUT
        )
        self.assertIsNone(rule.reason_for_a_path(str(shed / "notes.md")))
        self.assertEqual(self.asked, [portal, shed])

    def test_a_path_in_no_repository_is_taken_and_one_git_cannot_say_anything_of_is_not(self) -> None:
        """Covers: B176"""
        downloads = self.folder("downloads")
        unknown = self.folder("unknown", in_a_repository=False)
        rule = self.rule(parts=("globex-ag/",))
        self.assertIsNone(rule.reason_for_a_path(str(downloads / "mail.txt")))
        self.assertEqual(rule.reason_for_a_path(str(unknown / "contract.md")), folders_left_out.OF_NO_KNOWN_REPOSITORY)

    def test_a_tilde_is_the_home_folder_of_the_machine_as_for_the_named_folders(self) -> None:
        rule = self.rule(self.home / "customers")
        self.assertEqual(rule.reason_for_a_path("~/customers/acme/contract.md"), folders_left_out.IN_A_FOLDER_LEFT_OUT)
        self.assertIsNone(rule.reason_for_a_path("~"))

    def test_a_path_that_cannot_be_looked_at_is_left_out_and_nothing_raises(self) -> None:
        """Covers: B176"""
        loop = self.home / "loop"
        loop.symlink_to(loop)
        rule = self.rule(self.home / "customers")
        locked = self.folder("locked")
        (locked / "inner").mkdir()
        locked.chmod(0)
        self.addCleanup(locked.chmod, 0o700)
        too_deep = "/a" * (folders_left_out.DEEPEST_PATH + 1)
        for path in (
            "~nosuchuser42/x",
            "/home/alex/a\x00b",
            f"{loop}/x",
            "",
            "/a" * 3000,
            too_deep,
            f"{locked}/inner/x.md",
        ):
            with self.subTest(path=path[:60]):
                self.assertEqual(rule.reason_for_a_path(path), folders_left_out.IN_A_FOLDER_LEFT_OUT)


if __name__ == "__main__":
    unittest.main()
