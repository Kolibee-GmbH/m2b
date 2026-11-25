"""A lesson the owner keeps by hand, on its way into ``memory/lessons/``.

"Merk dir als Lehre: ..., wenn du scripts/check startest" in a session is the owner keeping a
lesson, so it needs no proposal and no answer. A client only adds to the store and only the
curation run writes ``memory/``, and no model step may write ``memory/lessons/`` (B261): so the
session's ``m2b lesson add`` writes one file, ``state/core/lessons-kept/<name>.json``, created
exclusively, and the run's harvest, in code, turns each into a lesson file and removes it.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from m2b.lessons import ACTION, EVERY_PROJECT, KINDS, KNOWLEDGE, Lesson, read_all, render
from m2b.lessons import FOLDER as LESSONS_FOLDER
from m2b.notes.characters import CONTROL, unsafe_characters, without_hidden
from m2b.notes.layout import STATE
from m2b.store.base import Store, StoreError

FOLDER = f"{STATE}/core/lessons-kept"
MAX_TEXT = 500
MAX_WORDS = 5
_LINE_BREAK = re.compile("[\r\n\u2028\u2029\x85]")
_NOT_A_SLUG = re.compile(r"[^a-z0-9]+")
MAX_NAME = 40
# German writes these out when the marks are dropped; any other mark is dropped alone (é is e).
# Letters whose stroke or ligature is part of the letter have no mark Unicode splits off, so they
# are written out here too, else they would be hyphens.
_WRITTEN_OUT = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "æ": "ae", "œ": "oe", "ø": "o", "ł": "l", "đ": "d", "ħ": "h", "\u0131": "i"}
)
_FILE = re.compile(r"[0-9a-f]{12}\.json")


class LessonRefusedError(ValueError):
    """What was given is no lesson; nothing was kept."""


@dataclass(frozen=True)
class KeptLesson:
    title: str
    text: str
    kind: str
    target: str
    day: str
    words: tuple[str, ...] = ()
    unless: tuple[str, ...] = ()
    ask: bool = False
    # The file that states the lesson already, where a reading found it there: the lesson only counts.
    kept_at: str | None = None


@dataclass
class Filed:
    lessons: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def checked(given: KeptLesson) -> KeptLesson:
    """The lesson as it is kept, or ``LessonRefusedError`` for one that could not be."""
    text, title = " ".join(given.text.split()), " ".join(given.title.split())
    # A text that begins with # would read back as a heading, and the lesson would be lost.
    if not text or len(text) > MAX_TEXT or _LINE_BREAK.search(given.text.strip()) or text.startswith("#"):
        raise LessonRefusedError(f"a lesson is one sentence of at most {MAX_TEXT} characters")
    if given.kind not in KINDS:
        raise LessonRefusedError(f"a lesson's kind is {' or '.join(KINDS)}")
    if given.kind == KNOWLEDGE and given.target != EVERY_PROJECT and given.kept_at is None:
        raise LessonRefusedError(
            "a knowledge lesson for one project belongs in that project's CLAUDE.md: keep it as a fix with m2b fix add"
        )
    words = tuple(word.strip() for word in given.words if word.strip())
    unless = tuple(word.strip() for word in given.unless if word.strip())
    if given.kind == ACTION and not words:
        raise LessonRefusedError("an action lesson names the words a command holds when it applies")
    for word in (*words, *unless):
        if "," in word or "[" in word or "]" in word or _LINE_BREAK.search(word):
            raise LessonRefusedError(f"{word!r} is no word of a command: no comma, bracket or line break")
    # Harvest writes these into memory/, where no model step's check runs: a character that hides or
    # reorders text would read one way to the owner and another to the model.
    for part in (given.text, given.title, *words, *unless, given.kept_at or ""):
        if (
            unsafe_characters(part)
            or CONTROL.sub("", part.replace("\n", "")) != part.replace("\n", "")
            or without_hidden(part) != part
        ):
            raise LessonRefusedError("a lesson holds no character that hides or reorders text or steers a terminal")
    if len(words) > MAX_WORDS or len(unless) > MAX_WORDS:
        raise LessonRefusedError(f"a lesson names at most {MAX_WORDS} words of each kind")
    kept_at = " ".join(given.kept_at.split()) if given.kept_at else None
    return KeptLesson(title or text[:60], text, given.kind, given.target, given.day, words, unless, given.ask, kept_at)


def keep(store: Store, lesson: KeptLesson) -> bool:
    """Adds the lesson for the next run; False when the same lesson waits already."""
    lesson = checked(lesson)
    raw = {
        "title": lesson.title,
        "text": lesson.text,
        "kind": lesson.kind,
        "target": lesson.target,
        "day": lesson.day,
        "words": list(lesson.words),
        "unless": list(lesson.unless),
        "ask": lesson.ask,
    }
    if lesson.kept_at is not None:
        raw["kept_at"] = lesson.kept_at
    drawn = json.dumps(
        [lesson.text, lesson.kind, lesson.target, raw["words"], raw["unless"], lesson.ask, lesson.kept_at],
        ensure_ascii=False,
    )
    name = hashlib.sha256(drawn.encode("utf-8")).hexdigest()[:12]
    try:
        store.create_exclusive(f"{FOLDER}/{name}.json", (json.dumps(raw, ensure_ascii=False) + "\n").encode("utf-8"))
    except FileExistsError:
        return False
    return True


def file_kept(store: Store) -> Filed:
    """Harvest's part: each kept lesson becomes a file under ``memory/lessons/`` and its waiting file
    goes. One that cannot be read or is no lesson stays and is a problem for the review."""
    filed = Filed()
    try:
        paths = sorted(path for path in store.scan(FOLDER).files if _FILE.fullmatch(PurePosixPath(path).name))
    except (OSError, StoreError) as error:
        filed.problems.append(f"the lessons kept by hand wait for the next run: {error}")
        return filed
    for path in paths:
        try:
            lesson = _read(store, path)
            name = _place(store, lesson)
            store.delete(path)
        except (OSError, StoreError, ValueError, KeyError, TypeError) as error:
            filed.problems.append(f"a lesson kept by hand ({PurePosixPath(path).name}) waits: {error}")
            continue
        filed.lessons.append(name)
    return filed


def _read(store: Store, path: str) -> KeptLesson:
    raw = json.loads(store.read_bytes(path).decode("utf-8"))
    return checked(
        KeptLesson(
            str(raw["title"]),
            str(raw["text"]),
            str(raw["kind"]),
            str(raw.get("target") or EVERY_PROJECT),
            str(raw["day"]),
            tuple(str(word) for word in raw.get("words", ())),
            tuple(str(word) for word in raw.get("unless", ())),
            raw.get("ask") is True,
            str(raw["kept_at"]) if raw.get("kept_at") is not None else None,
        )
    )


def _file_name(title: str) -> str:
    """The name a new lesson's file draws from its title, without ``.md``: ``Über Prüfungen`` is
    ``ueber-pruefungen``. Umlauts are written out, ß is ss (``casefold`` does that), a letter with
    another mark loses the mark, anything else between letters is one hyphen. A name longer than
    ``MAX_NAME`` ends at the last whole word before it, one long word at the limit. A title with nothing
    left of a to z or 0 to 9 is ``lesson``. Only new files are named here: a lesson that stands keeps the
    name it has, whatever this function made of its title then."""
    folded = unicodedata.normalize("NFC", title).casefold().translate(_WRITTEN_OUT)
    plain = "".join(c for c in unicodedata.normalize("NFKD", folded) if not unicodedata.combining(c))
    slug = _NOT_A_SLUG.sub("-", plain).strip("-")
    if len(slug) > MAX_NAME:
        cut = slug[: MAX_NAME + 1]
        slug = cut[: cut.rfind("-")] if "-" in cut else slug[:MAX_NAME]
    return slug or "lesson"


def _place(store: Store, lesson: KeptLesson) -> str:
    """Writes the lesson under a name drawn from its title; a name taken by another lesson gets a number.
    A lesson that stands already, kept on another day, is not written twice."""
    wanted = (lesson.text, lesson.kind, lesson.target, lesson.words, lesson.unless, lesson.ask, lesson.kept_at)
    for standing in read_all(store):
        held = (standing.text, standing.kind, standing.target, standing.words, standing.unless, standing.ask)
        if (*held, standing.kept_at) == wanted:
            return standing.name
    slug = _file_name(lesson.title)
    for number in range(1, 100):
        name = f"{slug}.md" if number == 1 else f"{slug}-{number}.md"
        text = render(
            Lesson(
                name,
                lesson.text,
                lesson.kind,
                lesson.target,
                lesson.day,
                lesson.kept_at,
                lesson.words,
                lesson.unless,
                lesson.ask,
            ),
            lesson.title,
            [],
        ).encode("utf-8")
        try:
            store.create_exclusive(f"{LESSONS_FOLDER}/{name}", text)
        except FileExistsError:
            if store.read_bytes(f"{LESSONS_FOLDER}/{name}") == text:
                return name
            continue
        return name
    raise ValueError(f"no free name for the lesson {slug}")
