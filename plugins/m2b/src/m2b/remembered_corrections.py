"""Corrections of how Claude works made in one session only, remembered for the readings after it.

A lesson stands on the same correction made in two different sessions (``glean``). A reading covers
the time since the last one, a few hours where runs come often, so a correction and its repeat in
another reading would never meet. A reading therefore also returns the corrections that stand in
one session and hold beyond the task at hand (``glean.SingleCorrection``), and code keeps them here
for ``REMEMBERED_FOR``.

They are kept in machine state, beside the days a repository was worked in
(``project_proposals``), and never in the synced store: the transcripts lie on this machine only,
and so does what was read in them. An entry holds what a later reading needs to make a lesson of
it: the person's typed words as code checked them, the Bash commands of the turn they answer (as
``sessions`` redacted and bounded them), the addresses of the repository the session start noted
for the session's folder, the matter in the model's words, and the lesson's kind and target as the
model gave them. Its id comes from the session and the prompt the quote stands in, so a period read
again adds no entry twice, whatever words of that prompt the model quotes then. At most ``MOST``
entries are kept; the oldest go first.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from m2b import lessons
from m2b.atomic_file import write_text_atomically

FILE = "remembered-corrections.json"
REMEMBERED_FOR = datetime.timedelta(days=30)
MOST = 300
_ID_LENGTH = 16


@dataclass(frozen=True)
class Correction:
    id: str
    session: str
    day: datetime.date
    quote: str
    commands: tuple[str, ...]
    addresses: tuple[str, ...]
    matter: str
    kind: str
    target: str


@dataclass(frozen=True)
class Found:
    """The corrections remembered, and why the file could not be read where it could not."""

    corrections: tuple[Correction, ...]
    failure: str | None = None


def correction_id(session: str, typed_at: datetime.datetime) -> str:
    """The same for the same prompt of the same session: a period read again may be answered with
    other words of that prompt, and must not remember its correction twice. One prompt is taken to
    hold one correction."""
    said = f"{session}\n{typed_at.astimezone(datetime.timezone.utc).isoformat()}"
    return hashlib.sha256(said.encode("utf-8", errors="replace")).hexdigest()[:_ID_LENGTH]


def remembered(state_dir: Path, today: datetime.date) -> Found:
    """The corrections remembered from earlier readings, those older than ``REMEMBERED_FOR`` left out.

    A file that is not there remembers nothing yet. One that cannot be read remembers nothing either
    and says why: the reading goes on, and its corrections are remembered anew.
    """
    path = state_dir / FILE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Found(())
    except (OSError, ValueError) as error:
        return Found((), f"{path.name} could not be read ({error})")
    given = raw.get("corrections") if isinstance(raw, dict) else None
    if not isinstance(given, list):
        return Found((), f"{path.name} holds no list of corrections")
    found = (_correction(entry) for entry in given)
    return Found(tuple(each for each in found if each is not None and today - each.day < REMEMBERED_FOR))


def joined(earlier: Iterable[Correction], new: Iterable[Correction]) -> list[Correction]:
    """Both, each id once: a correction remembered already stays as it was."""
    by_id: dict[str, Correction] = {}
    for correction in (*earlier, *new):
        by_id.setdefault(correction.id, correction)
    return list(by_id.values())


def remember(state_dir: Path, corrections: Sequence[Correction], today: datetime.date, temp_dir: Path) -> str | None:
    """Writes the corrections within ``REMEMBERED_FOR`` of today, the newest ``MOST``; returns why the
    write failed, else None. A failed write costs the reading nothing but these corrections."""
    recent = [each for each in corrections if today - each.day < REMEMBERED_FOR]
    # A stable sort keeps the order of one day as it was given.
    kept = sorted(recent, key=lambda each: each.day, reverse=True)[:MOST]
    written = {"corrections": [_as_written(each) for each in sorted(kept, key=lambda each: each.day)]}
    try:
        state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        write_text_atomically(state_dir / FILE, json.dumps(written, ensure_ascii=False) + "\n", temp_dir)
    except OSError as error:
        return str(error)
    return None


def _as_written(correction: Correction) -> dict[str, Any]:
    return {
        "id": correction.id,
        "session": correction.session,
        "day": correction.day.isoformat(),
        "quote": correction.quote,
        "commands": list(correction.commands),
        "addresses": list(correction.addresses),
        "matter": correction.matter,
        "kind": correction.kind,
        "target": correction.target,
    }


def _correction(entry: object) -> Correction | None:
    """One entry as written, or None where it is not in that form."""
    if not isinstance(entry, dict):
        return None
    texts = [entry.get(key) for key in ("id", "session", "day", "quote", "matter", "kind", "target")]
    if not all(isinstance(text, str) and text for text in texts):
        return None
    identifier, session, day, quote, matter, kind, target = (str(text) for text in texts)
    commands, addresses = _texts(entry.get("commands")), _texts(entry.get("addresses"))
    if commands is None or addresses is None or kind not in lessons.KINDS:
        return None
    try:
        when = datetime.date.fromisoformat(day)
    except ValueError:
        return None
    return Correction(identifier, session, when, quote, commands, addresses, matter, kind, target)


def _texts(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not all(isinstance(each, str) for each in value):
        return None
    return tuple(value)
