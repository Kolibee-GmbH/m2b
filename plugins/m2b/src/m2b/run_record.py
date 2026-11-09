"""The run record ``state/core/last-run.json``: when the last curation run happened, where, how it ended.

Only the curating machine's runner writes it; every machine reads it. ``state`` (running, succeeded,
failed), ``machine_id`` and ``started_at`` are required; the rest is optional, so a record from an
older runner still reads. Unknown fields are ignored, so a newer runner does not break an older
reader, and a malformed entry in one of the lists is left out rather than failing the whole record:
the session-start line needs the state, not every step.

``last_succeeded_at`` carries the end of the last successful run across failed ones, because the
due check counts from it (B13). ``deadline_at`` is the latest a run can end: its start plus the
fetch timeout, each supervised step's timeout and grace, and a margin for the code steps. A
``running`` record past it is an interrupted run.
"""

from __future__ import annotations

import datetime
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

from m2b.curate.report import Finding
from m2b.notes.frontmatter import parse_time
from m2b.notes.layout import STATE
from m2b.store.base import Store

RUN_RECORD = f"{STATE}/core/last-run.json"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"
STATES = (RUNNING, SUCCEEDED, FAILED)
# A step result besides succeeded and failed.
SKIPPED = "skipped"
# A message goes into a one-line notice at session start; captured output must not flood it.
MAX_TEXT_CHARACTERS = 300

_Entry = TypeVar("_Entry")


class RunRecordError(Exception):
    """The run record is there but cannot be understood."""


@dataclass(frozen=True)
class StepResult:
    """One step of a run: ``succeeded``, ``failed`` or ``skipped``; ``detail`` says why it failed or was skipped."""

    name: str
    result: str
    detail: str = ""


@dataclass(frozen=True)
class RunRecord:
    state: str
    machine_id: str
    started_at: datetime.datetime
    finished_at: datetime.datetime | None = None
    message: str = ""
    deadline_at: datetime.datetime | None = None
    last_succeeded_at: datetime.datetime | None = None
    steps: tuple[StepResult, ...] = ()
    findings: tuple[Finding, ...] = ()
    # The parts that were on when this machine ran; ``curate take-over`` lists them.
    parts: tuple[str, ...] = ()

    @property
    def last_activity(self) -> datetime.datetime:
        return self.finished_at or self.started_at

    @property
    def last_success(self) -> datetime.datetime | None:
        if self.state == SUCCEEDED and self.finished_at is not None:
            return self.finished_at
        return self.last_succeeded_at


def is_interrupted(record: RunRecord, now: datetime.datetime) -> bool:
    """A run that says running but is past its deadline: its runner died or its machine slept."""
    return record.state == RUNNING and record.deadline_at is not None and now > record.deadline_at


def load_run_record(store: Store) -> RunRecord | None:
    """None before the first run; raises ``EvictedFileError`` for an evicted record and
    ``RunRecordError`` for one that cannot be read as a run record."""
    try:
        data = store.read_bytes(RUN_RECORD)
    except FileNotFoundError:
        return None
    try:
        raw = json.loads(data.decode("utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("it is not a JSON object")
        state = raw.get("state")
        if state not in STATES:
            raise ValueError(f"unknown state {state!r}")
        return RunRecord(
            state=str(state),
            machine_id=_one_line(raw.get("machine_id")) or "an unknown machine",
            started_at=_time(raw.get("started_at"), "started_at"),
            finished_at=_optional_time(raw, "finished_at"),
            message=_one_line(raw.get("message")),
            deadline_at=_optional_time(raw, "deadline_at"),
            last_succeeded_at=_optional_time(raw, "last_succeeded_at"),
            steps=_entries(raw.get("steps"), _step),
            findings=_entries(raw.get("findings"), _finding),
            parts=_names(raw.get("parts")),
        )
    except ValueError as error:
        raise RunRecordError(f"the run record {RUN_RECORD} cannot be read: {error}") from error


def write_run_record(store: Store, record: RunRecord) -> None:
    store.replace(RUN_RECORD, (json.dumps(_raw(record), indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def _raw(record: RunRecord) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "state": record.state,
        "machine_id": record.machine_id,
        "started_at": _iso(record.started_at),
    }
    for key, moment in (
        ("finished_at", record.finished_at),
        ("deadline_at", record.deadline_at),
        ("last_succeeded_at", record.last_succeeded_at),
    ):
        if moment is not None:
            raw[key] = _iso(moment)
    if record.message:
        raw["message"] = record.message
    raw["steps"] = [
        {"name": step.name, "result": step.result, **({"detail": step.detail} if step.detail else {})}
        for step in record.steps
    ]
    raw["findings"] = [{"step": item.step, "kind": item.kind, "text": item.text} for item in record.findings]
    raw["parts"] = list(record.parts)
    return raw


def _iso(moment: datetime.datetime) -> str:
    """Whole seconds, the form ``parse_time`` reads back."""
    return moment.isoformat(timespec="seconds")


def _entries(value: object, parse: Callable[[Mapping[str, Any]], _Entry]) -> tuple[_Entry, ...]:
    if not isinstance(value, list):
        return ()
    entries = []
    for item in value:
        if not isinstance(item, dict):
            continue
        try:
            entries.append(parse(item))
        except (KeyError, TypeError, ValueError):
            continue
    return tuple(entries)


def _text(item: Mapping[str, Any], key: str) -> str:
    value = item[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} is not a text")
    return value


def _step(item: Mapping[str, Any]) -> StepResult:
    detail = item.get("detail")
    return StepResult(_text(item, "name"), _text(item, "result"), detail if isinstance(detail, str) else "")


def _finding(item: Mapping[str, Any]) -> Finding:
    return Finding(_text(item, "step"), _text(item, "kind"), _text(item, "text"))


def _names(value: object) -> tuple[str, ...]:
    """The names in a list; anything else in it, or a value that is no list, is left out."""
    if not isinstance(value, list):
        return ()
    return tuple(_one_line(item) for item in value if isinstance(item, str) and item.strip())


def _one_line(value: object) -> str:
    """Whitespace and line breaks collapsed to single spaces, cut to ``MAX_TEXT_CHARACTERS``."""
    text = " ".join(str(value).split()) if value else ""
    return text if len(text) <= MAX_TEXT_CHARACTERS else text[: MAX_TEXT_CHARACTERS - 3].rstrip() + "..."


def _optional_time(raw: Mapping[str, Any], key: str) -> datetime.datetime | None:
    return _time(raw[key], key) if raw.get(key) else None


def _time(value: object, key: str) -> datetime.datetime:
    if not isinstance(value, str):
        raise ValueError(f"{key} is missing")
    try:
        moment = parse_time(value)
    except ValueError as error:
        raise ValueError(f"{key} {value!r} is not a time like 2026-11-07T03:00:00+01:00") from error
    if moment.utcoffset() is None:
        raise ValueError(f"{key} {value!r} has no offset")
    return moment
