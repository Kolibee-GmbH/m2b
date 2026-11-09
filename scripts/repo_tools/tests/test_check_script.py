from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


class ScriptsCheckTest(unittest.TestCase):
    def test_in_ci_a_missing_claude_fails_the_run_before_anything_runs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sb-test-") as bin_dir:
            os.symlink(shutil.which("dirname") or "/usr/bin/dirname", Path(bin_dir) / "dirname")
            result = subprocess.run(
                ["/bin/sh", str(REPO / "scripts" / "check")],
                env={"PATH": bin_dir, "CI": "true", "HOME": bin_dir},
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("claude", result.stderr)
        self.assertIn("CI", result.stderr)


if __name__ == "__main__":
    unittest.main()
