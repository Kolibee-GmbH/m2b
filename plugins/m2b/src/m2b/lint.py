"""Lint, the deterministic half: findings about the store, and the two fixes that need no owner (B21).

``scan`` reads corpus, memory and the tasks and reports, never changes: names outside the schema,
notes without ``created`` or ``source``, a ``created`` without offset (tolerated, X5), notes in the
wrong month, refs and ``[[links]]`` that lead nowhere (B22), fact files no facts line points to
(lines are parsed, X13), an oversized or missing distillate, topic headings that would bring their
facts in too often or never (B48), incomplete bundles, the binary volume,
conflict copies, tasks whose capture is gone, and evicted files, which are listed and never read
(B6). The inbox is ingest's: what waits there is no finding (X12).

``fix`` removes what is safe to remove without asking: conflict copies in the corpus that equal
their original byte for byte (a looser match could delete a real note), and this product's own
hidden temp files older than a day (X22). A broken link in ``memory/`` is repaired by the lint
skill, from the candidates ``scan`` names; everything else is the owner's to decide.
"""

from __future__ import annotations

import datetime
import os
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from m2b.atomic_file import HIDDEN_TEMP_PREFIX
from m2b.curate.report import ACTION, INFO
from m2b.notes import frontmatter as keys
from m2b.notes.frontmatter import Note, NoteFormatError, read_created
from m2b.notes.layout import CORPUS, INBOX, MEMORY, MEMORY_INDEX, TASKS, is_journal_name
from m2b.notes.memory_index import MemoryIndex, Topic, is_day, split_topics
from m2b.notes.names import NoteName
from m2b.store.base import Store, StoreError, fetch_command
from m2b.tasks import markers
from m2b.tasks.base import Tasks, TasksError
from m2b.topic_match import MIN_WORD_CHARACTERS

__all__ = ["Finding", "LintReport", "TasksError", "fix", "scan"]

DISTILLATE_TARGET_BYTES = 2048
# A topic needs a few words to be found by, and few enough that each one means it.
TOPIC_WORDS = range(2, 6)
# A shorter word never matches, so the topic would never come in by it.
MIN_TOPIC_WORD = MIN_WORD_CHARACTERS
MAX_TOPIC_WORD = 40
MAX_TOPIC_NAME = 60
TEMP_FILE_MAX_AGE = datetime.timedelta(days=1)
NOTE_EXTENSION = ".md"
TEXT_EXTENSIONS = frozenset({".md", ".markdown", ".txt"})
EVICTED_EXAMPLES = 3

BROKEN_LINK = "broken-link"
_LINK = re.compile(r"\[\[([^\[\]\n]+)\]\]")
EARLIER_HEADING = "## Earlier"
# A value a fact had before a capture changed it: the old statement and the last day it held.
_EARLIER_LINE = re.compile(r"- .+ \(until (\d{4}-\d{2}-\d{2})\)")


@dataclass(frozen=True)
class Finding:
    code: str
    kind: str
    path: str
    text: str
    link: str | None = None
    candidates: tuple[str, ...] = ()


@dataclass
class LintReport:
    findings: list[Finding] = field(default_factory=list)

    def add(
        self, code: str, kind: str, path: str, text: str, link: str | None = None, candidates: tuple[str, ...] = ()
    ) -> None:
        self.findings.append(Finding(code, kind, path, text, link, candidates))


@dataclass
class _Corpus:
    files: list[str]
    evicted: list[str]
    names: set[str]

    def may_hold(self, name: str) -> bool:
        """Whether an evicted part of the corpus could hold this name, so a missing link is not proven."""
        parsed = NoteName.parse(name)
        if parsed is None:
            return False
        utc = parsed.time.astimezone(datetime.timezone.utc)
        expected = f"{CORPUS}/{utc:%Y}/{utc:%m}/{name}"
        return any(expected == entry or expected.startswith(entry + "/") for entry in self.evicted)


def scan(store: Store, tasks: Tasks | None = None) -> LintReport:
    report = LintReport()
    corpus_scan = store.scan(CORPUS)
    memory_scan = store.scan(MEMORY)
    corpus = _Corpus(corpus_scan.files, corpus_scan.evicted, {PurePosixPath(path).name for path in corpus_scan.files})
    for folder, evicted in ((CORPUS, corpus_scan.evicted), (MEMORY, memory_scan.evicted)):
        _evicted(report, folder, evicted)
    _corpus(store, report, corpus)
    _memory(store, report, memory_scan.files, memory_scan.evicted, corpus)
    if tasks is not None:
        _tasks(store, report, tasks, corpus)
    return report


def fix(store: Store, now: datetime.datetime | None = None) -> list[str]:
    """Removes identical conflict copies in the corpus and own temp files older than a day."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    removed = []
    for copy in store.conflict_copies(CORPUS):
        if copy.removable:
            store.delete(copy.path)
            removed.append(copy.path)
    cutoff = (now - TEMP_FILE_MAX_AGE).timestamp()
    for folder, _, names in os.walk(store.root):
        for name in names:
            path = Path(folder) / name
            if name.startswith(HIDDEN_TEMP_PREFIX) and os.lstat(path).st_mtime < cutoff:
                path.unlink()
                removed.append(path.relative_to(store.root).as_posix())
    return sorted(removed)


def _evicted(report: LintReport, folder: str, evicted: list[str]) -> None:
    if not evicted:
        return
    examples = ", ".join(evicted[:EVICTED_EXAMPLES]) + (", ..." if len(evicted) > EVICTED_EXAMPLES else "")
    noun = "file or folder" if len(evicted) == 1 else "files or folders"
    report.add(
        "evicted",
        INFO,
        folder,
        f"{len(evicted)} {noun} in {folder}/ not downloaded, not checked ({examples}); run: {fetch_command(folder)}",
    )


def _corpus(store: Store, report: LintReport, corpus: _Corpus) -> None:
    copies = {copy.path: copy for copy in store.conflict_copies(CORPUS)}
    stems: dict[str, set[str]] = {}
    # An evicted member or sidecar still completes its bundle; it is named under evicted.
    for relative in [*corpus.files, *corpus.evicted]:
        stems.setdefault(relative.rsplit(".", 1)[0], set()).add(relative)
    binaries: list[str] = []
    for relative in corpus.files:
        if relative in copies:
            continue
        name = PurePosixPath(relative).name
        if PurePosixPath(relative).suffix.lower() not in TEXT_EXTENSIONS:
            binaries.append(relative)
        if is_journal_name(name):
            continue
        if NoteName.parse(name) is None:
            report.add("name", ACTION, relative, f"{relative} is not named by the schema and cannot be linked")
            continue
        frontmatter = _read_note(store, report, relative) if name.endswith(NOTE_EXTENSION) else None
        if frontmatter is not None:
            _note(report, relative, frontmatter, corpus)
        _bundle(report, relative, frontmatter, stems)
    for path, copy in sorted(copies.items()):
        if copy.identical is True:
            report.add("conflict-copy", INFO, path, f"{path} equals {copy.original}; lint fix removes it")
        elif copy.identical is False:
            report.add("conflict-copy", ACTION, path, f"{path} differs from {copy.original}; keep one of them")
        else:
            report.add("conflict-copy", INFO, path, f"{path} or {copy.original} is not downloaded; not compared")
    if binaries:
        size = sum(os.lstat(store.path(relative)).st_size for relative in binaries)
        report.add("binary-volume", INFO, CORPUS, f"{len(binaries)} binary files, {size / 1024:.1f} KB in {CORPUS}/")


def _read_note(store: Store, report: LintReport, relative: str) -> keys.Frontmatter | None:
    """The note's frontmatter, read once per scan; a note that cannot serve as one is a finding."""
    try:
        frontmatter = Note.parse(store.read_text(relative)).frontmatter
        created = read_created(frontmatter) if frontmatter is not None else None
        if frontmatter is not None:
            frontmatter.get_list(keys.REFS)
    except (UnicodeDecodeError, NoteFormatError, StoreError, ValueError) as error:
        report.add("frontmatter", ACTION, relative, f"{relative} cannot be read as a note: {error}")
        return None
    if frontmatter is None or created is None or not frontmatter.get(keys.SOURCE):
        report.add("frontmatter", ACTION, relative, f"{relative} lacks a frontmatter with created and source")
        return None
    return frontmatter


def _note(report: LintReport, relative: str, frontmatter: keys.Frontmatter, corpus: _Corpus) -> None:
    created = read_created(frontmatter)
    assert created is not None
    if not created.has_offset:
        report.add("created-offset", INFO, relative, f"{relative} has a created time without offset")
    utc = (created.value if created.has_offset else created.value.astimezone()).astimezone(datetime.timezone.utc)
    if not relative.startswith(f"{CORPUS}/{utc:%Y}/{utc:%m}/"):
        report.add("month", ACTION, relative, f"{relative} belongs in {CORPUS}/{utc:%Y}/{utc:%m}/ by its created time")
    missing = [
        ref
        for ref in frontmatter.get_list(keys.REFS)
        if "://" not in ref and ref not in corpus.names and not corpus.may_hold(ref)
    ]
    if missing:
        report.add(
            "broken-ref", ACTION, relative, f"{relative} refers to {', '.join(missing)}, which is no corpus file"
        )


def _bundle(
    report: LintReport, relative: str, frontmatter: keys.Frontmatter | None, stems: dict[str, set[str]]
) -> None:
    stem = relative.rsplit(".", 1)[0]
    siblings = stems[stem] - {relative}
    if relative.endswith(NOTE_EXTENSION):
        if frontmatter is not None and frontmatter.get(keys.KIND) == keys.KIND_SIDECAR and not siblings:
            report.add("orphaned-sidecar", ACTION, relative, f"{relative} describes a file that is not next to it")
    elif f"{stem}{NOTE_EXTENSION}" not in siblings:
        report.add("orphaned-member", ACTION, relative, f"{relative} has no sidecar note next to it")


def _memory(store: Store, report: LintReport, files: list[str], evicted: list[str], corpus: _Corpus) -> None:
    index_path = f"{MEMORY}/{MEMORY_INDEX}"
    fact_files = [
        relative
        for relative in [*files, *evicted]
        if PurePosixPath(relative).parent.as_posix() == MEMORY
        and relative.endswith(NOTE_EXTENSION)
        and relative != index_path
    ]
    if not any(index_path == entry or index_path.startswith(entry + "/") for entry in evicted):
        _index(store, report, index_path, files, fact_files)
    for relative in files:
        if relative.endswith(NOTE_EXTENSION):
            text = _links(store, report, relative, corpus)
            if text is not None and relative in fact_files:
                _until(report, relative, text)
                _earlier(report, relative, text)


def _index(store: Store, report: LintReport, index_path: str, files: list[str], fact_files: list[str]) -> None:
    if index_path not in files:
        report.add("no-distillate", ACTION, index_path, f"{index_path} is missing; every session starts without it")
    else:
        text = store.read_bytes(index_path).decode("utf-8", errors="replace")
        _sizes(report, index_path, text)
        index = MemoryIndex.parse(text)
        for heading in index.unparsed_topic_headings:
            report.add(
                "topic-heading", ACTION, index_path, f"a heading is no topic '### <name> (<word>, <word>)': {heading}"
            )
        for heading in index.current_subheadings:
            report.add(
                "topic-heading",
                ACTION,
                index_path,
                f"topics belong under ## Facts; one under ## Current is ignored: {heading}",
            )
        for topic in index.topics:
            problem = _topic_problem(topic)
            if problem is not None:
                report.add("topic-words", ACTION, index_path, f"the topic {topic.name} {problem}")
        names = {PurePosixPath(relative).name for relative in fact_files}
        for fact in index.facts:
            if fact.file_name not in names:
                report.add(
                    "missing-fact-file", ACTION, index_path, f"the facts line for {fact.file_name} has no fact file"
                )
        for line in index.unparsed_fact_lines:
            report.add("index-line", ACTION, index_path, f"a facts line is not '- <statement> (<file>.md)': {line}")
        for line in index.invalid_since:
            report.add("invalid-since", ACTION, index_path, f"a current item's since is no YYYY-MM-DD day: {line}")
        indexed = index.indexed_files()
        for relative in fact_files:
            if PurePosixPath(relative).name not in indexed:
                report.add("unindexed-fact", ACTION, relative, f"{relative} has no facts line in {index_path}")


def _sizes(report: LintReport, index_path: str, text: str) -> None:
    """Each view against the target: what every session starts with, and each topic on its own."""
    split = split_topics(text)
    start = len((split.general + ", ".join(block.topic.name for block in split.blocks)).encode("utf-8"))
    views = [("the part every session starts with", start)]
    views += [(f"the topic {block.topic.name}", len(block.text.encode("utf-8"))) for block in split.blocks]
    for view, size in views:
        if size > DISTILLATE_TARGET_BYTES:
            report.add(
                "distillate-size", INFO, index_path, f"in {index_path}, {view} is {size} bytes, over its 2 KB target"
            )


def _topic_problem(topic: Topic) -> str | None:
    if len(topic.name) > MAX_TOPIC_NAME:
        return f"has a name over {MAX_TOPIC_NAME} characters"
    if len(topic.words) not in TOPIC_WORDS:
        return f"has {len(topic.words)} words; it needs {TOPIC_WORDS.start} to {TOPIC_WORDS.stop - 1}"
    for word in topic.words:
        if not MIN_TOPIC_WORD <= len(word) <= MAX_TOPIC_WORD:
            return f"has the word {word!r}; a word has {MIN_TOPIC_WORD} to {MAX_TOPIC_WORD} characters"
    return None


def _until(report: LintReport, relative: str, text: str) -> None:
    """A fact file's ``until`` must be a day, or the fact never expires and stays in every session."""
    try:
        frontmatter = Note.parse(text).frontmatter
    except NoteFormatError:
        return
    until = frontmatter.get(keys.UNTIL) if frontmatter is not None else None
    if until is not None and not is_day(str(until)):
        report.add("invalid-until", ACTION, relative, f"{relative} has until: {until}, which is no YYYY-MM-DD day")


def _earlier(report: LintReport, relative: str, text: str) -> None:
    """Each line under ``## Earlier`` is ``- <old statement> (until YYYY-MM-DD)``, the day it last held."""
    lines = [line.rstrip() for line in text.split("\n")]
    if EARLIER_HEADING not in lines:
        return
    for line in lines[lines.index(EARLIER_HEADING) + 1 :]:
        if line.startswith("#"):
            break
        match = _EARLIER_LINE.fullmatch(line.strip()) if line.strip() else None
        if line.strip() and (match is None or not is_day(match.group(1))):
            report.add(
                "invalid-earlier",
                ACTION,
                relative,
                f"{relative} has an earlier value that is not '- <statement> (until YYYY-MM-DD)': {line.strip()}",
            )
            return


def _links(store: Store, report: LintReport, relative: str, corpus: _Corpus) -> str | None:
    """Reports the links that lead nowhere and hands back the text, or None when it cannot be read."""
    try:
        text = store.read_text(relative)
    except (UnicodeDecodeError, StoreError) as error:
        report.add("unreadable", ACTION, relative, f"{relative} cannot be read: {error}")
        return None
    for link in _LINK.findall(text):
        target = link.strip()
        if "/" not in target and "." in target and (target in corpus.names or corpus.may_hold(target)):
            continue
        base = target.rsplit("/", 1)[-1]
        candidates = tuple(sorted(name for name in corpus.names if base in (name, name.rsplit(".", 1)[0])))
        report.add(
            BROKEN_LINK,
            ACTION,
            relative,
            f"{relative} links [[{target}]], which is no corpus file",
            link=target,
            candidates=candidates,
        )
    return text


def _tasks(store: Store, report: LintReport, tasks: Tasks, corpus: _Corpus) -> None:
    try:
        # Only a backend that keeps tasks as files has any; a tasks/ folder left from before a switch
        # to another backend is no one's.
        for path, problem in tasks.unreadable():
            report.add("task-file", ACTION, path, f"{problem}; the task is left out until the file is fixed")
    except TasksError as error:
        report.add("tasks-unreadable", INFO, TASKS, f"the tasks could not be read, so not checked: {error}")
        return
    try:
        items = tasks.items(marker=markers.CAPTURE, include_completed=False)
    except (TasksError, NoteFormatError) as error:
        report.add("tasks-unreadable", INFO, TASKS, f"the tasks could not be read, so not checked: {error}")
        return
    for task in items:
        marker = markers.marker_of(task.notes)
        if marker is None or not marker[1]:
            continue
        name = marker[1][0]
        if name in corpus.names or corpus.may_hold(name) or store.exists(f"{INBOX}/{name}"):
            continue
        report.add("task-without-capture", INFO, TASKS, f"the task {task.title!r} points to {name}, which is gone")
