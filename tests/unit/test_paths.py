from __future__ import annotations

import unittest
from pathlib import Path

from m2b import paths


class MachinePathsTest(unittest.TestCase):
    def test_every_machine_path_lies_under_m2b_home(self) -> None:
        machine = paths.machine_paths({"M2B_HOME": "/tmp/x", "HOME": "/home/alex"})

        for path in (machine.config_file, machine.state_dir, machine.temp_dir, machine.share_dir, machine.launcher):
            with self.subTest(path=path):
                self.assertEqual(path.parts[:3], ("/", "tmp", "x"))

    def test_the_layout_below_the_home_follows_the_xdg_folders(self) -> None:
        machine = paths.machine_paths({"M2B_HOME": "/tmp/x"})

        self.assertEqual(machine.config_file, Path("/tmp/x/.config/m2b/config.json"))
        self.assertEqual(machine.state_dir, Path("/tmp/x/.local/state/m2b"))
        self.assertEqual(machine.temp_dir, Path("/tmp/x/.local/state/m2b/tmp"))
        self.assertEqual(machine.share_dir, Path("/tmp/x/.local/share/m2b"))
        self.assertEqual(machine.launcher, Path("/tmp/x/.local/bin/m2b"))

    def test_without_m2b_home_the_user_home_is_the_root(self) -> None:
        machine = paths.machine_paths({"HOME": "/home/alex"})

        self.assertEqual(machine.home, Path("/home/alex"))
        self.assertEqual(machine.config_file, Path("/home/alex/.config/m2b/config.json"))

    def test_an_empty_m2b_home_counts_as_unset(self) -> None:
        self.assertEqual(paths.machine_paths({"M2B_HOME": "", "HOME": "/home/alex"}).home, Path("/home/alex"))

    def test_a_tilde_in_m2b_home_is_expanded(self) -> None:
        self.assertEqual(paths.machine_paths({"M2B_HOME": "~/sb", "HOME": "/home/alex"}).home, Path("/home/alex/sb"))


class ExpandTest(unittest.TestCase):
    def test_a_leading_tilde_means_the_machine_home(self) -> None:
        home = Path("/tmp/x")

        self.assertEqual(paths.expand("~/Second Brain", home), Path("/tmp/x/Second Brain"))
        self.assertEqual(paths.expand("~", home), home)

    def test_absolute_and_other_paths_stay_as_written(self) -> None:
        home = Path("/tmp/x")

        self.assertEqual(paths.expand("/data/store", home), Path("/data/store"))
        self.assertEqual(paths.expand("~alex/store", home), Path("~alex/store"))


if __name__ == "__main__":
    unittest.main()
