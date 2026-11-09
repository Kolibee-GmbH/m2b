"""``m2b distillate off / on``: projects whose sessions get no distillate."""

from __future__ import annotations

import unittest

import test_commands
from m2b import cli
from m2b.config.machine import load_machine_config


class DistillateCommandTest(test_commands.CommandTest):
    def setUp(self) -> None:
        super().setUp()
        self.set_up(calendar="none")
        self.project = self.home / "code" / "acme"
        (self.project / "api").mkdir(parents=True)

    def skipped(self) -> list[str]:
        return [str(path) for path in load_machine_config(self.machine).distillate.skip_under]

    def test_off_records_the_folder_once_and_on_takes_it_out(self) -> None:
        """Covers: B65"""
        self.assertEqual(self.run_command("distillate", "off", str(self.project))[0], cli.EXIT_OK)
        code, out, _ = self.run_command("distillate", "off", str(self.project / "api"))
        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("already", out)
        self.assertEqual(self.skipped(), [str(self.project.resolve())])

        code, out, _ = self.run_command("distillate", "on", str(self.project / "api"))
        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn(f"m2b distillate on {self.project.resolve()}", out)
        self.assertEqual(self.skipped(), [str(self.project.resolve())])

        self.assertEqual(self.run_command("distillate", "on", str(self.project))[0], cli.EXIT_OK)
        self.assertEqual(self.skipped(), [])

    def test_without_a_folder_it_takes_the_current_one(self) -> None:
        self.environ["PWD"] = str(self.project)
        self.run_command("distillate", "off")
        self.assertEqual(self.skipped(), [str(self.project.resolve())])


if __name__ == "__main__":
    unittest.main()
