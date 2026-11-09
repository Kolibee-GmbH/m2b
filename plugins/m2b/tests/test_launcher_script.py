from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]

# Stands for Python 3.8: runs the code it is given with the real interpreter, version set back.
OLD_PYTHON = """#!/bin/sh
shift 2
code=$1
shift
exec {python} -I -c "import sys; sys.version_info = (3, 8, 18, 'final', 0); sys.version = '3.8.18'; \\
sys.executable = '$0'; exec(compile(sys.argv.pop(1), '<launcher>', 'exec'))" "$code" "$@"
"""


class LauncherTest(unittest.TestCase):
    def test_an_old_python_gets_one_line_instead_of_a_traceback(self) -> None:
        """Covers: B52"""
        with tempfile.TemporaryDirectory(prefix="sb-test-") as folder:
            python = Path(folder) / "python3.8"
            python.write_text(OLD_PYTHON.format(python=sys.executable), encoding="utf-8")
            python.chmod(0o755)
            result = subprocess.run(
                [str(PLUGIN / "bin" / "m2b"), "status"],
                env={"PATH": os.environ.get("PATH", ""), "M2B_PYTHON": str(python), "M2B_HOME": folder},
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.splitlines(), [f"m2b needs Python 3.9 or newer; {python} is 3.8.18"])


if __name__ == "__main__":
    unittest.main()
