"""Checks that a test names every catalogued behavior (B and X IDs) in a ``Covers:`` line.

The catalog is a folder of parts, one Markdown file each, and an ID stands in one of them. The
part named like an add-on holds that add-on's rules: each needs a test in the add-on's own suite,
``tests/addons/<add-on>/``. A rule of any other part needs a test outside those suites: the core
is proven in a copy of the plugin without its add-ons, where their suites are gone.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from repo_tools import REPO_ROOT
from repo_tools.core_alone import ADDON_PARTS

BEHAVIOR_CATALOG = REPO_ROOT / "docs" / "behavior"
ADDON_NAMES = frozenset(addon.name for addon in ADDON_PARTS)

# X15 is a rule about the tests themselves, so a review checks it instead of a test.
NOT_TESTABLE = frozenset({"X15"})

TEST_FILE_SUFFIXES = frozenset({".py", ".json", ".ts", ".tsx", ".md"})

EXIT_COVERED = 0
EXIT_FINDINGS = 1
EXIT_BAD_CATALOG = 2

_ID_ROW = re.compile(r"^\|\s*([BX]\d+)\s*\|", re.MULTILINE)
_COVERS_LINE = re.compile(r"Covers:\s*([A-Z]\d+(?:\s*,\s*[A-Z]\d+)*)")
_ID = re.compile(r"[A-Z]\d+")
_ADDON_SUITES = ("tests", "addons")


class CatalogError(Exception):
    """The behavior catalog could not be read."""


@dataclass(frozen=True)
class CoverageReport:
    uncovered: list[str]
    # Named by a test, but by none of the suite its part asks for.
    outside_their_suite: list[str]
    unknown: dict[str, list[Path]]

    @property
    def has_findings(self) -> bool:
        return bool(self.uncovered or self.outside_their_suite or self.unknown)


def rule_ids(part_text: str) -> list[str]:
    """The IDs of the table rows of one part, in its order."""
    return _ID_ROW.findall(part_text)


def read_catalog(folder: Path) -> dict[str, str]:
    """The part of every rule a test can cover: parts in the order of their names, rules in a part's order."""
    parts = sorted(folder.glob("*.md"))
    if not parts:
        raise CatalogError(f"no part (a Markdown file) in {folder}")
    part_of: dict[str, Path] = {}
    for part in parts:
        identifiers = rule_ids(part.read_text(encoding="utf-8"))
        if not identifiers:
            raise CatalogError(f"{part.name} has no table row starting with a B or X ID")
        for identifier in identifiers:
            if identifier in part_of:
                raise CatalogError(f"{identifier} stands twice, in {part_of[identifier].name} and in {part.name}")
            part_of[identifier] = part
    return {identifier: part.stem for identifier, part in part_of.items() if identifier not in NOT_TESTABLE}


def covered_ids(text: str) -> set[str]:
    return {found for line in _COVERS_LINE.findall(text) for found in _ID.findall(line)}


def files_under_test_folders(roots: Iterable[Path]) -> list[Path]:
    """Every file under a ``tests`` folder below the given roots."""
    found: set[Path] = set()
    for root in roots:
        for tests_dir in [root] if root.name == "tests" else root.glob("**/tests"):
            found.update(p for p in tests_dir.rglob("*") if p.is_file() and p.suffix in TEST_FILE_SUFFIXES)
    return sorted(found)


def addon_suite_of(test_file: Path, addons: Collection[str]) -> str | None:
    """The add-on whose suite, ``tests/addons/<add-on>/``, holds the file; None for a test of no add-on."""
    folders = test_file.parts[:-1]
    for index, folder in enumerate(folders[2:], start=2):
        if folders[index - 2 : index] == _ADDON_SUITES and folder in addons:
            return folder
    return None


def build_report(
    catalog: Mapping[str, str], files: Iterable[Path], addons: Collection[str] = ADDON_NAMES
) -> CoverageReport:
    """Compares the catalog, which gives each ID its part, with the ``Covers:`` lines of the files."""
    suites_naming: dict[str, set[str | None]] = {}
    unknown: dict[str, list[Path]] = {}
    for path in files:
        suite = addon_suite_of(path, addons)
        for cited in covered_ids(path.read_text(encoding="utf-8", errors="replace")):
            suites_naming.setdefault(cited, set()).add(suite)
            if cited not in catalog and cited not in NOT_TESTABLE:
                unknown.setdefault(cited, []).append(path)
    return CoverageReport(
        uncovered=[identifier for identifier in catalog if identifier not in suites_naming],
        outside_their_suite=[
            identifier
            for identifier, part in catalog.items()
            if identifier in suites_naming and (part if part in addons else None) not in suites_naming[identifier]
        ],
        unknown=unknown,
    )


def _parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="coverage-check", description=__doc__)
    parser.add_argument("--catalog", type=Path, default=BEHAVIOR_CATALOG, help="the folder that holds the parts")
    parser.add_argument("roots", nargs="*", type=Path, default=[REPO_ROOT / "plugins", REPO_ROOT / "tests"])
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_arguments(sys.argv[1:] if argv is None else argv)
    try:
        catalog = read_catalog(arguments.catalog)
    except (OSError, CatalogError) as error:
        print(f"coverage: cannot read the catalog {arguments.catalog}: {error}", file=sys.stderr)
        return EXIT_BAD_CATALOG
    report = build_report(catalog, files_under_test_folders(arguments.roots))

    for cited, paths in sorted(report.unknown.items()):
        where = ", ".join(str(p) for p in paths)
        print(f"coverage: {cited} is not in the catalog, cited in {where}")
    for identifier in report.outside_their_suite:
        part = catalog[identifier]
        if part in ADDON_NAMES:
            print(f"coverage: {identifier} stands in the part of the {part} add-on, and no test of its suite names it")
        else:
            print(f"coverage: {identifier} stands in the part {part}, and only an add-on's tests name it")
    if report.uncovered:
        print(
            f"coverage: {len(report.uncovered)} of {len(catalog)} behaviors have no test: {', '.join(report.uncovered)}"
        )
    elif not report.outside_their_suite:
        print(f"coverage: all {len(catalog)} behaviors have a test")
    return EXIT_FINDINGS if report.has_findings else EXIT_COVERED


if __name__ == "__main__":
    sys.exit(main())
