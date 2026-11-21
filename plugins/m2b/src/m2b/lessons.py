"""Lessons the owner kept: corrections no source states, brought into every session.

A lesson is one file under ``memory/lessons/``, written by a curation run when the owner kept it,
like a fact file: frontmatter with its ``kind`` (``knowledge``, how to name or judge a thing, or
``action``, about a command), its ``target`` (``every project`` or a repository's address), the day
it was ``kept``, and ``kept_at`` once a source such as ``~/.claude/CLAUDE.md`` states it; then a
title, the lesson as one sentence, and its evidence. A capture is never a lesson, whatever it says
about itself: only what stands in this folder is read.

The session start brings the knowledge lessons for every project in a block of their own after the
distillate (B257). The block is not data like the distillate: it says that these are corrections
the owner made and kept, written as facts. A lesson kept at its source is left out, since the
source already reaches the session. The block comes whole up to ``MAX_BLOCK_CHARACTERS``; the
distillate is cut earlier to make room for it, as the owner chose.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from m2b.notes.characters import without_hidden
from m2b.notes.frontmatter import Note, NoteFormatError
from m2b.notes.layout import MEMORY
from m2b.store.base import EvictedFileError, Store

FOLDER = f"{MEMORY}/lessons"
KNOWLEDGE = "knowledge"
ACTION = "action"
KINDS = (KNOWLEDGE, ACTION)
EVERY_PROJECT = "every project"
# Said before a lesson is kept, for the repository of the folder it comes from; it is kept under that
# repository's address (``m2b lesson add``, the reading of the sessions), never under these words.
THIS_PROJECT = "this project"
KIND = "kind"
TARGET = "target"
KEPT = "kept"
KEPT_AT = "kept_at"
# An action lesson's words: all of ``words`` in a command and none of ``unless`` make it fire; with
# ``ask`` Claude Code asks the owner before the command runs instead of only reminding.
WORDS = "words"
UNLESS = "unless"
ASK = "ask"

BLOCK_HEADER = (
    "m2b lessons: the owner corrected Claude on each of these and kept the correction; they hold in "
    "every project, unless the owner says otherwise in this session:"
)
# The block takes room from the distillate, so it has a limit of its own: a quarter of the session start.
MAX_BLOCK_CHARACTERS = 2_400


@dataclass(frozen=True)
class Lesson:
    name: str
    text: str
    kind: str
    target: str
    kept: str
    kept_at: str | None = None
    words: tuple[str, ...] = ()
    unless: tuple[str, ...] = ()
    ask: bool = False

    @property
    def in_the_block(self) -> bool:
        return self.kind == KNOWLEDGE and self.target == EVERY_PROJECT and self.kept_at is None


def read_all(store: Store) -> list[Lesson]:
    """Every lesson, the oldest kept first; a file without a lesson's fields holds none.

    A folder or a lesson's file that is not downloaded raises ``EvictedFileError``, and a folder or
    file that cannot be read raises ``StoreError`` or ``OSError``: a list without it would read as
    the owner having given those lessons up, and the tool hook's list would lose them.
    """
    scan = store.scan(FOLDER)
    for path in scan.evicted:
        if path == FOLDER or _is_lesson_file(path):
            raise EvictedFileError(path)
    found: list[Lesson] = []
    for path in scan.files:
        if not _is_lesson_file(path):
            continue
        try:
            text = store.read_bytes(path).decode("utf-8", errors="replace")
        except FileNotFoundError:
            # Listed, then removed by a sync or a run elsewhere before it was read: it is gone.
            continue
        lesson = _parsed(PurePosixPath(path).name, text)
        if lesson is not None:
            found.append(lesson)
    found.sort(key=lambda lesson: (lesson.kept, lesson.name))
    return found


def _is_lesson_file(path: str) -> bool:
    return PurePosixPath(path).parent.as_posix() == FOLDER and path.endswith(".md")


def _parsed(name: str, text: str) -> Lesson | None:
    note = Note.parse(text)
    fields = note.frontmatter
    if fields is None:
        return None
    kind, target, kept = fields.get(KIND), fields.get(TARGET), fields.get(KEPT)
    if kind not in KINDS or not target or not kept:
        return None
    sentence = _sentence(note.body)
    if sentence is None:
        return None
    try:
        words, unless = tuple(fields.get_list(WORDS)), tuple(fields.get_list(UNLESS))
    except NoteFormatError:
        return None
    if kind == ACTION and not words:
        return None
    return Lesson(name, sentence, kind, target, kept, fields.get(KEPT_AT) or None, words, unless, fields.get_flag(ASK))


def _sentence(body: str) -> str | None:
    """The first paragraph after the title, as one line; None where another heading, such as the
    evidence, comes before any paragraph."""
    paragraph: list[str] = []
    titled = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            if paragraph or titled:
                break
            titled = True
            continue
        if not stripped:
            if paragraph:
                break
            continue
        paragraph.append(stripped)
    return " ".join(paragraph) or None


def render(lesson: Lesson, title: str, evidence: Sequence[str]) -> str:
    """A lesson's file as the curation run writes it."""
    fields: dict[str, str | bool | list[str]] = {KIND: lesson.kind, TARGET: lesson.target, KEPT: lesson.kept}
    if lesson.kept_at:
        fields[KEPT_AT] = lesson.kept_at
    if lesson.words:
        fields[WORDS] = list(lesson.words)
    if lesson.unless:
        fields[UNLESS] = list(lesson.unless)
    if lesson.ask:
        fields[ASK] = True
    links = "".join(f"- [[{name}]]\n" for name in evidence)
    body = f"# {title}\n\n{lesson.text}\n" + (f"\n## Evidence\n\n{links}" if links else "")
    return Note.new(fields, body).render()


def kept_at_source(found: Iterable[Lesson]) -> list[Lesson]:
    return [lesson for lesson in found if lesson.kept_at is not None]


def fitting(found: Sequence[Lesson]) -> tuple[list[Lesson], int]:
    """The lessons the block carries, whole and the oldest first, and how many it leaves out past
    ``MAX_BLOCK_CHARACTERS``."""
    chosen = [lesson for lesson in found if lesson.in_the_block]
    lines = [BLOCK_HEADER]
    for index, lesson in enumerate(chosen):
        left = len(chosen) - index
        # After the last lesson no line has to say that more are left out.
        tail = [_line(lesson)] if left == 1 else [_line(lesson), _more(left)]
        if len("\n".join([*lines, *tail])) + 1 > MAX_BLOCK_CHARACTERS:
            return chosen[:index], left
        lines.append(_line(lesson))
    return chosen, 0


def block(found: Sequence[Lesson]) -> str:
    """The block a session starts with; empty without a lesson for it."""
    carried, left = fitting(found)
    if not carried and not left:
        return ""
    lines = [BLOCK_HEADER, *(_line(lesson) for lesson in carried), *([_more(left)] if left else [])]
    return "\n".join(lines) + "\n"


def _line(lesson: Lesson) -> str:
    return f"- {without_hidden(lesson.text)}"


def _more(left: int) -> str:
    return f"({left} more {'lesson is' if left == 1 else 'lessons are'} kept in {FOLDER}/)"
