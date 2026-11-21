"""``m2b status``: how large everything is that a session in a folder starts with, and the sum."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import re
from pathlib import Path
from typing import Any
from unittest import mock

import test_runner
from m2b import hooks
from m2b.config.machine import load_machine_config
from m2b.hook_input import HookInput
from m2b.store.base import StoreError
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard

LESSON = "---\nkind: knowledge\ntarget: every project\nkept: 2026-11-20\n---\n# Once\n\nSay it once.\n"
STYLE = "---\nname: plain\ndescription: Short answers\nforce-for-plugin: true\n---\n\n- No opener.\n- No closer.\n"


def _key(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


class StartSizeTest(test_runner.RunnerTest):
    def setUp(self) -> None:
        super().setUp()
        self.user_home = Path(self.environ["HOME"])
        self.claude = self.claude_settings.parent
        self.project = self.user_home / "work" / "acme-shop"
        self.project.mkdir(parents=True)
        self.environ["CLAUDE_PROJECT_DIR"] = str(self.project)

    def put(self, path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def start(self) -> dict[str, Any]:
        answer: dict[str, Any] = self.run_json("status")["session_start"]
        return answer

    def parts(self) -> dict[str, dict[str, Any]]:
        return {part["name"]: part for part in self.start()["parts"]}

    def plugin_style(self, text: str = STYLE, enabled: bool = True) -> Path:
        install = self.bin.parent / "plugins" / "tidy" / "1.0.0"
        style = self.put(install / "output-styles" / "plain.md", text)
        self.installed.write_text(
            json.dumps({"version": 2, "plugins": {"tidy@acme": [{"scope": "user", "installPath": str(install)}]}}),
            encoding="utf-8",
        )
        self.put(self.claude / "settings.json", json.dumps({"enabledPlugins": {"tidy@acme": enabled}}))
        return style

    def test_it_names_every_file_a_session_starts_with_with_its_size_and_list_points_and_the_sum(self) -> None:
        """Covers: B268"""
        self.curating()
        self.write("memory/lessons/once.md", LESSON)
        self.put(self.claude / "CLAUDE.md", "# Global\n\n- Commits in English\n- No push\n")
        self.put(self.claude / "rules" / "tests.md", "# Tests\n\n1. Only the touched checks\n")
        self.put(self.project / "CLAUDE.md", "# Acme shop\n\nThe shop.\n\n* Run make test\n")
        self.put(self.project.parent / "CLAUDE.md", "# Work\n")
        self.plugin_style()
        memory = self.claude / "projects" / _key(self.project) / "memory" / "MEMORY.md"
        self.put(memory, "- [Builds](builds.md) - make, not npm\n")

        start = self.start()
        parts = {part["name"]: part for part in start["parts"]}

        self.assertEqual(start["folder"], "~/work/acme-shop")
        style_name = (
            "output style tidy:plain (" + str(self.bin.parent / "plugins/tidy/1.0.0/output-styles/plain.md") + ")"
        )
        self.assertEqual(
            list(parts),
            [
                str(self.claude / "CLAUDE.md"),
                str(self.claude / "rules" / "tests.md"),
                "~/work/acme-shop/CLAUDE.md",
                "~/work/CLAUDE.md",
                style_name,
                str(memory),
                "m2b distillate",
                "m2b notices, rule and lessons",
            ],
        )
        self.assertEqual(parts[str(self.claude / "CLAUDE.md")]["list_points"], 2)
        self.assertEqual(parts[str(self.claude / "rules" / "tests.md")]["list_points"], 1)
        self.assertEqual(parts["~/work/acme-shop/CLAUDE.md"]["list_points"], 1)
        self.assertEqual(parts[style_name]["list_points"], 2)
        self.assertEqual(parts[str(memory)]["list_points"], 1)
        self.assertEqual(parts["m2b notices, rule and lessons"]["list_points"], 1)
        self.assertEqual(start["list_points"], sum(part["list_points"] for part in parts.values()))
        self.assertAlmostEqual(start["kb"], sum(part["kb"] for part in parts.values()), delta=0.3)
        self.assertEqual(start["not_read"], 0)

    def test_m2bs_two_parts_are_the_two_outputs_its_session_start_prints(self) -> None:
        """Covers: B268, B287"""
        self.curating()
        self.write("memory/lessons/once.md", LESSON)
        config = load_machine_config(self.machine)
        printed = []
        for hook in (hooks.distillate, hooks.start_notes):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                hook(config, self.machine, self.environ, HookInput(cwd=str(self.project)))
            printed.append(out.getvalue())

        parts = self.parts()

        for name, text in zip(("m2b distillate", "m2b notices, rule and lessons"), printed):
            with self.subTest(name=name):
                self.assertAlmostEqual(parts[name]["kb"], len(text.encode("utf-8")) / 1024, delta=0.05)

    def test_a_rule_with_paths_is_listed_and_left_out_of_the_sum(self) -> None:
        """Covers: B268"""
        self.curating()
        self.put(self.claude / "rules" / "web.md", "---\npaths:\n  - src/**/*.ts\n---\n- Use strict mode\n")

        start = self.start()
        rule = next(part for part in start["parts"] if part["name"].endswith("web.md"))

        self.assertEqual(rule["when"], "only when a matching file is read")
        self.assertEqual(rule["list_points"], 1)
        others = [part for part in start["parts"] if part is not rule]
        self.assertEqual(start["list_points"], sum(part["list_points"] for part in others))

    def test_a_file_that_cannot_be_read_is_named_as_not_read_and_never_counted_as_empty(self) -> None:
        """Covers: B268"""
        self.curating()
        locked = self.put(self.project / "CLAUDE.md", "- a point\n")
        locked.chmod(0)
        self.addCleanup(locked.chmod, 0o644)
        if os.access(locked, os.R_OK):
            self.skipTest("this user reads a file without read permission")

        start = self.start()
        parts = {part["name"]: part for part in start["parts"]}

        self.assertEqual(
            parts["~/work/acme-shop/CLAUDE.md"], {"name": "~/work/acme-shop/CLAUDE.md", "not_read": "Permission denied"}
        )
        self.assertEqual(start["not_read"], 1)
        out = self.run_command("status")[1]
        self.assertIn("  ~/work/acme-shop/CLAUDE.md: not read (Permission denied)\n", out)
        self.assertIn(", 1 not read\n", out)

    def test_an_output_style_the_settings_name_that_cannot_be_found_is_not_read(self) -> None:
        """Covers: B268"""
        self.curating()
        self.put(self.claude / "settings.json", json.dumps({"outputStyle": "Explanatory"}))

        self.assertEqual(
            self.parts()["output style Explanatory"], {"name": "output style Explanatory", "not_read": "not found"}
        )

    def test_the_style_the_settings_name_is_found_in_the_users_output_styles(self) -> None:
        """Covers: B268"""
        self.curating()
        self.put(self.claude / "output-styles" / "brief.md", "---\nname: Brief\n---\n- One line\n")
        self.put(self.claude / "settings.json", json.dumps({"outputStyle": "Brief"}))

        name = f"output style Brief ({self.claude / 'output-styles' / 'brief.md'})"
        self.assertEqual(self.parts()[name]["list_points"], 1)

    def test_a_quoted_name_and_flag_in_a_styles_frontmatter_mean_the_plain_value(self) -> None:
        """Covers: B268"""
        self.curating()
        self.put(self.claude / "output-styles" / "brief.md", '---\nname: "Brief"\n---\n- One line\n')
        self.put(self.claude / "settings.json", json.dumps({"outputStyle": "Brief"}))
        self.assertIn(f"output style Brief ({self.claude / 'output-styles' / 'brief.md'})", self.parts())

        self.plugin_style(STYLE.replace("force-for-plugin: true", "force-for-plugin: 'true'"))
        self.assertTrue(any(name.startswith("output style tidy:plain") for name in self.parts()))

    def test_a_settings_file_that_cannot_be_read_leaves_the_style_not_read(self) -> None:
        """Covers: B268"""
        self.curating()
        self.put(self.claude / "settings.json", "{not json")

        part = self.parts()["output style"]

        self.assertTrue(part["not_read"].startswith(f"{self.claude / 'settings.json'} could not be read: "))
        self.assertIn("line 1", part["not_read"])

    def test_a_distillate_that_is_not_downloaded_or_cannot_be_read_is_not_read_and_a_missing_one_is_left_out(
        self,
    ) -> None:
        """Covers: B268"""
        self.curating()
        with mock.patch.object(DatalessGuard, "is_evicted", side_effect=lambda path: Path(path).name == "MEMORY.md"):
            self.assertEqual(self.parts()["m2b distillate"]["not_read"], "not downloaded to this machine")
        with mock.patch.object(FolderStore, "read_bytes", side_effect=StoreError("memory/MEMORY.md is locked")):
            self.assertEqual(self.parts()["m2b distillate"]["not_read"], "memory/MEMORY.md is locked")

        (self.store_root / "memory" / "MEMORY.md").unlink()

        self.assertFalse(any(name.startswith("m2b") for name in self.parts()))

    def test_lessons_that_are_not_downloaded_are_not_read_beside_the_distillate(self) -> None:
        """Covers: B268"""
        self.curating()
        self.write(
            "memory/lessons/once.md",
            "---\nkind: knowledge\ntarget: every project\nkept: 2026-11-20\n---\n# Once\n\nSay it once.\n",
        )
        with mock.patch.object(DatalessGuard, "is_evicted", side_effect=lambda path: Path(path).name == "once.md"):
            parts = self.parts()

        self.assertEqual(parts["m2b lessons"]["not_read"], "not downloaded to this machine")
        self.assertNotIn("not_read", parts["m2b distillate"])

    def test_a_plugin_that_is_not_enabled_forces_no_style(self) -> None:
        """Covers: B268"""
        self.curating()
        self.plugin_style(enabled=False)

        self.assertFalse(any(name.startswith("output style") for name in self.parts()))

    def test_a_worktree_counts_the_auto_memory_of_its_main_repository(self) -> None:
        """Covers: B268"""
        self.curating()
        main = self.user_home / "code" / "shop"
        worktree_git = main / ".git" / "worktrees" / "fix"
        worktree_git.mkdir(parents=True)
        self.put(worktree_git / "commondir", "../..\n")
        worktree = self.user_home / "trees" / "fix"
        self.put(worktree / ".git", f"gitdir: {worktree_git}\n")
        self.environ["CLAUDE_PROJECT_DIR"] = str(worktree)
        memory = self.put(self.claude / "projects" / _key(main.resolve()) / "memory" / "MEMORY.md", "- one\n")

        self.assertIn(str(memory), self.parts())

    def test_only_the_first_200_lines_of_the_auto_memory_count(self) -> None:
        """Covers: B268"""
        self.curating()
        memory = self.claude / "projects" / _key(self.project) / "memory" / "MEMORY.md"
        self.put(memory, "".join(f"- line {number}\n" for number in range(300)))

        self.assertEqual(self.parts()[str(memory)]["list_points"], 200)

    def test_a_folder_the_distillate_is_off_for_counts_nothing_of_m2b(self) -> None:
        """Covers: B268"""
        self.set_up(calendar="none", distillate={"skip_under": [str(self.project)]})
        self.write("memory/MEMORY.md", test_runner.MEMORY)

        part = self.parts()["m2b distillate (off in this folder)"]

        self.assertEqual((part["kb"], part["list_points"]), (0.0, 0))

    def test_it_only_reads_and_starts_no_model(self) -> None:
        """Covers: B268"""
        self.curating()
        self.put(self.claude / "CLAUDE.md", "- a point\n")
        self.put(self.project / "CLAUDE.md", "- a point\n")
        self.plugin_style()
        before = self.fingerprint()

        self.start()

        self.assertEqual(self.fingerprint(), before)
        self.assertEqual(self.calls(), [])

    def test_the_text_form_names_the_sum_and_one_line_per_file(self) -> None:
        """Covers: B268"""
        self.curating()
        self.put(self.project / "CLAUDE.md", "- a point\n")

        out = self.run_command("status")[1]

        self.assertRegex(out, r"\nsession start in ~/work/acme-shop: [0-9.]+ KB, [0-9]+ list points\n")
        self.assertIn("  ~/work/acme-shop/CLAUDE.md: 0.0 KB, 1 list points\n", out)

    def fingerprint(self) -> dict[str, str]:
        """Every file under Claude Code's folder, the home folder and the store, with a hash of its bytes."""
        seen: dict[str, str] = {}
        for root in (self.claude, self.user_home, self.store_root):
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    seen[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        return seen
