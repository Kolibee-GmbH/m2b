"""Step reports: how a model step hands its findings to the run.

A run opens a findings file under the machine state, ``runs/<token>.jsonl``, and passes the token
to its model steps in ``M2B_RUN_TOKEN``. ``m2b curate report`` appends one JSON line per finding;
the run reads them for its review and closes the file. Without an open run there is nowhere to
report to, so a report outside a run is refused. A finding is ``action`` (the owner must do
something; it keeps the review task open) or ``info``.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from m2b.paths import MachinePaths

RUN_TOKEN_VARIABLE = "M2B_RUN_TOKEN"
ACTION = "action"
INFO = "info"
KINDS = (ACTION, INFO)
# A finding is one line of the review task; a model must not flood it.
MAX_TEXT_CHARACTERS = 500
UNREADABLE_STEP = "run"

_TOKEN = re.compile(r"[0-9a-f]{32}")
_STEP = re.compile(r"[a-z][a-z0-9-]*")


class NoRunError(Exception):
    """There is no open run for this token: a report outside a curation run."""


class FindingError(Exception):
    """A finding with an unknown kind, a bad step name or no text."""


@dataclass(frozen=True)
class Finding:
    step: str
    kind: str
    text: str
    # A change of the facts or the copy of ``memory/`` the text describes, as data for the band
    # (``m2b band --json``); None for every other finding.
    change: Mapping[str, object] | None = None


def runs_dir(machine: MachinePaths) -> Path:
    return machine.state_dir / "runs"


def run_file(machine: MachinePaths, token: str) -> Path:
    if not _TOKEN.fullmatch(token):
        raise NoRunError("the run token is not one a curation run hands out")
    return runs_dir(machine) / f"{token}.jsonl"


def open_run(machine: MachinePaths) -> str:
    """Creates an empty findings file, readable only by the owner, and returns its token."""
    folder = runs_dir(machine)
    folder.mkdir(parents=True, exist_ok=True)
    while True:
        token = secrets.token_hex(16)
        try:
            descriptor = os.open(run_file(machine, token), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        os.close(descriptor)
        return token


def require_open_run(machine: MachinePaths, token: str) -> None:
    if not run_file(machine, token).is_file():
        raise NoRunError("no curation run is open for this run token")


def add_finding(machine: MachinePaths, token: str, finding: Finding) -> None:
    """Appends the finding as one line; the run's file must exist, a report never creates it."""
    path = run_file(machine, token)
    line = json.dumps({"step": finding.step, "kind": finding.kind, "text": _checked_text(finding)}) + "\n"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND)
    except FileNotFoundError as error:
        raise NoRunError("no curation run is open for this run token") from error
    try:
        os.write(descriptor, line.encode("utf-8"))
    finally:
        os.close(descriptor)


def read_findings(machine: MachinePaths, token: str) -> list[Finding]:
    """The run's findings in the order they came; a line that cannot be read becomes an action."""
    findings = []
    for line in run_file(machine, token).read_bytes().split(b"\n"):
        if not line.strip():
            continue
        try:
            raw = json.loads(line.decode("utf-8"))
            findings.append(Finding(str(raw["step"]), str(raw["kind"]), str(raw["text"])))
        except (ValueError, KeyError, TypeError):
            findings.append(Finding(UNREADABLE_STEP, ACTION, "a finding of this run could not be read"))
    return findings


def close_run(machine: MachinePaths, token: str) -> None:
    run_file(machine, token).unlink(missing_ok=True)


def _checked_text(finding: Finding) -> str:
    if finding.kind not in KINDS:
        raise FindingError(f"the kind {finding.kind!r} is not one of {', '.join(KINDS)}")
    if not _STEP.fullmatch(finding.step):
        raise FindingError(f"the step {finding.step!r} is not a step name like lint or worklog")
    text = one_line(finding.text)
    if not text:
        raise FindingError("a finding needs a text")
    return text


def one_line(text: str) -> str:
    """Whitespace and line breaks collapsed, cut to ``MAX_TEXT_CHARACTERS``: one paragraph of the review."""
    text = " ".join(text.split())
    if len(text) > MAX_TEXT_CHARACTERS:
        text = text[: MAX_TEXT_CHARACTERS - 3].rstrip() + "..."
    return text
