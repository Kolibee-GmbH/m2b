"""Where a project's repository lies on this machine, shown below the topic line that names it."""

from __future__ import annotations

import datetime
import shutil
import tempfile
import unittest
from pathlib import Path

from m2b import repository_places, session_remotes

NOW = datetime.datetime(2026, 11, 7, 9, 0, tzinfo=datetime.timezone.utc)
DAY = datetime.timedelta(days=1)
LINE = "- Repository: github.com/acme/portal (acme-portal.md)"
BLOCK = (
    "### Acme portal (Acme portal, acme-portal)\n"
    f"{LINE}\n"
    "- Login moves to the customer's identity provider in March → docs/records/014-login.md (acme-portal.md)\n"
)


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.notes = self.base / "state" / session_remotes.NOTES_FOLDER

    def folder(self, *parts: str) -> Path:
        folder = self.base.joinpath(*parts)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def note(self, folder: Path, *remotes: str, when: datetime.datetime = NOW, top: Path | None = None) -> None:
        session_remotes.note(
            self.notes,
            str(folder),
            frozenset(remotes),
            when,
            lambda path, text: path.write_text(text, encoding="utf-8"),
            top=None if top is None else str(top),
        )

    def shown(self, text: str = BLOCK) -> str:
        return repository_places.with_places(text, self.notes)


class WithPlacesTest(Fixture):
    def test_a_noted_clone_is_named_below_the_repository_line(self) -> None:
        """Covers: B247"""
        clone = self.folder("code", "acme-portal")
        self.note(clone, "git@github.com:acme/portal.git")

        self.assertEqual(self.shown().split("\n")[1:3], [LINE, f"  on this machine: {clone}"])

    def test_a_repository_no_folder_was_noted_with_is_not_cloned_here(self) -> None:
        """Covers: B247"""
        self.note(self.folder("code", "shed"), "https://github.com/alex/shed.git")

        self.assertEqual(self.shown().split("\n")[2], "  not cloned on this machine")

    def test_of_a_clone_and_its_worktrees_the_one_seen_last_that_still_exists_is_named(self) -> None:
        """Covers: B247"""
        clone = self.folder("code", "acme-portal")
        worktree = self.folder("worktrees", "acme-portal", "login")
        removed = self.base / "worktrees" / "acme-portal" / "old"
        self.note(clone, "https://github.com/acme/portal", when=NOW)
        self.note(worktree, "https://github.com/acme/portal", when=NOW + DAY)
        self.note(removed, "https://github.com/acme/portal", when=NOW + 2 * DAY)

        self.assertEqual(self.shown().split("\n")[2], f"  on this machine: {worktree}")

    def test_a_remote_with_user_password_port_or_another_spelling_matches_the_address(self) -> None:
        """Covers: B247"""
        for remote in (
            "https://alex:ghp_Zx81kQ4t@github.com/acme/portal.git",
            "ssh://git@github.com:22/acme/portal.git",
            "git@github.com:acme/portal",
            "HTTPS://GitHub.com/Acme/Portal/",
        ):
            with self.subTest(remote=remote):
                shutil.rmtree(self.notes, ignore_errors=True)
                clone = self.folder("code", f"clone-{len(remote)}")
                self.note(clone, remote)

                self.assertEqual(self.shown().split("\n")[2], f"  on this machine: {clone}")

    def test_the_folder_named_is_the_top_of_the_repository_where_the_session_started_below_it(self) -> None:
        """Covers: B247"""
        top = self.folder("code", "acme-portal")
        below = self.folder("code", "acme-portal", "docs")
        self.note(below, "https://github.com/acme/portal.git", top=top)

        self.assertEqual(self.shown().split("\n")[2], f"  on this machine: {top}")

    def test_a_note_older_than_thirty_days_still_names_a_folder_that_is_there(self) -> None:
        """Covers: B247"""
        clone = self.folder("code", "acme-portal")
        self.note(clone, "https://github.com/acme/portal.git", when=NOW - 40 * DAY)

        self.assertEqual(self.shown().split("\n")[2], f"  on this machine: {clone}")

    def test_a_block_without_a_repository_line_and_a_missing_notes_folder_stay_as_they_are(self) -> None:
        """Covers: B247"""
        plain = "### Riverside Choir (Riverside Choir)\n- The choir meets on Wednesdays (choir.md)\n"

        self.assertEqual(self.shown(plain), plain)
        self.assertEqual(self.shown().split("\n")[2], "  not cloned on this machine")

    def test_a_folder_that_cannot_be_looked_at_counts_as_not_there(self) -> None:
        """Covers: B247"""
        guarded = self.folder("code", "guarded")
        clone = self.folder("code", "acme-portal")
        self.note(clone, "https://github.com/acme/portal.git", when=NOW)
        self.note(guarded, "https://github.com/acme/portal.git", when=NOW + DAY)

        def is_there(folder: Path) -> bool:
            if folder == guarded:
                raise PermissionError("Operation not permitted")
            return folder.is_dir()

        shown = repository_places.with_places(BLOCK, self.notes, is_there)

        self.assertEqual(shown.split("\n")[2], f"  on this machine: {clone}")

    def test_a_line_that_only_looks_like_a_repository_line_gets_nothing(self) -> None:
        """Covers: B247"""
        self.note(self.folder("code", "acme-portal"), "https://github.com/acme/portal.git")
        for line in (
            "- Repository github.com/acme/portal (acme-portal.md)",
            "- The repository: github.com/acme/portal (acme-portal.md)",
            "  - Repository: github.com/acme/portal (acme-portal.md)",
        ):
            with self.subTest(line=line):
                self.assertEqual(self.shown(f"{line}\n"), f"{line}\n")


if __name__ == "__main__":
    unittest.main()
