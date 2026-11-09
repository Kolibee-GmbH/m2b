"""``memory/MEMORY.md``, the distillate: a facts section and a current section.

A facts line is ``- <statement> (<fact-file>.md)``. Lines are parsed, never matched as
substrings, so ``friend-alex.md`` does not count as indexing ``alex.md``. Facts before the first
``###`` heading of the facts section hold in every session. A topic is a group inside the facts
section, headed ``### <name> (<word>, <word>)``: its facts come into a session only when one of its
words is named, so what matters in one context stays out of the others. The words are the last
parenthesised group, so a name may hold parentheses. Only ``#`` and ``##`` start a section, so a
reader that knows nothing of topics reads their lines as facts and loses nothing. The current section
is a plain list of what is going on. An item may end in ``(since YYYY-MM-DD)``, the day it started
or was last confirmed, so a curation run can ask about one that went quiet; that suffix is read
apart from the item's text. One that is no date stays in the text and is reported.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field

FACTS_HEADING = "## Facts"
CURRENT_HEADING = "## Current"

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
    """A topic's heading and lines, exactly as they stand in the file."""

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


@dataclass
class MemoryIndex:
    facts: list[FactLine] = field(default_factory=list)
    current_lines: list[CurrentLine] = field(default_factory=list)
    unparsed_fact_lines: list[str] = field(default_factory=list)
    invalid_since: list[str] = field(default_factory=list)
    topics: list[Topic] = field(default_factory=list)
    # ``###`` headings in the facts section that are no topic; their facts hold everywhere.
    unparsed_topic_headings: list[str] = field(default_factory=list)
    # ``###`` headings under current, which has no topics.
    current_subheadings: list[str] = field(default_factory=list)

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
            elif _GROUP_HEADING.match(line) and section == FACTS_HEADING:
                topic = parse_topic_heading(line)
                if topic is not None:
                    index.topics.append(topic)
                else:
                    index.unparsed_topic_headings.append(line)
            elif _GROUP_HEADING.match(line) and section == CURRENT_HEADING:
                index.current_subheadings.append(line)
            elif line.startswith("- ") and section == CURRENT_HEADING:
                index.current_lines.append(_current_line(line, index.invalid_since))
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


def current_line_text(line: str) -> str:
    """A current line's item without its ``(since ...)``, as ``MemoryIndex.current`` holds it."""
    return _current_line(line, []).text


def _current_line(line: str, invalid: list[str]) -> CurrentLine:
    item = line[2:].strip()
    match = _SINCE.search(item)
    if match is None:
        return CurrentLine(item, None)
    if not is_day(match.group("since").strip()):
        invalid.append(line)
        return CurrentLine(item, None)
    return CurrentLine(item[: match.start()].rstrip(), match.group("since").strip())


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
    """Takes each topic block out of the facts section and leaves every other line as it is.

    What a session saw before topics existed (a title, other sections, lines the parser cannot
    read) stays in the general view; only parsed topics come out.
    """
    general: list[str] = []
    blocks: list[TopicBlock] = []
    section = ""
    block: list[str] | None = None
    topic: Topic | None = None
    for segment in re.split(r"(?<=\n)", text):
        line = segment.rstrip("\r\n")
        if block is not None and _BLOCK_END.match(line):
            assert topic is not None
            blocks.append(_block(topic, block))
            block = topic = None
        if is_section_heading(line):
            section = line.strip()
        heading = parse_topic_heading(line) if section == FACTS_HEADING and _GROUP_HEADING.match(line) else None
        if heading is not None:
            block, topic = [], heading
        if block is not None:
            block.append(segment)
        else:
            general.append(segment)
    if block is not None and topic is not None:
        blocks.append(_block(topic, block))
    return TopicSplit("".join(general), blocks)


def _block(topic: Topic, segments: list[str]) -> TopicBlock:
    """The blank lines that separate a block from the next heading are not part of it."""
    while segments and not segments[-1].strip():
        segments.pop()
    text = "".join(segments)
    return TopicBlock(topic, text if text.endswith("\n") else text + "\n")
