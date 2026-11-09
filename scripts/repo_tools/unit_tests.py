"""Runs one folder of unit tests with the given import root, and passes on zero tests.

``python3 -m unittest discover`` exits 5 when it finds no tests (Python 3.12 and newer),
which would make a plugin without tests fail the check.
"""

from __future__ import annotations

import argparse
import sys
import unittest
from collections.abc import Sequence
from pathlib import Path


def run_tests(tests_dir: Path, import_roots: list[Path], label: str) -> bool:
    for import_root in reversed(import_roots):
        sys.path.insert(0, str(import_root))
    if not tests_dir.is_dir():
        print(f"unit tests {label}: 0 tests (no tests folder)")
        return True
    suite = unittest.defaultTestLoader.discover(str(tests_dir), pattern="test_*.py", top_level_dir=str(tests_dir))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    python = ".".join(str(part) for part in sys.version_info[:3])
    verdict = "ok" if result.wasSuccessful() else "FAILED"
    print(f"unit tests {label}: {result.testsRun} tests on Python {python}, {verdict}")
    return result.wasSuccessful()


def _parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="unit-tests", description=__doc__)
    parser.add_argument("--tests", type=Path, required=True, help="the folder holding test_*.py files")
    parser.add_argument(
        "--import-root", type=Path, action="append", required=True, help="put on sys.path before the tests; repeatable"
    )
    parser.add_argument("--label", required=True, help="name in the summary line")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_arguments(sys.argv[1:] if argv is None else argv)
    return 0 if run_tests(arguments.tests, arguments.import_root, arguments.label) else 1


if __name__ == "__main__":
    sys.exit(main())
