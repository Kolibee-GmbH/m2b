"""The documentation's own promises: a page for every add-on, and links that lead somewhere."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from m2b.addons import addon_names

from repo_tools import evals_page

REPO = Path(__file__).resolve().parents[3]
ADDONS_PAGE = REPO / "docs" / "addons.md"
ADDON_PAGES = REPO / "docs" / "addons"
# A Markdown link or image to a relative target, without its #anchor or title.
RELATIVE_LINK = re.compile(r"\]\((?!https?:|mailto:|#)<?([^)#\s>]+)>?(?:#[^)\s]*)?(?:\s+\"[^\"]*\")?\)")
# The same in HTML, as the README's header uses.
HTML_LINK = re.compile(r"(?:href|src)=\"(?!https?:|mailto:|#)([^\"#]+)")


def _documents() -> list[Path]:
    return [*REPO.glob("*.md"), *(REPO / "docs").rglob("*.md")]


def _relative_links(text: str) -> list[str]:
    return RELATIVE_LINK.findall(text) + HTML_LINK.findall(text)


class AddonsPageTest(unittest.TestCase):
    def test_every_addon_has_its_own_page_and_the_overview_links_it(self) -> None:
        overview = ADDONS_PAGE.read_text(encoding="utf-8")

        self.assertEqual(sorted(page.stem for page in ADDON_PAGES.glob("*.md")), sorted(addon_names()))
        self.assertEqual([name for name in addon_names() if f"](addons/{name}.md)" not in overview], [])

    def test_the_readme_links_the_page(self) -> None:
        readme = (REPO / "README.md").read_text(encoding="utf-8")

        self.assertTrue("](docs/addons.md)" in readme, "README.md does not link docs/addons.md")


class EvalsPageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.page = evals_page.PAGE.read_text(encoding="utf-8")
        self.cases = sorted(evals_page.suite_cases(evals_page.EVALS))

    def test_the_results_have_a_row_for_every_case_of_the_suite_and_no_other(self) -> None:
        results = self.page.partition(evals_page.BLOCK_START)[2].partition(evals_page.BLOCK_END)[0]

        self.assertEqual(re.findall(r"^\| `([a-z-]+)` \|", results, re.MULTILINE), self.cases)

    def test_the_page_says_what_every_case_asks(self) -> None:
        described = self.page.partition(evals_page.BLOCK_END)[2]

        self.assertEqual(sorted(re.findall(r"^\| `([a-z-]+)` \|", described, re.MULTILINE)), self.cases)

    def test_the_results_name_the_run_they_come_from(self) -> None:
        for fact in ("Day", "m2b", "Claude Code", "Model", "Runs"):
            with self.subTest(fact=fact):
                self.assertRegex(self.page, rf"(?m)^\| {fact} \| \S.* \|$")

    def test_the_readme_links_the_page(self) -> None:
        readme = (REPO / "README.md").read_text(encoding="utf-8")

        self.assertTrue("](docs/evals.md)" in readme, "README.md does not link docs/evals.md")


class LinkTest(unittest.TestCase):
    def test_every_relative_link_in_the_docs_names_a_file_that_exists(self) -> None:
        broken = [
            f"{document.relative_to(REPO)}: {target}"
            for document in _documents()
            for target in _relative_links(document.read_text(encoding="utf-8"))
            if not (document.parent / target).exists()
        ]

        self.assertEqual(broken, [])


if __name__ == "__main__":
    unittest.main()
