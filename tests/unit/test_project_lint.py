"""A project topic's lines with a path: shown relative to the clone, and kept right by lint."""

from __future__ import annotations

import datetime
import unittest
from pathlib import Path

from m2b import lint, repository_places, session_remotes
from m2b.notes.memory_index import split_topics
from test_lint import NOW, LintFixture

PORTAL_HEADING = "### Acme portal (Acme portal, portal)\n"
REPOSITORY = "- Repository: github.com/acme/portal (acme-portal.md)\n"
POINTER = "- Login moves to the customer's identity provider in March → docs/records/014-login.md (acme-portal.md)\n"
WITH_HEADING = "- Kim Lee at Acme signs off every release → CLAUDE.md, Releases (acme-portal.md)\n"
FACT_FILE = "# Acme portal\n\n- Repository: github.com/acme/portal\n"


class NotesFixture(LintFixture):
    def noted(self, clone: Path, when: datetime.datetime = NOW) -> Path:
        notes = self.root.parent / "state" / session_remotes.NOTES_FOLDER
        session_remotes.note(
            notes,
            str(clone),
            frozenset({"git@github.com:acme/portal.git"}),
            when,
            lambda path, text: path.write_text(text, encoding="utf-8"),
            top=str(clone),
        )
        return notes


class PlaceLineTest(NotesFixture):
    def test_a_topic_with_pointers_says_their_paths_lie_in_the_folder_shown(self) -> None:
        """Covers: B254"""
        clone = self.root.parent / "code" / "acme-portal"
        clone.mkdir(parents=True)
        notes = self.noted(clone)

        shown = repository_places.with_places(PORTAL_HEADING + REPOSITORY + POINTER, notes)

        self.assertIn(f"{REPOSITORY}  on this machine: {clone}; the paths after → lie in it\n{POINTER}", shown)

    def test_a_topic_without_pointers_keeps_the_plain_place_line(self) -> None:
        """Covers: B254"""
        clone = self.root.parent / "code" / "acme-portal"
        clone.mkdir(parents=True)

        shown = repository_places.with_places(PORTAL_HEADING + REPOSITORY, self.noted(clone))

        self.assertIn(f"{REPOSITORY}  on this machine: {clone}\n", shown)


class PointerLineTest(unittest.TestCase):
    def test_a_pointer_is_the_word_with_a_path_after_the_last_arrow(self) -> None:
        """Covers: B254"""
        for line, path in (
            (POINTER, "docs/records/014-login.md"),
            (WITH_HEADING, "CLAUDE.md"),
            ("- Old login → SSO is planned → docs/x.md (acme-portal.md)\n", "docs/x.md"),
        ):
            with self.subTest(line=line):
                found = repository_places.POINTER_LINE.match(line)
                assert found is not None
                self.assertEqual(found.group("path"), path)

    def test_a_fact_that_only_holds_an_arrow_points_nowhere(self) -> None:
        """Covers: B254"""
        for line in (
            "- The price goes from 10 → 12 CHF in March (acme-portal.md)\n",
            "- Moved from Jira → GitHub issues, since May (acme-portal.md)\n",
        ):
            with self.subTest(line=line):
                self.assertIsNone(repository_places.POINTER_LINE.match(line))


class ProjectLintTest(NotesFixture):
    def project(self, *lines: str) -> None:
        index = "# Memory\n\n## Facts\n\n- Dana's birthday is on 3 March (dana.md)\n\n" + PORTAL_HEADING
        self.write("memory/MEMORY.md", index + "".join(lines) + "\n## Current\n\n- Planning the trip\n")
        self.write("memory/acme-portal.md", FACT_FILE)

    def clone(self, *files: str) -> Path:
        folder = self.root.parent / "code" / "acme-portal"
        for name in files:
            (folder / name).parent.mkdir(parents=True, exist_ok=True)
            (folder / name).write_text("x\n", encoding="utf-8")
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def codes(self, findings: list[lint.Finding]) -> list[str]:
        return [finding.code for finding in findings]

    def test_a_pointer_whose_file_the_clone_lacks_is_reported_with_its_project_and_path(self) -> None:
        """Covers: B255"""
        self.project(REPOSITORY, POINTER, WITH_HEADING)
        notes = self.noted(self.clone("CLAUDE.md"))

        findings = self.findings(notes=notes, now=NOW)

        [missing] = [finding for finding in findings if finding.code == lint.POINTER_MISSING]
        self.assertEqual(missing.kind, lint.ACTION)
        self.assertIn("the topic Acme portal points to docs/records/014-login.md", missing.text)
        self.assertNotIn(str(self.root.parent), missing.text)

    def test_pointers_whose_files_are_there_are_no_finding(self) -> None:
        """Covers: B255"""
        self.project(REPOSITORY, POINTER, WITH_HEADING)
        notes = self.noted(self.clone("CLAUDE.md", "docs/records/014-login.md"))

        self.assertNotIn(lint.POINTER_MISSING, self.codes(self.findings(notes=notes, now=NOW)))

    def test_a_pointer_out_of_the_repository_is_reported_as_no_path_in_it(self) -> None:
        """Covers: B255"""
        self.project(REPOSITORY, "- The shared rules → ../other/CLAUDE.md (acme-portal.md)\n")
        notes = self.noted(self.clone())

        [finding] = [finding for finding in self.findings(notes=notes, now=NOW) if finding.code == lint.POINTER_PATH]
        self.assertIn("../other/CLAUDE.md", finding.text)

    def test_an_absolute_pointer_is_reported_as_no_path_in_the_repository(self) -> None:
        """Covers: B255"""
        self.project(REPOSITORY, "- The shared rules → /etc/rules.md (acme-portal.md)\n")
        notes = self.noted(self.clone())

        codes = self.codes(self.findings(notes=notes, now=NOW))

        self.assertIn(lint.POINTER_PATH, codes)
        self.assertNotIn(lint.POINTER_MISSING, codes)

    def test_a_project_not_cloned_on_this_machine_has_its_pointers_unchecked(self) -> None:
        """Covers: B255"""
        self.project(REPOSITORY, POINTER)
        notes = self.root.parent / "state" / session_remotes.NOTES_FOLDER
        notes.mkdir(parents=True)

        self.assertNotIn(lint.POINTER_MISSING, self.codes(self.findings(notes=notes, now=NOW)))

    def test_a_repository_no_folder_had_for_30_days_is_reported(self) -> None:
        """Covers: B256"""
        self.project(REPOSITORY, POINTER)
        notes = self.noted(self.clone("docs/records/014-login.md"), when=NOW - datetime.timedelta(days=31))

        [finding] = [finding for finding in self.findings(notes=notes, now=NOW) if finding.code == lint.PROJECT_UNSEEN]
        self.assertEqual(finding.kind, lint.INFO)
        self.assertIn("github.com/acme/portal", finding.text)
        self.assertIn("30 days", finding.text)

    def test_a_repository_a_folder_had_within_30_days_is_no_finding(self) -> None:
        """Covers: B256"""
        self.project(REPOSITORY, POINTER)
        notes = self.noted(self.clone("docs/records/014-login.md"), when=NOW - datetime.timedelta(days=29))

        self.assertNotIn(lint.PROJECT_UNSEEN, self.codes(self.findings(notes=notes, now=NOW)))

    def test_a_topic_that_passes_4_kb_with_the_place_line_is_reported(self) -> None:
        """Covers: B254"""
        clone = self.clone()
        notes = self.noted(clone)
        line = "- A decision about the portal that matters to other projects (acme-portal.md)\n"
        filler = line * ((4000 - len(PORTAL_HEADING + REPOSITORY)) // len(line))
        self.project(REPOSITORY, filler)
        # One more line, so the topic as the prompt hook brings it is 10 bytes short of 4 KB.
        [block] = split_topics((self.root / "memory" / "MEMORY.md").read_text(encoding="utf-8")).blocks
        last = 4096 - 10 - len(block.text.encode("utf-8"))
        self.project(REPOSITORY, filler, "- " + "y" * (last - len("-  (acme-portal.md)\n")) + " (acme-portal.md)\n")
        [block] = split_topics((self.root / "memory" / "MEMORY.md").read_text(encoding="utf-8")).blocks
        self.assertEqual(len(block.text.encode("utf-8")), 4096 - 10)

        without_notes = self.codes(self.findings(now=NOW))
        with_notes = self.codes(self.findings(notes=notes, now=NOW))

        self.assertNotIn("topic-size", without_notes)
        self.assertIn("topic-size", with_notes)

    def test_a_repository_line_with_a_character_that_draws_nothing_is_checked_as_the_hook_reads_it(self) -> None:
        """Covers: B255"""
        self.project(REPOSITORY.replace(")\n", ")\u200e\n"), POINTER)
        notes = self.noted(self.clone())

        self.assertIn(lint.POINTER_MISSING, self.codes(self.findings(notes=notes, now=NOW)))

    def test_without_notes_lint_checks_no_project(self) -> None:
        """Covers: B256"""
        self.project(REPOSITORY, POINTER)

        codes = self.codes(self.findings())

        self.assertNotIn(lint.POINTER_MISSING, codes)
        self.assertNotIn(lint.PROJECT_UNSEEN, codes)
