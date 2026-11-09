"""When a topic of the distillate counts as named: one of its words in a prompt or a project path.

A word matches whole, with no letter, digit or underscore right before or after it, so "Acme"
does not fire on "Acmes" and "C++" or "node.js" still match as written. Text and words are
compared in Unicode NFC and case-folded, because macOS hands out paths in decomposed form
("u" plus a combining mark for "ü"). Inflected forms ("Müllers") do not match; the curator gives a
topic the forms the owner uses. Kept to the standard library and cheap to import, because the
prompt hook runs it before every prompt.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from pathlib import Path

from m2b.notes.memory_index import Topic

# Shorter words would fire on too much ordinary text.
MIN_WORD_CHARACTERS = 3

_PATH_SEPARATORS = re.compile(r"[-_./\\]+")
_SPACES = re.compile(r"\s+")


def normalized(text: str) -> str:
    return _SPACES.sub(" ", unicodedata.normalize("NFC", text).casefold()).strip()


def path_text(path: str) -> str:
    """A path as text to match words in: ``kim-lee_export`` reads as ``kim lee export``."""
    return _PATH_SEPARATORS.sub(" ", path)


def project_place(folder: Path, home: str | None) -> str:
    """The part of a project folder's path that may name a topic: below the owner's home folder, so
    the owner's own user name never does."""
    try:
        return str(folder.relative_to(home)) if home else str(folder)
    except ValueError:
        return str(folder)


def names_topic(topic: Topic, text: str) -> bool:
    return _names(topic.words, normalized(text))


def names_topic_in_path(topic: Topic, path: str) -> bool:
    """Like ``names_topic``, with the word read as a path too: "Hans-Peter Müller" is found in
    ``offer_hans_peter_müller``. In a prompt the word stays as written, so "node js" is not "node.js"."""
    return _names([path_text(word) for word in topic.words], normalized(path_text(path)))


def named_topics(topics: Iterable[Topic], *texts: str) -> list[Topic]:
    """The topics any of ``texts`` names, in the order given."""
    haystack = " \n ".join(normalized(text) for text in texts)
    return [topic for topic in topics if _names(topic.words, haystack)]


def _names(words: Sequence[str], haystack: str) -> bool:
    return any(_contains(haystack, normalized(word)) for word in words)


def _contains(haystack: str, word: str) -> bool:
    if len(word) < MIN_WORD_CHARACTERS:
        return False
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", haystack) is not None
