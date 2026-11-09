"""What the backup asks of the core, always through its launcher: settings, the task list, a finding.

A part talks to the core only through ``m2b`` and the store format, as an add-on does.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Callable

CORE_TIMEOUT_SECONDS = 60.0
EXIT_UNREACHABLE = 3
RUN_TOKEN_VARIABLE = "M2B_RUN_TOKEN"

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class CoreError(Exception):
    """The core did not answer as it should."""


class TasksUnreachableError(Exception):
    """The task list could not be reached; an empty answer would not have meant an empty list (X3)."""


class Core:
    def __init__(self, launcher: Path, environ: Mapping[str, str], run: Runner = subprocess.run) -> None:
        self._launcher, self._environ, self._run = launcher, environ, run

    def store(self) -> Path:
        return Path(str(self._json(["config", "get", "store.path", "--json"])))

    def settings(self) -> Any:
        """This machine's ``parts.backup``, ``on`` included, or None when it has none."""
        parts = self._json(["config", "get", "parts", "--json"])
        return parts.get("backup") if isinstance(parts, dict) else None

    def tasks(self) -> str:
        """The task list with completed tasks, as JSON text."""
        result = self._call(["tasks", "list", "--include-completed", "--json"])
        if result.returncode == EXIT_UNREACHABLE:
            raise TasksUnreachableError(_reason(result) or "the task list could not be reached")
        if result.returncode != 0:
            raise CoreError(f"m2b tasks list failed: {_reason(result)}")
        try:
            listed = json.loads(result.stdout)
        except ValueError as error:
            raise CoreError("m2b tasks list answered something that is not JSON") from error
        if not isinstance(listed, list):
            raise CoreError("m2b tasks list answered something that is not a list")
        return result.stdout

    def report(self, kind: str, text: str) -> bool:
        """Hands a finding to the curation run this step runs in; False outside a run."""
        if not self._environ.get(RUN_TOKEN_VARIABLE):
            return False
        result = self._call(["curate", "report", "--step", "backup", "--kind", kind, "--text", text])
        if result.returncode != 0:
            raise CoreError(f"m2b curate report failed: {_reason(result)}")
        return True

    def _json(self, arguments: Sequence[str]) -> Any:
        result = self._call(arguments)
        if result.returncode != 0:
            raise CoreError(f"m2b {' '.join(arguments[:3])} failed: {_reason(result)}")
        try:
            return json.loads(result.stdout)
        except ValueError as error:
            raise CoreError(f"m2b {' '.join(arguments[:3])} answered something that is not JSON") from error

    def _call(self, arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
        try:
            return self._run(
                [str(self._launcher), *arguments],
                capture_output=True,
                text=True,
                timeout=CORE_TIMEOUT_SECONDS,
                stdin=subprocess.DEVNULL,
                env=dict(self._environ),
            )
        except FileNotFoundError as error:
            raise CoreError(f"the m2b launcher {self._launcher} is missing; run /m2b:m2b setup") from error
        except (OSError, subprocess.TimeoutExpired) as error:
            raise CoreError(f"m2b {' '.join(arguments[:2])} could not be run: {error}") from error


def _reason(result: subprocess.CompletedProcess[str]) -> str:
    lines = (result.stderr.strip() or result.stdout.strip()).splitlines()
    return lines[-1] if lines else f"exit {result.returncode}"
