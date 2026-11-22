from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


class ScriptsCheckTest(unittest.TestCase):
    def run_in_ci_without_claude(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory(prefix="sb-test-") as bin_dir:
            os.symlink(shutil.which("dirname") or "/usr/bin/dirname", Path(bin_dir) / "dirname")
            return subprocess.run(
                ["/bin/sh", str(REPO / "scripts" / "check"), *arguments],
                env={"PATH": bin_dir, "CI": "true", "HOME": bin_dir},
                capture_output=True,
                text=True,
                timeout=30,
            )

    def test_in_ci_a_missing_claude_fails_the_run_before_anything_runs(self) -> None:
        for arguments in ((), ("--release",)):
            with self.subTest(arguments=arguments):
                result = self.run_in_ci_without_claude(*arguments)

                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn("claude", result.stderr)
                self.assertIn("CI", result.stderr)


if __name__ == "__main__":
    unittest.main()
