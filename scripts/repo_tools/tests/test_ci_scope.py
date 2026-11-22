"""Which checks a change needs: the full proof, or the short one of a release or a pin."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from repo_tools import ci_scope

MANIFEST = {"name": "m2b", "version": "0.13.0", "description": "Your second brain."}


class Repository:
    """A git repository of invented files, one commit per change."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.git("init", "-q")
        self.write("plugins/m2b/.claude-plugin/plugin.json", json.dumps(MANIFEST, indent=2) + "\n")
        self.write("CHANGELOG.md", "# Changelog\n\n## [0.13.0] - 2026-11-22\n")
        self.write("docs/evals.md", "# Evals\n")
        self.write(".claude-plugin/marketplace.json", '{"plugins": []}\n')
        self.write("plugins/m2b/src/m2b/ingest.py", "x = 1\n")
        self.base = self.commit()

    def git(self, *arguments: str) -> str:
        environment = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null", "PATH": "/usr/bin:/bin"}
        done = subprocess.run(
            ["git", "-c", "user.name=Alex", "-c", "user.email=alex@example.org", *arguments],
            cwd=self.root,
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )
        return done.stdout.strip()

    def write(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "change", "--allow-empty")
        return self.git("rev-parse", "HEAD")

    def scope(self, head: str) -> str:
        return ci_scope.scope(self.base, head, self.root)


class ScopeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.repo = Repository(Path(self._temp.name))

    def test_a_release_changes_the_version_the_changelog_and_the_eval_page(self) -> None:
        self.repo.write(
            "plugins/m2b/.claude-plugin/plugin.json", json.dumps({**MANIFEST, "version": "0.14.0"}, indent=2) + "\n"
        )
        self.repo.write("CHANGELOG.md", "# Changelog\n\n## [0.14.0] - 2026-12-01\n\n## [0.13.0] - 2026-11-22\n")
        self.repo.write("docs/evals.md", "# Evals\n\nnew scores\n")

        self.assertEqual(self.repo.scope(self.repo.commit()), ci_scope.RELEASE)

    def test_a_pin_changes_the_marketplace_alone(self) -> None:
        self.repo.write(".claude-plugin/marketplace.json", '{"plugins": [{"name": "m2b"}]}\n')

        self.assertEqual(self.repo.scope(self.repo.commit()), ci_scope.RELEASE)

    def test_any_other_file_needs_the_full_proof(self) -> None:
        self.repo.write("CHANGELOG.md", "# Changelog\n\nmore\n")
        self.repo.write("plugins/m2b/src/m2b/ingest.py", "x = 2\n")

        self.assertEqual(self.repo.scope(self.repo.commit()), ci_scope.FULL)

    def test_a_manifest_change_beyond_its_version_needs_the_full_proof(self) -> None:
        changed = {**MANIFEST, "version": "0.14.0", "description": "Another."}
        self.repo.write("plugins/m2b/.claude-plugin/plugin.json", json.dumps(changed, indent=2) + "\n")

        self.assertEqual(self.repo.scope(self.repo.commit()), ci_scope.FULL)

    def test_a_new_or_removed_file_of_the_list_needs_the_full_proof(self) -> None:
        (self.repo.root / "docs" / "evals.md").unlink()

        self.assertEqual(self.repo.scope(self.repo.commit()), ci_scope.FULL)

    def test_no_change_and_an_unknown_base_need_the_full_proof(self) -> None:
        head = self.repo.commit()

        self.assertEqual(self.repo.scope(head), ci_scope.FULL)
        self.assertEqual(ci_scope.scope("0" * 40, head, self.repo.root), ci_scope.FULL)
        self.assertEqual(ci_scope.scope("", head, self.repo.root), ci_scope.FULL)

    def test_the_command_prints_the_scope_and_says_why_on_standard_error(self) -> None:
        self.repo.write(".claude-plugin/marketplace.json", '{"plugins": [{"name": "m2b"}]}\n')
        head = self.repo.commit()
        out, err = io.StringIO(), io.StringIO()

        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ci_scope.main([self.repo.base, head, "--repository", str(self.repo.root)])

        self.assertEqual((code, out.getvalue()), (0, "release\n"))
        self.assertIn(".claude-plugin/marketplace.json", err.getvalue())
