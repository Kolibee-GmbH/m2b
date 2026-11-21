"""A current item above the topics that names exactly one topic moves under that topic, at every run (B290).

An item before the first ``###`` heading of ``## Current`` reaches every session, one under a topic
only a session about it. Ingest puts a new item where it belongs, but an item filed before its
topic existed, or one a worklog note brought in, stays above the topics until a capture about the
same thing comes, and until then every session pays for it. Lint's step moves it in code instead:
whether an item names a topic is decided the way a prompt brings a topic in (``topic_match``), by
a word of any of the topic's headings, whole and ignoring case, and only an item that names
exactly one topic moves. One that names two belongs to neither alone, and one that names none
holds everywhere. A word that stands only in a ``[[link]]`` names nothing, since a link is
evidence, not what the item says.

The item goes to the end of the topic's items under ``## Current``; a topic without a heading there
gets its heading copied from ``## Facts``, at the end of ``## Current``. Every other line stays as
it is, and the item keeps its text and its ``(since ...)``, so a "Still current?" question about it
still finds it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from m2b.notes.layout import MEMORY, MEMORY_INDEX
from m2b.notes.memory_index import (
    CURRENT_HEADING,
    MemoryIndex,
    Topic,
    current_line_text,
    ends_topic_block,
    is_section_heading,
    parse_topic_heading,
)
from m2b.store.base import Store, StoreError
from m2b.topic_match import named_topics

INDEX_PATH = f"{MEMORY}/{MEMORY_INDEX}"
_LINK = re.compile(r"\[\[[^\[\]\n]*\]\]")
_GROUP_HEADING = "### "


@dataclass(frozen=True)
class Placed:
    text: str
    # The items that moved, as ``MemoryIndex.current`` holds them.
    moved: tuple[str, ...] = ()


def place(store: Store) -> list[str]:
    """Moves the items in ``memory/MEMORY.md`` and names them; writes only when one moved.

    A distillate that is missing or cannot be read moves nothing: lint names it.
    """
    try:
        text = store.read_text(INDEX_PATH)
    except (FileNotFoundError, StoreError, UnicodeDecodeError):
        return []
    result = placed(text)
    if result.moved:
        store.replace(INDEX_PATH, result.text.encode("utf-8"))
    return list(result.moved)


def placed(text: str) -> Placed:
    segments = [segment for segment in re.split(r"(?<=\n)", text) if segment]
    lines = [segment.rstrip("\r\n") for segment in segments]
    current = _current_section(lines)
    topics = _topics(text)
    if current is None or not topics:
        return Placed(text)
    start, end = current
    zone_end = next((i for i in range(start + 1, end) if lines[i].startswith(_GROUP_HEADING)), end)
    moves: dict[int, Topic] = {}
    for i in range(start + 1, zone_end):
        if lines[i].startswith("- "):
            named = named_topics(topics, _LINK.sub(" ", current_line_text(lines[i])))
            if len(named) == 1:
                moves[i] = named[0]
    if not moves:
        return Placed(text)
    newline = "\r\n" if "\r\n" in text else "\n"
    kept = _without(segments, set(moves))
    by_topic: dict[str, list[str]] = {}
    for i, topic in moves.items():
        by_topic.setdefault(topic.name, []).append(_whole(segments[i], newline))
    for name, items in by_topic.items():
        kept = _insert(kept, name, items, _facts_heading(segments, name, newline), newline)
    return Placed("".join(kept), tuple(current_line_text(lines[i]) for i in moves))


def _current_section(lines: list[str]) -> tuple[int, int] | None:
    """The first ``## Current`` heading's index and the index where its section ends."""
    start = next(
        (i for i, line in enumerate(lines) if is_section_heading(line) and line.strip() == CURRENT_HEADING), None
    )
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if is_section_heading(lines[i])), len(lines))
    return start, end


def _topics(text: str) -> list[Topic]:
    """The distillate's topics, one per name, with the words of all its headings."""
    words: dict[str, dict[str, None]] = {}
    for topic in MemoryIndex.parse(text).topics:
        words.setdefault(topic.name, {}).update(dict.fromkeys(topic.words))
    return [Topic(name, tuple(names)) for name, names in words.items()]


def _without(segments: list[str], removed: set[int]) -> list[str]:
    """The segments without the removed ones; a removal that leaves two blank lines in a row leaves one."""
    kept: list[str] = []
    skip_blank = False
    for i, segment in enumerate(segments):
        if i in removed:
            skip_blank = skip_blank or (bool(kept) and not kept[-1].strip())
            continue
        if skip_blank and not segment.strip():
            skip_blank = False
            continue
        skip_blank = False
        kept.append(segment)
    return kept


def _insert(segments: list[str], name: str, items: list[str], facts_heading: str | None, newline: str) -> list[str]:
    lines = [segment.rstrip("\r\n") for segment in segments]
    current = _current_section(lines)
    if current is None:
        return segments
    start, end = current
    heading = next(
        (i for i in range(start + 1, end) if lines[i].startswith(_GROUP_HEADING) and _topic_name(lines[i]) == name),
        None,
    )
    if heading is not None:
        at = next((i for i in range(heading + 1, end) if ends_topic_block(lines[i])), end)
        while at > heading + 1 and not lines[at - 1].strip():
            at -= 1
        return _put(segments, at, items, newline)
    if facts_heading is None:
        return segments
    if end < len(segments):
        at = end
        while at > start + 1 and not lines[at - 1].strip():
            at -= 1
        follows = [] if at < end else [newline]
        return _put(segments, at, [newline, facts_heading, *items, *follows], newline)
    blank_before = end > start + 1 and not lines[end - 1].strip()
    return _put(segments, end, [*([] if blank_before else [newline]), facts_heading, *items], newline)


def _put(segments: list[str], at: int, new: list[str], newline: str) -> list[str]:
    before = segments[:at]
    if before:
        before[-1] = _whole(before[-1], newline)
    return [*before, *new, *segments[at:]]


def _facts_heading(segments: list[str], name: str, newline: str) -> str | None:
    """The topic's first heading in the file, as it stands there."""
    for segment in segments:
        line = segment.rstrip("\r\n")
        if line.startswith(_GROUP_HEADING) and _topic_name(line) == name:
            return _whole(segment, newline)
    return None


def _topic_name(line: str) -> str | None:
    topic = parse_topic_heading(line)
    return topic.name if topic is not None else None


def _whole(segment: str, newline: str) -> str:
    """The file's last line may lack its line end."""
    return segment if segment.endswith("\n") else segment + newline
