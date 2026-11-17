"""``m2b distillate off / on``: projects whose sessions get no distillate."""

from __future__ import annotations

import json
import unittest
from typing import Any
from unittest import mock

import test_commands
from m2b import cli
from m2b.config.machine import load_machine_config
from m2b.store.guard import DatalessGuard
from store_contract import FakeEviction

MEMORY = (
    "# Memory\n\n## Facts\n\n- Dana likes old maps (dana.md)\n\n"
    "### Acme Ltd (Acme, Kim Lee)\n- Kim Lee leads Acme's IT (kim-lee.md)\n- Acme pays within 30 days (acme.md)\n\n"
    "### Riverside Choir (choir)\n- The choir meets on Wednesdays (choir.md)\n\n"
    "## Current\n\n- Shed\n\n### Acme Ltd (Acme)\n- Export audit under way (since 2026-11-02)\n"
)


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


class DistillateTopicTest(test_commands.CommandTest):
    """``m2b distillate topic``: one topic's lines, as the distillate holds them at the call."""

    def setUp(self) -> None:
        super().setUp()
        self.set_up(calendar="none")
        self.index = self.store_root / "memory" / "MEMORY.md"
        self.index.parent.mkdir()
        self.index.write_text(MEMORY, encoding="utf-8")

    def topic(self, name: str) -> dict[str, Any]:
        code, out, err = self.run_command("distillate", "topic", "--json", "--", name)
        self.assertEqual(code, cli.EXIT_OK, err)
        answer: dict[str, Any] = json.loads(out)
        return answer

    def test_a_topic_comes_with_its_facts_and_its_current_items(self) -> None:
        """Covers: B188"""
        self.assertEqual(
            self.topic("Acme Ltd"),
            {
                "name": "Acme Ltd",
                "found": True,
                "facts": ["Kim Lee leads Acme's IT", "Acme pays within 30 days"],
                "current": ["Export audit under way (since 2026-11-02)"],
            },
        )

    def test_the_lines_are_those_of_the_call_not_of_an_earlier_one(self) -> None:
        """Covers: B188"""
        self.topic("Riverside Choir")
        self.index.write_text(MEMORY.replace("on Wednesdays", "on Thursdays"), encoding="utf-8")

        self.assertEqual(self.topic("Riverside Choir")["facts"], ["The choir meets on Thursdays"])

    def test_a_name_the_distillate_holds_no_topic_of_is_not_found(self) -> None:
        """Covers: B188"""
        for name in ("Globex", "acme ltd", "Dana likes old maps", "Facts"):
            with self.subTest(name=name):
                self.assertEqual(self.topic(name), {"name": name, "found": False, "facts": [], "current": []})

    def test_a_store_without_a_distillate_holds_no_topic(self) -> None:
        """Covers: B188"""
        self.index.unlink()

        self.assertEqual(self.topic("Acme Ltd"), {"name": "Acme Ltd", "found": False, "facts": [], "current": []})

    def test_no_line_comes_with_a_character_that_draws_nothing(self) -> None:
        """Covers: B188"""
        planted = MEMORY.replace("leads Acme's IT", "leads\u00ad Acme's IT\U000e0041").replace(
            "audit under way", "audit\u200b under way"
        )
        self.index.write_text(planted, encoding="utf-8")

        answer = self.topic("Acme Ltd")

        self.assertEqual(answer["facts"][0], "Kim Lee leads Acme's IT")
        self.assertEqual(answer["current"], ["Export audit under way (since 2026-11-02)"])

    def test_a_name_that_begins_with_a_dash_is_a_name(self) -> None:
        self.index.write_text(MEMORY.replace("### Riverside Choir (choir)", "### -json (choir)"), encoding="utf-8")

        self.assertEqual(self.topic("-json")["facts"], ["The choir meets on Wednesdays"])

    def test_without_json_the_lines_are_printed_under_the_name(self) -> None:
        """Covers: B188"""
        code, out, _ = self.run_command("distillate", "topic", "Acme Ltd")

        self.assertEqual(code, cli.EXIT_OK)
        self.assertEqual(
            out,
            "Acme Ltd, as the distillate holds it now\n"
            "- Kim Lee leads Acme's IT\n"
            "- Acme pays within 30 days\n"
            "Current\n"
            "- Export audit under way (since 2026-11-02)\n",
        )

        code, out, _ = self.run_command("distillate", "topic", "Globex")

        self.assertEqual(code, cli.EXIT_OK)
        self.assertEqual(out, "the distillate holds no topic named Globex now\n")

    def test_a_distillate_that_is_not_downloaded_is_said_and_never_an_empty_topic(self) -> None:
        """Covers: B188"""
        eviction = FakeEviction()
        eviction.evicted.add(self.index)
        guard = DatalessGuard(True, lstat=eviction.lstat)

        with mock.patch("m2b.store.factory.guard_for_platform", return_value=guard):
            code, out, err = self.run_command("distillate", "topic", "Acme Ltd", "--json")

        self.assertEqual(code, cli.EXIT_UNREACHABLE)
        self.assertEqual(out, "")
        self.assertIn("memory/MEMORY.md is not downloaded to this machine", err)

    def test_the_topic_must_be_named(self) -> None:
        code, _, _ = self.run_command("distillate", "topic")

        self.assertEqual(code, cli.EXIT_USAGE)


class DistillateTopicsTest(test_commands.CommandTest):
    """``m2b distillate topics``: what every session starts with, and each topic with its counts."""

    def setUp(self) -> None:
        super().setUp()
        self.set_up(calendar="none")
        self.index = self.store_root / "memory" / "MEMORY.md"
        self.index.parent.mkdir()
        self.index.write_text(MEMORY, encoding="utf-8")

    def topics(self) -> dict[str, Any]:
        code, out, err = self.run_command("distillate", "topics", "--json")
        self.assertEqual(code, cli.EXIT_OK, err)
        answer: dict[str, Any] = json.loads(out)
        return answer

    def test_the_facts_every_session_starts_with_come_with_their_fact_file_and_each_topic_with_its_counts(self) -> None:
        """Covers: B225"""
        self.assertEqual(
            self.topics(),
            {
                "facts": [{"statement": "Dana likes old maps", "file": "dana.md"}],
                "current": ["Shed"],
                "topics": [
                    {"name": "Acme Ltd", "facts": 2, "current": 1},
                    {"name": "Riverside Choir", "facts": 1, "current": 0},
                ],
            },
        )

    def test_a_fact_line_without_a_fact_file_is_a_fact_without_one(self) -> None:
        """Covers: B225"""
        without_file = MEMORY.replace("- Dana likes old maps (dana.md)", "- Dana likes old maps")
        self.index.write_text(without_file, encoding="utf-8")

        self.assertEqual(self.topics()["facts"], [{"statement": "Dana likes old maps", "file": None}])

    def test_a_store_without_a_distillate_starts_every_session_with_nothing(self) -> None:
        """Covers: B225"""
        self.index.unlink()

        self.assertEqual(self.topics(), {"facts": [], "current": [], "topics": []})

    def test_no_line_comes_with_a_character_that_draws_nothing(self) -> None:
        """Covers: B225"""
        self.index.write_text(MEMORY.replace("likes old maps", "likes​ old maps\U000e0041"), encoding="utf-8")

        self.assertEqual(self.topics()["facts"][0]["statement"], "Dana likes old maps")

    def test_without_json_the_lines_are_printed_under_what_they_are(self) -> None:
        """Covers: B225"""
        code, out, _ = self.run_command("distillate", "topics")

        self.assertEqual(code, cli.EXIT_OK)
        self.assertEqual(
            out,
            "Every session starts with\n"
            "- Dana likes old maps (dana.md)\n"
            "Current\n"
            "- Shed\n"
            "Topics, given to a session when a prompt names them\n"
            "- Acme Ltd: 2 facts, 1 current\n"
            "- Riverside Choir: 1 fact, 0 current\n",
        )

    def test_a_distillate_that_is_not_downloaded_is_said_and_never_one_without_lines(self) -> None:
        """Covers: B225"""
        eviction = FakeEviction()
        eviction.evicted.add(self.index)
        guard = DatalessGuard(True, lstat=eviction.lstat)

        with mock.patch("m2b.store.factory.guard_for_platform", return_value=guard):
            code, out, err = self.run_command("distillate", "topics", "--json")

        self.assertEqual(code, cli.EXIT_UNREACHABLE)
        self.assertEqual(out, "")
        self.assertIn("memory/MEMORY.md is not downloaded to this machine", err)


if __name__ == "__main__":
    unittest.main()
