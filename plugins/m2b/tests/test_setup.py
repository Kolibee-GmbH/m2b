"""``m2b setup inspect / apply``: a new store from nothing, or joining one that exists (B37)."""

from __future__ import annotations

import datetime
import json
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import test_commands
from m2b import cli, launcher, setup
from m2b.config import store_path
from m2b.config.machine import load_machine_config
from m2b.curate import model
from m2b.store.guard import DatalessGuard
from store_contract import FakeEviction

MEMORY = "# Memory\n\n## Facts\n\n## Current\n"
EXISTING_MEMORY = "# Memory\n\n## Facts\n\n- Dana likes old maps (dana.md)\n\n## Current\n"


class SetupTest(test_commands.CommandTest):
    def setUp(self) -> None:
        super().setUp()
        self.eviction = FakeEviction()
        self.installed = self.bin.parent / "installed_plugins.json"
        self.installed.write_text(json.dumps({"version": 2, "plugins": {}}), encoding="utf-8")
        self.environ[launcher.INSTALLED_PLUGINS_VARIABLE] = str(self.installed)
        self.environ["PATH"] = str(self.bin)
        self.fake_program("claude", "fake_claude.py", self.bin.parent / "model.json")
        self.reminders = self.fake_program("reminders", "fake_reminders.py", self.reminders_state)

    def answers(self, **changes: Any) -> dict[str, Any]:
        answers: dict[str, Any] = {
            "machine_id": "sb-test-m1",
            "store": {"backend": "folder", "path": str(self.store_root)},
            "calendar": "none",
            "tasks": {"backend": "markdown"},
            "owner": "Alex",
            "language": "en",
            "curates": True,
        }
        answers.update(changes)
        return {key: value for key, value in answers.items() if value is not None}

    def apply(self, answers: dict[str, Any], download: bool = True) -> tuple[int, Any, str]:
        guard = DatalessGuard(True, lstat=self.eviction.lstat)

        def fake_download(command: list[str], **_: Any) -> subprocess.CompletedProcess[bytes]:
            if download:
                self.eviction.evicted.clear()
            return subprocess.CompletedProcess(command, 0)

        with (
            mock.patch("m2b.store.factory.guard_for_platform", return_value=guard),
            mock.patch("m2b.store.folder.subprocess.run", fake_download),
            mock.patch("m2b.setup.FETCH_TIMEOUT_SECONDS", 0.5),
        ):
            code, out, err = self.run_command("setup", "apply", "--answers", json.dumps(answers), "--json")
        return code, json.loads(out) if code == 0 else None, err

    def snapshot(self) -> dict[str, tuple[bytes, int]]:
        files = {}
        for root in (self.home, self.store_root):
            for path in sorted(root.rglob("*")):
                if path.is_file() and "tmp" not in path.relative_to(root).parts:
                    files[str(path)] = (path.read_bytes(), path.stat().st_mtime_ns)
        return files

    def store_text(self, relative: str) -> str:
        return (self.store_root / relative).read_text(encoding="utf-8")

    def existing_store(self, curating: str = "sb-test-m2") -> None:
        self.write("store.json", json.dumps({
            "format": 1, "tasks": {"backend": "markdown"}, "curating_machine": curating, "journal_since": "2026-10-01",
        }))  # fmt: skip
        self.write("profile.json", json.dumps({"version": 1, "owner": "Alex", "language": "de"}))
        self.write("memory/MEMORY.md", EXISTING_MEMORY)
        self.write("STORE.md", "# an older contract\n")

    def write(self, relative: str, text: str) -> None:
        target = self.store_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


class StorePathTest(SetupTest):
    def test_a_store_path_the_curation_run_cannot_fence_is_refused_with_the_reason(self) -> None:
        """Covers: B81"""
        target = self.store_root.parent / "Notes (2026)"

        code, _, err = self.apply(self.answers(store={"backend": "folder", "path": str(target), "create": True}))

        self.assertEqual(code, cli.EXIT_USAGE, err)
        self.assertEqual(len(err.splitlines()), 1, err)
        self.assertIn("(", err)
        self.assertIn("curation", err)
        self.assertFalse(target.exists())
        self.assertFalse(self.machine.config_file.exists())

    def test_a_machine_that_only_captures_may_keep_its_store_in_such_a_folder(self) -> None:
        """Covers: B81"""
        path = "/sb-test/Dropbox (Personal)/m2b"

        answers = setup.parse_answers({"store": {"backend": "folder", "path": path}, "curates": False}, self.home)

        self.assertEqual(str(answers.store.path), path)

    def test_the_reason_stays_one_line_and_names_every_character_for_a_path_with_a_line_break(self) -> None:
        """Covers: B81"""
        reason = store_path.problem("/sb-test/Notes\n2026")

        assert reason is not None
        self.assertNotIn("\n", reason)
        self.assertIn("a line break", reason)

    def test_every_character_the_fence_refuses_is_refused_by_setup_too(self) -> None:
        """Covers: B81"""
        for character in store_path.UNSAFE_CHARACTERS:
            with self.subTest(character=character):
                path = f"/sb-test/Notes{character}2026"
                with self.assertRaises(setup.SetupError):
                    setup.parse_answers({"store": {"backend": "folder", "path": path}, "curates": True}, self.home)
                with self.assertRaises(model.FenceError):
                    model.store_rules(["Read(<store>/memory/**)"], Path(path))


class NewStoreTest(SetupTest):
    def test_a_new_store_gets_config_settings_profile_layout_contract_distillate_and_launcher(self) -> None:
        code, result, err = self.apply(self.answers(tasks={"backend": "apple-reminders", "list": "sb-test-inbox"}))

        self.assertEqual(code, cli.EXIT_OK, err)
        config = load_machine_config(self.machine)
        self.assertEqual(
            (config.machine_id, config.store.path, config.calendar.backend), ("sb-test-m1", self.store_root, "none")
        )
        self.assertEqual(config.executables["python3"], sys.executable)
        self.assertEqual(config.executables["claude"], str(self.bin / "claude"))
        self.assertEqual(config.executables["reminders"], self.reminders)
        settings = json.loads(self.store_text("store.json"))
        self.assertEqual(settings["curating_machine"], "sb-test-m1")
        self.assertEqual(settings["tasks"], {"backend": "apple-reminders", "list": "sb-test-inbox"})
        self.assertEqual(settings["journal_since"], datetime.date.today().isoformat())
        self.assertEqual(json.loads(self.store_text("profile.json")), {"version": 1, "owner": "Alex", "language": "en"})
        for folder in ("inbox", "corpus", "memory", "state/core"):
            self.assertTrue((self.store_root / folder).is_dir(), folder)
        self.assertEqual(self.store_text("memory/MEMORY.md"), MEMORY)
        self.assertIn("sb-test-inbox", self.store_text("STORE.md"))
        self.assertEqual(launcher.installed_launcher_version(self.machine), launcher.core_version())
        self.assertIsNone(result["take_over"])
        self.assertIn("store.json", result["written"])

    def test_a_second_run_with_the_same_answers_changes_no_file(self) -> None:
        """Covers: B66"""
        self.apply(self.answers())
        before = self.snapshot()

        code, result, err = self.apply(self.answers())

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(result["written"], [])
        self.assertEqual(self.snapshot(), before)

    def test_a_path_recorded_by_hand_survives_a_second_run(self) -> None:
        self.apply(self.answers())
        raw = json.loads(self.machine.config_file.read_text(encoding="utf-8"))
        raw["executables"]["python3"] = "/usr/bin/sb-test-python3"
        self.machine.config_file.write_text(json.dumps(raw), encoding="utf-8")
        before = self.machine.config_file.read_bytes()

        code, result, err = self.apply(self.answers())

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(result["written"], [])
        self.assertEqual(self.machine.config_file.read_bytes(), before)

    def test_the_curation_model_chosen_is_kept_and_a_run_without_the_answer_keeps_it(self) -> None:
        code, _, err = self.apply(self.answers(curation_model="sonnet"))
        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(self.config()["curation"]["model"], "sonnet")

        code, result, err = self.apply(self.answers())

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(result["written"], [])
        self.assertEqual(self.config()["curation"]["model"], "sonnet")

    def test_without_a_curation_model_answer_the_default_applies_and_nothing_is_recorded(self) -> None:
        self.apply(self.answers())

        self.assertNotIn("curation", self.config())

    def test_a_curation_model_other_than_haiku_or_sonnet_is_refused(self) -> None:
        code, _, err = self.apply(self.answers(curation_model="gpt"))

        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertIn("curation_model", err)
        self.assertFalse(self.machine.config_file.exists())

    def config(self) -> dict[str, Any]:
        raw: dict[str, Any] = json.loads(self.machine.config_file.read_text(encoding="utf-8"))
        return raw

    def test_a_launcher_that_cannot_be_written_exits_1_and_says_why(self) -> None:
        self.machine.launcher.parent.mkdir(parents=True)
        self.machine.launcher.write_text("#!/bin/sh\necho someone else's m2b\n", encoding="utf-8")

        code, _, _ = self.apply(self.answers())

        self.assertEqual(code, cli.EXIT_PROBLEM)
        self.assertIn("someone else", self.machine.launcher.read_text(encoding="utf-8"))
        self.assertTrue(self.machine.config_file.exists())

    def test_a_new_store_needs_the_owner_and_a_curating_machine_and_writes_nothing_without(self) -> None:
        for answers in (self.answers(owner=None), self.answers(curates=False), self.answers(language="xx")):
            with self.subTest(answers=answers):
                code, _, err = self.apply(answers)
                self.assertEqual(code, cli.EXIT_USAGE, err)
                self.assertFalse(self.machine.config_file.exists())
                self.assertEqual(list(self.store_root.iterdir()), [])

    def test_asked_to_create_it_a_folder_store_is_made_at_the_default_place_with_markdown_tasks(self) -> None:
        """The first run without configuration."""
        folder = self.store_root / "m2b"
        answers = self.answers(store={"backend": "folder", "path": str(folder), "create": True})
        answers["tasks"] = {"backend": "markdown"}
        code, result, err = self.apply(answers)

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertTrue((folder / "store.json").is_file())
        self.assertTrue((folder / "inbox").is_dir())
        self.assertIn("store.json", result["written"])

    def test_a_refused_quick_start_leaves_no_folder_behind(self) -> None:
        folder = self.store_root / "m2b"
        answers = self.answers(store={"backend": "folder", "path": str(folder), "create": True}, owner=None)
        answers["tasks"] = {"backend": "markdown"}

        self.assertEqual(self.apply(answers)[0], cli.EXIT_USAGE)
        self.assertFalse(folder.exists())

    def test_create_never_turns_a_folder_with_other_files_into_a_store(self) -> None:
        folder = self.store_root / "m2b"
        folder.mkdir()
        (folder / "README.md").write_text("a checkout", encoding="utf-8")
        answers = self.answers(store={"backend": "folder", "path": str(folder), "create": True})

        code, _, err = self.apply(answers)

        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertIn("holds files that are no m2b store", err)
        self.assertEqual(sorted(path.name for path in folder.iterdir()), ["README.md"])

    def test_create_is_refused_for_icloud_and_when_the_parent_is_missing(self) -> None:
        icloud = self.answers(store={"backend": "icloud", "path": str(self.store_root / "x"), "create": True})
        self.assertEqual(self.apply(icloud)[0], cli.EXIT_USAGE)
        deep = self.answers(store={"backend": "folder", "path": str(self.store_root / "no" / "m2b"), "create": True})
        self.assertEqual(self.apply(deep)[0], cli.EXIT_USAGE)
        self.assertFalse((self.store_root / "no").exists())

    def test_a_missing_store_folder_is_not_created(self) -> None:
        code, _, _ = self.apply(self.answers(store={"backend": "folder", "path": str(self.store_root / "typo")}))

        self.assertEqual(code, cli.EXIT_UNREACHABLE)
        self.assertFalse((self.store_root / "typo").exists())
        self.assertFalse(self.machine.config_file.exists())

    def test_each_part_is_listed_with_whether_it_is_on(self) -> None:
        _, result, _ = self.apply(self.answers())

        self.assertEqual([(part["name"], part["on"]) for part in result["parts"]], [
            ("band", False), ("herdr", False), ("worklog", False), ("backup", False),
        ])  # fmt: skip


class JoinTest(SetupTest):
    def test_joining_an_evicted_store_downloads_it_and_changes_no_file_in_it(self) -> None:
        """Covers: B37"""
        self.existing_store()
        before = {path: data for path, data in self.snapshot().items() if path.startswith(str(self.store_root))}
        for relative in ("store.json", "profile.json", "memory/MEMORY.md"):
            self.eviction.evicted.add(self.store_root / relative)

        code, result, err = self.apply(self.answers(owner=None, language=None, tasks=None, curates=False))

        self.assertEqual(code, cli.EXIT_OK, err)
        after = {path: data for path, data in self.snapshot().items() if path.startswith(str(self.store_root))}
        self.assertEqual(after, before)
        self.assertEqual(load_machine_config(self.machine).store.path, self.store_root)
        self.assertEqual(result["written"], [str(self.machine.config_file), str(self.machine.launcher)])

    def test_an_evicted_memory_folder_is_downloaded_and_its_distillate_never_written_over(self) -> None:
        """Covers: B37"""
        self.existing_store()
        memory = self.store_root / "memory"
        aside = self.bin.parent / "MEMORY.md.cloud"
        (memory / "MEMORY.md").rename(aside)
        self.eviction.evicted.add(memory)
        guard = DatalessGuard(True, lstat=self.eviction.lstat)

        def fake_download(command: list[str], **_: Any) -> subprocess.CompletedProcess[bytes]:
            if command[-1] == str(memory):
                aside.rename(memory / "MEMORY.md")
                self.eviction.evicted.discard(memory)
            return subprocess.CompletedProcess(command, 0)

        answers = json.dumps(self.answers(owner=None, language=None, tasks=None, curates=False))
        with (
            mock.patch("m2b.store.factory.guard_for_platform", return_value=guard),
            mock.patch("m2b.store.folder.subprocess.run", fake_download),
        ):
            code, _, err = self.run_command("setup", "apply", "--answers", answers)

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(self.store_text("memory/MEMORY.md"), EXISTING_MEMORY)

    def test_joining_a_reminders_store_records_the_reminders_program(self) -> None:
        self.existing_store()
        self.write("store.json", json.dumps({
            "format": 1, "tasks": {"backend": "apple-reminders", "list": "sb-test-inbox"},
            "curating_machine": "sb-test-m2", "journal_since": "2026-10-01",
        }))  # fmt: skip

        code, _, err = self.apply(self.answers(owner=None, language=None, tasks=None, curates=False))

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(load_machine_config(self.machine).executables["reminders"], self.reminders)

    def test_a_store_file_that_stays_evicted_stops_setup_before_any_write(self) -> None:
        """Covers: B37"""
        self.existing_store()
        self.eviction.evicted.add(self.store_root / "profile.json")

        code, _, err = self.apply(self.answers(owner=None, language=None, tasks=None, curates=False), download=False)

        self.assertEqual(code, cli.EXIT_UNREACHABLE)
        self.assertIn("profile.json", err)
        self.assertFalse(self.machine.config_file.exists())

    def test_a_second_machine_that_wants_to_curate_is_told_about_take_over(self) -> None:
        self.existing_store(curating="sb-test-m2")
        before = self.store_text("store.json")

        code, result, err = self.apply(self.answers(owner=None, language=None, tasks=None, curates=True))

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(self.store_text("store.json"), before)
        self.assertIn("m2b curate take-over", result["take_over"])
        self.assertIn("sb-test-m2", result["take_over"])

    def test_a_changed_answer_changes_only_its_file(self) -> None:
        self.existing_store()
        settings, memory, contract = (self.store_text(name) for name in ("store.json", "memory/MEMORY.md", "STORE.md"))

        code, result, err = self.apply(self.answers(owner=None, language="en", tasks=None, curates=False))

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(json.loads(self.store_text("profile.json"))["language"], "en")
        self.assertEqual(
            (self.store_text("store.json"), self.store_text("memory/MEMORY.md"), self.store_text("STORE.md")),
            (settings, memory, contract),
        )
        self.assertIn("profile.json", result["written"])

    def test_a_store_json_with_tasks_of_the_wrong_shape_is_a_usage_error(self) -> None:
        self.write(
            "store.json",
            json.dumps(
                {"format": 1, "tasks": "apple-reminders", "curating_machine": "x", "journal_since": "2026-10-01"}
            ),
        )

        code, _, err = self.apply(self.answers(owner=None, language=None, tasks=None, curates=False))

        self.assertEqual(code, cli.EXIT_USAGE, err)
        self.assertIn("tasks", err)
        self.assertFalse(self.machine.config_file.exists())

    def test_a_store_of_a_newer_format_is_refused(self) -> None:
        self.write(
            "store.json",
            json.dumps(
                {"format": 9, "tasks": {"backend": "markdown"}, "curating_machine": "x", "journal_since": "2026-10-01"}
            ),
        )

        code, _, _ = self.apply(self.answers(owner=None, language=None, tasks=None, curates=False))

        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertFalse(self.machine.config_file.exists())

    def test_an_existing_machine_config_keeps_its_id_and_parts(self) -> None:
        self.existing_store(curating="sb-test-m1")
        self.machine.config_file.parent.mkdir(parents=True)
        self.machine.config_file.write_text(json.dumps({
            "version": 1, "machine_id": "sb-test-m1", "store": {"backend": "folder", "path": "/elsewhere"},
            "curation": {"model_timeout_minutes": 20},
            "parts": {"backup": {"on": True, "target": "~/sb-test-backup"}},
        }), encoding="utf-8")  # fmt: skip

        code, result, err = self.apply(
            self.answers(machine_id="sb-test-renamed", owner=None, language=None, tasks=None)
        )

        self.assertEqual(code, cli.EXIT_OK, err)
        raw = json.loads(self.machine.config_file.read_text(encoding="utf-8"))
        self.assertEqual(raw["machine_id"], "sb-test-m1")
        self.assertEqual(raw["store"]["path"], str(self.store_root))
        self.assertEqual(raw["curation"], {"model_timeout_minutes": 20})
        self.assertEqual(raw["parts"], {"backup": {"on": True, "target": "~/sb-test-backup"}})
        self.assertEqual([part["name"] for part in result["parts"] if part["on"]], ["backup"])


class InspectTest(SetupTest):
    def test_inspect_shows_what_the_store_holds_after_downloading_it(self) -> None:
        self.existing_store()
        self.eviction.evicted.add(self.store_root / "profile.json")
        guard = DatalessGuard(True, lstat=self.eviction.lstat)

        def fake_download(command: list[str], **_: Any) -> subprocess.CompletedProcess[bytes]:
            self.eviction.evicted.clear()
            return subprocess.CompletedProcess(command, 0)

        with (
            mock.patch("m2b.store.factory.guard_for_platform", return_value=guard),
            mock.patch("m2b.store.folder.subprocess.run", fake_download),
        ):
            result = self.run_json(
                "setup", "inspect", "--store-backend", "folder", "--store-path", str(self.store_root)
            )

        self.assertEqual(result["store_settings"]["curating_machine"], "sb-test-m2")
        self.assertEqual(result["profile"], {"version": 1, "owner": "Alex", "language": "de"})
        self.assertTrue(result["distillate"])
        self.assertIsNone(result["machine_config"])

    def test_inspect_names_a_store_path_curation_cannot_use_before_the_interview(self) -> None:
        """Covers: B81"""
        target = self.store_root.parent / "Notes (2026)"

        result = self.run_json("setup", "inspect", "--store-backend", "folder", "--store-path", str(target))

        self.assertIn("(", result["store_path_problem"])
        clean = self.run_json("setup", "inspect", "--store-backend", "folder", "--store-path", str(self.store_root))
        self.assertIsNone(clean["store_path_problem"])

    def test_inspect_without_a_store_answer_uses_the_configured_store_and_an_empty_one_says_new(self) -> None:
        self.apply(self.answers())
        for name in ("store.json", "profile.json", "STORE.md", "memory/MEMORY.md"):
            (self.store_root / name).unlink()

        result = self.run_json("setup", "inspect")

        self.assertIsNone(result["store_settings"])
        self.assertIsNone(result["profile"])
        self.assertFalse(result["distillate"])
        self.assertEqual(result["machine_config"]["machine_id"], "sb-test-m1")


class FirstRunInspectTest(SetupTest):
    """The two answers the setup skill gets first on a new machine, both as JSON."""

    def test_a_machine_without_config_answers_that_nothing_is_set_up(self) -> None:
        """Covers: B60"""
        result = self.run_json("setup", "inspect")

        self.assertEqual(
            result,
            {
                "store": None,
                "store_path_problem": None,
                "store_exists": False,
                "store_settings": None,
                "profile": None,
                "distillate": False,
                "machine_config": None,
            },
        )

    def test_a_store_folder_that_does_not_exist_yet_answers_that_there_is_no_store_there(self) -> None:
        """Covers: B60"""
        folder = self.store_root.parent / "sb-test-quick-start"

        result = self.run_json("setup", "inspect", "--store-backend", "folder", "--store-path", str(folder))

        self.assertEqual(result["store"], {"backend": "folder", "path": str(folder)})
        self.assertFalse(result["store_exists"])
        self.assertIsNone(result["store_settings"])
        self.assertFalse(folder.exists())

    def test_a_folder_whose_parent_is_missing_still_cannot_be_reached(self) -> None:
        """Covers: B60"""
        folder = self.store_root.parent / "sb-test-not-mounted" / "m2b"

        code, _, err = self.run_command(
            "setup", "inspect", "--store-backend", "folder", "--store-path", str(folder), "--json"
        )

        self.assertEqual(code, cli.EXIT_UNREACHABLE, err)
        self.assertIn("cannot be reached", err)

    def test_a_store_that_exists_says_so(self) -> None:
        self.existing_store()

        result = self.run_json("setup", "inspect", "--store-backend", "folder", "--store-path", str(self.store_root))

        self.assertTrue(result["store_exists"])

    def test_without_json_a_machine_without_config_gets_one_line_per_answer(self) -> None:
        code, out, err = self.run_command("setup", "inspect")

        self.assertEqual((code, err), (cli.EXIT_OK, ""))
        self.assertIn("machine config: missing", out)
        self.assertIn("store: none named", out)


class StoreContractTest(unittest.TestCase):
    def test_the_contract_gives_an_integration_its_own_state_folder(self) -> None:
        """Covers: B82"""
        contract = setup.store_contract(2, "markdown", None)

        self.assertIn("- `state/integrations/<your name>/`: your own state.", contract)
        self.assertNotIn("add-on", contract.lower())


class SetupSkillTest(unittest.TestCase):
    """Structure only: the questions live once, in the skill (X15)."""

    skill = Path(__file__).resolve().parents[1] / "skills" / "setup" / "SKILL.md"

    def test_the_skill_may_only_run_setup_and_doctor(self) -> None:
        text = self.skill.read_text(encoding="utf-8")
        block = text.split("\n---\n", 1)[0].split("\n")[1:]
        fields = dict(line.split(": ", 1) for line in block if ": " in line)

        self.assertEqual(fields["name"], "setup")
        self.assertEqual(fields["allowed-tools"], "Bash(m2b setup *), Bash(m2b doctor), Bash(m2b doctor *)")
        for command in ("m2b setup inspect --json", "m2b setup apply --json --answers", "m2b doctor"):
            self.assertIn(command, text)


if __name__ == "__main__":
    unittest.main()
