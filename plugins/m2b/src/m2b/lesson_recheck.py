"""Whether a file every session loads now states a lesson of the block, checked again at every reading (B291).

A lesson is checked against its sources once, when the reading proposes it (``lesson_sources``).
The files change afterwards: the owner writes the rule into ``~/.claude/CLAUDE.md``, a plugin's
output style brings it. A lesson the block still carries then stands twice in every session. So
each reading of the sessions asks a model, with nothing to call, whether a line of the files every
session on this machine loads states a lesson of the block. These are the files under Claude Code's
own folder that ``start_size.start_files`` names for any folder: its ``CLAUDE.md``, its rules
without ``paths``, the output style chosen there. A project's files and Claude Code's memory of a
project reach only the sessions of that project, so they state nothing for every project.

Only ``right`` changes a lesson, and only where code holds the verdict to a line of a file it showed
(``lesson_sources.source_line``): the lesson keeps its file and gets ``kept_at``, the file that
states it, so it leaves the block and ``m2b status`` names it as kept at its source. A line that
says it wrongly or in part leaves the lesson as it is: the block is then the place the correction
holds.

The model is asked only when the lessons of the block or those files changed since the last
answer that could be read, which this machine remembers as a fingerprint in its own state: the
files are this machine's. It runs inside the reading, with ``curation.read_sessions`` on, since
that is the owner's consent that m2b reads Claude Code's files. An answer that cannot be read
changes nothing and keeps the fingerprint, so the next reading asks again.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from m2b import claude_code, fixes, lessons, start_size
from m2b.atomic_file import write_text_atomically
from m2b.lesson_sources import RIGHT, LessonSourcesError, Source, source_line, verdicts_of
from m2b.notes.frontmatter import Note
from m2b.redaction import redact
from m2b.store.base import Store

INSTRUCTION = Path(__file__).with_name("lesson_recheck_instruction.md")
STATE_FILE = "lesson-sources-checked.json"
FORMAT = 1
# Claude Code's memory of each project lies below this folder of its own; it reaches one project.
_PROJECTS = "projects"

# Asks the model: the instruction and the text to read in, its answer out; raises ``RecheckError``
# when there is none.
Ask = Callable[[str, str], str]


class RecheckError(Exception):
    """No answer that could be read; no lesson changed."""


@dataclass(frozen=True)
class Rechecked:
    # Each lesson that now stands at its source: its file's name and the file that states it.
    kept_at_source: tuple[tuple[str, str], ...] = ()
    # Why no model was asked, None when one was.
    skipped: str | None = None


def instruction() -> str:
    return INSTRUCTION.read_text(encoding="utf-8")


def recheck(store: Store, environ: Mapping[str, str], state_dir: Path, ask: Ask) -> Rechecked:
    """Checks the lessons of the block against the files every session loads, if either changed."""
    found = [lesson for lesson in lessons.read_all(store) if lesson.in_the_block]
    if not found:
        return Rechecked(skipped="no lesson in the block")
    sources = every_session_sources(environ)
    if not sources:
        return Rechecked(skipped="no file every session loads")
    fingerprint = _fingerprint(found, sources)
    if _last_fingerprint(state_dir) == fingerprint:
        return Rechecked(skipped="the lessons and the files every session loads are as at the last check")
    answer = ask(instruction(), step_input(found, sources))
    try:
        given = verdicts_of(answer)
    except LessonSourcesError as error:
        raise RecheckError(str(error)) from error
    stated: list[tuple[str, str]] = []
    for number, lesson in enumerate(found, start=1):
        verdict = given.get(number)
        if verdict is None or verdict.get("verdict") != RIGHT:
            continue
        source, _ = source_line(verdict, sources)
        if source is None or source.fix_path is None:
            continue
        if _keep_at(store, lesson, source.fix_path):
            stated.append((lesson.name, source.fix_path))
    # The block as the next reading finds it: a lesson kept at its source has left it.
    left = {name for name, _ in stated}
    _remember(state_dir, _fingerprint([lesson for lesson in found if lesson.name not in left], sources))
    return Rechecked(tuple(stated))


def every_session_sources(environ: Mapping[str, str]) -> list[Source]:
    """The files under Claude Code's own folder that a session in any folder loads; none without a
    home folder to start from. Each is named under ``~/.claude/``, as a fix names Claude Code's folder,
    also where ``CLAUDE_CONFIG_DIR`` puts it elsewhere, so no path of this machine reaches the store."""
    home = environ.get("HOME")
    if not home:
        return []
    claude = claude_code.claude_folder(environ)
    found: list[Source] = []
    for path in start_size.start_files(environ, Path(home)):
        relative = _below(path, claude)
        if relative is None or relative.parts[:1] == (_PROJECTS,):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if start_size.only_with_a_matching_file(text):
            continue
        shown = fixes.HOME_PREFIX + relative.as_posix()
        found.append(Source(shown, tuple(text.splitlines()), shown, ()))
    return found


def step_input(found: Sequence[lessons.Lesson], sources: Sequence[Source]) -> str:
    """The JSON document the model reads: the lessons by number, the sources by number, lines numbered."""
    document = {
        "lessons": [{"lesson": number, "text": lesson.text} for number, lesson in enumerate(found, start=1)],
        "sources": [
            {
                "source": number,
                "file": source.shown,
                "lines": [f"{index}: {redact(line)}" for index, line in enumerate(source.lines, start=1)],
            }
            for number, source in enumerate(sources, start=1)
        ],
    }
    return json.dumps(document, ensure_ascii=False, indent=1)


def _keep_at(store: Store, lesson: lessons.Lesson, stated_in: str) -> bool:
    """Writes ``kept_at`` into the lesson's file, as long as the file still holds that lesson."""
    path = f"{lessons.FOLDER}/{lesson.name}"
    try:
        text = store.read_text(path)
    # A byte that is no UTF-8 reads as a lesson, but its file is not written back with it replaced.
    except (FileNotFoundError, UnicodeDecodeError):
        return False
    note = Note.parse(text)
    if note.frontmatter is None or lessons.parse(lesson.name, text) != lesson:
        return False
    note.frontmatter.set(lessons.KEPT_AT, stated_in)
    store.replace(path, note.render().encode("utf-8"))
    return True


def _fingerprint(found: Sequence[lessons.Lesson], sources: Sequence[Source]) -> str:
    seen = {
        "lessons": [[lesson.name, lesson.text] for lesson in found],
        "sources": [[source.shown, list(source.lines)] for source in sources],
    }
    return hashlib.sha256(json.dumps(seen, ensure_ascii=False).encode("utf-8")).hexdigest()


def _last_fingerprint(state_dir: Path) -> str | None:
    """The fingerprint of the last check; a file that cannot be read remembers none, so the model is asked."""
    try:
        raw = json.loads((state_dir / STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict) or raw.get("format") != FORMAT or not isinstance(raw.get("checked"), str):
        return None
    return str(raw["checked"])


def _remember(state_dir: Path, fingerprint: str) -> None:
    """A write that fails is lost: the next reading only asks once more."""
    with contextlib.suppress(OSError):
        write_text_atomically(
            state_dir / STATE_FILE, json.dumps({"format": FORMAT, "checked": fingerprint}) + "\n", state_dir
        )


def _below(path: Path, folder: Path) -> Path | None:
    try:
        return path.relative_to(folder)
    except ValueError:
        return None
