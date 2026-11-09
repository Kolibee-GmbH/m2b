"""The handlers behind ``m2b``: each takes the parsed arguments and a ``Context``.

A handler calls the library, prints its answer and returns an exit code; ``cli`` parses the
arguments and turns the library's errors into exit codes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from m2b.paths import MachinePaths


@dataclass(frozen=True)
class Context:
    machine: MachinePaths
    environ: Mapping[str, str]


class UsageError(Exception):
    """The arguments do not make sense for this setup."""


class ProblemError(Exception):
    """The command ran and found something the user must act on (exit 1)."""
