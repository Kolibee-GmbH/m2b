"""What the files a session loads say of a proposed lesson: wrongly, rightly, or nothing (B274).

A lesson is never a second statement beside a source that says the matter already. Before the
reading proposes one, a model reads the lessons with the files a session in their folders starts
with (``start_size.start_files``: the CLAUDE.md files, the rules, the output style, Claude Code's
auto memory), each line numbered, and says per lesson which line states it wrongly, which states it
rightly, or that none does. It is asked once, with nothing to call, and only when the reading
found a lesson.

Code keeps the verdict only where it holds: the file is one it was shown, the line one of that
file, and the line it names is taken from the file, never from the answer, so no fix replaces a
line that is not there. A fix is possible only for a file under ``~/.claude/`` or in a repository
whose remotes the session start noted (``fixes``): the places a session can apply it. What a
verdict makes of a lesson:

- a line that says it wrongly, or so that following it gave the error: a fix of that line, with
  the new wording, and no lesson text;
- a line that says it rightly: no text, a pointer to that line, for the count;
- nothing, for a knowledge lesson for one project: a fix that adds it to that project's
  ``CLAUDE.md``; for every project, or an action, the lesson itself.

A lesson whose verdict cannot be used is left out and counted: proposed without it, it might stand
beside a source that says the same.
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from m2b import claude_code, fixes, lessons, start_size
from m2b.glean import FIX, STATED, AtSource, Proposal
from m2b.notes.characters import can_be_written, unsafe_characters
from m2b.redaction import redact
from m2b.session_remotes import repository_top

INSTRUCTION = Path(__file__).with_name("lesson_sources_instruction.md")
WRONG = "wrong"
RIGHT = "right"
NONE = "none"
VERDICTS = (WRONG, RIGHT, NONE)
# What the model is shown of the sources at most: the start of a session, several times over.
MAX_SOURCE_CHARACTERS = 200_000
PROJECT_FILE = "CLAUDE.md"


class LessonSourcesError(Exception):
    """The model's answer could not be read; that is no verdict on any lesson."""


@dataclass(frozen=True)
class Source:
    """A file a session loads: its name as the person reads it, its lines, and where a fix of it is
    kept, None where no session could apply one."""

    shown: str
    lines: tuple[str, ...]
    fix_path: str | None
    repositories: tuple[str, ...]


@dataclass(frozen=True)
class Folder:
    """A session's folder with the addresses of its repository's remotes, as the session start noted them."""

    path: str
    addresses: tuple[str, ...]


def instruction() -> str:
    return INSTRUCTION.read_text(encoding="utf-8")


@dataclass(frozen=True)
class Found:
    """The sources, each once, and per folder the numbers (from 1) of those a session there loads."""

    sources: tuple[Source, ...]
    of_folder: Mapping[str, frozenset[int]]
    # The files a session loads that could not be shown, as the person reads their names, and the
    # folders they are loaded in: there, that no source states a lesson is not known.
    not_shown: tuple[str, ...] = ()
    incomplete: frozenset[str] = frozenset()

    def of(self, folders: Sequence[str]) -> frozenset[int]:
        return frozenset().union(*(self.of_folder.get(folder, frozenset()) for folder in folders))


def sources_for(folders: Sequence[Folder], environ: Mapping[str, str]) -> Found:
    """The files a session in any of the folders starts with, each once, as long as they fit."""
    home = environ.get("HOME")
    claude = claude_code.claude_folder(environ)
    claude_is_home = home is not None and claude == Path(home) / ".claude"
    found: dict[Path, Source] = {}
    numbers: dict[Path, int] = {}
    of_folder: dict[str, set[int]] = {}
    not_shown: dict[str, None] = {}
    incomplete: set[str] = set()
    room = MAX_SOURCE_CHARACTERS
    for folder in folders:
        top = repository_top(Path(folder.path))
        loaded = of_folder.setdefault(folder.path, set())
        for path in start_size.start_files(environ, Path(folder.path)):
            if path in found:
                loaded.add(numbers[path])
                continue
            try:
                text = start_size.as_loaded(
                    path, path.read_text(encoding="utf-8", errors="replace"), environ, Path(folder.path)
                )
            except OSError:
                text = None
            if text is None or len(text) > room:
                not_shown[start_size.shown_path(path, home)] = None
                incomplete.add(folder.path)
                continue
            room -= len(text)
            fix_path, repositories = _where_a_fix_is_kept(path, claude if claude_is_home else None, top, folder)
            found[path] = Source(start_size.shown_path(path, home), tuple(text.splitlines()), fix_path, repositories)
            numbers[path] = len(found)
            loaded.add(numbers[path])
    of = {folder: frozenset(each) for folder, each in of_folder.items()}
    return Found(tuple(found.values()), of, tuple(not_shown), frozenset(incomplete))


def _where_a_fix_is_kept(
    path: Path, claude: Path | None, top: Path | None, folder: Folder
) -> tuple[str | None, tuple[str, ...]]:
    if claude is not None and _below(path, claude):
        return fixes.HOME_PREFIX + path.relative_to(claude).as_posix(), ()
    if top is not None and folder.addresses and _below(path, top):
        return path.relative_to(top).as_posix(), folder.addresses
    return None, ()


def _below(path: Path, folder: Path) -> bool:
    try:
        path.relative_to(folder)
    except ValueError:
        return False
    return True


def step_input(found: Sequence[Proposal], sources: Sequence[Source], loaded: Sequence[frozenset[int]]) -> str:
    """The JSON document the model reads: the lessons by number, each with the numbers of the sources
    its sessions load, and the sources by number, lines numbered."""
    document = {
        "lessons": [
            {
                "lesson": number,
                "text": proposal.text,
                "said": [proposal.quote, proposal.lesson.quote] if proposal.lesson else [proposal.quote],
                "sources": sorted(sources_of),
            }
            for number, (proposal, sources_of) in enumerate(zip(found, loaded), start=1)
        ],
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


@dataclass(frozen=True)
class Verdicts:
    # The lessons as they are proposed, each with what its source says where one says it.
    kept: tuple[Proposal, ...]
    # How many lessons had no verdict that could be used.
    left_out: int


def apply(
    answer: str,
    found: Sequence[Proposal],
    sources: Sequence[Source],
    loaded: Sequence[frozenset[int]],
    complete: Sequence[bool] | None = None,
) -> Verdicts:
    """The lessons with what the answer says of their sources, where code finds it holds; a verdict
    may name only a source the lesson's own sessions load."""
    given = verdicts_of(answer)
    kept: list[Proposal] = []
    left_out = 0
    shown_whole = complete if complete is not None else [True] * len(found)
    for number, (proposal, sources_of, whole) in enumerate(zip(found, loaded, shown_whole), start=1):
        verdict = given.get(number)
        # Where a file its sessions load was not shown, that none states the lesson is not known.
        if verdict is not None and verdict.get("verdict") == NONE and not whole:
            verdict = None
        placed = None if verdict is None else _placed(proposal, verdict, sources, sources_of)
        if placed is None:
            left_out += 1
        else:
            kept.append(placed)
    return Verdicts(tuple(kept), left_out)


def verdicts_of(answer: str) -> dict[int, Mapping[str, Any]]:
    """The verdicts of the first JSON object in the answer that has a list of them, by lesson number."""
    decoder = json.JSONDecoder()
    for start in (match.start() for match in re.finditer(r"\{", answer)):
        try:
            found, _ = decoder.raw_decode(answer, start)
        except ValueError:
            continue
        if isinstance(found, dict) and isinstance(found.get("verdicts"), list):
            verdicts: dict[int, Mapping[str, Any]] = {}
            for entry in found["verdicts"]:
                number = entry.get("lesson") if isinstance(entry, dict) else None
                if isinstance(number, int) and not isinstance(number, bool) and number not in verdicts:
                    verdicts[number] = entry
            return verdicts
    raise LessonSourcesError("the answer holds no JSON object with a list of verdicts")


def _placed(
    proposal: Proposal, verdict: Mapping[str, Any], sources: Sequence[Source], sources_of: frozenset[int]
) -> Proposal | None:
    """The proposal with its source where the verdict holds; None where it cannot be used."""
    lesson = proposal.lesson
    assert lesson is not None
    said = verdict.get("verdict")
    if said == NONE:
        return _with_nothing_at_source(proposal)
    if said not in (WRONG, RIGHT):
        return None
    source, line = source_line(verdict, sources)
    if source is None or line is None or verdict.get("source") not in sources_of:
        return None
    if said == RIGHT:
        stated = AtSource(STATED, source.shown, line, None, source.fix_path, source.repositories)
        return dataclasses.replace(proposal, lesson=dataclasses.replace(lesson, at_source=stated))
    wording = verdict.get("wording")
    if source.fix_path is None or not isinstance(wording, str) or not _one_text(wording):
        return None
    fix = AtSource(FIX, source.shown, line, wording.strip(), source.fix_path, source.repositories)
    return dataclasses.replace(proposal, lesson=dataclasses.replace(lesson, at_source=fix)) if _keepable(fix) else None


def _with_nothing_at_source(proposal: Proposal) -> Proposal | None:
    """A lesson no source states: a knowledge lesson for one project becomes a fix that adds it to
    that project's CLAUDE.md, which every session there loads; any other stays the lesson."""
    lesson = proposal.lesson
    assert lesson is not None
    if lesson.kind != lessons.KNOWLEDGE or lesson.target == lessons.EVERY_PROJECT:
        return proposal
    added = AtSource(FIX, f"{PROJECT_FILE} in {lesson.target}", None, proposal.text, PROJECT_FILE, (lesson.target,))
    return (
        dataclasses.replace(proposal, lesson=dataclasses.replace(lesson, at_source=added)) if _keepable(added) else None
    )


def source_line(verdict: Mapping[str, Any], sources: Sequence[Source]) -> tuple[Source | None, str | None]:
    number, line = verdict.get("source"), verdict.get("line")
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in (number, line)):
        return None, None
    assert isinstance(number, int) and isinstance(line, int)
    if not 1 <= number <= len(sources):
        return None, None
    source = sources[number - 1]
    if not 1 <= line <= len(source.lines) or not source.lines[line - 1].strip():
        return None, None
    text = source.lines[line - 1].strip()
    # The model was shown the line redacted; one that holds a credential goes into no proposal,
    # which the store keeps, and no fix could name it as it stands.
    if redact(text) != text:
        return None, None
    return source, text


def _one_text(text: str) -> bool:
    return (
        bool(text.strip()) and len(text) <= fixes.MAX_WORDING and can_be_written(text) and not unsafe_characters(text)
    )


def _keepable(fix: AtSource) -> bool:
    """Whether ``fixes`` would keep it as given, so the person keeps nothing that waits for ever."""
    try:
        fixes.new_fix(
            fix.path or "", fix.repositories, "this machine", fix.line, fix.wording or "", "check", "2000-01-01"
        )
    except fixes.FixRefusedError:
        return False
    return True
