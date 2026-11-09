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

from m2b.notes.characters import strip_unsafe, unsafe_characters
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


def unsafe_line(before: Snapshot, after: Snapshot) -> str | None:
    """Why the step must be undone: the first line it wrote that holds an unsafe character."""
    for path in sorted(after.files):
        new_lines = _lines(after.text(path))
        unchanged = Counter(_lines(before.text(path)))
        for line in new_lines:
            if unchanged[line] > 0:
                unchanged[line] -= 1
                continue
            names = unsafe_characters(line)
            if names:
                more = len(names) - _NAMED_CHARACTERS
                listed = ", ".join(names[:_NAMED_CHARACTERS]) + (f" and {more} more" if more > 0 else "")
                shown = _shown(strip_unsafe(line))
                return f'a line written to {path} holds {listed}, which hide or reorder text: "{shown}"'
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
        if before.files.get(path) != after.files.get(path):
            verb = "added" if path not in before.files else "removed" if path not in after.files else "changed"
            return f"the refresh step {verb} {path}, which is not due"
    names = {PurePosixPath(path).name for path in allowed}
    old = _refresh_view(before.text(INDEX_PATH), names, set(current))
    new = _refresh_view(after.text(INDEX_PATH), names, set(current))
    if old == new:
        return None
    for tag, old_start, old_end, new_start, new_end in difflib.SequenceMatcher(
        a=old, b=new, autojunk=False
    ).get_opcodes():
        if tag == "equal":
            continue
        line = (old[old_start:old_end] or new[new_start:new_end])[0].lstrip("\0")
        return f'the refresh step changed the line "{_shown(line)}" in {INDEX_PATH}, which belongs to no due fact'
    return None


def fact_changes(before: Snapshot, after: Snapshot) -> list[str]:
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
        replacements = added_by_file.get(parsed.file_name, []) if parsed is not None else []
        if replacements:
            changes.append(f'rewrote the facts line "{_shown(line)}" as "{_shown(replacements.pop(0))}"')
        else:
            changes.append(f'removed the facts line "{_shown(line)}"')
    for path in sorted(before.files):
        if path == INDEX_PATH or not path.endswith(".md"):
            continue
        if path not in after.files:
            changes.append(f"removed {path}")
        elif (before.text(path) or "").strip() and not (after.text(path) or "").strip():
            changes.append(f"emptied {path}")
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
