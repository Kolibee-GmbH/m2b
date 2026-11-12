"""The core imports nothing from an add-on, so it stands without one. What an add-on may import
from the core is for the add-on's own suite to hold, with the helpers from here."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

SOURCES = Path(__file__).resolve().parents[1] / "src"
CORE = "m2b"
WORKLOG = "m2b_worklog"


def imported_modules(package: str) -> set[str]:
    modules: set[str] = set()
    for source in (SOURCES / package).rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"), str(source))):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules.add(node.module)
    return modules


def of_package(modules: set[str], package: str) -> set[str]:
    return {module for module in modules if module == package or module.startswith(f"{package}.")}


class PackageBoundaryTest(unittest.TestCase):
    def test_the_core_imports_nothing_from_an_add_on(self) -> None:
        self.assertEqual(of_package(imported_modules(CORE), WORKLOG), set())


if __name__ == "__main__":
    unittest.main()
