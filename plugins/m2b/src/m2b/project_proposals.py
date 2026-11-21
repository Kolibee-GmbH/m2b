"""A repository the person keeps working in, proposed as a project when no topic names it.

A reading of the sessions (``curate.glean_step``) sees in which folder each session worked, and the
session start noted the git remotes of that folder (``session_remotes``). A repository the person
typed a prompt in on two days, and that no topic's ``Repository:`` line names and no project
capture in the inbox waits for, is proposed as a project. Kept, it becomes the capture the owner's
own "keep this project" makes (``project_capture``), and the filing makes it a topic.

A reading covers a day most of the time, so the days a repository was worked in are remembered in
machine state from one reading to the next, for ``REMEMBERED_FOR``: the transcripts lie on this
machine only, and so does what was seen in them. Only the days are kept, under the repository's
addresses; no folder, no prompt. A session in a folder the reading leaves out never reaches this
module, so its repository is neither remembered nor proposed.

The proposal stands on no words of the person: its quote is the repository's addresses, its source
``glean.WORKED``. Its id comes from the addresses alone, so the same repository is one proposal
from reading to reading, and a dropped one stays dropped as long as a settled proposal is
remembered.
"""

from __future__ import annotations

import contextlib
import datetime
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from m2b import glean, project_capture, proposals, session_remotes
from m2b.atomic_file import write_text_atomically
from m2b.sessions import Session
from m2b.store.base import Store

DAYS_FILE = "project-days.json"
REMEMBERED_FOR = session_remotes.KEEP_FOR
DAYS_NEEDED = 2

# The addresses of one repository, sorted, as the key the days are kept under.
Addresses = tuple[str, ...]


def days_worked(
    read: Sequence[Session], addresses_of: Mapping[str, Addresses], zone: datetime.tzinfo
) -> dict[Addresses, set[datetime.date]]:
    """The days the person typed a prompt in each repository, from the sessions read; ``addresses_of``
    gives a session's folder its repository's addresses, and a folder without any counts for none."""
    days: dict[Addresses, set[datetime.date]] = {}
    for session in read:
        addresses = addresses_of.get(session.folder, ())
        if not addresses:
            continue
        days.setdefault(addresses, set()).update(prompt.time.astimezone(zone).date() for prompt in session.prompts)
    return days


def remembered(state_dir: Path, today: datetime.date) -> dict[Addresses, set[datetime.date]]:
    """The days remembered from earlier readings, those older than ``REMEMBERED_FOR`` left out; a file
    that cannot be read remembers nothing, so a repository then needs its two days anew."""
    try:
        raw = json.loads((state_dir / DAYS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    given = raw.get("days") if isinstance(raw, dict) else None
    days: dict[Addresses, set[datetime.date]] = {}
    for key, values in (given if isinstance(given, dict) else {}).items():
        if not isinstance(key, str) or not isinstance(values, list):
            continue
        kept = {day for day in map(_day, values) if day is not None and today - day < REMEMBERED_FOR}
        if key.split() and kept:
            days[tuple(key.split())] = kept
    return days


def remember(state_dir: Path, days: Mapping[Addresses, Iterable[datetime.date]], temp_dir: Path) -> None:
    """Writes the days as they are to be remembered; a write that fails is lost, not an error of the
    reading, which then only proposes a repository later."""
    written = {
        " ".join(addresses): sorted(day.isoformat() for day in seen) for addresses, seen in sorted(days.items()) if seen
    }
    with contextlib.suppress(OSError):
        state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        write_text_atomically(state_dir / DAYS_FILE, json.dumps({"days": written}) + "\n", temp_dir)


def joined(
    earlier: Mapping[Addresses, set[datetime.date]], now: Mapping[Addresses, set[datetime.date]]
) -> dict[Addresses, set[datetime.date]]:
    """The days of both, per repository."""
    days = {addresses: set(seen) for addresses, seen in earlier.items()}
    for addresses, seen in now.items():
        days.setdefault(addresses, set()).update(seen)
    return days


def proposed(store: Store, days: Mapping[Addresses, set[datetime.date]]) -> list[proposals.Said]:
    """A project for each repository worked in on ``DAYS_NEEDED`` days that no topic names and no
    capture in the inbox waits for, with the last of its days."""
    found = []
    for addresses, seen in sorted(days.items()):
        if len(seen) < DAYS_NEEDED:
            continue
        if project_capture.known_as(store, addresses) is not None:
            continue
        if project_capture.waiting_capture(store, addresses) is not None:
            continue
        found.append(proposals.Said(proposal(addresses, seen), max(seen)))
    return found


def proposal(addresses: Addresses, days: Iterable[datetime.date]) -> glean.Proposal:
    seen = sorted(days)
    # The address keeps two repositories of one name apart: ``proposals.add`` also refuses a
    # proposal whose text one it knows has.
    text = (
        f"{session_remotes.name_of(addresses)} ({addresses[0]}) is a repository you worked in on "
        f"{seen[0].isoformat()} and {seen[-1].isoformat()}, with no topic: keep it as a project"
    )
    return glean.Proposal(glean.PROJECT, text, " ".join(addresses), "", source=glean.WORKED)


def addresses_in(entry: proposals.Entry) -> Addresses:
    """The addresses a project's proposal names, as its quote holds them."""
    return tuple(entry.quote.split())


def _day(value: object) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None
