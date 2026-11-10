"""The operating-system timer that runs the recorder's tick every five minutes.

herdr has no timer for plugins, and its startup hooks must not leave a process behind, so the tick
comes from the operating system: a launchd agent on macOS, a systemd user timer on Linux. Each run
is one short ``record.py --tick`` from the recorder copy, so an update of the copy reaches the next
tick without a restart.

``install`` from setup checks that the timer is loaded and starts it when it is not; the
session-start refresh only compares the timer's files, so it starts no process on a machine where
the timer is in place. A start that fails takes the files it wrote back out, so the next run tries
again. The interpreter stays the one the timer already runs while it still exists, so a session
started from another ``PATH`` does not rewrite the timer.

Without a timer the recorder still records, and the reader names no stretch as not recorded,
because it does so only from the first tick on.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import plistlib
import shlex
import subprocess
import sys
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from m2b_worklog.files import replace_file
from m2b_worklog.paths import WorklogPaths

LABEL = "m2b.worklog-recorder.tick"
UNIT = "m2b-worklog-recorder-tick"
INTERVAL_SECONDS = 300
COMMAND_TIMEOUT_SECONDS = 10.0
# The recorder reads these to find m2b's state and Claude Code's settings; the timer starts without them.
CARRIED_VARIABLES = ("M2B_HOME", "CLAUDE_CONFIG_DIR", "M2B_INSTALLED_PLUGINS", "M2B_MANAGED_SETTINGS")
MACOS = "darwin"

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class TimerError(Exception):
    """The timer could not be set up or taken out."""


@dataclass(frozen=True)
class TimerPlace:
    """Where the timer lives on this machine, how it is driven, and with which interpreter."""

    paths: WorklogPaths
    environ: Mapping[str, str]
    platform: str
    python: str

    @property
    def is_macos(self) -> bool:
        return self.platform == MACOS

    @property
    def is_linux(self) -> bool:
        return self.platform.startswith("linux")

    @property
    def tick_command(self) -> list[str]:
        return [self.python, str(self.paths.recorder_copy / "record.py"), "--tick"]

    @property
    def carried(self) -> dict[str, str]:
        return {name: self.environ[name] for name in CARRIED_VARIABLES if self.environ.get(name)}

    @property
    def launch_agent(self) -> Path:
        return self.paths.home / "Library" / "LaunchAgents" / f"{LABEL}.plist"

    @property
    def systemd_folder(self) -> Path:
        config = self.environ.get("XDG_CONFIG_HOME") or str(self.paths.home / ".config")
        return Path(config) / "systemd" / "user"

    @property
    def service(self) -> Path:
        return self.systemd_folder / f"{UNIT}.service"

    def files(self) -> dict[Path, bytes]:
        """The timer's files with the content they should have; none on a platform without a timer."""
        if self.is_macos:
            return {self.launch_agent: self._plist()}
        if self.is_linux:
            return {self.service: self._service().encode("utf-8"), self.systemd_folder / f"{UNIT}.timer": _TIMER}
        return {}

    def _plist(self) -> bytes:
        agent: dict[str, object] = {
            "Label": LABEL,
            "ProgramArguments": self.tick_command,
            "StartInterval": INTERVAL_SECONDS,
            "ProcessType": "Background",
            "StandardOutPath": os.devnull,
            "StandardErrorPath": os.devnull,
        }
        if self.carried:
            agent["EnvironmentVariables"] = self.carried
        return plistlib.dumps(agent)

    def _service(self) -> str:
        lines = [
            "[Unit]",
            "Description=m2b worklog: the recorder's sign of life while herdr runs",
            "",
            "[Service]",
            "Type=oneshot",
            "ExecStart=" + " ".join(_quoted(part) for part in self.tick_command),
            *(f"Environment={_quoted(f'{name}={value}', command=False)}" for name, value in self.carried.items()),
            "StandardOutput=null",
            "StandardError=null",
        ]
        return "\n".join(lines) + "\n"


_TIMER = b"""[Unit]
Description=m2b worklog: run the recorder's sign of life every five minutes

[Timer]
OnBootSec=300s
OnUnitActiveSec=300s
AccuracySec=30s

[Install]
WantedBy=timers.target
"""


def place_for(paths: WorklogPaths, environ: Mapping[str, str]) -> TimerPlace:
    """This machine's timer; ``M2B_TIMER_PLATFORM`` stands in for the platform in tests."""
    platform = environ.get("M2B_TIMER_PLATFORM") or sys.platform
    bare = TimerPlace(paths, environ, platform, sys.executable)
    kept = installed_python(bare)
    return TimerPlace(paths, environ, platform, kept or sys.executable)


def installed_python(place: TimerPlace) -> str | None:
    """The interpreter the installed timer runs, while it still exists."""
    try:
        if place.is_macos:
            python = plistlib.loads(place.launch_agent.read_bytes())["ProgramArguments"][0]
        elif place.is_linux:
            line = next(x for x in place.service.read_text(encoding="utf-8").splitlines() if x.startswith("ExecStart="))
            python = shlex.split(line[len("ExecStart=") :])[0]
        else:
            return None
    except (OSError, ValueError, KeyError, IndexError, TypeError, StopIteration, plistlib.InvalidFileException):
        return None
    return python if isinstance(python, str) and os.access(python, os.X_OK) else None


def install(place: TimerPlace, run: Runner = subprocess.run, verify: bool = False) -> str:
    """Writes and starts the timer; with ``verify`` (setup) also when its files are there but it is not loaded."""
    wanted = place.files()
    if not wanted:
        return f"no timer on {place.platform}; the worklog names no stretch as not recorded"
    _refuse_real_tools_in_a_sandbox(place)
    with _locked(place):
        in_place = all(path.is_file() and path.read_bytes() == data for path, data in wanted.items())
        if in_place and (not verify or _loaded(place, run)):
            return "timer in place"
        written = [path for path, data in wanted.items() if not path.is_file() or path.read_bytes() != data]
        for path in written:
            path.parent.mkdir(parents=True, exist_ok=True)
            replace_file(path, wanted[path])
        try:
            _start(place, run)
        except TimerError:
            for path in written:
                with contextlib.suppress(OSError):
                    path.unlink()
            raise
    return "timer set up to run every five minutes"


def remove(place: TimerPlace, run: Runner = subprocess.run) -> str:
    """Stops the timer and deletes its files; a timer that is not there is left as it is."""
    present = [path for path in place.files() if path.exists()]
    if not present:
        return "no timer was set up"
    _refuse_real_tools_in_a_sandbox(place)
    with _locked(place):
        if place.is_macos:
            _command(place, _launchctl(place), ["bootout", f"gui/{os.getuid()}/{LABEL}"], run, check=False)
        else:
            _command(place, _systemctl(place), ["--user", "disable", "--now", f"{UNIT}.timer"], run, check=False)
        for path in present:
            path.unlink()
        if not place.is_macos:
            _command(place, _systemctl(place), ["--user", "daemon-reload"], run, check=False)
    return "timer stopped and removed"


def _start(place: TimerPlace, run: Runner) -> None:
    if place.is_macos:
        domain = f"gui/{os.getuid()}"
        _command(place, _launchctl(place), ["bootout", f"{domain}/{LABEL}"], run, check=False)
        _command(place, _launchctl(place), ["bootstrap", domain, str(place.launch_agent)], run)
    else:
        _command(place, _systemctl(place), ["--user", "daemon-reload"], run)
        _command(place, _systemctl(place), ["--user", "enable", "--now", f"{UNIT}.timer"], run)


def _loaded(place: TimerPlace, run: Runner) -> bool:
    if place.is_macos:
        arguments = ["print", f"gui/{os.getuid()}/{LABEL}"]
        return _command(place, _launchctl(place), arguments, run, check=False) == 0
    return (
        _command(place, _systemctl(place), ["--user", "is-active", "--quiet", f"{UNIT}.timer"], run, check=False) == 0
    )


def _refuse_real_tools_in_a_sandbox(place: TimerPlace) -> None:
    """A run with its own ``M2B_HOME`` (a test) must never change the machine's real timer."""
    if not place.environ.get("M2B_HOME"):
        return
    tool = "M2B_LAUNCHCTL" if place.is_macos else "M2B_SYSTEMCTL"
    if not place.environ.get(tool):
        raise TimerError(f"M2B_HOME is set but {tool} is not; refusing to change this machine's timer")


@contextlib.contextmanager
def _locked(place: TimerPlace) -> Iterator[None]:
    """Sessions started together after an update would otherwise interleave stop and start."""
    lock_path = place.paths.recorder_copy.parent / "timer.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _launchctl(place: TimerPlace) -> str:
    return place.environ.get("M2B_LAUNCHCTL") or "launchctl"


def _systemctl(place: TimerPlace) -> str:
    return place.environ.get("M2B_SYSTEMCTL") or "systemctl"


def _command(place: TimerPlace, command: str, arguments: Sequence[str], run: Runner, check: bool = True) -> int:
    try:
        result = run(
            [command, *arguments],
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
            env=dict(place.environ),
        )
    except FileNotFoundError as error:
        raise TimerError(f"{command} was not found") from error
    except (OSError, subprocess.TimeoutExpired) as error:
        raise TimerError(f"{command} could not be run: {error}") from error
    if check and result.returncode != 0:
        reason = result.stderr.strip().splitlines()[:1]
        detail = f": {reason[0]}" if reason else ""
        raise TimerError(f"{command} {arguments[0]} ended with exit {result.returncode}{detail}")
    return result.returncode


def _quoted(text: str, command: bool = True) -> str:
    """One quoted word for a systemd unit, its specifiers taken literally; ``$`` only matters on a command line."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    if command:
        escaped = escaped.replace("$", "$$")
    return f'"{escaped}"'
