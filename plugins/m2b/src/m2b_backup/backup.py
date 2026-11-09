"""One backup: the settings, the target's checks, the mirror, the attic's pruning, the task dump.

It runs as the add-on's ``after_journal`` step, or alone through ``m2b-backup run``. The target
folder must exist: a disk that is not connected must not turn into a folder of that name on the
startup disk. It may not lie inside the store, nor the store inside it, or each backup would copy
the one before. What the owner should know (files not downloaded, a dump kept) goes to the curation
run as a finding when the step runs in one, and is printed either way.
"""

from __future__ import annotations

import datetime
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from m2b_backup import snapshot
from m2b_backup.core import TasksUnreachableError

DEFAULT_ATTIC_DAYS = 30
EVICTED_EXAMPLES = 3
INFO = "info"
ACTION = "action"


class BackupError(Exception):
    """The backup cannot run as set up; nothing was changed in the target."""


class NotSetUpError(Exception):
    """No ``addons.backup`` in this machine's config."""


class Core(Protocol):
    def store(self) -> Path: ...

    def settings(self) -> Any: ...

    def tasks(self) -> str: ...

    def report(self, kind: str, text: str) -> bool: ...


@dataclass(frozen=True)
class Settings:
    target: Path
    attic_days: int


@dataclass
class Outcome:
    result: snapshot.Result
    dump: str
    findings: list[tuple[str, str]] = field(default_factory=list)

    def lines(self) -> list[str]:
        r = self.result
        summary = f"backup: {r.copied} copied, {r.unchanged} unchanged, {r.to_attic} into the attic"
        if r.pruned:
            summary += f", attic days removed: {', '.join(r.pruned)}"
        return [summary, f"tasks: {self.dump}", *[f"{kind}: {text}" for kind, text in self.findings]]


def settings_of(raw: Any, home: Path) -> Settings:
    if raw is None:
        raise NotSetUpError("the backup is not set up on this machine; /m2b:backup-setup sets it up")
    if isinstance(raw, Mapping) and raw.get("on") is not True:
        raise NotSetUpError("the backup add-on is off on this machine; /m2b:backup-setup turns it on")
    if not isinstance(raw, Mapping) or not isinstance(raw.get("target"), str):
        raise BackupError("addons.backup in config.json needs a target folder; /m2b:backup-setup sets it")
    target = _expand(raw["target"], home)
    days = raw.get("attic_days", DEFAULT_ATTIC_DAYS)
    if not isinstance(days, int) or isinstance(days, bool) or days < 1:
        raise BackupError(f"addons.backup.attic_days must be a whole number of days, at least 1, not {days!r}")
    return Settings(target, days)


def run(core: Core, home: Path, today: datetime.date) -> Outcome:
    settings = settings_of(core.settings(), home)
    store = core.store()
    _check_store(store)
    _check_target(store, settings.target)
    try:
        result = snapshot.mirror(store, settings.target, today)
    except snapshot.UnlistableStoreError as error:
        raise BackupError(f"{error}; nothing was changed in the backup") from error
    result.pruned = snapshot.prune(settings.target, today, settings.attic_days)
    outcome = Outcome(result, "")
    outcome.dump = _dump(core, settings.target, outcome)
    if result.evicted:
        examples = ", ".join(result.evicted[:EVICTED_EXAMPLES]) + (
            ", ..." if len(result.evicted) > EVICTED_EXAMPLES else ""
        )
        outcome.findings.append(
            (
                INFO,
                f"{len(result.evicted)} files not downloaded were not backed up, the mirror keeps its previous "
                f"copies ({examples})",
            )
        )
    if result.unread:
        examples = ", ".join(result.unread[:EVICTED_EXAMPLES]) + (
            ", ..." if len(result.unread) > EVICTED_EXAMPLES else ""
        )
        outcome.findings.append(
            (
                INFO,
                f"{len(result.unread)} folders could not be read (not downloaded, or not listable), the mirror keeps "
                f"its copies of what they held ({examples})",
            )
        )
    for kind, text in outcome.findings:
        core.report(kind, text)
    return outcome


def _dump(core: Core, target: Path, outcome: Outcome) -> str:
    """Writes the dump unless the list could not be reached or came back empty over a dump with tasks."""
    path = target / snapshot.TASK_DUMP
    try:
        listed = core.tasks()
    except TasksUnreachableError as error:
        outcome.findings.append((ACTION, f"the task list could not be reached ({error}); the previous dump stays"))
        return "previous dump kept"
    count = len(json.loads(listed))
    if count == 0 and _holds_tasks(path):
        outcome.findings.append((ACTION, "the task list answered with no tasks at all; the previous dump stays"))
        return "previous dump kept"
    snapshot.write_dump(target, listed.encode("utf-8"))
    return f"{count} written"


def _holds_tasks(path: Path) -> bool:
    try:
        return bool(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return False


def _check_store(store: Path) -> None:
    """A store folder that is missing would read as a store whose files were all deleted."""
    if not (store / "store.json").exists():
        raise BackupError(f"the store {store} is not reachable; nothing was backed up")


def _check_target(store: Path, target: Path) -> None:
    if not target.is_dir():
        raise BackupError(f"the backup target {target} does not exist; connect its disk or run /m2b:backup-setup")
    store_real, target_real = store.resolve(), target.resolve()
    if store_real == target_real or store_real in target_real.parents or target_real in store_real.parents:
        raise BackupError(f"the backup target {target} and the store {store} must not lie inside each other")


def _expand(path: str, home: Path) -> Path:
    if path == "~" or path.startswith("~/"):
        return home / path[2:]
    if not path.startswith("/"):
        raise BackupError(f"the backup target must be absolute or start with ~/, not {path!r}")
    return Path(path)
