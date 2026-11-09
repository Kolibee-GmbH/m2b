"""The captures still in the store's inbox, created in the period: context for the verdict.

Worklog notes (``source: worklog``) and harvested candidates (``source: candidate``) are the
curator's own output, so they are never a source of the next worklog. A file that is not downloaded
(evicted by iCloud Drive) is not opened, which could hang; the source counts it in its detail.
"""

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass
from pathlib import Path

from m2b_worklog.sources import READ, SourceState

INBOX = "inbox"
NOT_SOURCES = frozenset({"worklog", "candidate"})
# macOS marks a file whose contents live only in the cloud (sys/stat.h SF_DATALESS).
SF_DATALESS = 0x40000000


@dataclass(frozen=True)
class Capture:
    name: str
    created: datetime.datetime
    source: str


@dataclass(frozen=True)
class InboxFacts:
    captures: list[Capture]
    state: SourceState


def read_inbox(store: Path, start: datetime.datetime, end: datetime.datetime) -> InboxFacts:
    folder = store / INBOX
    if not folder.is_dir():
        return InboxFacts([], SourceState.failed(f"the store has no inbox at {folder}"))
    found = []
    evicted = 0
    try:
        for path in sorted(folder.glob("*.md")):
            if is_evicted(path):
                evicted += 1
                continue
            fields = _frontmatter(path.read_text(encoding="utf-8", errors="replace"))
            created = _time(fields.get("created"))
            source = fields.get("source", "")
            if created is None or source in NOT_SOURCES or not start <= created < end:
                continue
            found.append(Capture(path.name, created, source))
    except OSError as error:
        return InboxFacts(found, SourceState.failed(str(error)))
    return InboxFacts(found, SourceState(READ, f"{evicted} not downloaded" if evicted else ""))


def is_evicted(path: Path) -> bool:
    return bool(getattr(os.lstat(path), "st_flags", 0) & SF_DATALESS)


def _frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip().strip('"')
    return fields


def _time(value: str | None) -> datetime.datetime | None:
    try:
        moment = datetime.datetime.fromisoformat(value) if value else None
    except ValueError:
        return None
    return moment if moment is not None and moment.tzinfo is not None else None
