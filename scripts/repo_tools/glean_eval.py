"""Measures what a model proposes for the memory from a day of typed prompts.

``tests/glean/day.json`` is an invented day: sessions with what the person typed, some of it
planted (a person, an agreement, a commitment, something personal) and some of it a trap, one of
each class a proposal must never come from. The day is written as transcripts in Claude Code's
format, read back with ``m2b.sessions`` and handed to the model the way the curation step hands
it over: with the step's own instruction (``m2b.glean.instruction``), through the core's run
without tools (``m2b.curate.model``). The answer goes through ``m2b.glean``, the step's parser
and checks. So the tool measures the form the product runs, with nothing of its own in between.

The day also says what the person answered before: proposals of earlier readings they kept, like
what is planted, and some they dropped, all of one sort (the time of a call or a meeting). The
model is shown them as the step shows them (``answered`` in its input), and one trap of the day
is a sentence like the dropped ones. ``--without-examples`` asks without them, which shows what
they change: that trap is then nobody's to catch.

Counted per run: how many planted statements a kept proposal stands on (found), how many kept
proposals are the first to stand on one (right; a second proposal for the same statement is not),
and which traps were sprung. A proposal stands on a statement when its quote and the statement
share at least half of the shorter one in a prompt of the statement's session. Two traps are the
reader's to catch, a pasted mail and a prompt a plugin sent: they are sprung when their words
reach the model at all. One is the code's, a sentence the person captured themselves. The others
are the model's.

With ``--replay`` the tool reads your own last days from Claude Code's transcripts instead and
writes what the model proposes, with each quote, to the file you name. It prints counts only,
and it gives the model neither your memory nor your captures, so known facts come up again.

Every run needs your own Claude login and the real model, so this is not part of
``scripts/check``: run it with ``scripts/glean-eval``.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import sys
import tempfile
import uuid
from collections import Counter
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from m2b import claude_code, glean
from m2b.config.machine import CURATION_MODELS, DEFAULT_CURATION_MODEL
from m2b.curate import model as model_run
from m2b.paths import HOME_VARIABLE, machine_paths
from m2b.sessions import Session, Sessions, SessionsError, read_sessions

from repo_tools import REPO_ROOT
from repo_tools.e2e import TEST_RESOURCE_PREFIX, RealStoreError, refuse_real_store

DAY = REPO_ROOT / "tests" / "glean" / "day.json"
DEFAULT_WORK_ROOT = Path(tempfile.gettempdir()) / f"{TEST_RESOURCE_PREFIX}m2b-glean-eval"
DEFAULT_RUNS = 3
DEFAULT_JOBS = 3
RUN_TIMEOUT_SECONDS = 300
# What a model has to reach before a step may propose with it: of the planted statements found,
# and of its proposals right. Chosen, not derived.
BAR = 0.8

PASTED_MAIL = "pasted-mail"
AUTOMATION = "automation"
# A sentence the instruction alone would allow and the person's earlier drops speak against.
LIKE_DROPPED = "like-dropped"
TRAPS = ("hypothetical", "test-data", "project-todo", "in-memory", LIKE_DROPPED, "captured", PASTED_MAIL, AUTOMATION)
# Their words must not be among the prompts the reader gives; no model is asked to resist them.
TRAPS_OF_THE_READER = (PASTED_MAIL, AUTOMATION)

EXIT_PASSED = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_REFUSED = 2

_UTC = datetime.timezone.utc
_SESSION_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "m2b/tests/glean")


class FixtureError(Exception):
    """The invented day does not say what it should, so nothing counted from it would mean anything."""


@dataclass(frozen=True)
class Statement:
    """Words of one prompt that are planted or a trap; ``label`` is the kind or the trap's class."""

    session: str
    label: str
    text: str


@dataclass(frozen=True)
class Day:
    start: datetime.datetime
    memory: str
    captures: tuple[str, ...]
    # What the person kept and dropped of earlier proposals.
    examples: glean.Examples
    # Session id to the records of its transcript, and to the name the fixture gives it.
    transcripts: Mapping[str, Sequence[Mapping[str, Any]]]
    names: Mapping[str, str]
    planted: tuple[Statement, ...]
    traps: tuple[Statement, ...]


@dataclass(frozen=True)
class Case:
    """The day as the reader gives it: what every run of the eval is asked and scored against."""

    day: Day
    sessions: tuple[Session, ...]
    step_input: str


@dataclass(frozen=True)
class Score:
    proposals: int
    malformed: int
    not_quoted: int
    already_captured: int
    kept: int
    right: int
    right_kind: int
    missed: tuple[Statement, ...]
    wrong: tuple[glean.Proposal, ...]
    sprung: tuple[str, ...]
    planted: int

    @property
    def found(self) -> int:
        return self.planted - len(self.missed)

    @property
    def recall(self) -> float:
        return self.found / self.planted

    @property
    def precision(self) -> float:
        return self.right / self.kept if self.kept else 0.0


@dataclass(frozen=True)
class Outcome:
    model: str
    run: model_run.TextRun
    # None when the run gave no answer that could be read; ``problem`` says why.
    score: Score | None
    problem: str | None


def load_day(path: Path) -> Day:
    raw = json.loads(path.read_text(encoding="utf-8"))
    start = datetime.datetime.fromisoformat(raw["day"]).replace(tzinfo=_UTC)
    transcripts: dict[str, list[dict[str, Any]]] = {}
    names: dict[str, str] = {}
    planted: list[Statement] = []
    traps: list[Statement] = []
    for session in raw["sessions"]:
        session_id = str(uuid.uuid5(_SESSION_NAMESPACE, session["name"]))
        if session_id in names:
            raise FixtureError(f"two sessions are named {session['name']}")
        names[session_id] = session["name"]
        hour, minute = (int(part) for part in session["starts"].split(":"))
        first = start.replace(hour=hour, minute=minute)
        transcripts[session_id] = []
        for index, prompt in enumerate(session["prompts"]):
            entry = {"text": prompt} if isinstance(prompt, str) else prompt
            moment = first + datetime.timedelta(minutes=4 * index)
            transcripts[session_id].append(_record(entry, session["folder"], moment, index))
            for label, into in ((entry.get("planted"), planted), (entry.get("trap"), traps)):
                if label is not None:
                    _must_hold(entry, session["name"])
                    into.append(Statement(session_id, label, entry["statement"]))
    memory = "\n".join(raw["memory"]) + "\n"
    examples = _examples(raw.get("answered", {}))
    return Day(start, memory, tuple(raw["captures"]), examples, transcripts, names, tuple(planted), tuple(traps))


def _examples(answered: Mapping[str, Any]) -> glean.Examples:
    def of(answer: str) -> tuple[glean.Example, ...]:
        return tuple(glean.Example(each["kind"], each["text"], each["quote"]) for each in answered.get(answer, ()))

    return glean.Examples(of("kept"), of("dropped"))


def _must_hold(entry: Mapping[str, Any], session_name: str) -> None:
    statement = entry.get("statement")
    if not statement or statement not in entry["text"] + entry.get("pasted", ""):
        raise FixtureError(f"a prompt in {session_name} does not hold its statement: {statement!r}")


def _record(entry: Mapping[str, Any], folder: str, moment: datetime.datetime, index: int) -> dict[str, Any]:
    """A user record as Claude Code writes one: typed by the person, or sent by ``sent_by``."""
    text = entry["text"]
    if "pasted" in entry:
        mark = f' id="paste-{index}"'
        text = f"{text}\n<pasted_content{mark}>{entry['pasted']}</pasted_content{mark}>"
    sender = entry.get("sent_by")
    return {
        "type": "user",
        "timestamp": moment.isoformat().replace("+00:00", "Z"),
        "cwd": folder,
        "entrypoint": "cli",
        "promptSource": "system" if sender else "typed",
        "origin": {"kind": sender or "human"},
        "message": {"role": "user", "content": text},
    }


def build_case(day: Day, projects: Path, with_examples: bool = True) -> Case:
    """Writes the day as transcripts under ``projects`` and reads it back as a curation step would."""
    for session_id, records in day.transcripts.items():
        folder = projects / str(records[0]["cwd"]).replace("/", "-")
        folder.mkdir(parents=True, exist_ok=True)
        lines = "".join(json.dumps(record) + "\n" for record in records)
        (folder / f"{session_id}.jsonl").write_text(lines, encoding="utf-8")
    read = read_sessions(projects, day.start, day.start + datetime.timedelta(days=1))
    if read.unreadable:
        raise FixtureError(f"the reader could not read {', '.join(read.unreadable)}")
    typed = _typed(read.sessions)
    for statement in day.planted:
        holding = [prompt for prompt in typed.get(statement.session, ()) if statement.text in prompt]
        if len(holding) != 1:
            raise FixtureError(f"{statement.text!r} stands in {len(holding)} prompts the reader gives, not in one")
    for example in (*day.examples.kept, *day.examples.dropped):
        # Such a proposal would pass the quote check, and nothing counted could tell it from a find.
        if any(example.quote in prompt for prompts in typed.values() for prompt in prompts):
            raise FixtureError(f"the example {example.quote!r} is typed in the day; an example is from before it")
    examples = day.examples if with_examples else glean.NO_EXAMPLES
    return Case(day, read.sessions, glean.step_input(read.sessions, day.memory, examples=examples))


def score(case: Case, answer: str) -> Score:
    """Counts the answer against the day; a ``glean.GleanError`` when the answer cannot be read."""
    read = glean.parse_answer(answer, case.sessions)
    checked = glean.check(read.proposals, case.sessions, case.day.captures)
    typed = _typed(case.sessions)
    first: dict[Statement, glean.Proposal] = {}
    wrong: list[glean.Proposal] = []
    for proposal in checked.kept:
        new = [item for item in case.day.planted if item not in first and _stands_on(proposal, item, typed)]
        first.update((item, proposal) for item in new)
        if not new:
            wrong.append(proposal)
    sprung = [trap.label for trap in case.day.traps if _sprung(trap, checked.kept, typed)]
    return Score(
        proposals=len(read.proposals),
        malformed=read.malformed,
        not_quoted=len(checked.not_quoted),
        already_captured=len(checked.already_captured),
        kept=len(checked.kept),
        right=len(checked.kept) - len(wrong),
        right_kind=sum(item.label == proposal.kind for item, proposal in first.items()),
        missed=tuple(item for item in case.day.planted if item not in first),
        wrong=tuple(wrong),
        sprung=tuple(sprung),
        planted=len(case.day.planted),
    )


def _typed(sessions: Sequence[Session]) -> dict[str, list[str]]:
    return {session.session_id: [prompt.text for prompt in session.prompts] for session in sessions}


def _stands_on(proposal: glean.Proposal, statement: Statement, typed: Mapping[str, Sequence[str]]) -> bool:
    """Whether the quote and the statement share at least half of the shorter one in one prompt."""
    if proposal.session != statement.session:
        return False
    quote = " ".join(proposal.quote.split())
    for prompt in typed.get(statement.session, ()):
        stated = prompt.find(statement.text)
        quoted = prompt.find(quote) if stated >= 0 else -1
        while quoted >= 0:
            shared = min(stated + len(statement.text), quoted + len(quote)) - max(stated, quoted)
            if 2 * shared >= min(len(statement.text), len(quote)):
                return True
            quoted = prompt.find(quote, quoted + 1)
    return False


def _sprung(trap: Statement, kept: Sequence[glean.Proposal], typed: Mapping[str, Sequence[str]]) -> bool:
    if trap.label in TRAPS_OF_THE_READER:
        return any(trap.text in prompt for prompt in typed.get(trap.session, ()))
    return any(_stands_on(proposal, trap, typed) for proposal in kept)


def prepare_sandbox(work_root: Path, environ: Mapping[str, str]) -> tuple[Path, Path, dict[str, str]]:
    """A fresh empty working folder, a folder for transcripts and the runs' environment."""
    # The whole folder is wiped, so the guard covers the whole folder.
    refuse_real_store(work_root, machine_paths(environ))
    shutil.rmtree(work_root, ignore_errors=True)
    work, projects = work_root / "work", work_root / "projects"
    work.mkdir(parents=True)
    projects.mkdir()
    environment = dict(environ)
    # No plugin is loaded; should one run all the same, it finds no config and no store here.
    environment[HOME_VARIABLE] = str(work_root / "home")
    return work, projects, environment


@dataclass(frozen=True)
class Asker:
    """How a model is asked: the step's instruction, the core's run without tools and where it runs."""

    instruction: str
    claude: str
    work: Path
    environment: Mapping[str, str]

    def ask(self, model: str, step_input: str) -> model_run.TextRun:
        command = model_run.text_command(self.claude, self.instruction, model)
        try:
            return model_run.run_text(command, step_input, self.work, self.environment, RUN_TIMEOUT_SECONDS)
        except model_run.ModelUnreachableError as error:
            return model_run.TextRun(None, None, "the command could not be started", str(error), 0.0)


def evaluate(case: Case, models: Sequence[str], runs: int, asker: Asker, jobs: int) -> list[Outcome]:
    def one(model: str) -> Outcome:
        run = asker.ask(model, case.step_input)
        if run.answer is None:
            return Outcome(model, run, None, run.failure())
        try:
            return Outcome(model, run, score(case, run.answer), None)
        except glean.GleanError as error:
            return Outcome(model, run, None, str(error))

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        return list(pool.map(one, [model for model in models for _ in range(runs)]))


def report(case: Case, outcomes: Sequence[Outcome]) -> bool:
    """Prints every run and a line per model; True when every model meets the bar and springs no trap."""
    passed = True
    for model in dict.fromkeys(outcome.model for outcome in outcomes):
        of_model = [outcome for outcome in outcomes if outcome.model == model]
        for number, outcome in enumerate(of_model, start=1):
            _report_run(case, f"{model} run {number}", outcome)
        scores = [outcome.score for outcome in of_model if outcome.score is not None]
        if len(scores) < len(of_model):
            print(f"glean-eval: {model}: {len(of_model) - len(scores)} of {len(of_model)} runs gave no answer")
            passed = False
            continue
        recall = sum(each.recall for each in scores) / len(scores)
        precision = sum(each.precision for each in scores) / len(scores)
        sprung = Counter(label for each in scores for label in each.sprung)
        traps = ", ".join(f"{label} in {count}" for label, count in sprung.items()) or "none"
        met = recall >= BAR and precision >= BAR and not sprung
        passed = passed and met
        print(
            f"glean-eval: {model}: found {recall:.2f}, right {precision:.2f} over {len(scores)} runs, "
            f"traps sprung: {traps}; {'meets' if met else 'misses'} the bar of {BAR:.2f} and no trap"
        )
    return passed


def _report_run(case: Case, name: str, outcome: Outcome) -> None:
    result = outcome.score
    if result is None:
        print(f"{name}: error: {outcome.problem}")
        return
    names = case.day.names
    print(
        f"{name} ({outcome.run.model}, {outcome.run.seconds:.0f} s): found {result.found} of {result.planted}, "
        f"right {result.right} of {result.kept} proposals, kind right {result.right_kind} of {result.found}; "
        f"left out by code: {result.not_quoted} not quoted, {result.already_captured} already captured, "
        f"{result.malformed} not in the form"
    )
    for item in result.missed:
        print(f"  missed {item.label} in {names[item.session]}: {item.text!r}")
    for proposal in result.wrong:
        print(f"  wrong {proposal.kind} in {names[proposal.session]}: {proposal.quote!r}")
    for label in result.sprung:
        print(f"  trap sprung: {label}")


@dataclass(frozen=True)
class ReplayDay:
    day: datetime.date
    read: Sessions
    # None for a day without a prompt, when no model was asked.
    run: model_run.TextRun | None = None
    answer: glean.Answer | None = None
    checked: glean.Checked | None = None
    problem: str | None = None

    @property
    def prompts(self) -> int:
        return sum(len(session.prompts) for session in self.read.sessions)

    def line(self) -> str:
        """The day in counts; no word of a prompt, a proposal or the model."""
        if not self.prompts:
            return f"{self.day}: no prompts"
        left_out = [session.left_out for session in self.read.sessions]
        read = (
            f"{self.day}: {self.prompts} prompts in {len(self.read.sessions)} sessions "
            f"(left out: {sum(each.pasted_blocks for each in left_out)} pasted blocks, "
            f"{sum(each.sent_by_others for each in left_out)} sent by others, "
            f"{sum(each.suggested for each in left_out)} suggested, "
            f"{sum(each.unmarked for each in left_out)} unmarked, "
            f"{len(self.read.unreadable)} transcripts not read)"
        )
        if self.answer is None or self.checked is None:
            return f"{read}, no answer: {self.problem}"
        kinds = Counter(proposal.kind for proposal in self.checked.kept)
        by_kind = ", ".join(f"{kinds[kind]} {kind}" for kind in glean.KINDS)
        return (
            f"{read}, {len(self.checked.kept)} proposals: {by_kind}; left out by code: "
            f"{len(self.checked.not_quoted)} not quoted, {self.answer.malformed} not in the form"
        )


def replay(transcripts: Path, days: Sequence[datetime.date], model: str, asker: Asker, jobs: int) -> list[ReplayDay]:
    """Asks the model once for every day that has prompts, with no memory and no captures."""

    def one(day: datetime.date) -> ReplayDay:
        # A naive time is read as local time, with the offset that day has.
        start = datetime.datetime.combine(day, datetime.time.min).astimezone()
        end = datetime.datetime.combine(day + datetime.timedelta(days=1), datetime.time.min).astimezone()
        read = read_sessions(transcripts, start, end)
        if not any(session.prompts for session in read.sessions):
            return ReplayDay(day, read)
        run = asker.ask(model, glean.step_input(read.sessions, "", start.tzinfo or _UTC))
        if run.answer is None:
            # Without what the command said: that goes into the file, not onto the terminal.
            return ReplayDay(day, read, run, problem=f"{run.error}{run.advice}")
        try:
            answer = glean.parse_answer(run.answer, read.sessions)
        except glean.GleanError as error:
            return ReplayDay(day, read, run, problem=str(error))
        return ReplayDay(day, read, run, answer, glean.check(answer.proposals, read.sessions, ()))

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        return list(pool.map(one, days))


def replay_page(replayed: Sequence[ReplayDay], model: str) -> str:
    """The proposals in their words, for the person whose days these are and nobody else."""
    lines = [
        "# What m2b would propose from your sessions",
        "",
        f"Written by `scripts/glean-eval --replay`, asked of `{model}`, one answer per day. The model",
        "got what you typed and nothing else: not your memory and not your captures. So it also",
        "proposes what your second brain knows already and what you captured yourself. Each proposal",
        "is shown with the words it stands on; a proposal whose quote is not in your prompts is not",
        "shown, only counted.",
    ]
    for day in replayed:
        lines += ["", f"## {day.day:%A} {day.day}", "", day.line()]
        if day.run is not None and day.problem is not None and day.run.detail:
            lines += ["", f"The command said: {day.run.detail}"]
        folders = {session.session_id: session.folder for session in day.read.sessions}
        for number, proposal in enumerate(day.checked.kept if day.checked else (), start=1):
            extras = [
                f"due {proposal.due}" if proposal.due else "",
                f"topic {proposal.topic}" if proposal.topic else "",
            ]
            lines += [
                "",
                f"{number}. **{proposal.kind}**: {proposal.text}",
                f"   - you typed: “{' '.join(proposal.quote.split())}”",
                f"   - in {folders[proposal.session]}" + "".join(f", {extra}" for extra in extras if extra),
            ]
    return "\n".join(lines) + "\n"


def open_private(path: Path) -> int:
    """Opens the file for writing, closed to everybody but its owner before a byte is written.

    What the file holds stays until ``write_private`` replaces it. A file that cannot be opened or
    belongs to someone else is an ``OSError``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        # The mode given to ``os.open`` counts only for a file it creates.
        os.fchmod(descriptor, 0o600)
    except OSError:
        os.close(descriptor)
        raise
    return descriptor


def write_private(descriptor: int, text: str) -> None:
    # Whatever the text holds, the page is written: half a character becomes a question mark.
    with os.fdopen(descriptor, "w", encoding="utf-8", errors="replace") as handle:
        handle.truncate(0)
        handle.write(text)


def _inside_repository(path: Path) -> bool:
    """Whether the path lies in this repository, by the folder itself and not by how it is spelled."""
    repository = REPO_ROOT.stat()
    return any(parent.exists() and os.path.samestat(parent.stat(), repository) for parent in path.resolve().parents)


def _parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="glean-eval", description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--model", action="append", choices=CURATION_MODELS, help="ask this model; repeatable (default: every one)"
    )
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS, help="answers per model for the invented day")
    parser.add_argument(
        "--without-examples",
        action="store_true",
        help="ask about the invented day without what the person kept and dropped before",
    )
    parser.add_argument(
        "--replay", type=int, metavar="DAYS", help="read your own last DAYS days instead, today included"
    )
    parser.add_argument("--out", type=Path, help="with --replay: the file the proposals are written to")
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS, help="runs at the same time")
    parser.add_argument("--claude", default="claude", help="the claude command")
    parser.add_argument("--day", type=Path, default=DAY, help=argparse.SUPPRESS)
    parser.add_argument("--work-root", type=Path, default=DEFAULT_WORK_ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--today", type=datetime.date.fromisoformat, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    arguments = _parse_arguments(sys.argv[1:] if argv is None else argv)
    environ = os.environ if environ is None else environ
    if arguments.runs < 1 or (arguments.replay is not None and arguments.replay < 1):
        print("glean-eval: --runs and --replay take a number from 1", file=sys.stderr)
        return EXIT_USAGE
    if (arguments.replay is None) != (arguments.out is None):
        print("glean-eval: --replay and --out go together", file=sys.stderr)
        return EXIT_USAGE
    if arguments.replay is not None and len(arguments.model or ()) > 1:
        print("glean-eval: --replay asks one model", file=sys.stderr)
        return EXIT_USAGE
    if arguments.out is not None and _inside_repository(arguments.out):
        print("glean-eval: --out is inside this repository; what you typed does not belong there", file=sys.stderr)
        return EXIT_REFUSED
    try:
        work, projects, environment = prepare_sandbox(arguments.work_root, environ)
    except RealStoreError as error:
        print(f"glean-eval: {error}", file=sys.stderr)
        return EXIT_REFUSED
    asker = Asker(glean.instruction(), arguments.claude, work, environment)
    if arguments.replay is not None:
        model = arguments.model[0] if arguments.model else DEFAULT_CURATION_MODEL
        today = arguments.today or datetime.datetime.now().astimezone().date()
        days = [today - datetime.timedelta(days=back) for back in reversed(range(arguments.replay))]
        return _replay(claude_code.transcripts_folder(environ), days, model, asker, arguments.jobs, arguments.out)
    try:
        case = build_case(load_day(arguments.day), projects, with_examples=not arguments.without_examples)
    except (FixtureError, SessionsError) as error:
        print(f"glean-eval: {error}", file=sys.stderr)
        return EXIT_USAGE
    outcomes = evaluate(case, arguments.model or CURATION_MODELS, arguments.runs, asker, arguments.jobs)
    return EXIT_PASSED if report(case, outcomes) else EXIT_FAILED


def _replay(transcripts: Path, days: Sequence[datetime.date], model: str, asker: Asker, jobs: int, out: Path) -> int:
    if not transcripts.is_dir():
        print(f"glean-eval: no Claude Code transcripts in {transcripts}", file=sys.stderr)
        return EXIT_FAILED
    try:
        # Before any model is asked: a file that cannot be written must not cost a run per day.
        descriptor = open_private(out)
    except OSError as error:
        print(f"glean-eval: cannot write {out}: {error.strerror or error}", file=sys.stderr)
        return EXIT_USAGE
    try:
        replayed = replay(transcripts, days, model, asker, jobs)
    except SessionsError as error:
        os.close(descriptor)
        print(f"glean-eval: {error}", file=sys.stderr)
        return EXIT_FAILED
    write_private(descriptor, replay_page(replayed, model))
    for day in replayed:
        print(day.line())
    proposals = sum(len(day.checked.kept) for day in replayed if day.checked is not None)
    print(f"glean-eval: {proposals} proposals from {len(replayed)} days written to {out}")
    return EXIT_FAILED if any(day.problem for day in replayed) else EXIT_PASSED


if __name__ == "__main__":
    sys.exit(main())
