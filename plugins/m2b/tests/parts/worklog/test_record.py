"""The recorder herdr starts per event: what it writes, and when it writes nothing."""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys

from m2b_worklog import periods
from worklog_fixtures import RECORDER_DIR, WorklogFixture, load_recorder, snapshot_reply

record = load_recorder()
NOW = datetime.datetime(2026, 3, 14, 9, 30, 0, 250_000, tzinfo=datetime.timezone(datetime.timedelta(hours=1)))

SHED = {
    "workspace_id": "w1",
    "label": "garden-shed",
    "number": 1,
    "worktree": {
        "repo_name": "garden-shed",
        "repo_root": "/home/alex/projects/garden-shed",
        "checkout_path": "/home/alex/projects/garden-shed",
        "repo_key": "k1",
        "is_linked_worktree": False,
    },
}
SHED_PANE = {"pane_id": "p1", "workspace_id": "w1", "tab_id": "t1", "cwd": "/home/alex/projects/garden-shed/roof"}


def status_event(status: str, pane: str = "p1", workspace: str = "w1") -> dict[str, str]:
    data = {"type": "pane_agent_status_changed", "pane_id": pane, "workspace_id": workspace, "agent_status": status}
    return {"HERDR_PLUGIN_EVENT": "pane.agent_status_changed", "HERDR_PLUGIN_EVENT_JSON": json.dumps(data)}


class RecordTest(WorklogFixture):
    def setUp(self) -> None:
        super().setUp()
        self.install_plugins("m2b@m2b")
        self.switch("on")
        self.herdr_reply.write_text(snapshot_reply([SHED], [SHED_PANE]), encoding="utf-8")

    def lines(self, workspace: str = "w1") -> list[dict[str, object]]:
        path = self.state / f"{workspace}.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def test_one_line_per_event_with_time_kind_workspace_pane_and_folder(self) -> None:
        self.assertTrue(record.record({**self.environ, **status_event("working")}, NOW))

        self.assertEqual(
            self.lines(),
            [
                {
                    "time": "2026-03-14T09:30:00.250+01:00",
                    "kind": "agent_working",
                    "workspace": "w1",
                    "pane": "p1",
                    "cwd": "/home/alex/projects/garden-shed/roof",
                }
            ],
        )

    def test_status_focus_and_workspace_events_get_their_kinds(self) -> None:
        events = [
            status_event("working"),
            status_event("blocked"),
            status_event("idle"),
            status_event("done"),
            {
                "HERDR_PLUGIN_EVENT": "pane.focused",
                "HERDR_PLUGIN_EVENT_JSON": '{"pane_id": "p1", "workspace_id": "w1"}',
            },
            {"HERDR_PLUGIN_EVENT": "workspace.focused", "HERDR_PLUGIN_EVENT_JSON": '{"workspace_id": "w1"}'},
            {"HERDR_PLUGIN_EVENT": "workspace.created", "HERDR_PLUGIN_EVENT_JSON": json.dumps({"workspace": SHED})},
            {"HERDR_PLUGIN_EVENT": "pane.exited", "HERDR_PLUGIN_EVENT_JSON": '{"pane_id": "p1", "workspace_id": "w1"}'},
            {"HERDR_PLUGIN_EVENT": "workspace.closed", "HERDR_PLUGIN_EVENT_JSON": '{"workspace_id": "w1"}'},
        ]
        for event in events:
            record.record({**self.environ, **event}, NOW)

        self.assertEqual(
            [line["kind"] for line in self.lines()],
            [
                "agent_working",
                "agent_blocked",
                "agent_stopped",
                "agent_stopped",
                "focus",
                "focus",
                "workspace_opened",
                "agent_stopped",
                "workspace_closed",
            ],
        )

    def test_reads_the_event_inside_an_envelope_and_without_an_event_name(self) -> None:
        data = {"type": "pane_agent_status_changed", "pane_id": "p1", "workspace_id": "w1", "agent_status": "working"}

        record.record({**self.environ, "HERDR_PLUGIN_EVENT_JSON": json.dumps({"event": "x", "data": data})}, NOW)

        self.assertEqual([line["kind"] for line in self.lines()], ["agent_working"])

    def test_the_kinds_are_the_ones_the_periods_read(self) -> None:
        self.assertEqual(record.KINDS, periods.EVENT_KINDS)

    def test_records_nothing_when_the_m2b_plugin_is_not_installed(self) -> None:
        """Covers: B38"""
        self.install_plugins("second-brain@elsewhere", "m2b@another-marketplace")

        self.assertFalse(record.record({**self.environ, **status_event("working")}, NOW))
        self.assertEqual(sorted(p.name for p in self.state.iterdir()), ["recording"])

    def test_records_nothing_while_the_plugin_is_turned_off_in_claude_code(self) -> None:
        """Covers: B38"""
        self.claude_settings({"enabledPlugins": {"m2b@m2b": False}})

        self.assertFalse(record.record({**self.environ, **status_event("working")}, NOW))
        self.assertEqual(self.lines(), [])

        self.claude_settings({"enabledPlugins": {"m2b@m2b": True}}, managed=True)
        self.assertTrue(record.record({**self.environ, **status_event("working")}, NOW))

    def test_records_nothing_when_the_settings_cannot_be_read(self) -> None:
        settings = self.base / "claude-config" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text("{", encoding="utf-8")

        self.assertFalse(record.record({**self.environ, **status_event("working")}, NOW))

    def test_records_nothing_without_installed_plugins_or_with_the_switch_off_or_missing(self) -> None:
        """Covers: B38"""
        self.installed.unlink()
        self.assertFalse(record.record({**self.environ, **status_event("working")}, NOW))
        self.install_plugins("m2b@m2b")
        self.switch("off")
        self.assertFalse(record.record({**self.environ, **status_event("working")}, NOW))
        (self.state / "recording").unlink()
        self.assertFalse(record.record({**self.environ, **status_event("working")}, NOW))
        self.assertEqual(list(self.state.iterdir()), [])

    def test_an_event_it_does_not_know_or_cannot_read_is_skipped(self) -> None:
        for event in [
            {"HERDR_PLUGIN_EVENT": "tab.renamed", "HERDR_PLUGIN_EVENT_JSON": '{"workspace_id": "w1"}'},
            {"HERDR_PLUGIN_EVENT": "pane.focused", "HERDR_PLUGIN_EVENT_JSON": "not json"},
            {"HERDR_PLUGIN_EVENT": "pane.focused", "HERDR_PLUGIN_EVENT_JSON": '{"workspace_id": "../x"}'},
        ]:
            self.assertFalse(record.record({**self.environ, **event}, NOW))
        self.assertEqual(self.lines(), [])

    def test_without_a_snapshot_the_line_has_no_folder(self) -> None:
        self.herdr_reply.unlink()

        record.record({**self.environ, **status_event("working")}, NOW)

        self.assertIsNone(self.lines()[0]["cwd"])

    def test_the_workspace_cache_maps_the_id_to_repository_label_and_folder(self) -> None:
        record.record({**self.environ, **status_event("working")}, NOW)
        record.record({**self.environ, **status_event("idle")}, NOW)

        cache = json.loads((self.state / "workspaces.json").read_text(encoding="utf-8"))
        self.assertEqual(
            cache,
            {
                "w1": [
                    {
                        "repo": "garden-shed",
                        "label": "garden-shed",
                        "folder": "/home/alex/projects/garden-shed",
                        "since": "2026-03-14T09:30:00.250+01:00",
                    }
                ]
            },
        )

    def test_a_workspace_id_seen_again_with_another_folder_starts_a_new_entry(self) -> None:
        record.record({**self.environ, **status_event("working")}, NOW)
        reused = {**SHED, "label": "acme-invoices", "worktree": None}
        pane = {"pane_id": "p1", "workspace_id": "w1", "tab_id": "t1", "cwd": "/home/alex/work/acme-invoices"}
        self.herdr_reply.write_text(snapshot_reply([reused], [pane]), encoding="utf-8")

        record.record({**self.environ, **status_event("idle")}, NOW + datetime.timedelta(hours=2))

        entries = json.loads((self.state / "workspaces.json").read_text(encoding="utf-8"))["w1"]
        self.assertEqual(
            [entry["folder"] for entry in entries], ["/home/alex/projects/garden-shed", "/home/alex/work/acme-invoices"]
        )
        self.assertEqual(entries[1]["label"], "acme-invoices")
        self.assertIsNone(entries[1]["repo"])

    def test_herdr_runs_it_as_a_script_and_it_always_exits_0(self) -> None:
        environ = {**self.environ, **status_event("working"), "PATH": os.environ.get("PATH", "")}
        environ["HERDR_BIN_PATH"] = environ.pop("M2B_HERDR")

        result = subprocess.run(
            [sys.executable, "record.py"], cwd=RECORDER_DIR, env=environ, capture_output=True, text=True, timeout=20
        )
        broken = subprocess.run(
            [sys.executable, "record.py"],
            cwd=RECORDER_DIR,
            env={**environ, "M2B_HOME": "/dev/null/nowhere"},
            capture_output=True,
            text=True,
            timeout=20,
        )

        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
        self.assertEqual(self.lines()[0]["cwd"], "/home/alex/projects/garden-shed/roof")
        self.assertEqual((broken.returncode, broken.stdout, broken.stderr), (0, "", ""))


class PlainWorkspaceCacheTest(WorklogFixture):
    """A workspace without a worktree: its folder comes from a pane, and panes differ."""

    def setUp(self) -> None:
        super().setUp()
        self.install_plugins("m2b@m2b")
        self.switch("on")
        plain = {"workspace_id": "w2", "label": "notes", "number": 2, "worktree": None}
        panes = [
            {"pane_id": "p1", "workspace_id": "w2", "tab_id": "t1", "cwd": "/home/alex/notes"},
            {"pane_id": "p2", "workspace_id": "w2", "tab_id": "t1", "cwd": "/home/alex/notes/drafts"},
        ]
        self.herdr_reply.write_text(snapshot_reply([plain], panes), encoding="utf-8")

    def test_events_without_a_folder_and_other_panes_keep_one_entry(self) -> None:
        events = [
            status_event("working", "p1", "w2"),
            {"HERDR_PLUGIN_EVENT": "workspace.focused", "HERDR_PLUGIN_EVENT_JSON": '{"workspace_id": "w2"}'},
            status_event("working", "p2", "w2"),
            {"HERDR_PLUGIN_EVENT": "workspace.focused", "HERDR_PLUGIN_EVENT_JSON": '{"workspace_id": "w2"}'},
            status_event("idle", "p1", "w2"),
        ]
        for event in events:
            record.record({**self.environ, **event}, NOW)

        entries = json.loads((self.state / "workspaces.json").read_text(encoding="utf-8"))["w2"]
        self.assertEqual(
            entries,
            [{"repo": None, "label": "notes", "folder": "/home/alex/notes", "since": "2026-03-14T09:30:00.250+01:00"}],
        )

    def test_a_first_event_without_a_folder_gets_the_folder_later(self) -> None:
        record.record(
            {
                **self.environ,
                "HERDR_PLUGIN_EVENT": "workspace.focused",
                "HERDR_PLUGIN_EVENT_JSON": '{"workspace_id": "w2"}',
            },
            NOW,
        )
        record.record({**self.environ, **status_event("working", "p1", "w2")}, NOW)

        entries = json.loads((self.state / "workspaces.json").read_text(encoding="utf-8"))["w2"]
        self.assertEqual([entry["folder"] for entry in entries], ["/home/alex/notes"])

    def test_a_reused_id_whose_first_events_have_no_folder_still_starts_a_new_entry(self) -> None:
        record.record({**self.environ, **status_event("working", "p1", "w2")}, NOW)
        reused = {"workspace_id": "w2", "label": "acme-invoices", "number": 2, "worktree": None}
        pane = {"pane_id": "p7", "workspace_id": "w2", "tab_id": "t1", "cwd": "/home/alex/work/acme-invoices"}
        self.herdr_reply.write_text(snapshot_reply([reused], [pane]), encoding="utf-8")
        later = NOW + datetime.timedelta(hours=3)

        for event in [
            {"HERDR_PLUGIN_EVENT": "workspace.created", "HERDR_PLUGIN_EVENT_JSON": json.dumps({"workspace": reused})},
            {"HERDR_PLUGIN_EVENT": "workspace.focused", "HERDR_PLUGIN_EVENT_JSON": '{"workspace_id": "w2"}'},
            status_event("working", "p7", "w2"),
        ]:
            record.record({**self.environ, **event}, later)

        entries = json.loads((self.state / "workspaces.json").read_text(encoding="utf-8"))["w2"]
        self.assertEqual(
            [(entry["label"], entry["folder"]) for entry in entries],
            [("notes", "/home/alex/notes"), ("acme-invoices", "/home/alex/work/acme-invoices")],
        )
