"""Which package may import which: the core stands without an add-on, and an add-on reaches the
core through the ``m2b`` command. The worklog imports two modules of the core, each knowledge
that must exist once: how credentials are found, and what Claude Code writes into a transcript."""

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

    def test_the_worklog_imports_from_the_core_only_the_redaction_and_claude_codes_format(self) -> None:
        self.assertEqual(of_package(imported_modules(WORKLOG), CORE), {"m2b.redaction", "m2b.claude_code"})

    def test_what_the_worklog_imports_imports_nothing_of_the_core_so_it_reaches_no_store(self) -> None:
        for module in ("redaction", "claude_code"):
            with self.subTest(module=module):
                tree = ast.parse((SOURCES / CORE / f"{module}.py").read_text(encoding="utf-8"))
                imported = {
                    name
                    for node in ast.walk(tree)
                    for name in (
                        [alias.name for alias in node.names]
                        if isinstance(node, ast.Import)
                        else [node.module or ""]
                        if isinstance(node, ast.ImportFrom)
                        else []
                    )
                }

                self.assertEqual(of_package(imported, CORE), set())


if __name__ == "__main__":
    unittest.main()
