"""Measures how well a model files an inbox: what lands in memory and the task list, and where.

``tests/ingest/`` is an invented store (``given/``) and an invented inbox (``inbox.json``): twenty
captures of one day, in English and German, and for each what it should leave behind. Together
they are twenty things: facts about the owner and people, facts that belong under a topic, things
going on, tasks with a day and without. One capture holds nothing to file.

For each model the tool puts the store and the inbox into a sandbox of their own and starts a
real curation run there, ``m2b curate --force`` with its own ``M2B_HOME`` and ``curation.model``
set to that model, so the ingest skill, the fence and the commands are the ones an installation
runs. Then it reads the store with the core's own parsers and counts.

An expectation is found when a facts line, a current item or a task of its capture holds each of
its words; they are regular expressions, because a model words its lines its own way. A found one
is right when every detail the filing rules decide holds too: the line stands above the first
topic or under the named one, its fact file links the capture, a current item carries the
capture's day, a task its day or none, and a fact that changed no longer stands with its old
value, which its fact file keeps under ``## Earlier``. One line may hold two expected facts. A
fact that only its fact file states is missed, and the report says so: no session starts with it,
though a search finds it. A new
line, task or topic no expectation accounts for is extra and printed, a line or task with the
capture it came from; whether it is a good split or noise is the reader's call. One that names no
capture of the inbox is without a source, and a fact or a task from the capture that holds
nothing is named too; a current item names no capture, so one made of that capture is an extra
like any other.

The turn limit of a model step is raised for these runs: the default fits a day's inbox, and
twenty captures at once take more calls than that.

Every run asks the real model on your own Claude login, several minutes each, so this is not part
of ``scripts/check``: run it with ``scripts/ingest-eval``.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from m2b.config.machine import CURATION_MODELS, StoreLocation
from m2b.notes import frontmatter as keys
from m2b.notes import layout
from m2b.notes.frontmatter import Note
from m2b.notes.memory_index import CurrentLine, FactLine, MemoryIndex
from m2b.notes.names import NoteName
from m2b.paths import HOME_VARIABLE, MachinePaths, machine_paths
from m2b.store.factory import open_store
from m2b.tasks import markers
from m2b.tasks.base import Task
from m2b.tasks.markdown import MarkdownTasks

from repo_tools import REPO_ROOT
from repo_tools.e2e import (
    CORE_PLUGIN,
    MODEL,
    MODEL_RUNNER_VARIABLE,
    MODEL_STUB_STORE_VARIABLE,
    RUN_RECORD_PATH,
    TEST_RESOURCE_PREFIX,
    RealStoreError,
    isolated_machine_config,
    model_stub,
    refuse_real_store,
)

FIXTURE = REPO_ROOT / "tests" / "ingest"
DEFAULT_WORK_ROOT = Path(tempfile.gettempdir()) / f"{TEST_RESOURCE_PREFIX}m2b-ingest-eval"
DEFAULT_RUNS = 3
DEFAULT_JOBS = 3
# The share of the expectations a model has to get right, found and with every detail, before it
# is good enough to file an inbox. Chosen, not derived; the same bar as for proposals.
BAR = 0.8
# A day's inbox fits the default of a hundred turns; twenty captures at once do not.
MAX_TURNS = 400
MODEL_TIMEOUT_MINUTES = 20
# Longer than the run's own budget for its model steps, so the product's supervisor ends a slow
# run before this tool does.
RUN_TIMEOUT_SECONDS = 4 * MODEL_TIMEOUT_MINUTES * 60

FACT = "fact"
CURRENT = "current"
TASK = "task"
KINDS = (FACT, CURRENT, TASK)
# The captures are written as on a machine an hour east of UTC, so each one's day is the fixture's.
CAPTURE_OFFSET = datetime.timezone(datetime.timedelta(hours=1))

EXIT_PASSED = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_REFUSED = 2

_LINK = re.compile(r"\[\[([^\[\]]+)\]\]")
# A fact file's section of earlier values, up to its next section.
_EARLIER = re.compile(r"^## Earlier[ \t]*\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)


class FixtureError(Exception):
    """The invented inbox does not say what it should, so nothing counted from it would mean anything."""


@dataclass(frozen=True)
class Expectation:
    """One thing a capture should leave behind; ``what`` names it in the report."""

    capture: str
    what: str
    kind: str
    words: tuple[re.Pattern[str], ...]
    # For a fact or a current item: whether the filing rules decide its place, and then the name
    # of its topic, None for above the first topic.
    place_judged: bool = False
    topic: re.Pattern[str] | None = None
    # For a task: its day, None for none.
    due: datetime.date | None = None
    # For a fact that replaces another: the old value, which no facts line may hold any more, and
    # what its fact file keeps of it under ``## Earlier``.
    no_longer: re.Pattern[str] | None = None
    earlier: re.Pattern[str] | None = None

    def __str__(self) -> str:
        return f"{self.what} ({self.kind} from {self.capture})"


@dataclass(frozen=True)
class Capture:
    name: NoteName
    text: str
    follow_up: str | None
    expected: tuple[Expectation, ...]

    @property
    def file(self) -> str:
        return str(self.name)

    @property
    def created(self) -> datetime.datetime:
        return self.name.time.astimezone(CAPTURE_OFFSET)


@dataclass(frozen=True)
class Inbox:
    captures: tuple[Capture, ...]
    # The names of the topics a filing may start; any other new topic is extra.
    topics: tuple[re.Pattern[str], ...] = ()

    @property
    def expectations(self) -> tuple[Expectation, ...]:
        return tuple(expectation for capture in self.captures for expectation in capture.expected)


@dataclass(frozen=True)
class Filed:
    """What the count reads of a store."""

    facts: tuple[FactLine, ...]
    current: tuple[CurrentLine, ...]
    # Without the curator's own: its review and its questions are no filing.
    tasks: tuple[Task, ...]
    # The names of the topics, of either section.
    topics: frozenset[str]
    # Fact file name to its text, to the notes it links, and to what stands under its ``## Earlier``.
    fact_files: Mapping[str, str]
    links: Mapping[str, frozenset[str]]
    earlier: Mapping[str, str]
    waiting: frozenset[str]
    archived: frozenset[str]


@dataclass(frozen=True)
class Miss:
    expectation: Expectation
    # The fact file that states it and links its capture, when only the facts list lacks it.
    fact_file: str | None = None

    def __str__(self) -> str:
        where = f": {self.fact_file} holds it, no facts line does" if self.fact_file is not None else ""
        return f"{self.expectation}{where}"


@dataclass(frozen=True)
class Flaw:
    expectation: Expectation
    problems: tuple[str, ...]


@dataclass(frozen=True)
class Score:
    expected: int
    missed: tuple[Miss, ...]
    flawed: tuple[Flaw, ...]
    extra: tuple[str, ...]
    without_source: tuple[str, ...]
    from_nothing: tuple[str, ...]
    waiting: tuple[str, ...]
    gone: tuple[str, ...]

    @property
    def found(self) -> int:
        return self.expected - len(self.missed)

    @property
    def right(self) -> int:
        return self.found - len(self.flawed)

    @property
    def nothing_left_behind(self) -> bool:
        """Every capture is in the archive, no line or task lacks a source, and no fact or task
        came from the capture that holds nothing."""
        return not (self.without_source or self.from_nothing or self.waiting or self.gone)


@dataclass(frozen=True)
class Outcome:
    model: str
    seconds: float
    score: Score
    # What went wrong with the curation run itself: it could not start, it failed, a call was denied.
    problems: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not self.problems and self.score.nothing_left_behind


def load_inbox(path: Path) -> Inbox:
    raw = json.loads(path.read_text(encoding="utf-8"))
    captures = tuple(_capture(entry) for entry in raw["captures"])
    files = [capture.file for capture in captures]
    if len(set(files)) != len(files):
        raise FixtureError("two captures have one file name")
    return Inbox(captures, tuple(_pattern(name) for name in raw.get("topics", ())))


def _capture(entry: Mapping[str, Any]) -> Capture:
    name = NoteName.parse(entry["file"])
    if name is None:
        raise FixtureError(f"{entry['file']!r} is no name of a capture")
    expected = tuple(_expectation(entry["file"], item) for item in entry.get("expected", ()))
    return Capture(name, entry["text"], entry.get("follow_up"), expected)


def _expectation(file: str, raw: Mapping[str, Any]) -> Expectation:
    kind = raw["kind"]
    if kind not in KINDS:
        raise FixtureError(f"{file}: {raw['what']!r} is of the kind {kind!r}; known: {', '.join(KINDS)}")
    if not raw["words"]:
        raise FixtureError(f"{file}: {raw['what']!r} names no words")
    if (kind == TASK) != ("due" in raw) or (kind == TASK and "topic" in raw):
        raise FixtureError(f"{file}: {raw['what']!r}: a task says its due day, and only a task does")
    if kind != FACT and ("no_longer" in raw or "earlier" in raw):
        raise FixtureError(f"{file}: {raw['what']!r}: only a fact replaces an earlier value")
    topic, due, no_longer, earlier = raw.get("topic"), raw.get("due"), raw.get("no_longer"), raw.get("earlier")
    return Expectation(
        capture=file,
        what=raw["what"],
        kind=kind,
        words=tuple(_pattern(word) for word in raw["words"]),
        place_judged="topic" in raw,
        topic=_pattern(topic) if topic is not None else None,
        due=datetime.date.fromisoformat(due) if due is not None else None,
        no_longer=_pattern(no_longer) if no_longer is not None else None,
        earlier=_pattern(earlier) if earlier is not None else None,
    )


def _pattern(text: str) -> re.Pattern[str]:
    return re.compile(text, re.IGNORECASE)


def write_store(given: Path, inbox: Inbox, store: Path) -> None:
    """The store before the run: ``given`` with every capture of the inbox waiting."""
    shutil.copytree(given, store)
    folder = store / layout.INBOX
    folder.mkdir()
    for capture in inbox.captures:
        note = Note.new({}, capture.text + "\n")
        assert note.frontmatter is not None
        keys.set_created(note.frontmatter, capture.created)
        note.frontmatter.set(keys.SOURCE, capture.name.source)
        if capture.follow_up is not None:
            note.frontmatter.set(keys.FOLLOW_UP, capture.follow_up)
        (folder / capture.file).write_text(note.render(), encoding="utf-8")


def read_filed(store: Path, temp_dir: Path) -> Filed:
    memory = store / layout.MEMORY
    index_file = memory / layout.MEMORY_INDEX
    index = MemoryIndex.parse(_text(index_file) if index_file.is_file() else "")
    texts = {path.name: _text(path) for path in sorted(memory.glob("*.md")) if path.name != layout.MEMORY_INDEX}
    temp_dir.mkdir(parents=True, exist_ok=True)
    tasks = MarkdownTasks(open_store(StoreLocation("folder", store), temp_dir)).items(include_completed=True)
    return Filed(
        facts=tuple(index.facts),
        current=tuple(index.current_lines),
        tasks=tuple(task for task in tasks if task.marker not in markers.CURATOR),
        topics=frozenset(topic.name for topic in index.topics),
        fact_files=texts,
        links={name: frozenset(_LINK.findall(text)) for name, text in texts.items()},
        earlier={name: "".join(_EARLIER.findall(text)) for name, text in texts.items()},
        waiting=frozenset(_visible_names(store / layout.INBOX)),
        archived=frozenset(_visible_names(store / layout.CORPUS)),
    )


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _visible_names(folder: Path) -> list[str]:
    return [path.name for path in folder.rglob("*") if path.is_file() and not path.name.startswith(".")]


def score(inbox: Inbox, before: Filed, after: Filed) -> Score:
    """What a run made of the inbox: ``before`` is the store it started from, ``after`` what it left."""
    missed: list[Miss] = []
    flawed: list[Flaw] = []
    accounted: list[object] = []
    for capture in inbox.captures:
        for expectation in capture.expected:
            candidates = _candidates(expectation, capture, after)
            if not candidates:
                missed.append(Miss(expectation, _stating_fact_file(expectation, after)))
                continue
            item, problems = min(candidates, key=lambda candidate: len(candidate[1]))
            accounted.append(item)
            if problems:
                flawed.append(Flaw(expectation, tuple(problems)))
    files = {capture.file for capture in inbox.captures}
    extra, without_source = _unaccounted(before, after, accounted, files)
    started = sorted(after.topics - before.topics)
    extra += [f"topic {name!r}" for name in started if not any(topic.search(name) for topic in inbox.topics)]
    return Score(
        expected=len(inbox.expectations),
        missed=tuple(missed),
        flawed=tuple(flawed),
        extra=tuple(extra),
        without_source=tuple(without_source),
        from_nothing=tuple(_filed_from_nothing(inbox, after)),
        waiting=tuple(sorted(files & after.waiting)),
        gone=tuple(sorted(files - after.waiting - after.archived)),
    )


def _candidates(expectation: Expectation, capture: Capture, after: Filed) -> list[tuple[object, list[str]]]:
    """Each line or task that holds the expectation's words, with what is wrong about it."""

    def holds(text: str) -> bool:
        return all(word.search(text) for word in expectation.words)

    if expectation.kind == FACT:
        return [(line, _fact_problems(expectation, line, after)) for line in after.facts if holds(line.statement)]
    if expectation.kind == CURRENT:
        day = capture.created.date().isoformat()
        return [(item, _current_problems(expectation, item, day)) for item in after.current if holds(item.text)]
    of_capture = [task for task in after.tasks if _capture_of(task) == capture.file]
    return [(task, _task_problems(expectation, task)) for task in of_capture if holds(task.title)]


def _stating_fact_file(expectation: Expectation, after: Filed) -> str | None:
    """The fact file that holds a fact's words and links its capture, for one the facts list lacks."""
    if expectation.kind != FACT:
        return None
    for name, text in after.fact_files.items():
        if expectation.capture in after.links[name] and all(word.search(text) for word in expectation.words):
            return name
    return None


def _fact_problems(expectation: Expectation, line: FactLine, after: Filed) -> list[str]:
    problems = _place_problems(expectation, line.topic)
    if expectation.capture not in after.links.get(line.file_name, frozenset()):
        problems.append(f"{line.file_name} does not link the capture")
    old = expectation.no_longer
    if old is not None and any(old.search(other.statement) for other in after.facts):
        problems.append(f"a facts line still says {old.pattern!r}")
    kept = expectation.earlier
    if kept is not None and not kept.search(after.earlier.get(line.file_name, "")):
        problems.append(f"{line.file_name} keeps no earlier value like {kept.pattern!r}")
    return problems


def _current_problems(expectation: Expectation, item: CurrentLine, day: str) -> list[str]:
    problems = _place_problems(expectation, item.topic)
    if item.since != day:
        problems.append(f"dated {item.since or 'not at all'}, the capture is of {day}")
    return problems


def _place_problems(expectation: Expectation, topic: str | None) -> list[str]:
    if not expectation.place_judged:
        return []
    wanted = expectation.topic
    if (wanted is None and topic is None) or (wanted is not None and topic is not None and wanted.search(topic)):
        return []
    stands = f"under the topic {topic}" if topic is not None else "above the first topic"
    belongs = f"under a topic named like {wanted.pattern!r}" if wanted is not None else "above the first topic"
    return [f"stands {stands}, belongs {belongs}"]


def _task_problems(expectation: Expectation, task: Task) -> list[str]:
    due = task.due.date() if isinstance(task.due, datetime.datetime) else task.due
    if due == expectation.due:
        return []
    return [f"due {due or 'on no day'}, expected {expectation.due or 'no day'}"]


def _capture_of(task: Task) -> str | None:
    """The capture a task was made from, by its marker."""
    marker = markers.marker_of(task.notes)
    return marker[1][0] if marker is not None and marker[1] else None


def _unaccounted(
    before: Filed, after: Filed, accounted: Sequence[object], files: set[str]
) -> tuple[list[str], list[str]]:
    """What the run added that no expectation accounts for: with a capture of the inbox behind it, and without."""
    extra: list[str] = []
    without_source: list[str] = []

    def sort(what: str, sources: Sequence[str]) -> None:
        if sources:
            extra.append(f"{what}, from {', '.join(sources)}")
        else:
            without_source.append(what)

    # Each line that was there or is accounted for stands once; a second one like it is new.
    lines = Counter(before.facts) + Counter(line for line in set(accounted) if isinstance(line, FactLine))
    for line in after.facts:
        if lines[line]:
            lines[line] -= 1
            continue
        sources = sorted(after.links.get(line.file_name, frozenset()) & files)
        sort(f"facts line {line.statement!r} ({line.file_name})", sources)
    items = Counter(item.text for item in before.current)
    items += Counter(item.text for item in set(accounted) if isinstance(item, CurrentLine))
    for item in after.current:
        if items[item.text]:
            items[item.text] -= 1
            continue
        # A current item names no capture, so nothing says where it came from.
        extra.append(f"current item {item.text!r}")
    known_tasks = {task.id for task in before.tasks}
    for task in after.tasks:
        if task.id not in known_tasks and task not in accounted:
            source = _capture_of(task)
            sort(f"task {task.title!r}", [source] if source in files else [])
    return extra, without_source


def _filed_from_nothing(inbox: Inbox, after: Filed) -> list[str]:
    empty = [capture.file for capture in inbox.captures if not capture.expected]
    found = [f"{name} links {file}" for file in empty for name, links in sorted(after.links.items()) if file in links]
    return found + [
        f"task {task.title!r} from {file}" for file in empty for task in after.tasks if _capture_of(task) == file
    ]


@dataclass(frozen=True)
class Runner:
    """Where the curation runs start: the fixture, the folder for their sandboxes, the environment."""

    inbox: Inbox
    given: Path
    work_root: Path
    environ: Mapping[str, str]
    # For the tool's own tests: every model step replays this script in the scripted stand-in
    # for ``claude``, and no model is asked.
    script: Mapping[str, Any] | None = None

    def run(self, model: str, number: int) -> Outcome:
        """One curation run with ``model`` over the inbox, in a sandbox of its own, and its count."""
        sandbox = self.work_root / f"{model}-{number}"
        home, work, store = sandbox / "home", sandbox / "work", sandbox / "store"
        work.mkdir(parents=True)
        write_store(self.given, self.inbox, store)
        temp_dir = sandbox / "tmp"
        before = read_filed(store, temp_dir)
        held = score(self.inbox, before, before)
        if held.found:
            raise FixtureError(f"the store before the run already holds {held.found} of what the inbox should bring")

        config = isolated_machine_config(store, MODEL)
        config["curation"] = {"model": model, "model_timeout_minutes": MODEL_TIMEOUT_MINUTES, "max_turns": MAX_TURNS}
        config_file = MachinePaths(home).config_file
        config_file.parent.mkdir(parents=True)
        config_file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

        environment = dict(self.environ)
        environment[HOME_VARIABLE] = str(home)
        environment["M2B_CORE_ROOT"] = str(CORE_PLUGIN)
        environment["PATH"] = os.pathsep.join([str(CORE_PLUGIN / "bin"), self.environ.get("PATH", "")])
        environment.pop(MODEL_RUNNER_VARIABLE, None)
        environment.pop(MODEL_STUB_STORE_VARIABLE, None)
        if self.script is not None:
            environment[MODEL_RUNNER_VARIABLE] = str(model_stub(sandbox, self.script, CORE_PLUGIN))
            environment[MODEL_STUB_STORE_VARIABLE] = str(store)

        started = time.monotonic()
        problems = _curate(work, environment, store)
        seconds = time.monotonic() - started
        return Outcome(model, seconds, score(self.inbox, before, read_filed(store, temp_dir)), tuple(problems))


def _curate(work: Path, environment: Mapping[str, str], store: Path) -> list[str]:
    """Starts the curation run and waits for it; why it did not succeed, if it did not.

    The run record decides: a denied call fails its step, and a failed step of the core fails the run."""
    try:
        result = subprocess.run(
            ["m2b", "curate", "--force"],
            cwd=work,
            env=dict(environment),
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return [f"the curation run could not run to its end: {error}"]
    try:
        record = json.loads((store / RUN_RECORD_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        said = result.stderr.strip()[:400]
        return [f"the curation run ended with exit {result.returncode} and left no run record: {said}"]
    if record.get("state") != "succeeded":
        return [f"the curation run {record.get('state')}: {record.get('message')}"]
    return []


def evaluate(runner: Runner, models: Sequence[str], runs: int, jobs: int) -> list[Outcome]:
    numbered = [(model, number) for model in models for number in range(1, runs + 1)]
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        return list(pool.map(lambda pair: runner.run(*pair), numbered))


def report(outcomes: Sequence[Outcome]) -> bool:
    """Prints every run and a line per model; True when every model meets the bar in runs that left nothing behind."""
    passed = True
    for model in dict.fromkeys(outcome.model for outcome in outcomes):
        of_model = [outcome for outcome in outcomes if outcome.model == model]
        for number, outcome in enumerate(of_model, start=1):
            _report_run(f"{model} run {number}", outcome)
        # One division over the counts of all runs: a mean of ratios can land a hair below a bar it meets.
        expected = sum(outcome.score.expected for outcome in of_model)
        found = sum(outcome.score.found for outcome in of_model) / expected
        right = sum(outcome.score.right for outcome in of_model) / expected
        unclean = sum(1 for outcome in of_model if not outcome.clean)
        # Whatever is right was found, so the bar on what is right is the bar on both.
        met = right >= BAR and not unclean
        passed = passed and met
        print(
            f"ingest-eval: {model}: found {found:.2f}, right {right:.2f} over {len(of_model)} runs, "
            f"{unclean} of them failed or left something behind; "
            f"{'meets' if met else 'misses'} the bar of {BAR:.2f} with every run clean"
        )
    return passed


def _report_run(name: str, outcome: Outcome) -> None:
    result = outcome.score
    print(
        f"{name} ({outcome.seconds:.0f} s): found {result.found} of {result.expected}, right {result.right}, "
        f"{len(result.extra)} extra"
    )
    for problem in outcome.problems:
        print(f"  run: {problem}")
    for miss in result.missed:
        print(f"  missed: {miss}")
    for flaw in result.flawed:
        print(f"  flawed: {flaw.expectation}: {'; '.join(flaw.problems)}")
    for label, items in (
        ("extra", result.extra),
        ("without a source", result.without_source),
        ("filed from a capture that holds nothing", result.from_nothing),
        ("still in the inbox", result.waiting),
        ("in neither the inbox nor the archive", result.gone),
    ):
        for item in items:
            print(f"  {label}: {item}")


def prepare_work_root(work_root: Path, environ: Mapping[str, str]) -> None:
    """A fresh empty folder for the sandboxes of this call; the ones of the call before go."""
    # The whole folder is wiped, so the guard covers the whole folder.
    refuse_real_store(work_root, machine_paths(environ))
    shutil.rmtree(work_root, ignore_errors=True)
    work_root.mkdir(parents=True)


def _parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ingest-eval", description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--model",
        action="append",
        choices=CURATION_MODELS,
        help="curate with this model; repeatable (default: every one)",
    )
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS, help="curation runs per model")
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS, help="runs at the same time")
    parser.add_argument("--fixture", type=Path, default=FIXTURE, help=argparse.SUPPRESS)
    parser.add_argument("--work-root", type=Path, default=DEFAULT_WORK_ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--script", type=Path, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    arguments = _parse_arguments(sys.argv[1:] if argv is None else argv)
    environ = os.environ if environ is None else environ
    if arguments.runs < 1:
        print("ingest-eval: --runs takes a number from 1", file=sys.stderr)
        return EXIT_USAGE
    try:
        prepare_work_root(arguments.work_root, environ)
    except RealStoreError as error:
        print(f"ingest-eval: {error}", file=sys.stderr)
        return EXIT_REFUSED
    script = json.loads(arguments.script.read_text(encoding="utf-8")) if arguments.script is not None else None
    try:
        inbox = load_inbox(arguments.fixture / "inbox.json")
        runner = Runner(inbox, arguments.fixture / "given", arguments.work_root, environ, script)
        outcomes = evaluate(runner, arguments.model or CURATION_MODELS, arguments.runs, arguments.jobs)
    except FixtureError as error:
        print(f"ingest-eval: {error}", file=sys.stderr)
        return EXIT_USAGE
    passed = report(outcomes)
    print(f"ingest-eval: the stores of the runs are in {arguments.work_root} until the next call")
    return EXIT_PASSED if passed else EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
