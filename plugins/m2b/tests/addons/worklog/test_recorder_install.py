"""Installing and removing the recorder in a fake herdr, and refreshing the installed copy."""

from __future__ import annotations

import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

from m2b_worklog import recorder, timer
from m2b_worklog.paths import RECORDER_ID, RECORDER_SOURCE, worklog_paths
from worklog_fixtures import COMMAND, WorklogFixture


class CommandFixture(WorklogFixture):
    def run_command(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environ = {**self.environ, "PATH": os.environ.get("PATH", ""), "M2B_PYTHON": sys.executable}
        return subprocess.run([str(COMMAND), *arguments], capture_output=True, text=True, env=environ, timeout=30)

    @property
    def copy(self) -> Path:
        return self.home / ".local" / "share" / "m2b" / "worklog-recorder"


class RecorderTest(CommandFixture):
    def test_install_copies_the_recorder_and_links_the_copy(self) -> None:
        result = self.run_command("recorder", "install")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            sorted(p.name for p in self.copy.iterdir()), ["herdr-plugin.toml", "linked-version", "record.py"]
        )
        self.assertEqual((self.copy / "record.py").read_bytes(), (RECORDER_SOURCE / "record.py").read_bytes())
        self.assertEqual(self.linked(), {RECORDER_ID: str(self.copy)})

    def test_install_twice_links_once(self) -> None:
        self.run_command("recorder", "install")
        again = self.run_command("recorder", "install")

        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("already linked", again.stdout)
        self.assertEqual(
            [call for call in self.herdr_calls_made() if call.startswith("plugin link")], [f"plugin link {self.copy}"]
        )

    def test_remove_unlinks_and_deletes_the_copy_and_runs_twice(self) -> None:
        self.run_command("recorder", "install")
        self.state.mkdir(parents=True)
        (self.state / "w1.jsonl").write_text('{"kind": "focus"}\n', encoding="utf-8")

        first = self.run_command("recorder", "remove")
        second = self.run_command("recorder", "remove")

        self.assertEqual((first.returncode, second.returncode), (0, 0), first.stderr + second.stderr)
        self.assertEqual(self.linked(), {})
        self.assertFalse(self.copy.exists())
        self.assertIn("was not linked", second.stdout)
        self.assertTrue((self.state / "w1.jsonl").exists())

    def test_a_herdr_that_cannot_be_run_is_one_error_line(self) -> None:
        environ_herdr = self.environ["M2B_HERDR"]
        self.environ["M2B_HERDR"] = str(self.base / "no-herdr")

        result = self.run_command("recorder", "install")

        self.environ["M2B_HERDR"] = environ_herdr
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr.count("\n"), 1)
        self.assertIn("was not found", result.stderr)

    def test_refresh_replaces_an_installed_copy_and_leaves_a_missing_one_absent(self) -> None:
        paths = worklog_paths(self.environ)
        self.assertFalse(recorder.refresh(paths, self.environ))
        self.assertFalse(self.copy.exists())

        self.run_command("recorder", "install")
        (self.copy / "record.py").write_text("# an older recorder\n", encoding="utf-8")

        self.assertTrue(recorder.refresh(paths, self.environ))
        self.assertEqual((self.copy / "record.py").read_bytes(), (RECORDER_SOURCE / "record.py").read_bytes())
        self.assertFalse(recorder.refresh(paths, self.environ))

    def test_a_plugin_list_herdr_does_not_answer_as_a_list_is_an_error(self) -> None:
        paths = worklog_paths(self.environ)

        def garbled(command: list[str], **options: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(command, 0, "plugins: none", "")

        with self.assertRaises(recorder.HerdrError):
            recorder.install(paths, self.environ, garbled)


class RelinkTest(CommandFixture):
    """herdr keeps a plugin's events and startup as they were at link time, so a new version is linked again."""

    def test_install_links_again_when_herdr_holds_another_version(self) -> None:
        """Covers: B88"""
        self.run_command("recorder", "install")
        self.herdr_holds_version("0.1.0")

        result = self.run_command("recorder", "install")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.herdr_calls_made().count(f"plugin link {self.copy}"), 2)
        self.assertIn("linked again in herdr", result.stdout)

    def test_an_upgrade_links_the_new_version_at_the_next_session_start_once(self) -> None:
        """Covers: B88"""
        self.run_command("recorder", "install")
        self.herdr_holds_version("0.1.0")
        (self.copy / "linked-version").unlink()
        manifest = self.copy / "herdr-plugin.toml"
        manifest.write_text(manifest.read_text(encoding="utf-8").replace('version = "0.2.0"', 'version = "0.1.0"'))
        paths = worklog_paths(self.environ)

        self.assertTrue(recorder.refresh(paths, self.environ))
        recorder.refresh(paths, self.environ)

        self.assertEqual(self.herdr_calls_made().count(f"plugin link {self.copy}"), 2)
        self.assertEqual(recorder.linked_recorder(self.environ)["version"], "0.2.0")  # type: ignore[index]

    def test_a_failed_link_is_tried_again_and_the_timer_is_set_up_anyway(self) -> None:
        """Covers: B88"""
        self.run_command("recorder", "install")
        (self.copy / "linked-version").write_text("0.1.0\n", encoding="utf-8")
        for path in self.home.glob("Library/LaunchAgents/*"):
            path.unlink()
        paths = worklog_paths(self.environ)
        broken = {**self.environ, "M2B_HERDR": str(self.base / "no-herdr")}

        with self.assertRaises(recorder.HerdrError):
            recorder.refresh(paths, broken)
        self.assertTrue(any(self.home.glob("Library/LaunchAgents/*.plist")))
        recorder.refresh(paths, self.environ)

        self.assertEqual((self.copy / "linked-version").read_text(encoding="utf-8"), "0.2.0\n")

    def test_a_steady_refresh_asks_neither_herdr_nor_the_timer(self) -> None:
        paths = worklog_paths(self.environ)
        self.run_command("recorder", "install")
        calls = (len(self.herdr_calls_made()), len(self.timer_calls_made()))

        recorder.refresh(paths, self.environ)

        self.assertEqual((len(self.herdr_calls_made()), len(self.timer_calls_made())), calls)

    def test_a_machine_that_does_not_record_gets_no_timer_from_the_refresh(self) -> None:
        self.run_command("recorder", "install")
        self.run_command("recorder", "remove")
        self.run_command("recorder", "install")
        for path in self.home.glob("Library/LaunchAgents/*"):
            path.unlink()

        recorder.refresh(worklog_paths(self.environ), self.environ, recording=False)

        self.assertEqual(list(self.home.glob("Library/LaunchAgents/*")), [])

    def test_a_recorder_turned_off_in_herdr_reads_could_not_read(self) -> None:
        listed = {"plugin_id": RECORDER_ID, "enabled": False, "version": "0.2.0"}
        reply = json.dumps({"result": {"plugins": [listed]}})

        state = recorder.herdr_state(self.environ, lambda *a, **k: subprocess.CompletedProcess(a, 0, reply, ""))

        self.assertFalse(state.is_read)
        self.assertIn("turned off in herdr", state.detail)


class TimerTest(CommandFixture):
    """The operating-system timer that runs the tick; only fakes of launchctl and systemctl run."""

    @property
    def agent(self) -> Path:
        return self.home / "Library" / "LaunchAgents" / "m2b.worklog-recorder.tick.plist"

    def place(self, platform: str = "darwin", **environ: str) -> timer.TimerPlace:
        return timer.TimerPlace(worklog_paths(self.environ), {**self.environ, **environ}, platform, sys.executable)

    def test_install_sets_up_a_launch_agent_on_macos(self) -> None:
        """Covers: B88"""
        result = self.run_command("recorder", "install")

        self.assertEqual(result.returncode, 0, result.stderr)
        agent = plistlib.loads(self.agent.read_bytes())
        self.assertEqual(agent["ProgramArguments"][1:], [str(self.copy / "record.py"), "--tick"])
        self.assertEqual(agent["StartInterval"], 300)
        self.assertEqual(agent["EnvironmentVariables"]["M2B_HOME"], str(self.home))
        self.assertIn(f"launchctl bootstrap gui/{os.getuid()} {self.agent}", self.timer_calls_made())
        self.assertIn("timer set up", result.stdout)

    def test_install_twice_starts_the_timer_once_and_remove_takes_it_out(self) -> None:
        """Covers: B88"""
        self.run_command("recorder", "install")
        self.run_command("recorder", "install")
        bootstraps = [call for call in self.timer_calls_made() if " bootstrap " in call]

        result = self.run_command("recorder", "remove")

        self.assertEqual(len(bootstraps), 1)
        self.assertFalse(self.agent.exists())
        self.assertIn(f"launchctl bootout gui/{os.getuid()}/m2b.worklog-recorder.tick", self.timer_calls_made())
        self.assertIn("timer stopped and removed", result.stdout)

    def test_setup_starts_a_timer_whose_files_are_there_but_which_is_not_loaded(self) -> None:
        """Covers: B88"""
        timer.install(self.place())

        self.assertEqual(timer.install(self.place(), verify=True), "timer in place")
        self.assertEqual(timer.install(self.place(FAKE_TIMER_FAIL="print")), "timer in place")
        self.assertIn("timer set up", timer.install(self.place(FAKE_TIMER_FAIL="print"), verify=True))
        self.assertEqual(
            [c for c in self.timer_calls_made() if " bootstrap " in c][1:],
            [f"launchctl bootstrap gui/{os.getuid()} {self.agent}"],
        )

    def test_a_timer_that_cannot_be_set_up_is_said_and_the_recorder_still_links(self) -> None:
        self.environ["FAKE_TIMER_EXIT"] = "1"

        result = self.run_command("recorder", "install")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("the timer could not be set up", result.stdout)
        self.assertFalse(self.agent.exists())
        self.assertEqual(self.linked(), {RECORDER_ID: str(self.copy)})

    def test_remove_takes_the_timer_out_even_when_herdr_is_gone(self) -> None:
        """Covers: B88"""
        self.run_command("recorder", "install")
        (self.state / "alive").mkdir(parents=True)
        (self.state / "alive" / "first-tick").write_text("2026-03-14T09:00:00+01:00\n", encoding="utf-8")
        self.environ["M2B_HERDR"] = str(self.base / "no-herdr")

        result = self.run_command("recorder", "remove")

        self.assertEqual(result.returncode, 1)
        self.assertFalse(self.agent.exists())
        self.assertFalse(self.copy.exists())
        self.assertFalse((self.state / "alive" / "first-tick").exists())

    def test_the_timer_keeps_the_interpreter_it_runs_while_that_exists(self) -> None:
        other = self.base / "python3"
        other.write_text("#!/bin/sh\n", encoding="utf-8")
        other.chmod(0o755)
        timer.install(timer.TimerPlace(worklog_paths(self.environ), self.environ, "darwin", str(other)))

        kept = timer.place_for(worklog_paths(self.environ), self.environ)
        other.unlink()
        replaced = timer.place_for(worklog_paths(self.environ), self.environ)

        self.assertEqual((kept.python, replaced.python), (str(other), sys.executable))

    def test_a_sandboxed_home_never_reaches_the_real_launchctl(self) -> None:
        environ = {key: value for key, value in self.environ.items() if key != "M2B_LAUNCHCTL"}

        with self.assertRaises(timer.TimerError):
            timer.install(timer.TimerPlace(worklog_paths(environ), environ, "darwin", sys.executable))

    def test_on_linux_a_systemd_user_timer_with_its_paths_quoted(self) -> None:
        """Covers: B88"""
        paths = worklog_paths({**self.environ, "M2B_HOME": str(self.base / "a home$")})
        environ = {**self.environ, "M2B_HOME": str(self.base / "a home$"), "XDG_CONFIG_HOME": str(self.base / "config")}
        place = timer.TimerPlace(paths, environ, "linux", "/usr/bin/python3")

        timer.install(place)

        units = self.base / "config" / "systemd" / "user"
        service = (units / "m2b-worklog-recorder-tick.service").read_text(encoding="utf-8")
        copy = f"{self.base}/a home$$/.local/share/m2b/worklog-recorder/record.py"
        self.assertIn(f'ExecStart="/usr/bin/python3" "{copy}" "--tick"', service)
        self.assertIn(f'Environment="M2B_HOME={self.base}/a home$"', service)
        self.assertIn("OnUnitActiveSec=300s", (units / "m2b-worklog-recorder-tick.timer").read_text(encoding="utf-8"))
        self.assertEqual(
            self.timer_calls_made(),
            ["systemctl --user daemon-reload", "systemctl --user enable --now m2b-worklog-recorder-tick.timer"],
        )
        self.assertEqual(timer.installed_python(place), "/usr/bin/python3")

        timer.remove(place)

        self.assertEqual(list(units.iterdir()), [])

    def test_a_platform_without_a_timer_gets_none_and_says_so(self) -> None:
        self.assertIn("no timer", timer.install(self.place("freebsd")))
        self.assertEqual(self.timer_calls_made(), [])


class HerdrCheckTest(WorklogFixture):
    """What setup asks first: is herdr there, new enough and running."""

    def check(self, **fake: str) -> dict[str, object]:
        environ = {**self.environ, "PATH": os.environ.get("PATH", ""), "M2B_PYTHON": sys.executable, **fake}
        result = subprocess.run(
            [str(COMMAND), "recorder", "check", "--json"], capture_output=True, text=True, env=environ, timeout=30
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        answer: dict[str, object] = json.loads(result.stdout)
        return answer

    def test_a_running_herdr_of_0_9_or_later_is_ready(self) -> None:
        """Covers: B90"""
        self.assertEqual(self.check(), {"herdr": "0.9.3", "running": True, "ready": True, "problem": None})
        self.assertTrue(self.check(FAKE_HERDR_VERSION="1.2.0")["ready"])

    def test_an_older_herdr_is_not_ready_and_says_how_to_update(self) -> None:
        """Covers: B90"""
        answer = self.check(FAKE_HERDR_VERSION="0.8.4")

        self.assertEqual((answer["herdr"], answer["ready"]), ("0.8.4", False))
        self.assertIn("older than 0.9.0", str(answer["problem"]))
        self.assertIn("herdr update", str(answer["problem"]))

    def test_a_herdr_that_is_not_running_is_not_ready(self) -> None:
        """Covers: B90"""
        answer = self.check(FAKE_HERDR_RUNNING="no")

        self.assertEqual((answer["running"], answer["ready"]), (False, False))
        self.assertIn("not running", str(answer["problem"]))

    def test_without_herdr_it_names_where_to_get_it(self) -> None:
        """Covers: B90"""
        answer = self.check(M2B_HERDR=str(self.base / "no-herdr"))

        self.assertEqual((answer["herdr"], answer["running"], answer["ready"]), (None, False, False))
        self.assertIn("https://herdr.dev", str(answer["problem"]))

    def test_the_lowest_version_is_the_one_the_manifest_asks_for(self) -> None:
        manifest = (RECORDER_SOURCE / "herdr-plugin.toml").read_text(encoding="utf-8")

        self.assertIn(f'min_herdr_version = "{recorder.MIN_HERDR_VERSION}"', manifest)
