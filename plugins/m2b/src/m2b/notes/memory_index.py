"""``memory/MEMORY.md``, the distillate: a facts section and a current section.

A facts line is ``- <statement> (<fact-file>.md)``. Lines are parsed, never matched as
substrings, so ``friend-alex.md`` does not count as indexing ``alex.md``. Facts before the first
``###`` heading of the facts section hold in every session. A topic is a group inside the facts
section, headed ``### <name> (<word>, <word>)``: its facts come into a session only when one of its
words is named, so what matters in one context stays out of the others. The words are the last
parenthesised group, so a name may hold parentheses. Only ``#`` and ``##`` start a section, so a
reader that knows nothing of topics reads their lines as facts and loses nothing. The current section
is a list of what is going on, with topics under the same headings: an item before its first ``###``
heading holds in every session, one under a topic comes in with that topic. Headings with one name,
in either section, are one topic, and a word of any of them names it. An item may end in
``(since YYYY-MM-DD)``, the day it started or was last confirmed, so a curation run can ask about one
that went quiet; that suffix is read apart from the item's text. One that is no date stays in the
text and is reported.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field

FACTS_HEADING = "## Facts"
CURRENT_HEADING = "## Current"
# What a session reads above a topic's current items; in the file they stand under ``## Current``.
CURRENT_IN_TOPIC = "#### Current"
_TOPIC_SECTIONS = (FACTS_HEADING, CURRENT_HEADING)

# Only top-level and second-level headings switch the section; deeper ones group lines in it.
_SECTION_HEADING = re.compile(r"#{1,2} ")
_SINCE = re.compile(r"\s*\(since (?P<since>[^()]*)\)\s*\Z")
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_FACT_LINE = re.compile(r"- (?P<statement>\S.*?) \((?P<file>[^()/\s]+\.md)\)\s*\Z")
_GROUP_HEADING = re.compile(r"### ")
_TOPIC_HEADING = re.compile(r"### (?P<name>\S.*?) \((?P<words>[^()]*)\)\s*\Z")
# A topic's block runs until the next heading of its own level or above; deeper ones stay in it.
_BLOCK_END = re.compile(r"#{1,3} ")


@dataclass(frozen=True)
class FactLine:
    statement: str
    file_name: str
    # The topic it belongs to, None for a fact that holds everywhere.
    topic: str | None = None


@dataclass(frozen=True)
class Topic:
    name: str
    words: tuple[str, ...]


@dataclass(frozen=True)
class TopicBlock:
    """A topic as a session gets it: its heading and facts as they stand in the file, then its
    current items under ``#### Current``. The topic holds the words of all its headings."""

    topic: Topic
    text: str


@dataclass(frozen=True)
class TopicSplit:
    """The distillate's text without its topic blocks, and the blocks."""

    general: str
    blocks: list[TopicBlock]


@dataclass(frozen=True)
class CurrentLine:
    text: str
    since: str | None
    # The topic it belongs to, None for an item that holds everywhere.
    topic: str | None = None


@dataclass
class _TopicPart:
    """One block of a topic in the file: its heading and the lines below it."""

    topic: Topic
    heading: str
    is_current: bool
    body: list[str] = field(default_factory=list)


@dataclass
class MemoryIndex:
    facts: list[FactLine] = field(default_factory=list)
    current_lines: list[CurrentLine] = field(default_factory=list)
    unparsed_fact_lines: list[str] = field(default_factory=list)
    invalid_since: list[str] = field(default_factory=list)
    # One per topic heading, so a topic that stands in both sections is here twice.
    topics: list[Topic] = field(default_factory=list)
    # ``###`` headings in the facts or the current section that are no topic; their lines hold everywhere.
    unparsed_topic_headings: list[str] = field(default_factory=list)

    @property
    def current(self) -> list[str]:
        """The current items without their ``(since ...)``."""
        return [line.text for line in self.current_lines]

    @classmethod
    def parse(cls, text: str) -> MemoryIndex:
        index = cls()
        section = ""
        topic: Topic | None = None
        for raw_line in text.split("\n"):
            line = raw_line.removesuffix("\r")
            if is_section_heading(line):
                section, topic = line.strip(), None
            elif _GROUP_HEADING.match(line) and section in _TOPIC_SECTIONS:
                topic = parse_topic_heading(line)
                if topic is not None:
                    index.topics.append(topic)
                else:
                    index.unparsed_topic_headings.append(line)
            elif line.startswith("- ") and section == CURRENT_HEADING:
                name = topic.name if topic is not None else None
                index.current_lines.append(_current_line(line, index.invalid_since, name))
            elif line.startswith("- ") and section == FACTS_HEADING:
                parsed = parse_fact_line(line, topic.name if topic is not None else None)
                if parsed is not None:
                    index.facts.append(parsed)
                else:
                    index.unparsed_fact_lines.append(line)
        return index

    def indexed_files(self) -> set[str]:
        """The fact files the facts section points to."""
        return {fact.file_name for fact in self.facts}


def is_day(text: str) -> bool:
    """``YYYY-MM-DD`` naming a day that exists."""
    if _DAY.match(text) is None:
        return False
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        return False
    return True


def is_section_heading(line: str) -> bool:
    """A line that starts a section; a deeper heading only groups lines inside one."""
    return _SECTION_HEADING.match(line) is not None


def ends_topic_block(line: str) -> bool:
    """A heading of a topic's own level or above ends its block; a deeper one stays in it."""
    return _BLOCK_END.match(line) is not None


def current_line_text(line: str) -> str:
    """A current line's item without its ``(since ...)``, as ``MemoryIndex.current`` holds it."""
    return _current_line(line, []).text


def _current_line(line: str, invalid: list[str], topic: str | None = None) -> CurrentLine:
    item = line[2:].strip()
    match = _SINCE.search(item)
    if match is None:
        return CurrentLine(item, None, topic)
    if not is_day(match.group("since").strip()):
        invalid.append(line)
        return CurrentLine(item, None, topic)
    return CurrentLine(item[: match.start()].rstrip(), match.group("since").strip(), topic)


def parse_fact_line(line: str, topic: str | None = None) -> FactLine | None:
    match = _FACT_LINE.match(line.removesuffix("\r"))
    if match is None:
        return None
    return FactLine(match.group("statement"), match.group("file"), topic)


def parse_topic_heading(line: str) -> Topic | None:
    """``### <name> (<word>, <word>)``, or None for a heading that names no words."""
    match = _TOPIC_HEADING.match(line.removesuffix("\r"))
    if match is None:
        return None
    words = tuple(word.strip() for word in match.group("words").split(",") if word.strip())
    return Topic(match.group("name").strip(), words) if words else None


def split_topics(text: str) -> TopicSplit:
    """Takes each topic block out of the facts and the current section and leaves every other line as it is.

    What a session saw before topics existed (a title, other sections, lines the parser cannot
    read) stays in the general view; only parsed topics come out. Blocks under one name are one
    topic, where the name first stands.
    """
    general: list[str] = []
    parts: list[_TopicPart] = []
    section = ""
    part: _TopicPart | None = None
    for segment in re.split(r"(?<=\n)", text):
        line = segment.rstrip("\r\n")
        if ends_topic_block(line):
            part = None
        if is_section_heading(line):
            section = line.strip()
        heading = parse_topic_heading(line) if section in _TOPIC_SECTIONS and _GROUP_HEADING.match(line) else None
        if heading is not None:
            part = _TopicPart(heading, segment, section == CURRENT_HEADING)
            parts.append(part)
        elif part is not None:
            part.body.append(segment)
        else:
            general.append(segment)
    by_name: dict[str, list[_TopicPart]] = {}
    for part in parts:
        by_name.setdefault(part.topic.name, []).append(part)
    return TopicSplit("".join(general), [_topic_block(same_name) for same_name in by_name.values()])


def _topic_block(parts: list[_TopicPart]) -> TopicBlock:
    words = tuple(dict.fromkeys(word for part in parts for word in part.topic.words))
    facts = [line for part in parts if not part.is_current for line in _body(part)]
    current = [line for part in parts if part.is_current for line in _body(part)]
    lines = [_whole_line(parts[0].heading), *facts]
    if current:
        lines += [f"{CURRENT_IN_TOPIC}\n", *current]
    return TopicBlock(Topic(parts[0].topic.name, words), "".join(lines))


def _body(part: _TopicPart) -> list[str]:
    """A block's lines; the blank ones that separate it from the next heading are not part of it."""
    lines = list(part.body)
    while lines and not lines[-1].strip():
        lines.pop()
    return [_whole_line(line) for line in lines]


def _whole_line(segment: str) -> str:
    """The file's last line may lack its line end."""
    return segment if segment.endswith("\n") else segment + "\n"
