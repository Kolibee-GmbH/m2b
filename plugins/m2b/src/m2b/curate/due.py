"""Whether a curation run is due on this machine (B12).

In this order: a run holding the lock is in progress; after a failed run the backoff decides,
even over a full inbox, so a failure that does not clear by itself costs one attempt and not one
per session; a visible file in the inbox (evicted ones count, hidden ones do not) makes it due,
unless the last run could not file it and it has not changed since; so does a last success older
than 20 hours, or none. A run record that cannot be read leaves the
answer to the run, whose preflight downloads or rewrites it. Whether this machine curates at all
is the caller's question.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from m2b.curate.machine_state import load_backoff, load_stuck_inbox, lock_is_held
from m2b.notes.layout import INBOX
from m2b.paths import MachinePaths
from m2b.run_record import RunRecordError, load_run_record
from m2b.store.base import Store, StoreError

DUE_AFTER = datetime.timedelta(hours=20)


@dataclass(frozen=True)
class Due:
    due: bool
    reason: str


def check_due(store: Store, machine: MachinePaths, now: datetime.datetime) -> Due:
    if lock_is_held(machine):
        return Due(False, "a curation run is in progress on this machine")
    backoff = load_backoff(machine)
    if backoff is not None and now < backoff.retry_at:
        return Due(False, f"the last run failed; the next attempt waits until {_when(backoff.retry_at)}")
    try:
        inbox = store.scan(INBOX)
    except StoreError as error:
        return Due(True, f"the inbox could not be listed: {error}")
    stuck = load_stuck_inbox(machine)
    waiting = len([path for path in inbox.files if not _unchanged(store, path, stuck)]) + len(inbox.evicted)
    if waiting:
        return Due(True, f"{waiting} capture{'' if waiting == 1 else 's'} in the inbox")
    try:
        record = load_run_record(store)
    except (RunRecordError, StoreError) as error:
        return Due(True, str(error))
    last_success = record.last_success if record else None
    if last_success is None:
        return Due(True, "no curation run has succeeded yet")
    if now - last_success > DUE_AFTER:
        return Due(True, f"the last successful run was at {_when(last_success)}")
    next_due = _when(last_success + DUE_AFTER)
    return Due(False, f"the last successful run was at {_when(last_success)}; the next is due after {next_due}")


def _unchanged(store: Store, path: str, stuck: dict[str, int]) -> bool:
    """A file the last run could not file, with the same modification time as then."""
    if path not in stuck:
        return False
    try:
        return store.path(path).stat().st_mtime_ns == stuck[path]
    except OSError:
        return False


def _when(moment: datetime.datetime) -> str:
    return f"{moment.astimezone():%Y-%m-%d %H:%M}"
