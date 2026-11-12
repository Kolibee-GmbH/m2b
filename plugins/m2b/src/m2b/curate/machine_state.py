"""What the runner keeps on this machine, under ``~/.local/state/m2b/``, never in
the store, because the store syncs to other machines.

- **The lock** ``curate.lock``: ``fcntl.flock`` on an open file. It belongs to the open file,
  not to the process, so a child that was handed the descriptor keeps the run locked after the
  runner itself was killed; the lock dies with the last process of the run. The descriptor is
  not inheritable by default: it reaches only the children the runner passes it to.
- **The run log** ``run.log``: one JSON line per run outcome, rotated to ``run.log.1`` at 1 MB.
  It is the only trace of a refusal on a machine that does not curate, and of a run whose run
  record could not be written (``unrecorded``), which the session-start hook shows from here.
- **The last attempt** ``last-attempt.json``: a run that was not due, or was asked for on a
  paused machine without being forced, overwritten each time. It is an attempt, not an outcome,
  so it stays out of the run log; ``m2b status`` shows it, so a scheduled run that started
  nothing still shows it reached m2b.
- **The background run's errors** ``detached-run.err``: what the last run started in the
  background wrote on standard error, replaced at each such start. A run that dies before it can
  write a run record or a line of the run log leaves its reason nowhere else.
- **The backoff** ``backoff.json``: after a failed run the next attempt waits 1, then 4, then 20
  hours, so a failure that does not clear by itself does not start a model run at every session
  start; a successful run removes it.
- **The copies of memory** ``memory-before-run/<start>/``: ``memory/`` as it was before a run's
  first model step, so the owner can take back a line the run removed or rewrote. A copy stays
  while a finding about a changed facts line names it, while it is marked unchecked, and the
  run's own copy until the next run.
- **The unchecked copies** ``memory-unchecked.json``: the copies whose run has not stored its
  changed facts lines yet. A run stopped hard leaves its copy here, and the next run past
  preflight compares it with ``memory/`` and reports what that run left.
- **The changed facts lines** ``memory-changes.json``: what ingest and lint removed or rewrote,
  repeated in every review until the owner completes the review task, because the review task
  holds only the findings of the last run and these are never found again.
- **The stuck inbox files** ``inbox-stuck.json``: files ingest could not file after the last run,
  with their modification time. Until one changes it makes no run due, so one export the codec
  cannot read does not start a model run at every session start.
- **The evicted inbox entries** ``inbox-evicted.json``: captures the last run found not
  downloaded, with their modification time. Until one changes it makes no run due, so a capture
  iCloud keeps in the cloud does not start a run at every session start.
- **Leftovers:** temp files older than an hour, and findings files of runs that were killed.
  Anything younger may belong to a command running right now in another session.
"""

from __future__ import annotations

import contextlib
import datetime
import errno
import fcntl
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from m2b.atomic_file import replace_atomically
from m2b.curate.report import Finding, runs_dir
from m2b.paths import MachinePaths

LOCK_FILE = "curate.lock"
RUN_LOG = "run.log"
BACKOFF_FILE = "backoff.json"
ATTEMPT_FILE = "last-attempt.json"
DETACHED_ERRORS = "detached-run.err"
MEMORY_BEFORE_RUN = "memory-before-run"
MEMORY_CHANGES = "memory-changes.json"
MEMORY_UNCHECKED = "memory-unchecked.json"
STUCK_INBOX = "inbox-stuck.json"
EVICTED_INBOX = "inbox-evicted.json"
MAX_LOG_BYTES = 1024 * 1024
LAST_EVENT_BYTES = 16 * 1024
BACKOFF_HOURS = (1, 4, 20)
TEMP_MAX_AGE = datetime.timedelta(hours=1)
FINDINGS_MAX_AGE = datetime.timedelta(days=1)

REFUSED = "refused"
UNRECORDED = "unrecorded"
SUCCEEDED = "succeeded"
FAILED = "failed"
NOT_DUE = "not_due"
PAUSED = "paused"


def lock_file(machine: MachinePaths) -> Path:
    return machine.state_dir / LOCK_FILE


def run_log(machine: MachinePaths) -> Path:
    return machine.state_dir / RUN_LOG


def backoff_file(machine: MachinePaths) -> Path:
    return machine.state_dir / BACKOFF_FILE


def attempt_file(machine: MachinePaths) -> Path:
    return machine.state_dir / ATTEMPT_FILE


def detached_errors(machine: MachinePaths) -> Path:
    return machine.state_dir / DETACHED_ERRORS


def memory_copies(machine: MachinePaths) -> Path:
    return machine.state_dir / MEMORY_BEFORE_RUN


def memory_copy(machine: MachinePaths, started: datetime.datetime) -> Path:
    """The copy of ``memory/`` for the run that started then, named by that time in UTC."""
    return memory_copies(machine) / f"{started.astimezone(datetime.timezone.utc):%Y%m%dT%H%M%SZ}"


def mark_unchecked(machine: MachinePaths, copy: Path) -> None:
    """Names a copy of ``memory/`` whose run has not stored its changed facts lines yet.

    A run that ends without storing them, stopped hard or past its check, leaves the name here for
    the next run, which compares that copy with ``memory/``.
    """
    names = [path.name for path in unchecked_copies(machine)]
    if copy.name not in names:
        names.append(copy.name)
    _write_names(machine, names)


def unchecked_copies(machine: MachinePaths) -> list[Path]:
    """The copies named by ``mark_unchecked`` that are still there, oldest first."""
    try:
        raw = json.loads((machine.state_dir / MEMORY_UNCHECKED).read_text(encoding="utf-8"))
        names = [str(name) for name in raw]
    except (OSError, ValueError, TypeError):
        return []
    copies = [memory_copies(machine) / name for name in sorted(set(names)) if name and "/" not in name]
    return [copy for copy in copies if copy.is_dir()]


def clear_unchecked(machine: MachinePaths) -> None:
    (machine.state_dir / MEMORY_UNCHECKED).unlink(missing_ok=True)


def _write_names(machine: MachinePaths, names: list[str]) -> None:
    path = machine.state_dir / MEMORY_UNCHECKED
    path.parent.mkdir(parents=True, exist_ok=True)
    replace_atomically(path, (json.dumps(names) + "\n").encode("utf-8"), machine.temp_dir)


def load_memory_changes(machine: MachinePaths) -> list[Finding]:
    """The changed facts lines still waiting for the owner; nothing when the file cannot be read."""
    try:
        raw = json.loads((machine.state_dir / MEMORY_CHANGES).read_text(encoding="utf-8"))
        return [
            Finding(
                str(item["step"]),
                str(item["kind"]),
                str(item["text"]),
                item.get("change") if isinstance(item.get("change"), dict) else None,
            )
            for item in raw
        ]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def save_memory_changes(machine: MachinePaths, findings: list[Finding]) -> None:
    path = machine.state_dir / MEMORY_CHANGES
    if not findings:
        path.unlink(missing_ok=True)
        return
    data = [
        {"step": finding.step, "kind": finding.kind, "text": finding.text}
        | ({"change": dict(finding.change)} if finding.change is not None else {})
        for finding in findings
    ]
    replace_atomically(path, (json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8"), machine.temp_dir)


def load_stuck_inbox(machine: MachinePaths) -> dict[str, int]:
    """Inbox files ingest could not file, by store path, with their modification time in nanoseconds."""
    return _load_times(machine, STUCK_INBOX)


def save_stuck_inbox(machine: MachinePaths, stuck: dict[str, int]) -> None:
    _save_times(machine, STUCK_INBOX, stuck)


def load_evicted_inbox(machine: MachinePaths) -> dict[str, int]:
    """Inbox entries the last run found not downloaded, by store path, with their modification time.

    Kept apart from the stuck files: a capture that downloads later keeps its modification time,
    and as a stuck file it would never be filed.
    """
    return _load_times(machine, EVICTED_INBOX)


def save_evicted_inbox(machine: MachinePaths, evicted: dict[str, int]) -> None:
    _save_times(machine, EVICTED_INBOX, evicted)


def _load_times(machine: MachinePaths, name: str) -> dict[str, int]:
    try:
        raw = json.loads((machine.state_dir / name).read_text(encoding="utf-8"))
        return {str(path): int(mtime) for path, mtime in raw.items()}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def _save_times(machine: MachinePaths, name: str, times: dict[str, int]) -> None:
    path = machine.state_dir / name
    if not times:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    replace_atomically(path, (json.dumps(times, ensure_ascii=False) + "\n").encode("utf-8"), machine.temp_dir)


def prune_memory_copies(machine: MachinePaths, keep: set[Path]) -> None:
    """Removes every copy of ``memory/`` but those in ``keep``."""
    try:
        copies = list(memory_copies(machine).iterdir())
    except FileNotFoundError:
        return
    for copy in copies:
        if copy not in keep and copy.is_dir() and not copy.name.startswith("."):
            shutil.rmtree(copy, ignore_errors=True)


class RunLock:
    """The machine's curation lock; ``acquire`` never waits."""

    def __init__(self, machine: MachinePaths) -> None:
        self._path = lock_file(machine)
        self._descriptor: int | None = None

    def acquire(self) -> bool:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            os.close(descriptor)
            if error.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                return False
            raise
        self._descriptor = descriptor
        return True

    @property
    def descriptor(self) -> int:
        if self._descriptor is None:
            raise RuntimeError("the lock is not held")
        return self._descriptor

    @property
    def pass_fds(self) -> tuple[int, ...]:
        """For ``subprocess``: hands the lock to a child, so the run stays locked while it lives."""
        return (self.descriptor,)

    def release(self) -> None:
        """Closes this process's descriptor; children that hold it keep the run locked."""
        if self._descriptor is not None:
            os.close(self._descriptor)
            self._descriptor = None


def lock_is_held(machine: MachinePaths) -> bool:
    """Whether a run holds the lock right now; the answer can be stale a moment later."""
    probe = RunLock(machine)
    if probe.acquire():
        probe.release()
        return False
    return True


@dataclass(frozen=True)
class LogEvent:
    time: datetime.datetime | None
    kind: str
    message: str


def log_event(machine: MachinePaths, kind: str, message: str, now: datetime.datetime) -> None:
    path = run_log(machine)
    path.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(FileNotFoundError):
        if path.stat().st_size >= MAX_LOG_BYTES:
            os.replace(path, path.with_name(f"{RUN_LOG}.1"))
    line = json.dumps({"time": now.isoformat(), "kind": kind, "message": message}, ensure_ascii=False) + "\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(descriptor, line.encode("utf-8"))
    finally:
        os.close(descriptor)


def last_event(machine: MachinePaths) -> LogEvent | None:
    """The newest line of the run log; None when there is none or it cannot be read."""
    try:
        with run_log(machine).open("rb") as log:
            log.seek(0, os.SEEK_END)
            log.seek(max(log.tell() - LAST_EVENT_BYTES, 0))
            lines = [line for line in log.read().split(b"\n") if line.strip()]
    except FileNotFoundError:
        return None
    if not lines:
        return None
    try:
        raw = json.loads(lines[-1].decode("utf-8"))
        moment = datetime.datetime.fromisoformat(raw["time"]) if raw.get("time") else None
        if moment is not None and moment.utcoffset() is None:
            # A time without offset cannot be compared with the run record's; it counts as unknown.
            moment = None
        return LogEvent(moment, str(raw["kind"]), str(raw.get("message") or ""))
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


@dataclass(frozen=True)
class Backoff:
    failures: int
    last_failed_at: datetime.datetime

    @property
    def retry_at(self) -> datetime.datetime:
        hours = BACKOFF_HOURS[min(self.failures, len(BACKOFF_HOURS)) - 1]
        return self.last_failed_at + datetime.timedelta(hours=hours)


def load_backoff(machine: MachinePaths) -> Backoff | None:
    """None after a success; a file that cannot be read counts as one failure when it was written."""
    path = backoff_file(machine)
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    try:
        raw = json.loads(data.decode("utf-8"))
        failures = int(raw["failures"])
        moment = datetime.datetime.fromisoformat(raw["last_failed_at"])
        if failures < 1 or moment.utcoffset() is None:
            raise ValueError("out of range")
        return Backoff(failures, moment)
    except (ValueError, KeyError, TypeError, AttributeError):
        written = datetime.datetime.fromtimestamp(path.stat().st_mtime, datetime.timezone.utc)
        return Backoff(1, written)


def record_attempt(machine: MachinePaths, kind: str, message: str, now: datetime.datetime) -> None:
    """Overwrites the last attempt; a run that is not due, or not forced on a paused machine, writes
    it instead of a run log line."""
    data = json.dumps({"time": now.isoformat(), "kind": kind, "message": message}, ensure_ascii=False) + "\n"
    replace_atomically(attempt_file(machine), data.encode("utf-8"), machine.temp_dir)


def last_attempt(machine: MachinePaths) -> LogEvent | None:
    """The last attempt; None when there is none, it cannot be read, or its time has no offset."""
    try:
        raw = json.loads(attempt_file(machine).read_text(encoding="utf-8"))
        moment = datetime.datetime.fromisoformat(raw["time"])
        if moment.utcoffset() is None:
            return None
        return LogEvent(moment, str(raw["kind"]), str(raw.get("message") or ""))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def record_failure(machine: MachinePaths, now: datetime.datetime) -> Backoff:
    previous = load_backoff(machine)
    backoff = Backoff((previous.failures if previous else 0) + 1, now)
    data = json.dumps({"failures": backoff.failures, "last_failed_at": now.isoformat()}) + "\n"
    replace_atomically(backoff_file(machine), data.encode("utf-8"), machine.temp_dir)
    return backoff


def reset_backoff(machine: MachinePaths) -> None:
    backoff_file(machine).unlink(missing_ok=True)


def clear_leftovers(machine: MachinePaths, now: datetime.datetime) -> list[Path]:
    """Removes temp entries older than an hour and findings files older than a day."""
    removed = []
    for folder, max_age in ((machine.temp_dir, TEMP_MAX_AGE), (runs_dir(machine), FINDINGS_MAX_AGE)):
        cutoff = (now - max_age).timestamp()
        try:
            entries = list(folder.iterdir())
        except FileNotFoundError:
            continue
        for entry in entries:
            try:
                if entry.lstat().st_mtime >= cutoff:
                    continue
                if entry.is_dir() and not entry.is_symlink():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
            except FileNotFoundError:
                continue
            removed.append(entry)
    return removed
