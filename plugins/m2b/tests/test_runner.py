"""The curation run: preflight, the steps in their order, the review and the run record."""

from __future__ import annotations

import datetime
import json
import os
import signal
import sys
from pathlib import Path
from typing import Any
from unittest import mock

import test_commands
from m2b import candidates, expiry, launcher, parts
from m2b.atomic_file import HIDDEN_TEMP_PREFIX
from m2b.config import machine
from m2b.config.profile import save_profile
from m2b.config.store_settings import load_store_settings
from m2b.curate import machine_state, memory_guard, model, runner
from m2b.run_record import FAILED, RUN_RECORD, RUNNING, SUCCEEDED, load_run_record
from m2b.store.base import StoreReadError
from m2b.store.guard import DatalessGuard
from m2b.tasks import markers
from m2b.tasks.base import Task, TasksUnreachableError
from m2b.tasks.factory import open_tasks
from store_contract import FakeEviction

CORE_BIN = launcher.PLUGIN_ROOT / "bin"
MEMORY = "# Memory\n\n## Facts\n\n## Current\n"
CAPTURE = "---\ncreated: 2026-11-07T08:00:00+01:00\nsource: cli\n---\nDana likes old maps\n"
START = datetime.datetime(2026, 11, 7, 9, 0).astimezone()

UNSORTED = (
    "# Memory\n\n## Facts\n\n- Dana likes old maps (dana.md)\n- Kim Lee leads Acme's IT (kim-lee.md)\n\n## Current\n"
)
SORTED = (
    "# Memory\n\n## Facts\n\n- Dana likes old maps (dana.md)\n\n"
    "### Acme Ltd (Acme Ltd, Acme, Kim Lee)\n- Kim Lee leads Acme's IT (kim-lee.md)\n\n## Current\n"
)

INGEST_FILES_THE_CAPTURE = [
    {"tool": "Bash", "command": "m2b ingest list --json"},
    {"tool": "Bash", "command": "m2b ingest note <capture:cli> 'filed: nothing to file'"},
    {"tool": "Bash", "command": "m2b ingest finish <capture:cli>"},
]

# A module step: writes what it saw (working folder, variables, the run record) next to itself.
LINKED_NOTE = "20261103T081200Z-cli-c3d4.md"
PART_STEP = """#!{python}
import json, os, sys
from pathlib import Path
record = Path(os.environ["SB_TEST_STORE"], "state/core/last-run.json")
seen = {{
    "argv": sys.argv[1:],
    "cwd_entries": sorted(os.listdir(".")),
    "cwd": os.getcwd(),
    "curation_run": os.environ.get("M2B_CURATION_RUN"),
    "token": os.environ.get("M2B_RUN_TOKEN"),
    "record": json.loads(record.read_text()) if record.exists() else None,
}}
with open(Path(__file__).with_suffix(".seen"), "a") as out:
    out.write(json.dumps(seen) + "\\n")
sys.exit(int(os.environ.get("SB_TEST_PART_EXIT", "0")))
"""


class RunnerTest(test_commands.CommandTest):
    def setUp(self) -> None:
        super().setUp()
        self.actions = self.bin.parent / "model.json"
        self.model({})
        self.environ[model.MODEL_RUNNER_VARIABLE] = self.fake_program("claude", "fake_claude.py", self.actions)
        self.environ["PATH"] = os.pathsep.join([str(CORE_BIN), os.environ.get("PATH", "")])
        self.environ["M2B_PYTHON"] = sys.executable
        self.environ["M2B_STUB_STORE"] = str(self.store_root)
        self.environ["SB_TEST_STORE"] = str(self.store_root)
        self.installed = self.bin.parent / "installed_plugins.json"
        self.installed.write_text(json.dumps({"version": 2, "plugins": {}}), encoding="utf-8")
        self.environ[launcher.INSTALLED_PLUGINS_VARIABLE] = str(self.installed)
        self.claude_settings = self.bin.parent / "claude-config" / "settings.json"
        self.environ["CLAUDE_CONFIG_DIR"] = str(self.claude_settings.parent)
        self.eviction = FakeEviction()
        self.clock = START

    def curating(self, tasks: dict[str, Any] | None = None, **extra: Any) -> None:
        self.set_up(tasks, calendar="none", **extra)
        save_profile(self.store, {"version": 1, "owner": "Alex", "language": "en"})
        self.write("memory/MEMORY.md", MEMORY)

    def write(self, relative: str, text: str) -> None:
        target = self.store_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def capture(self, name: str = "20261107T070000Z-cli-a1b2.md") -> None:
        self.write(f"inbox/{name}", CAPTURE)

    def model(self, skills: dict[str, list[dict[str, Any]]], outcomes: dict[str, str] | None = None) -> None:
        outcomes = outcomes or {}
        script = {
            "skills": {
                f"/{skill}": {"actions": actions, "outcome": outcomes.get(skill, "success")}
                for skill, actions in skills.items()
            }
        }
        self.actions.write_text(json.dumps(script), encoding="utf-8")

    def calls(self) -> list[dict[str, Any]]:
        calls_file = Path(f"{self.actions}.calls")
        if not calls_file.exists():
            return []
        return [json.loads(line) for line in calls_file.read_text(encoding="utf-8").splitlines()]

    def run_curate(
        self, force: bool = True, fetch_timeout: float = 5, refresh_all: bool = False, sort_facts: bool = False
    ) -> runner.RunOutcome:
        guard = DatalessGuard(True, lstat=self.eviction.lstat)
        with mock.patch("m2b.store.factory.guard_for_platform", return_value=guard):
            return runner.curate(
                self.machine,
                self.environ,
                force=force,
                clock=lambda: self.clock,
                fetch_timeout_seconds=fetch_timeout,
                refresh_all=refresh_all,
                sort_facts=sort_facts,
            )

    def tasks(self) -> Any:
        return open_tasks(load_store_settings(self.store).tasks, self.store, {})

    def review_tasks(self) -> list[Any]:
        return self.tasks().items(marker=markers.REVIEW, include_completed=True)

    def repairable_link(self) -> None:
        """A broken memory link with one candidate: the one finding the lint model step is started for."""
        self.write(
            f"corpus/2026/11/{LINKED_NOTE}",
            "---\ncreated: 2026-11-03T09:12:00+01:00\nsource: cli\n---\nOffice at eight\n",
        )
        self.write("memory/dana.md", f"# Dana\n\n- Birthday on 3 March.\n\n## Evidence\n\n- [[{LINKED_NOTE[:-3]}]]\n")

    def part(self, name: str, slot: str) -> Path:
        """Turns a part on with a fake step script in ``slot`` and returns the file it reports into."""
        script = self.bin.parent / "parts" / f"{name}-step"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(PART_STEP.format(python=sys.executable), encoding="utf-8")
        script.chmod(0o755)
        fake = parts.Part(name, "a fake part", parts.PartStep(slot, (str(script), "run")))
        patcher = mock.patch.object(parts, "PARTS", tuple(fake if part.name == name else part for part in parts.PARTS))
        patcher.start()
        self.addCleanup(patcher.stop)
        machine.set_part_on(self.machine, name, True)
        return script.with_suffix(".seen")


class CleanRunTest(RunnerTest):
    def test_a_clean_run_files_the_inbox_runs_every_step_in_order_and_records_it(self) -> None:
        self.curating()
        self.capture()
        self.model({"m2b:ingest": INGEST_FILES_THE_CAPTURE})

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(list((self.store_root / "inbox").iterdir()), [])
        record = load_run_record(self.store)
        assert record is not None
        self.assertEqual(record.state, SUCCEEDED)
        self.assertEqual(record.machine_id, "sb-test-m1")
        self.assertEqual(
            [(step.name, step.result) for step in record.steps],
            [
                ("harvest", "succeeded"),
                ("ingest", "succeeded"),
                ("refresh", "skipped"),
                ("lint", "succeeded"),
                ("journal", "succeeded"),
                ("review", "succeeded"),
            ],
        )
        self.assertEqual(record.started_at, START)
        self.assertEqual(record.last_success, START)
        self.assertEqual(self.review_tasks(), [])
        self.assertIsNone(machine_state.load_backoff(self.machine))
        event = machine_state.last_event(self.machine)
        assert event is not None
        self.assertEqual(event.kind, machine_state.SUCCEEDED)

    def test_each_model_step_runs_fenced_with_its_own_rules_from_an_empty_folder(self) -> None:
        self.curating()
        self.repairable_link()
        self.capture()
        self.model({"m2b:ingest": INGEST_FILES_THE_CAPTURE})

        self.run_curate()

        calls = self.calls()
        self.assertEqual([call["arguments"][1] for call in calls], ["/m2b:ingest", "/m2b:lint"])
        store = f"/{self.store_root}"
        ingest_rules = calls[0]["arguments"][calls[0]["arguments"].index("--allowedTools") + 1 :][:6]
        self.assertEqual(
            ingest_rules,
            [
                "Bash(m2b ingest *)",
                "Bash(m2b search *)",
                "Bash(m2b curate report *)",
                f"Read({store}/inbox/**)",
                f"Read({store}/memory/**)",
                f"Edit({store}/memory/**)",
            ],
        )
        lint_rules = calls[1]["arguments"][calls[1]["arguments"].index("--allowedTools") + 1 :][:5]
        self.assertEqual(
            lint_rules,
            [
                "Bash(m2b lint *)",
                "Bash(m2b search *)",
                "Bash(m2b curate report *)",
                f"Read({store}/memory/**)",
                f"Edit({store}/memory/**)",
            ],
        )
        for call in calls:
            self.assertEqual(call["cwd_entries"], [])
            self.assertEqual(call["environment"]["M2B_CURATION_RUN"], "1")
            self.assertRegex(call["environment"]["M2B_RUN_TOKEN"] or "", r"\A[0-9a-f]{32}\Z")
        self.assertEqual(calls[0]["environment"]["M2B_RUN_TOKEN"], calls[1]["environment"]["M2B_RUN_TOKEN"])

    def test_a_fact_past_its_day_starts_the_refresh_step_allowed_that_file_alone(self) -> None:
        """Covers: B41"""
        self.curating()
        self.write("memory/sam.md", "---\nuntil: 2026-11-01\n---\n# Sam\n")
        self.write("memory/robin.md", "---\nuntil: 2026-12-01\n---\n# Robin\n")

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        [call] = self.calls()
        self.assertEqual(call["arguments"][1], "/m2b:refresh")
        store = f"/{self.store_root}"
        rules = call["arguments"][call["arguments"].index("--allowedTools") + 1 :][:7]
        self.assertEqual(
            rules,
            [
                "Bash(m2b refresh *)",
                "Bash(m2b curate report *)",
                f"Read({store}/memory/MEMORY.md)",
                f"Edit({store}/memory/MEMORY.md)",
                f"Read({store}/corpus/**)",
                f"Read({store}/memory/sam.md)",
                f"Edit({store}/memory/sam.md)",
            ],
        )

    def test_a_quiet_current_item_is_asked_about_and_the_next_run_applies_the_answer(self) -> None:
        """Covers: B42"""
        self.curating()
        current = "- Planning the trip to Porto (since 2026-09-01)\n"
        self.write("memory/MEMORY.md", f"# Memory\n\n## Facts\n\n## Current\n\n{current}")

        self.assertEqual(self.run_curate().state, SUCCEEDED)
        [question] = self.tasks().items(marker=markers.CURRENT)
        self.assertEqual(question.title, "Still current? Planning the trip to Porto")
        self.assertEqual(self.calls(), [])

        self.tasks().complete(question.id)
        self.clock = START + datetime.timedelta(days=1)
        self.assertEqual(self.run_curate().state, SUCCEEDED)

        self.assertIn(
            "- Planning the trip to Porto (since 2026-11-08)\n",
            (self.store_root / "memory" / "MEMORY.md").read_text(encoding="utf-8"),
        )
        self.assertEqual(self.tasks().items(marker=markers.CURRENT, include_completed=True), [])

    def test_refresh_all_runs_now_and_lets_the_refresh_step_date_the_undated_lines(self) -> None:
        """Covers: B43"""
        self.curating()
        self.capture()
        self.model({"m2b:ingest": INGEST_FILES_THE_CAPTURE})
        self.write("memory/robin.md", "# Robin\n")

        outcome = self.run_curate(force=False, refresh_all=True)

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        ingest, refresh = self.calls()
        self.assertEqual(refresh["arguments"][1], "/m2b:refresh")
        self.assertIsNone(ingest["environment"]["M2B_REFRESH_ALL"])
        self.assertEqual(
            json.loads(refresh["environment"]["M2B_REFRESH_ALL"]), {"facts": ["memory/robin.md"], "current": []}
        )
        store = f"/{self.store_root}"
        rules = refresh["arguments"][refresh["arguments"].index("--allowedTools") + 1 :][:8]
        self.assertEqual(
            rules,
            [
                "Bash(m2b refresh *)",
                "Bash(m2b search *)",
                "Bash(m2b curate report *)",
                f"Read({store}/memory/MEMORY.md)",
                f"Edit({store}/memory/MEMORY.md)",
                f"Read({store}/corpus/**)",
                f"Read({store}/memory/robin.md)",
                f"Edit({store}/memory/robin.md)",
            ],
        )

    def test_sort_facts_runs_now_and_its_step_may_edit_only_the_distillate(self) -> None:
        """Covers: B51"""
        self.curating()
        self.write("memory/MEMORY.md", UNSORTED)
        self.model({"m2b:sort-facts": [{"tool": "Write", "file_path": "<store>/memory/MEMORY.md", "content": SORTED}]})

        outcome = self.run_curate(force=False, sort_facts=True)

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        (call,) = self.calls()
        self.assertEqual(call["arguments"][1], "/m2b:sort-facts")
        store = f"/{self.store_root}"
        rules = call["arguments"][call["arguments"].index("--allowedTools") + 1 :][:4]
        self.assertEqual(
            rules,
            [
                "Bash(m2b refresh due *)",
                "Bash(m2b curate report *)",
                f"Read({store}/memory/**)",
                f"Edit({store}/memory/MEMORY.md)",
            ],
        )
        self.assertEqual((self.store_root / "memory" / "MEMORY.md").read_text(encoding="utf-8"), SORTED)
        assert outcome.record is not None
        self.assertIn(("sort", "succeeded"), [(step.name, step.result) for step in outcome.record.steps])

    def test_a_sorting_step_that_changes_a_statement_is_put_back_and_fails(self) -> None:
        """Covers: B51"""
        self.curating()
        self.write("memory/MEMORY.md", UNSORTED)
        changed = SORTED.replace("leads Acme's IT", "led Acme's IT")
        self.model({"m2b:sort-facts": [{"tool": "Write", "file_path": "<store>/memory/MEMORY.md", "content": changed}]})

        outcome = self.run_curate(sort_facts=True)

        self.assertEqual(outcome.state, FAILED)
        self.assertIn("sort: the sorting step changed the facts lines", outcome.message)
        self.assertEqual((self.store_root / "memory" / "MEMORY.md").read_text(encoding="utf-8"), UNSORTED)

    def test_a_sorting_step_that_fails_after_a_bad_edit_still_puts_the_file_back_and_says_so(self) -> None:
        """Covers: B51"""
        self.curating()
        self.write("memory/MEMORY.md", UNSORTED)
        changed = SORTED.replace("leads Acme's IT", "led Acme's IT")
        self.model(
            {
                "m2b:sort-facts": [
                    {"tool": "Write", "file_path": "<store>/memory/MEMORY.md", "content": changed},
                    {"tool": "Bash", "command": "rm -rf /"},
                ]
            }
        )

        outcome = self.run_curate(sort_facts=True)

        self.assertEqual(outcome.state, FAILED)
        self.assertIn("denied", outcome.message)
        self.assertIn("memory/MEMORY.md is as it was before", outcome.message)
        self.assertEqual((self.store_root / "memory" / "MEMORY.md").read_text(encoding="utf-8"), UNSORTED)

    def test_a_sorting_step_that_writes_a_heading_with_an_unsafe_character_is_put_back_and_fails(self) -> None:
        """Covers: B56"""
        self.curating()
        self.write("memory/MEMORY.md", UNSORTED)
        planted = SORTED.replace("### Acme Ltd (", "### Acme Ltd\u200b (")
        self.model({"m2b:sort-facts": [{"tool": "Write", "file_path": "<store>/memory/MEMORY.md", "content": planted}]})

        outcome = self.run_curate(sort_facts=True)

        self.assertEqual(outcome.state, FAILED)
        self.assertIn("U+200B", outcome.message)
        self.assertEqual((self.store_root / "memory" / "MEMORY.md").read_text(encoding="utf-8"), UNSORTED)

    def test_sorting_without_a_distillate_is_skipped(self) -> None:
        self.curating()
        (self.store_root / "memory" / "MEMORY.md").unlink()

        outcome = self.run_curate(sort_facts=True)

        assert outcome.record is not None
        self.assertIn(("sort", "skipped"), [(step.name, step.result) for step in outcome.record.steps])
        self.assertEqual(self.calls(), [])

    def test_an_ordinary_run_does_not_sort(self) -> None:
        self.curating()
        self.write("memory/MEMORY.md", UNSORTED)

        outcome = self.run_curate()

        assert outcome.record is not None
        self.assertNotIn("sort", [step.name for step in outcome.record.steps])
        self.assertEqual(self.calls(), [])

    def test_refresh_all_works_through_a_large_memory_in_batches(self) -> None:
        """Covers: B43"""
        self.curating()
        names = [f"memory/person-{number:02}.md" for number in range(12)]
        for name in names:
            self.write(name, "# Someone\n")

        outcome = self.run_curate(refresh_all=True)

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        batches = [json.loads(call["environment"]["M2B_REFRESH_ALL"])["facts"] for call in self.calls()]
        self.assertEqual(batches, [names[:10], names[10:]])

    def test_refresh_all_reports_an_undated_file_it_could_not_read(self) -> None:
        # Preflight downloads memory/; a file evicted again during the run is listed apart.
        self.curating()
        evicted = expiry.Undated([], [], ["memory/robin.md"], [])

        with mock.patch("m2b.curate.runner.expiry.undated", return_value=evicted):
            outcome = self.run_curate(refresh_all=True)

        self.assertEqual((outcome.state, self.calls()), (SUCCEEDED, []))
        record = load_run_record(self.store)
        assert record is not None
        [refresh] = [step for step in record.steps if step.name == "refresh"]
        self.assertEqual(refresh.detail, "no fact is past its day and no line read is undated")
        self.assertIn("memory/robin.md is not downloaded", self.review_tasks()[0].notes)

    def test_refresh_all_with_every_line_dated_skips_the_refresh_step(self) -> None:
        self.curating()
        self.write("memory/robin.md", "---\nuntil: 2026-12-01\n---\n# Robin\n")

        outcome = self.run_curate(refresh_all=True)

        self.assertEqual((outcome.state, self.calls()), (SUCCEEDED, []))

    def test_with_no_fact_past_its_day_the_refresh_step_is_skipped(self) -> None:
        """Covers: B67"""
        self.curating()
        self.write("memory/robin.md", "---\nuntil: 2026-12-01\n---\n# Robin\n")

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.calls(), [])
        record = load_run_record(self.store)
        assert record is not None
        [refresh] = [step for step in record.steps if step.name == "refresh"]
        self.assertEqual(refresh.result, "skipped")

    def test_an_empty_inbox_skips_the_ingest_model_run(self) -> None:
        """Covers: B67"""
        self.curating()
        self.repairable_link()

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED)
        self.assertEqual([call["arguments"][1] for call in self.calls()], ["/m2b:lint"])

    def test_without_a_link_the_model_can_repair_lint_runs_in_code_and_still_reports(self) -> None:
        self.curating()
        self.write("memory/dana.md", "# Dana\n\n- Birthday on 3 March.\n\n## Evidence\n\n- [[nothing-here.md]]\n")

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.calls(), [])
        record = load_run_record(self.store)
        assert record is not None
        self.assertIn(("lint", "succeeded"), [(step.name, step.result) for step in record.steps])
        (review,) = self.review_tasks()
        self.assertIn("lint: memory/dana.md links [[nothing-here.md]], which is no corpus file", review.notes)

    def test_without_the_model_lint_still_removes_the_old_temp_files(self) -> None:
        self.curating()
        leftover = self.store_root / "memory" / f"{HIDDEN_TEMP_PREFIX}dana.md"
        leftover.write_text("half written", encoding="utf-8")
        old = (START - datetime.timedelta(days=2)).timestamp()
        os.utime(leftover, (old, old))

        self.assertEqual(self.run_curate().state, SUCCEEDED)
        self.assertEqual(self.calls(), [])
        self.assertFalse(leftover.exists())

    def test_a_clean_store_starts_no_model_for_lint(self) -> None:
        """Covers: B67"""
        self.curating()

        self.assertEqual(self.run_curate().state, SUCCEEDED)
        self.assertEqual(self.calls(), [])
        record = load_run_record(self.store)
        assert record is not None
        self.assertEqual(record.steps[1].name, "ingest")
        self.assertEqual(record.steps[1].result, "skipped")

    def test_findings_of_the_model_steps_reach_the_review_and_info_stays_in_the_record(self) -> None:
        """Covers: B14"""
        self.curating()
        self.repairable_link()
        self.model(
            {
                "m2b:lint": [
                    {
                        "tool": "Bash",
                        "command": "m2b curate report --step lint --kind action --text 'dana.md links two notes'",
                    },
                    {"tool": "Bash", "command": "m2b curate report --step lint --kind info --text '3 notes evicted'"},
                ]
            }
        )

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED)
        (review,) = self.review_tasks()
        self.assertIn("lint: dana.md links two notes", review.notes)
        self.assertNotIn("evicted", review.notes)
        record = load_run_record(self.store)
        assert record is not None
        self.assertEqual(
            [(item.kind, item.text) for item in record.findings],
            [("action", "dana.md links two notes"), ("info", "3 notes evicted")],
        )
        self.assertEqual(list(machine_state.runs_dir(self.machine).iterdir()), [])

    def test_a_clean_run_completes_an_open_review_task(self) -> None:
        """Covers: B15"""
        self.curating()
        review_id = self.tasks().add("Review", notes=markers.marker_line(markers.REVIEW))

        self.run_curate()

        (review,) = self.review_tasks()
        self.assertEqual(review.id, review_id)
        self.assertTrue(review.completed)


class FailingStepTest(RunnerTest):
    def test_a_failing_ingest_lets_the_later_steps_run_names_the_failure_and_keeps_the_last_success(self) -> None:
        """Covers: B13"""
        self.curating()
        earlier = START - datetime.timedelta(hours=30)
        self.write(
            RUN_RECORD,
            json.dumps(
                {
                    "state": "succeeded",
                    "machine_id": "sb-test-m1",
                    "started_at": earlier.isoformat(),
                    "finished_at": earlier.isoformat(),
                }
            ),
        )
        self.capture()
        self.model({"m2b:ingest": []}, outcomes={"m2b:ingest": "error"})

        outcome = self.run_curate()

        self.assertEqual(outcome.state, FAILED)
        record = load_run_record(self.store)
        assert record is not None
        self.assertEqual(
            [(step.name, step.result) for step in record.steps],
            [
                ("harvest", "succeeded"),
                ("ingest", "failed"),
                ("refresh", "skipped"),
                ("lint", "succeeded"),
                ("journal", "succeeded"),
                ("review", "succeeded"),
            ],
        )
        self.assertEqual(record.last_success, earlier)
        self.assertIn("ingest", record.message)
        (review,) = self.review_tasks()
        self.assertIn("ingest", review.notes)
        self.assertEqual(len(list((self.store_root / "inbox").iterdir())), 1)
        backoff = machine_state.load_backoff(self.machine)
        assert backoff is not None
        self.assertEqual(backoff.failures, 1)

    def test_a_denied_tool_call_fails_the_step_and_reaches_the_review(self) -> None:
        self.curating()
        self.repairable_link()
        self.model({"m2b:lint": [{"tool": "Bash", "command": "rm -rf /"}]})

        outcome = self.run_curate()

        self.assertEqual(outcome.state, FAILED)
        (review,) = self.review_tasks()
        self.assertIn("rm -rf /", review.notes)

    def test_an_inbox_that_cannot_be_listed_fails_ingest_and_the_later_steps_still_run(self) -> None:
        """Covers: B13"""
        self.curating()
        real_scan = runner.Store.scan

        def scan(store: Any, folder: str) -> Any:
            if folder == "inbox":
                raise runner.StoreError("inbox could not be listed: Operation not permitted")
            return real_scan(store, folder)

        with mock.patch.object(runner.Store, "scan", scan):
            outcome = self.run_curate()

        self.assertEqual(outcome.state, FAILED)
        record = load_run_record(self.store)
        assert record is not None
        self.assertEqual([(step.name, step.result) for step in record.steps][1], ("ingest", "failed"))
        self.assertEqual(record.steps[-1].name, "review")
        self.assertIsNotNone(machine_state.load_backoff(self.machine))

    def test_a_failure_outside_any_step_after_preflight_still_finishes_the_run_record(self) -> None:
        self.curating()

        with mock.patch("m2b.curate.runner.report.open_run", side_effect=OSError("disk full")):
            outcome = self.run_curate()

        self.assertEqual(outcome.state, FAILED)
        record = load_run_record(self.store)
        assert record is not None
        self.assertEqual(record.state, FAILED)
        self.assertIn("disk full", record.message)
        self.assertIsNotNone(machine_state.load_backoff(self.machine))

    def test_after_a_failure_a_success_resets_the_backoff(self) -> None:
        self.curating()
        machine_state.record_failure(self.machine, START - datetime.timedelta(hours=2))

        self.assertEqual(self.run_curate().state, SUCCEEDED)

        self.assertIsNone(machine_state.load_backoff(self.machine))


class PreflightTest(RunnerTest):
    def test_a_machine_not_named_in_store_json_refuses_and_writes_only_its_local_log(self) -> None:
        """Covers: B62"""
        self.curating()
        self.capture()
        settings = json.loads((self.store_root / "store.json").read_text(encoding="utf-8"))
        settings["curating_machine"] = "sb-test-m2"
        (self.store_root / "store.json").write_text(json.dumps(settings), encoding="utf-8")

        outcome = self.run_curate()

        self.assertEqual(outcome.state, runner.NOT_CURATING)
        self.assertIn("sb-test-m2", outcome.message)
        self.assertFalse((self.store_root / RUN_RECORD).exists())
        self.assertEqual(self.calls(), [])
        event = machine_state.last_event(self.machine)
        assert event is not None
        self.assertEqual(event.kind, machine_state.REFUSED)

    def test_a_second_run_while_one_holds_the_lock_returns_at_once(self) -> None:
        self.curating()
        lock = machine_state.RunLock(self.machine)
        self.assertTrue(lock.acquire())
        self.addCleanup(lock.release)

        outcome = self.run_curate()

        self.assertEqual(outcome.state, runner.ALREADY_RUNNING)
        self.assertFalse((self.store_root / RUN_RECORD).exists())

    def test_without_force_a_run_that_is_not_due_does_nothing(self) -> None:
        self.curating()
        finished = START - datetime.timedelta(hours=2)
        self.write(
            RUN_RECORD,
            json.dumps(
                {
                    "state": "succeeded",
                    "machine_id": "sb-test-m1",
                    "started_at": finished.isoformat(),
                    "finished_at": finished.isoformat(),
                }
            ),
        )

        outcome = self.run_curate(force=False)

        self.assertEqual(outcome.state, runner.NOT_DUE)
        self.assertEqual(self.calls(), [])

    def test_a_run_that_is_not_due_records_the_attempt_naming_the_last_success(self) -> None:
        """A scheduled run that finds nothing to do still shows that it reached m2b."""
        self.curating()
        finished = START - datetime.timedelta(hours=2)
        self.write(
            RUN_RECORD,
            json.dumps(
                {
                    "state": "succeeded",
                    "machine_id": "sb-test-m1",
                    "started_at": finished.isoformat(),
                    "finished_at": finished.isoformat(),
                }
            ),
        )

        self.run_curate(force=False)

        attempt = machine_state.last_attempt(self.machine)
        assert attempt is not None
        self.assertEqual((attempt.kind, attempt.time), (machine_state.NOT_DUE, START))
        self.assertIn("the last successful run was at", attempt.message)
        # An attempt is not an outcome: the run log, which the session-start hook reads, stays as it was.
        self.assertFalse(machine_state.run_log(self.machine).exists())

    def test_unreachable_tasks_stop_the_run_before_any_write_but_the_run_record(self) -> None:
        self.curating(tasks={"backend": "apple-reminders", "list": "sb-test-missing"})
        self.capture()
        before = sorted(
            path.relative_to(self.store_root).as_posix() for path in self.store_root.rglob("*") if path.is_file()
        )

        with self.assertRaises(TasksUnreachableError):
            self.run_curate()

        after = sorted(
            path.relative_to(self.store_root).as_posix() for path in self.store_root.rglob("*") if path.is_file()
        )
        self.assertEqual(sorted(set(after) - set(before)), [RUN_RECORD])
        record = load_run_record(self.store)
        assert record is not None
        self.assertEqual(record.state, FAILED)
        self.assertIn("preflight", record.message)
        self.assertEqual([(step.name, step.result) for step in record.steps], [("preflight", "failed")])
        self.assertEqual(self.calls(), [])
        self.assertIsNotNone(machine_state.load_backoff(self.machine))

    def test_a_memory_file_that_stays_evicted_stops_the_run_at_preflight(self) -> None:
        self.curating()
        self.write("memory/dana.md", "# Dana\n\n- Likes old maps.\n")
        self.eviction.evicted.add(self.store_root / "memory" / "dana.md")

        with self.assertRaises(runner.StoreError):
            self.run_curate(fetch_timeout=0.3)

        record = load_run_record(self.store)
        assert record is not None
        self.assertEqual(record.state, FAILED)
        self.assertIn("memory/dana.md", record.message)
        self.assertEqual(self.calls(), [])

    def test_a_capture_that_stays_evicted_waits_for_the_next_run_and_is_named(self) -> None:
        """Covers: B79"""
        self.curating()
        self.capture()
        self.eviction.evicted.add(self.store_root / "inbox" / "20261107T070000Z-cli-a1b2.md")

        outcome = self.run_curate(fetch_timeout=0.3)

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.calls(), [], "no model step for a capture it cannot read")
        record = load_run_record(self.store)
        assert record is not None
        (finding,) = [finding for finding in record.findings if finding.step == "ingest"]
        self.assertIn("inbox/20261107T070000Z-cli-a1b2.md", finding.text)
        self.assertTrue((self.store_root / "inbox" / "20261107T070000Z-cli-a1b2.md").exists())
        self.assertIn("inbox/20261107T070000Z-cli-a1b2.md", machine_state.load_evicted_inbox(self.machine))

    def test_a_sidecar_whose_member_stays_evicted_starts_no_model_step(self) -> None:
        """Covers: B79"""
        self.curating()
        stem = "20261107T070000Z-cli-c3d4"
        self.write(
            f"inbox/{stem}.md", "---\ncreated: 2026-11-07T08:00:00+01:00\nsource: cli\nkind: sidecar\n---\nphoto\n"
        )
        self.write(f"inbox/{stem}.jpg", "jpeg")
        self.eviction.evicted.add(self.store_root / "inbox" / f"{stem}.jpg")

        outcome = self.run_curate(fetch_timeout=0.3)

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.calls(), [])

    def test_a_stuck_file_beside_an_evicted_capture_starts_no_model_step(self) -> None:
        """Covers: B79"""
        self.curating()
        self.write("inbox/note.md", "---\ncreated: 2026-01-01\nsource: cli\n---\nexported\n")
        stuck = self.store_root / "inbox" / "note.md"
        machine_state.save_stuck_inbox(self.machine, {"inbox/note.md": stuck.stat().st_mtime_ns})
        self.capture()
        self.eviction.evicted.add(self.store_root / "inbox" / "20261107T070000Z-cli-a1b2.md")

        outcome = self.run_curate(fetch_timeout=0.3)

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.calls(), [])

    def test_a_run_record_that_cannot_be_written_leaves_the_cause_in_the_local_log(self) -> None:
        self.curating()
        (self.store_root / RUN_RECORD).mkdir(parents=True)

        with self.assertRaises(runner.RunRecordWriteError):
            self.run_curate()

        event = machine_state.last_event(self.machine)
        assert event is not None
        self.assertEqual(event.kind, machine_state.UNRECORDED)
        self.assertIn(RUN_RECORD, event.message)
        self.assertEqual(self.calls(), [])

    def test_a_store_without_a_profile_stops_at_preflight(self) -> None:
        self.set_up(calendar="none")
        self.write("memory/MEMORY.md", MEMORY)

        with self.assertRaises(runner.NotSetUpError):
            self.run_curate()

        record = load_run_record(self.store)
        assert record is not None
        self.assertEqual(record.state, FAILED)


class PartStepTest(RunnerTest):
    def test_part_steps_run_in_their_slots_from_this_plugin_inside_the_run(self) -> None:
        self.curating()
        self.capture()
        self.model({"m2b:ingest": INGEST_FILES_THE_CAPTURE})
        before = self.part("worklog", "before_ingest")
        after = self.part("backup", "after_journal")

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        record = load_run_record(self.store)
        assert record is not None
        self.assertEqual(
            [step.name for step in record.steps],
            ["harvest", "worklog", "ingest", "refresh", "lint", "journal", "backup", "review"],
        )
        (seen,) = [json.loads(line) for line in before.read_text(encoding="utf-8").splitlines()]
        self.assertEqual((seen["argv"], seen["cwd_entries"], seen["curation_run"]), (["run"], [], "1"))
        self.assertRegex(seen["token"], r"\A[0-9a-f]{32}\Z")
        self.assertEqual(seen["record"]["state"], RUNNING)
        deadline = datetime.datetime.fromisoformat(seen["record"]["deadline_at"])
        supervised = 5 * (datetime.timedelta(minutes=15) + datetime.timedelta(seconds=model.DEFAULT_GRACE_SECONDS))
        # The run's fetch timeout (5 s here) twice: preflight, and the journal for older month files.
        fetch = 2 * datetime.timedelta(seconds=5)
        self.assertEqual(deadline - START, fetch + supervised + runner.CODE_STEPS_MARGIN)
        self.assertTrue(after.exists())
        self.assertEqual(record.parts, ("worklog", "backup"))

    def test_a_failing_part_step_is_reported_and_the_run_goes_on(self) -> None:
        self.curating()
        self.part("worklog", "before_ingest")
        self.environ["SB_TEST_PART_EXIT"] = "4"

        outcome = self.run_curate()

        self.assertEqual(outcome.state, FAILED)
        record = load_run_record(self.store)
        assert record is not None
        self.assertEqual([(step.name, step.result) for step in record.steps][1], ("worklog", "failed"))
        self.assertEqual(record.steps[-1].name, "review")
        self.assertIn("exit 4", record.steps[1].detail)

    def test_a_part_turned_off_has_no_step_and_leaves_nothing_to_clear(self) -> None:
        """Covers: B64"""
        self.curating()
        seen = self.part("worklog", "before_ingest")
        machine.set_part_on(self.machine, "worklog", False)

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertFalse(seen.exists())
        record = load_run_record(self.store)
        assert record is not None
        self.assertNotIn("worklog", [step.name for step in record.steps])
        self.assertEqual((record.findings, record.parts), ((), ()))
        self.assertEqual(self.review_tasks(), [])

    def test_the_real_part_steps_are_this_plugins_own_commands(self) -> None:
        steps = {part.name: part.step for part in parts.PARTS if part.step}
        self.assertEqual(set(steps), {"worklog", "backup"})
        for step in steps.values():
            assert step is not None
            self.assertTrue((launcher.PLUGIN_ROOT / step.command[0]).is_file(), step.command)


class JournalStepTest(RunnerTest):
    def test_a_month_file_the_journal_leaves_alone_is_named_in_the_review_and_the_run_succeeds(self) -> None:
        """Covers: B78"""
        self.curating()
        (self.store_root / "corpus" / "2026" / "09").mkdir(parents=True)
        september = self.store_root / "corpus" / "2026" / "09" / "202609-done.md"
        september.write_text("old\n", encoding="utf-8")
        self.eviction.evicted.add(september)
        done = Task("aaaa00000001", "Call the plumber", completed=True, completed_at=START.replace(month=9))
        settings = json.loads((self.store_root / "store.json").read_text(encoding="utf-8"))
        settings["journal_since"] = "2026-09-01"
        self.write("store.json", json.dumps(settings))

        with mock.patch("m2b.tasks.markdown.MarkdownTasks.completed_items", return_value=[done]):
            outcome = self.run_curate(fetch_timeout=0)

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        (review,) = self.review_tasks()
        self.assertIn("journal: corpus/2026/09/202609-done.md is not downloaded", review.notes)
        self.assertEqual(september.read_text(encoding="utf-8"), "old\n")


class HarvestStepTest(RunnerTest):
    def test_a_ticked_candidate_becomes_a_capture_that_the_same_run_files(self) -> None:
        """Covers: B34"""
        self.curating()
        tasks = self.tasks()
        proposal = candidates.propose(self.store, tasks, "Dana likes old maps", "Remember?", START)
        assert proposal.task_id is not None
        tasks.complete(proposal.task_id)
        self.model(
            {
                "m2b:ingest": [
                    {"tool": "Bash", "command": "m2b ingest note <capture:candidate> 'filed: fact'"},
                    {"tool": "Bash", "command": "m2b ingest finish <capture:candidate>"},
                ]
            }
        )

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(list((self.store_root / "inbox").iterdir()), [])
        corpus = list((self.store_root / "corpus").rglob("*-candidate-*.md"))
        self.assertEqual(len(corpus), 1)


GUARDED = "# Memory\n\n## Facts\n\n- Dana likes old maps (dana.md)\n- Sam brings plywood (sam.md)\n\n## Current\n"
SAM_DUE = "---\nuntil: 2026-11-01\n---\n# Sam\n\n- Brings plywood.\n"


class GuardedModelStepTest(RunnerTest):
    """Code compares ``memory/`` before and after each model step that may edit it."""

    def setUp(self) -> None:
        super().setUp()
        self.curating()
        self.write("memory/MEMORY.md", GUARDED)
        self.write("memory/dana.md", "# Dana\n\n- Likes old maps.\n")
        self.write("memory/sam.md", SAM_DUE)

    def memory_file(self, name: str) -> str:
        return (self.store_root / "memory" / name).read_text(encoding="utf-8")

    def edit_index(self, old: str, new: str) -> dict[str, Any]:
        return {"tool": "Edit", "file_path": "<store>/memory/MEMORY.md", "old_string": old, "new_string": new}

    def test_a_refresh_step_that_edits_its_own_fact_and_line_succeeds(self) -> None:
        """Covers: B54"""
        self.model(
            {
                "m2b:refresh": [
                    {"tool": "Write", "file_path": "<store>/memory/sam.md", "content": "# Sam\n\n- Brought plywood.\n"},
                    self.edit_index("Sam brings plywood", "Sam brought plywood"),
                ]
            }
        )

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertIn("- Sam brought plywood (sam.md)", self.memory_file("MEMORY.md"))
        self.assertEqual(self.review_tasks(), [])

    def test_a_refresh_step_that_changes_another_line_is_put_back_and_fails(self) -> None:
        """Covers: B54"""
        self.model(
            {
                "m2b:refresh": [
                    {"tool": "Write", "file_path": "<store>/memory/sam.md", "content": "# Sam\n\n- Brought plywood.\n"},
                    self.edit_index("- Dana likes old maps (dana.md)\n", ""),
                ]
            }
        )

        outcome = self.run_curate()

        self.assertEqual(outcome.state, FAILED)
        self.assertIn("refresh: ", outcome.message)
        self.assertIn("Dana likes old maps", outcome.message)
        self.assertIn("memory/ is as it was before the step", outcome.message)
        self.assertEqual(self.memory_file("MEMORY.md"), GUARDED)
        self.assertEqual(self.memory_file("sam.md"), SAM_DUE)
        (review,) = self.review_tasks()
        self.assertIn("refresh", review.notes)

    def test_a_refresh_step_that_fails_after_a_bad_edit_still_puts_memory_back(self) -> None:
        """Covers: B54"""
        self.model(
            {
                "m2b:refresh": [
                    self.edit_index("- Dana likes old maps (dana.md)\n", ""),
                    {"tool": "Bash", "command": "rm -rf /"},
                ]
            }
        )

        outcome = self.run_curate()

        self.assertEqual(outcome.state, FAILED)
        self.assertIn("denied", outcome.message)
        self.assertIn("memory/ is as it was before the step", outcome.message)
        self.assertEqual(self.memory_file("MEMORY.md"), GUARDED)

    def test_an_ingest_step_that_rewrites_or_removes_facts_lines_keeps_them_and_lists_them_in_the_review(self) -> None:
        """Covers: B55"""
        self.write("memory/sam.md", "# Sam\n\n- Brings plywood.\n")
        self.capture()
        self.model(
            {
                "m2b:ingest": [
                    self.edit_index("Dana likes old maps", "Dana collects old maps"),
                    self.edit_index("- Sam brings plywood (sam.md)\n", ""),
                    *INGEST_FILES_THE_CAPTURE[1:],
                ]
            }
        )

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertIn("- Dana collects old maps (dana.md)", self.memory_file("MEMORY.md"))
        (review,) = self.review_tasks()
        self.assertIn(
            'ingest: rewrote the facts line "- Dana likes old maps (dana.md)" as "- Dana collects old maps (dana.md)"',
            review.notes,
        )
        self.assertIn('ingest: removed the facts line "- Sam brings plywood (sam.md)"', review.notes)
        (saved,) = (self.machine.state_dir / "memory-before-run").iterdir()
        self.assertIn(f"memory/ as it was before this run is in {saved}", review.notes)
        self.assertIn("20261107T070000Z-cli-a1b2.md", review.notes)
        self.assertEqual((saved / "MEMORY.md").read_text(encoding="utf-8"), GUARDED)

    def test_an_ingest_step_that_only_adds_facts_lines_leaves_the_review_alone(self) -> None:
        """Covers: B55"""
        self.write("memory/sam.md", "# Sam\n\n- Brings plywood.\n")
        self.capture()
        self.model(
            {
                "m2b:ingest": [
                    self.edit_index("(sam.md)\n", "(sam.md)\n- Robin visits in May (robin.md)\n"),
                    {"tool": "Write", "file_path": "<store>/memory/robin.md", "content": "# Robin\n"},
                    *INGEST_FILES_THE_CAPTURE[1:],
                ]
            }
        )

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.review_tasks(), [])

    def test_a_lint_step_that_removes_a_facts_line_lists_it_in_the_review(self) -> None:
        """Covers: B55"""
        self.write("memory/sam.md", "# Sam\n\n- Brings plywood.\n")
        self.repairable_link()
        self.write("memory/MEMORY.md", GUARDED)
        self.model({"m2b:lint": [self.edit_index("- Sam brings plywood (sam.md)\n", "")]})

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        (review,) = self.review_tasks()
        self.assertIn('lint: removed the facts line "- Sam brings plywood (sam.md)"', review.notes)

    def test_an_ingest_step_that_writes_an_unsafe_character_is_put_back_and_fails(self) -> None:
        """Covers: B56"""
        self.write("memory/sam.md", "# Sam\n\n- Brings plywood.\n")
        before = self.memory_file("MEMORY.md")
        self.capture()
        self.model(
            {
                "m2b:ingest": [
                    self.edit_index("(dana.md)\n", "(dana.md)\n- Robin‮ visits (robin.md)\n"),
                    *INGEST_FILES_THE_CAPTURE[1:],
                ]
            }
        )

        outcome = self.run_curate()

        self.assertEqual(outcome.state, FAILED)
        self.assertIn("ingest: ", outcome.message)
        self.assertIn("U+202E", outcome.message)
        self.assertIn("memory/ is as it was before the step", outcome.message)
        self.assertIn("the captures it filed are in the archive: 20261107T070000Z-cli-a1b2.md", outcome.message)
        self.assertEqual(self.memory_file("MEMORY.md"), before)

    def test_an_undone_ingest_clears_facts_filed_on_captures_it_left_in_the_inbox(self) -> None:
        """Covers: B56"""
        self.write("memory/sam.md", "# Sam\n\n- Brings plywood.\n")
        self.capture()
        self.model(
            {
                "m2b:ingest": [
                    self.edit_index("(dana.md)\n", "(dana.md)\n- Robin\u202e visits (robin.md)\n"),
                    {"tool": "Bash", "command": "m2b ingest facts-filed <capture:cli>"},
                    {"tool": "Bash", "command": "rm -rf /"},
                ]
            }
        )

        outcome = self.run_curate()

        self.assertEqual(outcome.state, FAILED)
        self.assertIn("facts_filed was taken off 20261107T070000Z-cli-a1b2.md", outcome.message)
        capture = (self.store_root / "inbox" / "20261107T070000Z-cli-a1b2.md").read_text(encoding="utf-8")
        self.assertNotIn("facts_filed", capture)

    def test_a_reported_change_stays_in_the_review_with_its_copy_until_the_owner_completes_it(self) -> None:
        """Covers: B55"""
        self.write("memory/sam.md", "# Sam\n\n- Brings plywood.\n")
        self.capture()
        self.model(
            {"m2b:ingest": [self.edit_index("- Sam brings plywood (sam.md)\n", ""), *INGEST_FILES_THE_CAPTURE[1:]]}
        )
        self.run_curate()
        (first,) = self.review_tasks()
        copies = sorted((self.machine.state_dir / "memory-before-run").iterdir())
        self.assertEqual(len(copies), 1)

        self.clock = START + datetime.timedelta(hours=5)
        self.capture("20261107T120000Z-cli-c3d4.md")
        self.model({"m2b:ingest": INGEST_FILES_THE_CAPTURE})
        self.run_curate()

        (second,) = self.review_tasks()
        self.assertFalse(second.completed)
        self.assertIn('ingest: removed the facts line "- Sam brings plywood (sam.md)"', second.notes)
        self.assertIn(str(copies[0]), second.notes)
        self.assertTrue((copies[0] / "MEMORY.md").read_text(encoding="utf-8").count("Sam brings plywood"))

        self.tasks().complete(first.id)
        self.clock = START + datetime.timedelta(hours=10)
        self.run_curate()

        # Lint still reports sam.md, whose line is gone; the change itself is not repeated.
        (third,) = self.review_tasks()
        self.assertNotIn("removed the facts line", third.notes)
        self.assertEqual([path for path in copies if path.exists()], [])

    def test_a_file_ingest_cannot_read_is_reported_and_starts_no_model_run_again_until_it_changes(self) -> None:
        """Covers: B57"""
        self.write("memory/sam.md", "# Sam\n\n- Brings plywood.\n")
        self.write("inbox/note.md", "---\ncreated: 2026-01-01\nsource: cli\n---\nexported\n")
        self.model({"m2b:ingest": [{"tool": "Bash", "command": "m2b ingest list --json"}]})
        self.run_curate()
        self.assertEqual(len(self.calls()), 1)

        self.clock = START + datetime.timedelta(hours=1)
        self.assertEqual(self.run_curate(force=False).state, runner.NOT_DUE)
        outcome = self.run_curate()

        self.assertEqual(len(self.calls()), 1)
        assert outcome.record is not None
        self.assertIn(("ingest", "skipped"), [(step.name, step.result) for step in outcome.record.steps])
        (review,) = self.review_tasks()
        self.assertIn("ingest: inbox/note.md", review.notes)

    def test_after_a_failed_ingest_step_a_file_it_left_still_makes_the_next_run_due(self) -> None:
        """Covers: B57"""
        self.write("memory/sam.md", "# Sam\n\n- Brings plywood.\n")
        self.write("inbox/groceries.txt", "milk\n")
        self.model({"m2b:ingest": [{"tool": "Bash", "command": "m2b ingest list --json"}]}, {"m2b:ingest": "error"})
        self.run_curate()

        self.assertEqual(machine_state.load_stuck_inbox(self.machine), {})

    def test_a_file_that_arrives_during_the_ingest_step_is_not_taken_for_stuck(self) -> None:
        """Covers: B57"""
        self.write("memory/sam.md", "# Sam\n\n- Brings plywood.\n")
        self.write("inbox/note.md", "---\ncreated: 2026-01-01\nsource: cli\n---\nexported\n")
        self.model({"m2b:ingest": [{"tool": "Bash", "command": "m2b ingest list --json"}]})
        original = runner._Run._model

        def model_then_a_capture_syncs_in(run: Any, *arguments: Any, **options: Any) -> None:
            original(run, *arguments, **options)
            self.write("inbox/later.txt", "arrived mid-step\n")

        with mock.patch.object(runner._Run, "_model", autospec=True, side_effect=model_then_a_capture_syncs_in):
            self.run_curate()

        self.assertEqual(list(machine_state.load_stuck_inbox(self.machine)), ["inbox/note.md"])

    def test_a_snapshot_that_cannot_be_taken_keeps_the_model_from_running(self) -> None:
        self.capture()
        self.model({"m2b:ingest": INGEST_FILES_THE_CAPTURE})
        unreadable = StoreReadError("memory/dana.md could not be read: permission denied")

        with mock.patch.object(memory_guard.Snapshot, "take", side_effect=unreadable):
            outcome = self.run_curate()

        self.assertEqual(outcome.state, FAILED)
        self.assertIn("ingest: memory/dana.md could not be read", outcome.message)
        self.assertEqual(self.calls(), [])


# What a model step writes into MEMORY.md before the runner is stopped: a zero-width space that
# reads one way to the owner and another to the model.
HIDDEN_LINE = "- Dana​ likes old maps (dana.md)\n"
SIGTERM_EXIT = SystemExit(128 + signal.SIGTERM)


class StoppedStepTest(RunnerTest):
    """A runner stopped during a model step, by SIGTERM, still checks ``memory/``, or the next run does."""

    def setUp(self) -> None:
        super().setUp()
        self.curating()
        self.write("memory/MEMORY.md", GUARDED)
        self.write("memory/dana.md", "# Dana\n\n- Likes old maps.\n")
        self.write("memory/sam.md", SAM_DUE)

    def memory_file(self, name: str) -> str:
        return (self.store_root / "memory" / name).read_text(encoding="utf-8")

    def plant_and_stop(self, run: Any, *arguments: Any, **options: Any) -> None:
        self.write("memory/MEMORY.md", GUARDED + HIDDEN_LINE)
        raise SIGTERM_EXIT

    def remove_a_line_and_stop(self, run: Any, *arguments: Any, **options: Any) -> None:
        self.write("memory/MEMORY.md", self.memory_file("MEMORY.md").replace("- Sam brings plywood (sam.md)\n", ""))
        raise SIGTERM_EXIT

    def stopped_run(self, model_step: Any, sort_facts: bool = False) -> None:
        with (
            mock.patch.object(runner._Run, "_model", autospec=True, side_effect=model_step),
            self.assertRaises(SystemExit),
        ):
            self.run_curate(sort_facts=sort_facts)

    def test_a_guarded_step_stopped_by_sigterm_still_puts_a_hidden_line_back(self) -> None:
        """Covers: B76"""
        self.stopped_run(self.plant_and_stop)

        self.assertEqual(self.memory_file("MEMORY.md"), GUARDED)

    def test_the_sorting_step_stopped_by_sigterm_still_puts_a_hidden_line_back(self) -> None:
        """Covers: B76"""
        self.write("memory/sam.md", "# Sam\n\n- Brings plywood.\n")

        self.stopped_run(self.plant_and_stop, sort_facts=True)

        self.assertEqual(self.memory_file("MEMORY.md"), GUARDED)

    def test_a_check_that_fails_after_sigterm_still_lets_the_runner_stop(self) -> None:
        """Covers: B76"""
        unreadable = StoreReadError("memory/dana.md could not be read: permission denied")

        with mock.patch.object(runner._Run, "_memory_problem", autospec=True, side_effect=unreadable):
            self.stopped_run(self.plant_and_stop)

        self.assertEqual(self.calls(), [], "no later model step started")

    def test_a_sorting_check_that_fails_after_sigterm_still_lets_the_runner_stop(self) -> None:
        """Covers: B76"""
        self.write("memory/sam.md", "# Sam\n\n- Brings plywood.\n")
        unreadable = StoreReadError("memory/MEMORY.md could not be read: permission denied")

        with mock.patch.object(runner._Run, "_sorting_problem", autospec=True, side_effect=unreadable):
            self.stopped_run(self.plant_and_stop, sort_facts=True)

    def killed_run(self, model_step: Any, sort_facts: bool = False) -> None:
        """A run whose check never ran either, as after SIGKILL or a second signal during the check."""
        with (
            mock.patch.object(runner._Run, "_memory_problem", autospec=True, side_effect=SIGTERM_EXIT),
            mock.patch.object(runner._Run, "_sorting_problem", autospec=True, side_effect=SIGTERM_EXIT),
        ):
            self.stopped_run(model_step, sort_facts=sort_facts)
        record = load_run_record(self.store)
        assert record is not None
        self.assertEqual(record.state, RUNNING)

    def next_run(self) -> Any:
        self.clock = START + datetime.timedelta(hours=2)
        with mock.patch.object(runner._Run, "_model", autospec=True):
            self.run_curate()
        (review,) = self.review_tasks()
        return review

    def test_the_next_run_names_a_hidden_line_an_interrupted_run_left_and_keeps_its_copy(self) -> None:
        """Covers: B76"""
        self.killed_run(self.plant_and_stop)
        (copy,) = machine_state.memory_copies(self.machine).iterdir()

        review = self.next_run()

        self.assertIn("interrupted", review.notes)
        self.assertIn("Dana likes old maps", review.notes)
        self.assertIn("U+200B", review.notes)
        self.assertIn(str(copy), review.notes)
        self.assertEqual((copy / "MEMORY.md").read_text(encoding="utf-8"), GUARDED)

    def test_the_next_run_lists_the_facts_lines_an_interrupted_run_removed(self) -> None:
        """Covers: B76"""
        self.killed_run(self.remove_a_line_and_stop)
        (copy,) = machine_state.memory_copies(self.machine).iterdir()

        review = self.next_run()

        self.assertIn('removed the facts line "- Sam brings plywood (sam.md)"', review.notes)
        self.assertIn(str(copy), review.notes)
        self.assertTrue(copy.is_dir())

    def test_a_sorting_run_killed_hard_is_checked_by_the_next_run(self) -> None:
        """Covers: B76"""
        self.write("memory/sam.md", "# Sam\n\n- Brings plywood.\n")

        self.killed_run(self.plant_and_stop, sort_facts=True)

        self.assertIn("U+200B", self.next_run().notes)

    def test_a_run_that_fails_at_preflight_in_between_keeps_the_check_for_the_next(self) -> None:
        """Covers: B76"""
        self.killed_run(self.plant_and_stop)
        (copy,) = machine_state.memory_copies(self.machine).iterdir()
        self.clock = START + datetime.timedelta(hours=1)
        unreachable = TasksUnreachableError("the task list is not reachable yet")
        with (
            mock.patch("m2b.tasks.markdown.MarkdownTasks.check_reachable", side_effect=unreachable),
            self.assertRaises(TasksUnreachableError),
        ):
            self.run_curate()

        review = self.next_run()

        self.assertIn("U+200B", review.notes)
        self.assertIn(str(copy), review.notes)

    def test_two_stopped_runs_in_a_row_still_name_what_the_first_left(self) -> None:
        """Covers: B76"""
        self.killed_run(self.plant_and_stop)
        (first,) = machine_state.memory_copies(self.machine).iterdir()
        self.clock = START + datetime.timedelta(hours=1)
        self.killed_run(self.remove_a_line_and_stop)

        review = self.next_run()

        self.assertIn("U+200B", review.notes)
        self.assertIn(str(first), review.notes)
        self.assertTrue(first.is_dir())

    def test_a_rewritten_facts_line_is_named_without_the_characters_that_hide_text(self) -> None:
        """Covers: B76"""

        def rewrite_with_a_hidden_character(run: Any, *arguments: Any, **options: Any) -> None:
            self.write("memory/MEMORY.md", GUARDED.replace("Dana likes old maps", "Dana\u200b likes old maps a lot"))
            raise SIGTERM_EXIT

        self.killed_run(rewrite_with_a_hidden_character)

        review = self.next_run()

        self.assertIn("Dana likes old maps a lot", review.notes)
        self.assertNotIn("\u200b", review.notes)

    def test_a_copy_from_before_another_machines_runs_is_not_compared(self) -> None:
        """Curation moved to another machine and back: its runs and the owner's edits since are no interruption."""
        self.killed_run(self.remove_a_line_and_stop)
        record = json.loads((self.store_root / RUN_RECORD).read_text(encoding="utf-8"))
        later = (START + datetime.timedelta(hours=1)).isoformat()
        record.update(state=SUCCEEDED, machine_id="sb-test-other", started_at=later, finished_at=later)
        self.write(RUN_RECORD, json.dumps(record))

        self.clock = START + datetime.timedelta(hours=2)
        with mock.patch.object(runner._Run, "_model", autospec=True):
            self.run_curate()

        self.assertNotIn("interrupted", " ".join(task.notes for task in self.review_tasks()))
        self.assertEqual(machine_state.unchecked_copies(self.machine), [])

    def test_an_interrupted_run_that_changed_nothing_adds_nothing_to_the_review(self) -> None:
        self.killed_run(lambda run, *arguments, **options: (_ for _ in ()).throw(SIGTERM_EXIT))

        self.clock = START + datetime.timedelta(hours=2)
        with mock.patch.object(runner._Run, "_model", autospec=True):
            outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.review_tasks(), [])


if __name__ == "__main__":
    import unittest

    unittest.main()
