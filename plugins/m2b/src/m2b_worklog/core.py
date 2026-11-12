"""What the worklog asks of the core, always through its launcher, as an integration
would: an add-on talks to the core only through ``m2b`` and the store format.

The store's folder and the profile, and the fenced model step. ``Core`` is what the daily worklog
needs; ``LauncherCore`` is the real one, tests hand in their own.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from m2b_worklog.paths import WorklogPaths
from m2b_worklog.sources.git import Runner

CORE_TIMEOUT_SECONDS = 30.0
# The model step has its own timeout in the core; this one only catches a launcher that hangs.
MODEL_TIMEOUT_SECONDS = 4 * 60 * 60.0


class CoreError(Exception):
    """The core did not answer."""


def ask(paths: WorklogPaths, arguments: list[str], run: Runner = subprocess.run) -> Any:
    try:
        result = run(
            [str(paths.launcher), *arguments, "--json"],
            capture_output=True,
            text=True,
            timeout=CORE_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError as error:
        raise CoreError(f"the m2b launcher {paths.launcher} is missing; run /m2b:m2b setup") from error
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CoreError(f"m2b {' '.join(arguments)} could not be run: {error}") from error
    if result.returncode != 0:
        reason = result.stderr.strip().splitlines()[:1]
        raise CoreError(f"m2b {' '.join(arguments)} failed" + (f": {reason[0]}" if reason else ""))
    try:
        return json.loads(result.stdout)
    except ValueError as error:
        raise CoreError(f"m2b {' '.join(arguments)} answered something that is not JSON") from error


class Core(Protocol):
    def store(self) -> Path: ...

    def profile(self) -> dict[str, Any]: ...

    def model(self, skill: str, allow: Sequence[str]) -> None: ...


class LauncherCore:
    def __init__(self, paths: WorklogPaths, environ: Mapping[str, str], run: Runner = subprocess.run) -> None:
        self._paths, self._environ, self._run = paths, environ, run

    def store(self) -> Path:
        return Path(str(ask(self._paths, ["config", "get", "store.path"], self._run)))

    def profile(self) -> dict[str, Any]:
        profile = ask(self._paths, ["profile", "get"], self._run)
        return profile if isinstance(profile, dict) else {}

    def model(self, skill: str, allow: Sequence[str]) -> None:
        """``m2b curate model``, which loads this plugin and its skills; inside a curation run it joins that run."""
        arguments = ["curate", "model", "--skill", skill]
        for rule in allow:
            arguments += ["--allow", rule]
        self._call(arguments, MODEL_TIMEOUT_SECONDS)

    def _call(self, arguments: list[str], timeout: float) -> None:
        try:
            result = self._run(
                [str(self._paths.launcher), *arguments],
                capture_output=True,
                text=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
                env=dict(self._environ),
            )
        except FileNotFoundError as error:
            raise CoreError(f"the m2b launcher {self._paths.launcher} is missing; run /m2b:m2b setup") from error
        except (OSError, subprocess.TimeoutExpired) as error:
            raise CoreError(f"m2b {' '.join(arguments[:2])} could not be run: {error}") from error
        if result.returncode != 0:
            reason = (result.stderr.strip() or result.stdout.strip()).splitlines()[-1:]
            raise CoreError(f"m2b {' '.join(arguments[:2])} failed" + (f": {reason[0]}" if reason else ""))
