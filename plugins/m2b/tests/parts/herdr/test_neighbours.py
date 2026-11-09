"""Neighbour sessions from a herdr snapshot: the hook, the parser and the command."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from m2b_herdr import neighbours
from m2b_herdr.neighbours import HEADER, MAX_BLOCK_BYTES, HerdrError

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
COMMAND = PLUGIN_ROOT / "bin" / "m2b-herdr"
FAKE_HERDR = Path(__file__).resolve().parent / "fakes" / "fake_herdr.py"


def agent(pane: str, workspace: str, status: str, title: str | None, cwd: str | None) -> dict[str, Any]:
    return {
        "pane_id": pane,
        "workspace_id": workspace,
        "tab_id": f"{workspace}-t1",
        "terminal_id": f"term-{pane}",
        "agent_status": status,
        "terminal_title_stripped": title,
        "cwd": cwd,
        "focused": False,
    }


def snapshot(*agents: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "0.9.3",
        "protocol": 22,
        "workspaces": [
            {"workspace_id": "w1", "label": "garden-shed", "number": 1},
            {"workspace_id": "w2", "label": "acme-invoices", "number": 2},
        ],
        "tabs": [],
        "panes": [],
        "layouts": [],
        "agents": list(agents),
    }


def reply(snap: object) -> str:
    return json.dumps({"id": "r1", "result": {"type": "session_snapshot", "snapshot": snap}})


THREE_AGENTS = snapshot(
    agent("p1", "w1", "working", "✳ ⠂ Plan the shed roof", "/home/alex/projects/garden-shed"),
    agent("p2", "w2", "idle", "Fix the invoice export", "/home/alex/work/acme-invoices"),
    agent("p3", "w2", "done", None, None),
)


class FakeRun:
    """Stands in for ``subprocess.run``; records the command line."""

    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = "", error: Exception | None = None):
        self.stdout, self.returncode, self.stderr, self.error = stdout, returncode, stderr, error
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str], **options: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        self.options = options
        if self.error is not None:
            raise self.error
        return subprocess.CompletedProcess(command, self.returncode, self.stdout, self.stderr)


IN_HERDR = {"HERDR_PANE_ID": "p3"}


class HookTest(unittest.TestCase):
    def test_lists_the_other_agents_with_workspace_task_state_and_place(self) -> None:
        """Covers: B10"""
        run = FakeRun(stdout=reply(THREE_AGENTS))

        output = neighbours.hook_output(IN_HERDR, run)

        self.assertEqual(
            output,
            f"{HEADER}\n"
            "- garden-shed · Plan the shed roof · working · projects/garden-shed\n"
            "- acme-invoices · Fix the invoice export · idle · work/acme-invoices\n",
        )
        self.assertEqual(run.calls, [["herdr", "api", "snapshot"]])
        self.assertEqual(run.options["timeout"], 2.0)

    def test_idle_and_finished_sessions_stay_listed_and_states_are_plain_words(self) -> None:
        """Covers: B10"""
        snap = snapshot(
            agent("p1", "w1", "blocked", "Ask first", None),
            agent("p2", "w1", "done", "Finished", None),
            agent("p4", "w1", "unknown", "Odd", None),
            agent("p5", "w1", "sleeping", "Newer state", None),
        )

        output = neighbours.hook_output(IN_HERDR, FakeRun(stdout=reply(snap)))

        self.assertIn("- garden-shed · Ask first · waiting for approval\n", output)
        self.assertIn("- garden-shed · Finished · done, not looked at yet\n", output)
        self.assertIn("- garden-shed · Odd · state unknown\n", output)
        self.assertIn("- garden-shed · Newer state · state unknown\n", output)

    def test_prints_nothing_outside_herdr(self) -> None:
        """Covers: B7"""
        run = FakeRun(stdout=reply(THREE_AGENTS))

        self.assertEqual(neighbours.hook_output({}, run), "")
        self.assertEqual(neighbours.hook_output({"HERDR_PANE_ID": ""}, run), "")
        self.assertEqual(run.calls, [])

    def test_prints_nothing_inside_a_curation_run(self) -> None:
        """Covers: B7"""
        run = FakeRun(stdout=reply(THREE_AGENTS))

        self.assertEqual(neighbours.hook_output({**IN_HERDR, "M2B_CURATION_RUN": "1"}, run), "")
        self.assertEqual(run.calls, [])

    def test_no_other_session_prints_nothing(self) -> None:
        only_me = snapshot(agent("p3", "w1", "working", "Me", None))

        self.assertEqual(neighbours.hook_output(IN_HERDR, FakeRun(stdout=reply(only_me))), "")

    def test_a_failed_snapshot_is_one_line_saying_herdr_could_not_be_read(self) -> None:
        """Covers: B7"""
        failures = {
            "missing": FakeRun(error=FileNotFoundError("herdr")),
            "slow": FakeRun(error=subprocess.TimeoutExpired(["herdr"], 2.0)),
            "exit": FakeRun(returncode=1, stderr="no server is running\n"),
            "garbled": FakeRun(stdout="not json"),
            "no snapshot": FakeRun(stdout=json.dumps({"id": "r1", "result": {}})),
            "result not an object": FakeRun(stdout=json.dumps({"id": "r1", "result": []})),
            "agents not a list": FakeRun(stdout=reply({"agents": {}})),
        }
        for name, run in failures.items():
            with self.subTest(name):
                output = neighbours.hook_output(IN_HERDR, run)
                self.assertEqual(output.count("\n"), 1)
                self.assertTrue(output.startswith("m2b neighbours: herdr could not be read ("), output)

        self.assertIn("within 2 seconds", neighbours.hook_output(IN_HERDR, failures["slow"]))
        self.assertIn("no server is running", neighbours.hook_output(IN_HERDR, failures["exit"]))

    def test_the_herdr_command_can_be_named(self) -> None:
        run = FakeRun(stdout=reply(THREE_AGENTS))

        neighbours.hook_output({**IN_HERDR, "M2B_HERDR": "/opt/herdr/bin/herdr"}, run)

        self.assertEqual(run.calls, [["/opt/herdr/bin/herdr", "api", "snapshot"]])


class ParseTest(unittest.TestCase):
    def test_entries_without_a_pane_are_skipped(self) -> None:
        snap = snapshot(
            {"workspace_id": "w1", "agent_status": "idle"}, "not an agent", agent("p1", "w1", "idle", "A", None)
        )

        found = neighbours.neighbours(snap, own_pane="p9")

        self.assertEqual([n.task for n in found], ["A"])

    def test_an_unknown_workspace_falls_back_to_its_id_then_to_session(self) -> None:
        snap = snapshot(
            agent("p1", "w9", "idle", "A", None), {**agent("p2", "w1", "idle", "B", None), "workspace_id": None}
        )

        found = neighbours.neighbours(snap, own_pane=None)

        self.assertEqual([n.workspace for n in found], ["w9", "session"])

    def test_the_task_loses_the_agent_glyph_and_a_spinner_but_keeps_short_words(self) -> None:
        self.assertEqual(neighbours.task_of("✳ ⠐ Plan the roof"), "Plan the roof")
        self.assertEqual(neighbours.task_of("* Plan the roof"), "Plan the roof")
        self.assertEqual(neighbours.task_of("A plan for Q3"), "A plan for Q3")
        self.assertEqual(neighbours.task_of("✳"), "")
        self.assertEqual(neighbours.task_of(None), "")

    def test_a_missing_task_says_so_and_a_missing_place_is_left_out(self) -> None:
        line = neighbours.Neighbour(workspace="garden-shed", task="", state="idle", place="").line()

        self.assertEqual(line, "- garden-shed · no title · idle")

    def test_the_place_is_the_last_two_parts_of_the_folder(self) -> None:
        self.assertEqual(neighbours.place_of("/home/alex/projects/garden-shed/"), "projects/garden-shed")
        self.assertEqual(neighbours.place_of("/tmp"), "tmp")
        self.assertEqual(neighbours.place_of(None), "")


class BudgetTest(unittest.TestCase):
    def test_a_long_list_is_cut_with_and_n_more_within_the_budget(self) -> None:
        """Covers: B10"""
        found = [neighbours.Neighbour(f"workspace-{n}", "x" * 80, "idle", f"projects/p{n}") for n in range(60)]

        block = neighbours.render(found)

        self.assertLessEqual(len(block.encode("utf-8")), MAX_BLOCK_BYTES)
        shown = block.count("\n- ")
        self.assertLess(shown, 60)
        self.assertTrue(block.endswith(f"and {60 - shown} more\n"), block[-40:])

    def test_a_list_within_the_budget_is_not_cut(self) -> None:
        found = [neighbours.Neighbour("w", "task", "idle", "") for _ in range(3)]

        self.assertNotIn("more", neighbours.render(found))


class PartTest(unittest.TestCase):
    def test_the_part_is_on_only_when_m2b_parts_list_says_so(self) -> None:
        rows = [{"name": "band", "on": True}, {"name": "herdr", "on": True}]
        self.assertTrue(neighbours.part_on({}, FakeRun(stdout=json.dumps(rows))))
        rows[1]["on"] = False
        self.assertFalse(neighbours.part_on({}, FakeRun(stdout=json.dumps(rows))))
        self.assertFalse(neighbours.part_on({}, FakeRun(stdout="not json")))
        self.assertFalse(neighbours.part_on({}, FakeRun(returncode=2, stdout="")))
        self.assertFalse(neighbours.part_on({}, FakeRun(error=subprocess.TimeoutExpired(["m2b"], 10))))
        run = FakeRun(stdout="[]")
        neighbours.part_on({"M2B_HOME": "/sb-test-home"}, run)
        self.assertEqual(run.calls[0][1:], ["parts", "list", "--json"])


class CommandTest(unittest.TestCase):
    """The installed command with a fake herdr, as the session-start hook runs it."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        base = Path(self._temp.name)
        self.reply = base / "reply.json"
        self.calls = base / "calls.txt"
        self.herdr = base / "herdr"
        self.herdr.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE_HERDR}" "$@"\n', encoding="utf-8")
        self.herdr.chmod(0o755)
        home = base / "home"
        self.config = home / ".config" / "m2b" / "config.json"
        self.part("on")
        self.environ = {
            "PATH": os.environ.get("PATH", ""),
            "M2B_HOME": str(home),
            "M2B_PYTHON": sys.executable,
            "M2B_HERDR": str(self.herdr),
            "FAKE_HERDR_REPLY": str(self.reply),
            "FAKE_HERDR_CALLS": str(self.calls),
        }

    def part(self, state: str) -> None:
        """This machine's config with the herdr part on or off, written as ``m2b parts`` reads it."""
        self.config.parent.mkdir(parents=True, exist_ok=True)
        raw = {"version": 1, "machine_id": "sb-test-m1", "store": {"backend": "folder", "path": "/sb-test-store"}}
        raw["parts"] = {"herdr": {"on": state == "on"}}
        self.config.write_text(json.dumps(raw), encoding="utf-8")

    def _run(self, *arguments: str, **environ: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(COMMAND), *arguments], capture_output=True, text=True, env={**self.environ, **environ}, timeout=20
        )

    def test_the_hook_lists_the_neighbours_and_exits_0(self) -> None:
        """Covers: B10"""
        self.reply.write_text(reply(THREE_AGENTS), encoding="utf-8")

        result = self._run("neighbours", HERDR_PANE_ID="p3")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertIn("- acme-invoices · Fix the invoice export · idle · work/acme-invoices\n", result.stdout)

    def test_with_the_part_off_or_m2b_not_set_up_the_hook_prints_nothing_and_asks_herdr_nothing(self) -> None:
        """Covers: B64"""
        self.reply.write_text(reply(THREE_AGENTS), encoding="utf-8")
        self.part("off")
        off = self._run("neighbours", HERDR_PANE_ID="p3")
        self.config.unlink()
        not_set_up = self._run("neighbours", HERDR_PANE_ID="p3")

        for result in (off, not_set_up):
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
        self.assertFalse(self.calls.exists())

    def test_the_hook_gives_up_after_two_seconds_with_one_line(self) -> None:
        """Covers: B7"""
        self.reply.write_text(reply(THREE_AGENTS), encoding="utf-8")

        result = self._run("neighbours", HERDR_PANE_ID="p3", FAKE_HERDR_SLEEP="5")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout, "m2b neighbours: herdr could not be read (herdr did not answer within 2 seconds).\n"
        )

    def test_check_says_whether_herdr_answers_and_only_reads(self) -> None:
        self.reply.write_text(reply(THREE_AGENTS), encoding="utf-8")

        answered = self._run("check")
        failed = self._run("check", FAKE_HERDR_EXIT="1")

        self.assertEqual(answered.returncode, 0)
        self.assertIn("herdr answers: 3 agent sessions open", answered.stdout)
        self.assertIn("outside herdr", answered.stdout)
        self.assertEqual(failed.returncode, 1)
        self.assertIn("herdr could not be read", failed.stdout)
        self.assertEqual(self.calls.read_text(encoding="utf-8").splitlines(), ["api snapshot", "api snapshot"])


class ReadSnapshotTest(unittest.TestCase):
    def test_returns_the_snapshot_object(self) -> None:
        self.assertEqual(neighbours.read_snapshot("herdr", FakeRun(stdout=reply(THREE_AGENTS))), THREE_AGENTS)

    def test_an_empty_answer_is_an_error(self) -> None:
        with self.assertRaises(HerdrError):
            neighbours.read_snapshot("herdr", FakeRun(stdout="{}"))


if __name__ == "__main__":
    unittest.main()
