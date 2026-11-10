"""The session-start hook: the recording switch follows which machine curates; the copy follows updates."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from m2b_worklog import session_start
from m2b_worklog.paths import RECORDER_SOURCE, worklog_paths
from worklog_fixtures import WorklogFixture


def addons(worklog: bool) -> list[dict[str, object]]:
    return [{"name": "worklog", "on": worklog, "summary": "y"}]


class FakeStatus:
    """Stands in for ``subprocess.run`` on the launcher; records the command line.

    ``m2b addons list`` gets ``addons_answer`` (the worklog add-on on unless given), ``m2b status`` the rest.
    """

    def __init__(
        self,
        answer: object = None,
        returncode: int = 0,
        error: Exception | None = None,
        stderr: str = "",
        addons_answer: object = None,
    ) -> None:
        self.answer, self.returncode, self.error, self.stderr = answer, returncode, error, stderr
        self.addons_answer = addons(True) if addons_answer is None else addons_answer
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str], **options: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        if command[1:3] == ["addons", "list"]:
            if isinstance(self.addons_answer, Exception):
                raise self.addons_answer
            text = self.addons_answer if isinstance(self.addons_answer, str) else json.dumps(self.addons_answer)
            return subprocess.CompletedProcess(command, 0, text, "")
        if self.error is not None:
            raise self.error
        stdout = self.answer if isinstance(self.answer, str) else json.dumps(self.answer)
        return subprocess.CompletedProcess(command, self.returncode, stdout, self.stderr)


def status(curates: bool, worklog: bool = True) -> dict[str, object]:
    return {
        "machine_id": "alex-laptop",
        "addons": {"worklog": worklog},
        "curating_machine": "x",
        "this_machine_curates": curates,
        "inbox": {"count": 0},
    }


class SessionStartTest(WorklogFixture):
    def setUp(self) -> None:
        super().setUp()
        self.paths = worklog_paths(self.environ)

    def switch_value(self) -> str | None:
        path = self.state / "recording"
        return path.read_text(encoding="utf-8").strip() if path.exists() else None

    def install_copy(self) -> None:
        self.paths.recorder_copy.mkdir(parents=True)
        (self.paths.recorder_copy / "herdr-plugin.toml").write_text("# installed by setup\n", encoding="utf-8")

    def test_installing_the_plugin_without_its_setup_never_turns_recording_on(self) -> None:
        """Covers: B38"""
        self.assertEqual(session_start.session_start(self.paths, self.environ, FakeStatus(status(True))), "")

        self.assertEqual(self.switch_value(), "off")

    def test_the_switch_is_on_while_this_machine_curates_and_off_after_a_take_over(self) -> None:
        """Covers: B38"""
        self.install_copy()
        run = FakeStatus(status(True))
        self.assertEqual(session_start.session_start(self.paths, self.environ, run), "")
        self.assertEqual(self.switch_value(), "on")
        launcher = str(self.home / ".local" / "bin" / "m2b")
        self.assertEqual(run.calls, [[launcher, "addons", "list", "--json"], [launcher, "status", "--json"]])

        self.assertEqual(session_start.session_start(self.paths, self.environ, FakeStatus(status(False))), "")
        self.assertEqual(self.switch_value(), "off")

    def test_the_worklog_addon_turned_off_turns_recording_off_at_the_next_session(self) -> None:
        self.install_copy()
        self.assertEqual(session_start.session_start(self.paths, self.environ, FakeStatus(status(True))), "")
        self.assertEqual(self.switch_value(), "on")

        run = FakeStatus(status(True, worklog=False))
        self.assertEqual(session_start.session_start(self.paths, self.environ, run), "")
        self.assertEqual(self.switch_value(), "off")

    def test_m2b_not_set_up_turns_recording_off_and_prints_nothing(self) -> None:
        self.switch("on")

        not_set_up = "m2b: not set up: no machine config. Run /m2b:m2b setup in Claude Code.\n"
        output = session_start.session_start(self.paths, self.environ, FakeStatus("", returncode=2, stderr=not_set_up))

        self.assertEqual(output, "")
        self.assertEqual(self.switch_value(), "off")

    def test_no_launcher_yet_means_not_set_up_and_prints_nothing(self) -> None:
        """Covers: B7"""
        self.switch("on")

        output = session_start.session_start(self.paths, self.environ, FakeStatus(error=FileNotFoundError("m2b")))

        self.assertEqual(output, "")
        self.assertEqual(self.switch_value(), "off")

    def test_a_core_that_cannot_answer_leaves_the_switch_and_says_so_in_one_line(self) -> None:
        self.switch("on")
        for name, run in {
            "broken config": FakeStatus("", returncode=2, stderr="m2b: config.json is not valid JSON\n"),
            "timeout": FakeStatus(error=subprocess.TimeoutExpired(["m2b"], 20)),
            "garbled": FakeStatus("not json"),
            "failed": FakeStatus("", returncode=1),
            "unreadable store": FakeStatus({**status(False), "store_error": "store.json is not JSON"}),
        }.items():
            with self.subTest(name):
                output = session_start.session_start(self.paths, self.environ, run)
                self.assertEqual(output.count("\n"), 1)
                self.assertTrue(output.startswith("m2b worklog: could not check which machine curates"), output)
                self.assertEqual(self.switch_value(), "on")

    def test_with_the_worklog_addon_off_it_says_nothing_and_asks_nothing_else(self) -> None:
        """A core-only user: no line, no status probe, and no switch file written."""
        run = FakeStatus({**status(False), "store_error": "store.json is not JSON"}, addons_answer=addons(False))

        self.assertEqual(session_start.session_start(self.paths, self.environ, run), "")
        self.assertEqual(len(run.calls), 1)
        self.assertIsNone(self.switch_value())

        self.switch("on")
        self.assertEqual(session_start.session_start(self.paths, self.environ, run), "")
        self.assertEqual(self.switch_value(), "off")

    def test_addons_that_cannot_be_read_leave_the_switch_and_print_nothing(self) -> None:
        self.switch("on")
        for name, answer in {"garbled": "not json", "timeout": subprocess.TimeoutExpired(["m2b"], 10)}.items():
            with self.subTest(name):
                run = FakeStatus(status(True), addons_answer=answer)
                self.assertEqual(session_start.session_start(self.paths, self.environ, run), "")
                self.assertEqual(self.switch_value(), "on")

    def test_nothing_happens_inside_a_curation_run(self) -> None:
        run = FakeStatus(status(True))

        self.assertEqual(session_start.session_start(self.paths, {**self.environ, "M2B_CURATION_RUN": "1"}, run), "")
        self.assertEqual(run.calls, [])
        self.assertIsNone(self.switch_value())

    def test_an_installed_recorder_copy_is_replaced_after_an_update(self) -> None:
        copy = self.paths.recorder_copy
        copy.mkdir(parents=True)
        (copy / "herdr-plugin.toml").write_text('id = "m2b.worklog-recorder"\n', encoding="utf-8")
        (copy / "record.py").write_text("# the recorder of an older version\n", encoding="utf-8")

        session_start.session_start(self.paths, self.environ, FakeStatus(status(True)))

        for name in ("herdr-plugin.toml", "record.py"):
            self.assertEqual((copy / name).read_bytes(), (RECORDER_SOURCE / name).read_bytes())

    def test_without_an_installed_recorder_nothing_is_copied(self) -> None:
        session_start.session_start(self.paths, self.environ, FakeStatus(status(True)))

        self.assertFalse(self.paths.recorder_copy.exists())


class TemporaryNamesTest(WorklogFixture):
    def setUp(self) -> None:
        super().setUp()
        self.paths = worklog_paths(self.environ)

    def switch_value(self) -> str | None:
        path = self.state / "recording"
        return path.read_text(encoding="utf-8").strip() if path.exists() else None

    def test_a_leftover_temporary_name_does_not_stop_the_switch_or_the_copy(self) -> None:
        self.state.mkdir(parents=True)
        (self.state / ".recording.new").mkdir()
        copy = self.paths.recorder_copy
        copy.mkdir(parents=True)
        (copy / "herdr-plugin.toml").write_text("# older\n", encoding="utf-8")
        (copy / ".record.py.new").mkdir()
        (copy / ".herdr-plugin.toml.new").mkdir()

        output = session_start.session_start(self.paths, self.environ, FakeStatus(status(True)))

        self.assertEqual(output, "")
        self.assertEqual(self.switch_value(), "on")
        self.assertEqual((copy / "record.py").read_bytes(), (RECORDER_SOURCE / "record.py").read_bytes())
