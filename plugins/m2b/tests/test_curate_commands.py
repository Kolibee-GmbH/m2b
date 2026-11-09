"""``m2b curate`` with ``--force`` and ``--detach``, ``curate take-over``, ``parts list / on / off``."""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import signal
import subprocess
import time

import test_runner
from m2b import cli, launcher
from m2b.config.machine import load_machine_config
from m2b.config.store_settings import load_store_settings
from m2b.curate import machine_state, runner
from m2b.run_record import RUN_RECORD, RUNNING, SUCCEEDED, load_run_record


class CurateCommandTest(test_runner.RunnerTest):
    def test_curate_force_runs_and_says_how_it_ended(self) -> None:
        self.curating()

        code, out, err = self.run_command("curate", "--force")

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertIn("succeeded", out)
        record = load_run_record(self.store)
        assert record is not None
        self.assertEqual(record.state, SUCCEEDED)

    def test_a_failed_run_exits_1(self) -> None:
        self.curating()
        self.repairable_link()
        self.model({"m2b:lint": []}, outcomes={"m2b:lint": "error"})

        code, out, _ = self.run_command("curate", "--force")

        self.assertEqual(code, cli.EXIT_PROBLEM)
        self.assertIn("lint", out)

    def test_not_the_curating_machine_and_already_running_exit_0(self) -> None:
        """Covers: B62, B63"""
        self.curating()
        lock = machine_state.RunLock(self.machine)
        self.assertTrue(lock.acquire())
        code, out, _ = self.run_command("curate", "--force")
        lock.release()
        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("already running", out)

        self.set_store_value("curating_machine", "sb-test-m2")
        code, out, _ = self.run_command("curate", "--force")
        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("not the curating machine", out)

    def test_unreachable_tasks_exit_3(self) -> None:
        self.curating(tasks={"backend": "apple-reminders", "list": "sb-test-missing"})

        code, _, err = self.run_command("curate", "--force")

        self.assertEqual(code, cli.EXIT_UNREACHABLE)
        self.assertIn("sb-test-missing", err)

    def test_without_force_a_run_that_is_not_due_exits_0_and_does_nothing(self) -> None:
        """Covers: B12"""
        self.curating()
        self.write(
            RUN_RECORD,
            json.dumps(
                {"state": "succeeded", "machine_id": "sb-test-m1", "started_at": _ago(1), "finished_at": _ago(1)}
            ),
        )

        code, out, _ = self.run_command("curate")

        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("no curation run is due", out)
        self.assertEqual(self.calls(), [])

    def test_the_subcommands_still_parse(self) -> None:
        self.curating()
        code, _, err = self.run_command("curate", "report", "--step", "lint", "--kind", "info", "--text", "x")
        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertIn("M2B_RUN_TOKEN", err)

    def set_store_value(self, key: str, value: object) -> None:
        path = self.store_root / "store.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw[key] = value
        path.write_text(json.dumps(raw), encoding="utf-8")


class KilledRunnerTest(test_runner.RunnerTest):
    def test_the_lock_stays_held_while_a_model_step_runs_after_the_runner_was_killed(self) -> None:
        self.curating()
        self.repairable_link()
        pid_file = self.bin.parent / "hanging.pid"
        self.model({"m2b:lint": [{"hang": str(pid_file)}]})
        environ = {**os.environ, **self.environ}
        command = launcher.core_command(["curate", "--force"])
        runner_process = subprocess.Popen(command, env=environ, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(runner_process.wait)
        self.addCleanup(_kill, runner_process.pid)
        deadline = time.monotonic() + 20
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertTrue(pid_file.exists(), "the model step never started")

        runner_process.kill()
        runner_process.wait()

        self.assertTrue(machine_state.lock_is_held(self.machine))
        code, out, _ = self.run_command("curate", "--force")
        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("already running", out)
        record = load_run_record(self.store)
        assert record is not None
        self.assertEqual(record.state, RUNNING)

        # The model step's process group: the stub and the child it hangs on.
        os.killpg(os.getpgid(int(pid_file.read_text(encoding="utf-8"))), signal.SIGKILL)
        deadline = time.monotonic() + 10
        while machine_state.lock_is_held(self.machine) and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertFalse(machine_state.lock_is_held(self.machine))


class DetachTest(test_runner.RunnerTest):
    def test_detach_starts_the_run_in_the_background_and_returns_at_once(self) -> None:
        """Covers: B11"""
        self.curating()
        started: list[list[str]] = []

        def fake_start(command: list[str], **options: object) -> object:
            started.append(command)
            self.assertTrue(options.get("start_new_session"))
            return _Started()

        with test_runner.mock.patch("m2b.curate.detach.subprocess.Popen", side_effect=fake_start):
            code, out, err = self.run_command("curate", "--force", "--detach")

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertIn("started in the background", out)
        (command,) = started
        self.assertEqual(command[-2:], ["curate", "--force"])
        self.assertFalse((self.store_root / RUN_RECORD).exists())

    def test_refresh_all_reaches_the_run(self) -> None:
        outcome = runner.RunOutcome(SUCCEEDED, "the curation run succeeded")
        with test_runner.mock.patch("m2b.commands.curate.runner.curate", return_value=outcome) as curate:
            code, _, err = self.run_command("curate", "--refresh-all")

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(curate.call_args.kwargs, {"force": False, "refresh_all": True, "sort_facts": False})

    def test_sort_facts_reaches_the_run(self) -> None:
        """Covers: B51"""
        outcome = runner.RunOutcome(SUCCEEDED, "the curation run succeeded")
        with test_runner.mock.patch("m2b.commands.curate.runner.curate", return_value=outcome) as curate:
            code, _, err = self.run_command("curate", "--sort-facts")

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(curate.call_args.kwargs, {"force": False, "refresh_all": False, "sort_facts": True})

    def test_detach_passes_sort_facts_on_to_the_run_it_starts(self) -> None:
        self.curating()

        with test_runner.mock.patch("m2b.curate.detach.subprocess.Popen", return_value=_Started()) as start:
            code, _, err = self.run_command("curate", "--sort-facts", "--detach")

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(start.call_args.args[0][-3:], ["curate", "--force", "--sort-facts"])

    def test_detach_passes_refresh_all_on_to_the_run_it_starts(self) -> None:
        self.curating()

        with test_runner.mock.patch("m2b.curate.detach.subprocess.Popen", return_value=_Started()) as start:
            code, _, err = self.run_command("curate", "--refresh-all", "--detach")

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(start.call_args.args[0][-3:], ["curate", "--force", "--refresh-all"])

    def test_detach_says_why_nothing_started(self) -> None:
        self.curating()
        lock = machine_state.RunLock(self.machine)
        self.assertTrue(lock.acquire())
        self.addCleanup(lock.release)

        with test_runner.mock.patch("m2b.curate.detach.subprocess.Popen") as start:
            code, out, _ = self.run_command("curate", "--force", "--detach")

        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("already running", out)
        start.assert_not_called()


class TakeOverTest(test_runner.RunnerTest):
    def test_take_over_names_this_machine_and_lists_the_parts_that_were_on_there(self) -> None:
        self.curating()
        self.set_store("sb-test-m2")
        self.write(
            RUN_RECORD,
            json.dumps(
                {
                    "state": "succeeded",
                    "machine_id": "sb-test-m2",
                    "started_at": _ago(5),
                    "finished_at": _ago(5),
                    "parts": ["worklog", "backup"],
                }
            ),
        )

        code, out, err = self.run_command("curate", "take-over")

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(load_store_settings(self.store).curating_machine, "sb-test-m1")
        self.assertIn("sb-test-m2", out)
        self.assertIn("/m2b:worklog-setup", out)
        self.assertIn("/m2b:backup-setup", out)
        self.assertEqual(self.run_command("curate", "--force")[0], cli.EXIT_OK)

    def test_take_over_refuses_a_store_path_no_curation_run_can_work_in(self) -> None:
        """Covers: B81"""
        self.curating()
        self.set_store("sb-test-m2")
        linked = self.store_root.parent / "Dropbox (Personal)"
        linked.symlink_to(self.store_root)
        config = json.loads(self.machine.config_file.read_text(encoding="utf-8"))
        config["store"]["path"] = str(linked)
        self.machine.config_file.write_text(json.dumps(config), encoding="utf-8")

        code, _, err = self.run_command("curate", "take-over")

        self.assertEqual(code, cli.EXIT_USAGE, err)
        self.assertIn("(", err)
        self.assertEqual(load_store_settings(self.store).curating_machine, "sb-test-m2")

    def test_the_old_machine_stops_at_its_next_preflight(self) -> None:
        self.curating()
        self.run_command("curate", "take-over")
        self.set_store("sb-test-m2")

        code, out, _ = self.run_command("curate", "--force")

        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("not the curating machine", out)
        self.assertFalse((self.store_root / RUN_RECORD).exists())

    def test_an_unreadable_run_record_does_not_stop_a_take_over(self) -> None:
        self.curating()
        self.set_store("sb-test-m2")
        self.write(RUN_RECORD, "{truncated")

        code, out, err = self.run_command("curate", "take-over")

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(load_store_settings(self.store).curating_machine, "sb-test-m1")
        self.assertIn("cannot be read", out)
        self.assertIn("parts that were on", out)

    def test_take_over_on_the_curating_machine_changes_nothing(self) -> None:
        self.curating()
        before = (self.store_root / "store.json").read_bytes()

        code, out, _ = self.run_command("curate", "take-over")

        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("already", out)
        self.assertEqual((self.store_root / "store.json").read_bytes(), before)

    def test_take_over_during_a_run_on_the_other_machine_is_refused(self) -> None:
        self.curating()
        self.set_store("sb-test-m2")
        start = datetime.datetime.now().astimezone().replace(microsecond=0) - datetime.timedelta(minutes=5)
        self.write(
            RUN_RECORD,
            json.dumps(
                {
                    "state": "running",
                    "machine_id": "sb-test-m2",
                    "started_at": start.isoformat(),
                    "deadline_at": (start + datetime.timedelta(minutes=30)).isoformat(),
                }
            ),
        )

        code, _, err = self.run_command("curate", "take-over")

        self.assertEqual(code, cli.EXIT_PROBLEM)
        self.assertIn("sb-test-m2", err)
        self.assertEqual(load_store_settings(self.store).curating_machine, "sb-test-m2")

    def set_store(self, curating_machine: str) -> None:
        path = self.store_root / "store.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["curating_machine"] = curating_machine
        path.write_text(json.dumps(raw), encoding="utf-8")


class PartsCommandTest(test_runner.RunnerTest):
    def test_a_part_is_off_until_turned_on_and_off_keeps_its_settings(self) -> None:
        self.curating()
        code, out, _ = self.run_command("parts", "list", "--json")
        self.assertEqual(code, cli.EXIT_OK)
        self.assertEqual([(row["name"], row["on"]) for row in json.loads(out)], [
            ("band", False), ("herdr", False), ("worklog", False), ("backup", False),
        ])  # fmt: skip

        self.run_command("config", "set", "parts.backup", '{"target": "~/sb-test-backup"}')
        self.assertEqual(self.run_command("parts", "on", "backup"), (cli.EXIT_OK, "backup is on\n", ""))
        self.assertEqual(self.run_command("parts", "on", "backup")[1], "backup was on already\n")
        self.assertEqual(self.run_command("parts", "off", "backup")[1], "backup is off\n")
        self.assertEqual(load_machine_config(self.machine).parts["backup"], {"target": "~/sb-test-backup", "on": False})

        code, out, _ = self.run_command("parts", "list")
        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("backup   off  after each curation run", out)

    def test_an_unknown_part_is_a_usage_error_that_names_the_parts(self) -> None:
        self.curating()
        code, _, err = self.run_command("parts", "on", "bakcup")
        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertIn("band, herdr, worklog, backup", err)

    def test_before_setup_the_parts_cannot_be_listed(self) -> None:
        code, _, err = self.run_command("parts", "list", "--json")
        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertIn("not set up", err)


class _Started:
    pid = 4242


def _ago(hours: float) -> str:
    moment = datetime.datetime.now().astimezone() - datetime.timedelta(hours=hours)
    return moment.isoformat(timespec="seconds")


def _kill(pid: int) -> None:
    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, signal.SIGKILL)


if __name__ == "__main__":
    import unittest

    unittest.main()
