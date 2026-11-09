"""Lists the catalogued behaviors (B and X IDs) that no test names in a ``Covers:`` line."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from repo_tools import REPO_ROOT

BEHAVIOR_CATALOG = REPO_ROOT / "docs" / "behavior.md"

# X15 is a rule about the tests themselves, so a review checks it instead of a test.
NOT_TESTABLE = frozenset({"X15"})

TEST_FILE_SUFFIXES = frozenset({".py", ".json", ".ts", ".tsx", ".md"})

EXIT_REPORTED = 0
EXIT_UNKNOWN_IDS = 1
EXIT_BAD_CATALOG = 2

_ID_ROW = re.compile(r"^\|\s*([BX]\d+)\s*\|", re.MULTILINE)
_COVERS_LINE = re.compile(r"Covers:\s*([A-Z]\d+(?:\s*,\s*[A-Z]\d+)*)")
_ID = re.compile(r"[A-Z]\d+")


class CatalogError(Exception):
    """The behavior catalog could not be read."""


@dataclass(frozen=True)
class CoverageReport:
    uncovered: list[str]
    unknown: dict[str, list[Path]]


def catalogued_ids(catalog_text: str) -> list[str]:
    """Returns the IDs of the catalog's tables, in catalog order, without the untestable ones."""
    found = _ID_ROW.findall(catalog_text)
    if not found:
        raise CatalogError("no table row starting with a B or X ID")
    return [identifier for identifier in found if identifier not in NOT_TESTABLE]


def covered_ids(text: str) -> set[str]:
    return {found for line in _COVERS_LINE.findall(text) for found in _ID.findall(line)}


def files_under_test_folders(roots: Iterable[Path]) -> list[Path]:
    """Every file under a ``tests`` folder below the given roots."""
    found: set[Path] = set()
    for root in roots:
        for tests_dir in [root] if root.name == "tests" else root.glob("**/tests"):
            found.update(p for p in tests_dir.rglob("*") if p.is_file() and p.suffix in TEST_FILE_SUFFIXES)
    return sorted(found)


def build_report(catalog: Sequence[str], files: Iterable[Path]) -> CoverageReport:
    known = set(catalog)
    covered: set[str] = set()
    unknown: dict[str, list[Path]] = {}
    for path in files:
        for cited in covered_ids(path.read_text(encoding="utf-8", errors="replace")):
            covered.add(cited)
            if cited not in known and cited not in NOT_TESTABLE:
                unknown.setdefault(cited, []).append(path)
    return CoverageReport(uncovered=[i for i in catalog if i not in covered], unknown=unknown)


def _parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="coverage-check", description=__doc__)
    parser.add_argument("--catalog", type=Path, default=BEHAVIOR_CATALOG)
    parser.add_argument("roots", nargs="*", type=Path, default=[REPO_ROOT / "plugins", REPO_ROOT / "tests"])
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_arguments(sys.argv[1:] if argv is None else argv)
    try:
        catalog = catalogued_ids(arguments.catalog.read_text(encoding="utf-8"))
    except (OSError, CatalogError) as error:
        print(f"coverage: cannot read the catalog {arguments.catalog}: {error}", file=sys.stderr)
        return EXIT_BAD_CATALOG
    report = build_report(catalog, files_under_test_folders(arguments.roots))

    for cited, paths in sorted(report.unknown.items()):
        where = ", ".join(str(p) for p in paths)
        print(f"coverage: {cited} is not in the catalog, cited in {where}")
    if report.uncovered:
        print(
            f"coverage: {len(report.uncovered)} of {len(catalog)} behaviors have no test: {', '.join(report.uncovered)}"
        )
    else:
        print(f"coverage: all {len(catalog)} behaviors have a test")
    return EXIT_UNKNOWN_IDS if report.unknown else EXIT_REPORTED


if __name__ == "__main__":
    sys.exit(main())
