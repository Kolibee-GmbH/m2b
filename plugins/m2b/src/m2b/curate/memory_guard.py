"""What a model step did to ``memory/``, compared in code after the step.

Ingest, refresh and lint run a model that may edit ``memory/``, and it reads text the code does not
control: captures, the worklog note, archived evidence. A capture that says "clear the facts" or a
misread rule could rewrite or drop any line of the distillate, and the fence cannot tell such an edit
from a wanted one. So the runner takes a snapshot of ``memory/`` before each of these steps and
compares afterwards:

- **Every step, sorting included:** a line the step wrote or changed that holds a character which hides or reorders
  text (``m2b.notes.characters``) puts ``memory/`` back as it was before the step, and the step
  fails. Such a line reads differently to the owner than to the model.
- **Refresh:** its allowed change is exact, so it is enforced. Only the due fact files and the
  distillate's lines for them may change (in the backfill also the current items it was given, and
  only by their ``(since ...)``); anything else puts ``memory/`` back and fails the step.
- **Ingest and lint:** their edits are many and legitimate, so they are reported, not enforced.
  Every facts line they removed or rewrote and every fact file they emptied or removed goes into the
  review task, with where the copy of ``memory/`` from before the run is kept.

Why a step failed is said without the line's text: by file, line number and, for a hidden
character, its code point. A file the step added is not named either, because the model chose its
name. The reason goes into the run record, and the session start prints it as a notice of m2b's
own, above the line that marks the distillate as data; a quoted line or a chosen name would carry
whatever a capture made the model write into every session, in m2b's voice.

The copy from before the run lives in machine state, never in the store (``machine_state``).
"""

from __future__ import annotations

import difflib
import os
import shutil
import tempfile
from collections import Counter
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from m2b.notes.characters import unsafe_characters
from m2b.notes.layout import MEMORY, MEMORY_INDEX
from m2b.notes.memory_index import (
    CURRENT_HEADING,
    FACTS_HEADING,
    current_line_text,
    is_section_heading,
    parse_fact_line,
)
from m2b.store.base import Store

INDEX_PATH = f"{MEMORY}/{MEMORY_INDEX}"
# Enough of a line to recognise it in a one-line finding.
_SHOWN_CHARACTERS = 120
_GROUP_HEADING = "### "
# Tag characters spell whole words; three of them name the kind, the rest would flood the finding.
_NAMED_CHARACTERS = 3
_ADDED_FILE = "a file the step added to memory/"


@dataclass(frozen=True)
class Snapshot:
    """Every file below ``memory/`` by its store path."""

    files: Mapping[str, bytes]

    @classmethod
    def take(cls, store: Store) -> Snapshot:
        """Raises ``StoreError`` when a file cannot be read; then there is nothing to compare with."""
        return cls({path: store.read_bytes(path) for path in store.list_files(MEMORY, recursive=True)})

    @classmethod
    def load(cls, folder: Path) -> Snapshot:
        """A snapshot ``save`` wrote; raises ``OSError`` when it cannot be read."""
        files = sorted(path for path in folder.rglob("*") if path.is_file())
        return cls(
            {PurePosixPath(MEMORY, *path.relative_to(folder).parts).as_posix(): path.read_bytes() for path in files}
        )

    def restore(self, store: Store) -> None:
        """Puts ``memory/`` back: changed and removed files as they were, new ones removed."""
        for path in store.list_files(MEMORY, recursive=True):
            if path not in self.files:
                store.delete(path)
        for path, data in self.files.items():
            try:
                current: bytes | None = store.read_bytes(path)
            except FileNotFoundError:
                current = None
            if current != data:
                store.replace(path, data)

    def save(self, folder: Path) -> None:
        """Writes the files below ``folder``, readable by the owner alone, in place of what was there."""
        folder.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{folder.name}-", dir=folder.parent))
        try:
            for path, data in self.files.items():
                target = staging.joinpath(*PurePosixPath(path).relative_to(MEMORY).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                try:
                    os.write(descriptor, data)
                finally:
                    os.close(descriptor)
            shutil.rmtree(folder, ignore_errors=True)
            os.replace(staging, folder)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def text(self, path: str) -> str | None:
        data = self.files.get(path)
        return None if data is None else data.decode("utf-8", errors="replace")


def unsafe_line(before: Snapshot, after: Snapshot, added_files_stay: bool = False) -> str | None:
    """Why the step must be undone: the first line it wrote that holds an unsafe character.

    A file the step added is named only where it stays (``added_files_stay``): what an interrupted
    run left is reported in the review, and the owner has to find the file.
    """
    for path in sorted(after.files):
        unchanged = Counter(_lines(before.text(path)))
        for number, line in enumerate(_lines(after.text(path)), start=1):
            if unchanged[line] > 0:
                unchanged[line] -= 1
                continue
            names = unsafe_characters(line)
            if names:
                more = len(names) - _NAMED_CHARACTERS
                listed = ", ".join(names[:_NAMED_CHARACTERS]) + (f" and {more} more" if more > 0 else "")
                where = path if added_files_stay or path in before.files else _ADDED_FILE
                return f"line {number} written to {where} holds {listed}, which hide or reorder text"
    return None


def refresh_problem(before: Snapshot, after: Snapshot, files: Collection[str], current: Collection[str]) -> str | None:
    """Why the refresh step did more than rewrite ``files`` and their lines (and date ``current``)."""
    allowed = set(files)
    for path in sorted(set(before.files) | set(after.files)):
        if path == INDEX_PATH:
            continue
        if path in allowed:
            if path in before.files and path not in after.files:
                return f"the refresh step removed {path}, a due fact file it may only rewrite"
            continue
        if path not in before.files:
            return f"the refresh step wrote {_ADDED_FILE}, where it may only rewrite the due fact files"
        if before.files[path] != after.files.get(path):
            return f"the refresh step {'changed' if path in after.files else 'removed'} {path}, which is not due"
    names = {PurePosixPath(path).name for path in allowed}
    old = _refresh_view(before.text(INDEX_PATH), names, set(current))
    new = _refresh_view(after.text(INDEX_PATH), names, set(current))
    if old == new:
        return None
    # One entry of a view is one line, so a place in the old view is a line of the file as it was
    # before the step, and as it is again once the step is undone.
    for tag, old_start, _, _, _ in difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if tag == "insert":
            did = f"added a line below line {old_start}" if old_start else "added a line above line 1"
        else:
            did = f"{'removed' if tag == 'delete' else 'changed'} line {old_start + 1}"
        return f"the refresh step {did} of {INDEX_PATH}, which belongs to no due fact"
    return None


# The kinds of ``FactChange``, as ``m2b band --json`` names them.
REWROTE = "rewrote"
REMOVED = "removed"
FILE_REMOVED = "file_removed"
FILE_EMPTIED = "file_emptied"
# Not a change: where the copy of ``memory/`` from before the run lies, and the captures it filed.
COPY = "copy"


@dataclass(frozen=True)
class FactChange:
    """One change of the facts that the review shows: the whole lines before and after, or the file."""

    kind: str
    file: str
    before: str | None = None
    after: str | None = None

    def described(self) -> str:
        """The finding's text in the review task, each line cut at ``_SHOWN_CHARACTERS``."""
        if self.kind == REWROTE:
            return f'rewrote the facts line "{_shown(self.before or "")}" as "{_shown(self.after or "")}"'
        if self.kind == REMOVED:
            return f'removed the facts line "{_shown(self.before or "")}"'
        return f"{'removed' if self.kind == FILE_REMOVED else 'emptied'} {self.file}"

    def as_json(self) -> dict[str, object]:
        return {"kind": self.kind, "file": self.file, "before": self.before, "after": self.after}


def fact_changes(before: Snapshot, after: Snapshot) -> list[str]:
    """Each change of ``fact_change_list`` as the review task words it."""
    return [change.described() for change in fact_change_list(before, after)]


def fact_change_list(before: Snapshot, after: Snapshot) -> list[FactChange]:
    """Each facts line the step removed or rewrote, and each fact file it emptied or removed.

    A line moved to another place in the facts section, into a topic for one, is no change; a line
    gone while a new one names the same fact file was rewritten.
    """
    old = _facts_lines(before.text(INDEX_PATH))
    new = _facts_lines(after.text(INDEX_PATH))
    added = Counter(new) - Counter(old)
    lost = Counter(old) - Counter(new)
    added_by_file: dict[str, list[str]] = {}
    for line in new:
        if added[line] > 0:
            added[line] -= 1
            parsed = parse_fact_line(line)
            if parsed is not None:
                added_by_file.setdefault(parsed.file_name, []).append(line)
    changes = []
    for line in old:
        if lost[line] <= 0:
            continue
        lost[line] -= 1
        parsed = parse_fact_line(line)
        file_name = parsed.file_name if parsed is not None else ""
        replacements = added_by_file.get(file_name, []) if parsed is not None else []
        stated = line.strip()
        if replacements:
            changes.append(FactChange(REWROTE, file_name, stated, replacements.pop(0).strip()))
        else:
            changes.append(FactChange(REMOVED, file_name, stated))
    for path in sorted(before.files):
        if path == INDEX_PATH or not path.endswith(".md"):
            continue
        if path not in after.files:
            changes.append(FactChange(FILE_REMOVED, path))
        elif (before.text(path) or "").strip() and not (after.text(path) or "").strip():
            changes.append(FactChange(FILE_EMPTIED, path))
    return changes


def _lines(text: str | None) -> list[str]:
    return [] if text is None else [line.removesuffix("\r") for line in text.split("\n")]


def _facts_lines(text: str | None) -> list[str]:
    """The lines of the facts section that state something: no headings, no blank lines."""
    lines = []
    in_facts = False
    for line in _lines(text):
        if is_section_heading(line):
            in_facts = line.strip() == FACTS_HEADING
        elif in_facts and line.strip() and not line.startswith(_GROUP_HEADING):
            lines.append(line.rstrip())
    return lines


def _refresh_view(text: str | None, fact_files: set[str], current: set[str]) -> list[str]:
    """The distillate with the lines refresh may change replaced by what must stay of them.

    A due fact's line may be rewritten, so only the file it names stays; a backfilled current item
    may gain its ``(since ...)``, so its text stays. Blank lines at the end do not count.
    """
    view = []
    section = ""
    for line in _lines(text):
        if is_section_heading(line):
            section = line.strip()
        parsed = parse_fact_line(line) if section == FACTS_HEADING and line.startswith("- ") else None
        if parsed is not None and parsed.file_name in fact_files:
            view.append(f"\0fact {parsed.file_name}")
        elif section == CURRENT_HEADING and line.startswith("- ") and current_line_text(line) in current:
            view.append(f"\0current {current_line_text(line)}")
        else:
            view.append(line)
    while view and not view[-1].strip():
        view.pop()
    return view


def _shown(line: str) -> str:
    line = line.strip()
    return line if len(line) <= _SHOWN_CHARACTERS else line[: _SHOWN_CHARACTERS - 3].rstrip() + "..."
