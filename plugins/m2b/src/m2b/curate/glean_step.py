"""The curation step ``glean``: what the person typed since the last reading, and what a model proposes from it.

The step is in a run only while ``curation.read_sessions`` is true in the machine config: the
transcripts are this machine's, and reading them is the person's decision. It runs after harvest
and before ingest, so what the person captured themselves is in the inbox or the archive by then.

A reading covers the time from the last one's end (``read_until`` in ``proposals.json``) to the
run's start: the last ``FIRST_PERIOD`` at the first reading, never more than ``LONGEST_PERIOD``,
and what lies before that is named as not read. Sessions that started in or below a folder that is
left out do not reach the model: the folders the profile's ``worklog_leave_out`` names, compared
as written with no look at the disk, and those with ``m2b distillate off``. One list for "sessions
m2b never reads" cannot be forgotten in one of two places. A session whose folder is not an
absolute path cannot be compared with either and is left out too. The same setting names work by
its repository's git remotes: a session is left out when a remote noted for its folder at a
session start, or one git names there now, holds a part the profile names, and also when neither
says anything of the folder, since it is then not shown to be other work (``session_remotes``).

The model is asked once, with nothing to call (``model.text_step``), and only when a session left
has a prompt of the person's, typed or pasted. With the prompts it gets the distillate and what the
person kept and dropped of earlier proposals (``proposals.examples``); harvest has settled the
answers by then, so the last ones are among them. It also gets the proposals that still wait
(``proposals.waiting_examples``), so that none of them is proposed again in other words. Code
checks its answer (``glean.check``) against
the prompts and against the captures of the period, and ``proposals`` keeps what is new and counts,
per kind, what was added and what stood on no words of the person. The counts go to the run as
information, never into the review: nothing here asks the person to act. What the reader left out of
the sessions it read is among them, so a day's reading shows what it did not take.

Before the reading, ``recheck_lessons`` asks whether a file every session loads now states a lesson
of the block (``lesson_recheck``); a model is asked only when the lessons or those files changed.

The model is also shown the lessons the person kept and asked which prompts correct Claude on one
of them again; code keeps such a correction only where its words stand in what was typed on the
day after the lesson was kept, and counts it under the lesson (``lesson_counts``).

A repository the person typed in on two days, in this reading or remembered from one before, and
that no topic names, is proposed as a project by code (``project_proposals``), with no model and
no words of the person; the days are remembered in machine state once the reading is saved.

When anything fails, the transcripts that cannot be looked at, a model without an answer, an
answer that cannot be read, nothing is saved and ``read_until`` stays, so the next run reads the
period again. A period in which nothing carries Claude Code's mark of who sent it fails the same
way: the reader then gives no prompt at all, and that must not pass for a day on which nothing
was typed; ids that depend only on session and quote keep a second reading from doubling
anything. The runner reports the failure in the review and lets the run succeed: this step reads a
file format Claude Code does not promise, and its failure must not hold back the filing of the
inbox.
"""

from __future__ import annotations

import dataclasses
import datetime
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from m2b import (
    claude_code,
    fixes,
    folders_left_out,
    glean,
    kept_lessons,
    lesson_counts,
    lesson_recheck,
    lesson_sources,
    lessons,
    project_capture,
    project_files,
    project_proposals,
    proposals,
    session_remotes,
    sessions,
)
from m2b.candidates import same_text
from m2b.config.errors import ConfigError
from m2b.config.machine import MachineConfig
from m2b.curate import model, period_captures
from m2b.notes.layout import MEMORY, MEMORY_INDEX
from m2b.paths import MachinePaths
from m2b.store.base import Store, StoreError

FIRST_PERIOD = datetime.timedelta(hours=24)
LONGEST_PERIOD = datetime.timedelta(days=7)

_MOMENT = "%Y-%m-%d %H:%M"
# A slash command as the reader gives it: only its name.
_COMMAND_NAME = re.compile(r"/\S+")


class GleanStepError(Exception):
    """The model gave no answer; the text says why."""


@dataclass(frozen=True)
class Reading:
    """How a reading ended: why no model was asked, or None when one was, and what the run reports of it."""

    skipped: str | None
    notes: tuple[str, ...]


def recheck_lessons(
    store: Store,
    config: MachineConfig,
    machine: MachinePaths,
    environ: Mapping[str, str],
    pass_fds: Sequence[int] = (),
) -> list[str]:
    """Whether a file every session loads now states a lesson of the block (``lesson_recheck``), as
    the run's information. Whatever keeps it from an answer is said, and the reading goes on: the
    lessons then stay in the block, as before."""

    def ask(instruction: str, text: str) -> str:
        run = model.text_step(config, machine, environ, instruction, text, pass_fds)
        if run.answer is None:
            raise lesson_recheck.RecheckError(run.failure())
        return run.answer

    try:
        result = lesson_recheck.recheck(store, environ, machine.state_dir, ask)
    # ``ValueError`` too: a lesson's frontmatter that cannot take the field must not cost the reading.
    except (lesson_recheck.RecheckError, StoreError, OSError, ValueError) as error:
        return [f"the kept lessons were not checked again against the files every session loads: {error}"]
    return [
        f"the lesson {name} is stated in {stated_in} now and left the block, kept at its source"
        for name, stated_in in result.kept_at_source
    ]


def propose(
    store: Store,
    config: MachineConfig,
    machine: MachinePaths,
    environ: Mapping[str, str],
    started: datetime.datetime,
    pass_fds: Sequence[int] = (),
) -> Reading:
    """Reads the sessions up to ``started``, the run's start, and keeps what is proposed from them."""
    kept = proposals.load(store)
    zone = started.tzinfo or datetime.timezone.utc
    earliest = started - LONGEST_PERIOD
    start = (kept.read_until or started - FIRST_PERIOD).astimezone(zone)
    if start >= started:
        return Reading(f"the sessions are read up to {start.strftime(_MOMENT)}", ())
    notes: list[str] = []
    if start < earliest:
        start = earliest
        notes.append(
            f"what was typed before {start.strftime(_MOMENT)} was not read: "
            f"a reading goes back {LONGEST_PERIOD.days} days at most"
        )
    found = sessions.read_sessions(claude_code.transcripts_folder(environ), start, started)
    without_mark = _nothing_marked(found.sessions)
    if without_mark:
        raise GleanStepError(
            f"nothing typed since {start.strftime(_MOMENT)} carries Claude Code's mark of who sent it, "
            f"{_count(without_mark, 'text')} {'is' if without_mark == 1 else 'are'} without it: "
            "Claude Code may write its transcripts in a way this m2b does not read"
        )
    left_out = folders_left_out.rule(store, config, machine, environ, started)
    reasons = {session.session_id: left_out.reason(session.folder) for session in found.sessions}
    considered = [session for session in found.sessions if reasons[session.session_id] is None]
    read = [session for session in considered if session.prompts]
    notes += _left_out_notes(Counter(reason for reason in reasons.values() if reason is not None))
    if found.unreadable:
        notes.append(f"{_count(len(found.unreadable), 'transcript')} could not be read")
    notes += _left_out_of(considered)
    if not read:
        proposals.save(store, dataclasses.replace(kept, read_until=started))
        return Reading(f"no session since {start.strftime(_MOMENT)} has a prompt of yours", tuple(notes))
    notes_folder = machine.state_dir / session_remotes.NOTES_FOLDER
    projects = _projects_of(read, store, notes_folder, started)
    read = project_files.shown(read, projects)
    captures = period_captures.captures_since(store, start, started)
    examples = proposals.examples(kept, started)
    if examples != glean.NO_EXAMPLES:
        notes.append(
            f"the model was shown {len(examples.kept)} kept and "
            f"{_count(len(examples.dropped), 'dropped proposal')} as examples"
        )
    waiting = proposals.waiting_examples(kept)
    if waiting:
        notes.append(f"the model was shown {_count(len(waiting), 'proposal')} that {_wait(len(waiting))} for an answer")
    pasted = sum(len(prompt.pasted) for session in read for prompt in session.prompts)
    if pasted:
        notes.append(f"{_count(pasted, 'pasted text')} {_were(pasted)} read with the prompts they stand in")
    standing = lessons.read_all(store)
    as_fixes = _kept_as_fixes(store)
    shown_lessons = [
        *(glean.ShownLesson(lesson.name, lesson.text, lesson.kept) for lesson in standing),
        *(as_fixes or ()),
    ]
    given = glean.step_input(read, _distillate(store), zone, examples, waiting, shown_lessons)
    run = model.text_step(config, machine, environ, glean.instruction(), given, pass_fds)
    if run.answer is None:
        raise GleanStepError(run.failure())
    answer = glean.parse_answer(run.answer, read)
    checked = glean.check(answer.proposals, read, captures.texts)
    placed, without_repository = _for_their_project(checked, read, notes_folder, started)
    placed = project_files.pointed(placed, read, projects)
    placed, not_keepable, known = _new_lessons(placed, standing, zone)
    placed, unchecked = _at_their_sources(
        placed, read, config, machine, environ, notes_folder, started, pass_fds, kept.entries
    )
    # Before the weakest lesson is chosen, so this reading's corrections count in that choice.
    corrections = glean.checked_corrections(answer.corrections, read, shown_lessons, zone)
    try:
        if as_fixes is None:
            # The counts are written with the lessons that stand, so a fix not known now would lose its own.
            raise StoreError("the fixes kept from lessons could not be read")
        again = lesson_counts.add(
            store, corrections, {lesson.name: lesson.kept for lesson in shown_lessons}, started.astimezone(zone).date()
        )
    # A counter must not cost the reading its proposals: whatever keeps the file from being read or
    # written is said, and the reading goes on.
    except (lesson_counts.LessonCountsError, ConfigError, StoreError) as error:
        notes.append(f"the corrections of kept lessons were not counted: {error}")
    else:
        if again:
            notes.append(f"{_count(again, 'correction')} of a kept lesson counted: Claude was corrected on it again")
    placed = _within_the_start(placed, standing, store, kept.entries)
    said = [proposals.Said(proposal, typed_at.astimezone(zone).date()) for proposal, typed_at in placed]
    repositories = {
        session.folder: tuple(sorted(_addresses(notes_folder, session.folder, started))) for session in read
    }
    worked = project_proposals.joined(
        project_proposals.remembered(machine.state_dir, started.astimezone(zone).date()),
        project_proposals.days_worked(read, repositories, zone),
    )
    said += project_proposals.proposed(store, worked)
    added = proposals.add(kept, said, started)
    counted = added.proposals
    # Only what this reading added: a project that waits or was answered stays a candidate while
    # its days are remembered, and ``add`` refuses it again.
    new_projects = sum(entry.kind == glean.PROJECT for key, entry in counted.entries.items() if key not in kept.entries)
    if new_projects:
        notes.append(
            f"{new_projects} {'repository' if new_projects == 1 else 'repositories'} without a topic "
            f"{_were(new_projects)} worked in on two days and proposed as a project"
        )
    for refused in checked.not_quoted:
        counted = proposals.counted(counted, refused.kind, "not_quoted")
    if not_keepable:
        counted = proposals.counted(counted, glean.LESSON, "not_quoted", not_keepable)
        notes.append(f"{_count(not_keepable, 'lesson')} left out: not in the form a lesson is kept in")
    if known:
        notes.append(f"{_count(known, 'lesson')} left out: a lesson like it is kept already")
    if unchecked.count:
        counted = proposals.counted(counted, glean.LESSON, "not_quoted", unchecked.count)
        notes.append(f"{_count(unchecked.count, 'lesson')} left out: {unchecked.why}")
    if without_repository:
        counted = proposals.counted(counted, glean.LESSON, "not_quoted", without_repository)
        notes.append(
            f"{_count(without_repository, 'lesson')} for one project left out: "
            "no repository is known that both its sessions worked in"
        )
    proposals.save(store, dataclasses.replace(counted, read_until=started))
    project_proposals.remember(machine.state_dir, worked, machine.temp_dir)
    sent = sum(len(session.prompts) for session in read)
    summary = (
        f"read {_count(len(read), 'session')} with {_count(sent, 'prompt')} since {start.strftime(_MOMENT)}: "
        f"{_count(added.added, 'proposal')} added, "
        f"{added.added_before} like one that waits, is answered or expired, "
        f"{len(checked.not_quoted)} without the person's words, "
        f"{len(checked.already_captured)} captured already, {answer.malformed} not in the form"
    )
    return Reading(None, (summary, *notes, *period_captures.capture_notes(captures)))


def _for_their_project(
    checked: glean.Checked, read: Sequence[sessions.Session], notes: Path, now: datetime.datetime
) -> tuple[list[tuple[glean.Proposal, datetime.datetime]], int]:
    """The kept proposals with when their words were typed, each lesson for one project named by the
    address of the repository both its sessions worked in, and how many such lessons have none.

    The address comes from the remotes the session start noted for each session's folder; a lesson
    for one project is kept only where both folders name the same repository, so it reaches the
    sessions of that repository on every machine.
    """
    folders = {session.session_id: session.folder for session in read}
    placed: list[tuple[glean.Proposal, datetime.datetime]] = []
    without = 0
    for proposal, typed_at in zip(checked.kept, checked.kept_at):
        lesson = proposal.lesson
        if lesson is None or lesson.target != lessons.THIS_PROJECT:
            placed.append((proposal, typed_at))
            continue
        first, second = (_addresses(notes, folders.get(key, ""), now) for key in (proposal.session, lesson.session))
        common = sorted(first & second)
        if not common:
            without += 1
            continue
        placed.append((dataclasses.replace(proposal, lesson=dataclasses.replace(lesson, target=common[0])), typed_at))
    return placed, without


def _projects_of(
    read: Sequence[sessions.Session], store: Store, notes: Path, now: datetime.datetime
) -> dict[str, project_files.Project]:
    """The project of each session's folder that wrote a file: the topic whose ``Repository:`` line
    names one of the addresses the session start noted for the folder, with the repository's folder,
    the one the session start noted, else the one the file system shows."""
    # A note without the repository's folder gives the folder itself as its top: that is no answer.
    tops = {noted.folder: noted.top for noted in session_remotes.noted_folders(notes) if noted.top != noted.folder}
    projects: dict[str, project_files.Project] = {}
    for session in read:
        if not session.written or session.folder in projects:
            continue
        addresses = tuple(sorted(_addresses(notes, session.folder, now)))
        topic = project_capture.known_as(store, addresses) if addresses else None
        if topic is None:
            continue
        top = tops.get(session.folder) or str(session_remotes.repository_top(Path(session.folder)) or session.folder)
        projects[session.folder] = project_files.Project(topic, top, addresses)
    return projects


@dataclass(frozen=True)
class _Unchecked:
    count: int = 0
    why: str = ""


def _at_their_sources(
    placed: Sequence[tuple[glean.Proposal, datetime.datetime]],
    read: Sequence[sessions.Session],
    config: MachineConfig,
    machine: MachinePaths,
    environ: Mapping[str, str],
    notes: Path,
    now: datetime.datetime,
    pass_fds: Sequence[int],
    known: Mapping[str, proposals.Entry],
) -> tuple[list[tuple[glean.Proposal, datetime.datetime]], _Unchecked]:
    """The proposals, each lesson with what the files its sessions load say of it (``lesson_sources``).

    Asked only when there is a lesson. Where the model gives no answer that can be read, the lessons
    are left out with the reason: proposed unchecked, one might stand beside a source that says it.
    """
    # A lesson that waits under its id or its text already is refused when it is added: no model
    # run is spent on its sources.
    found = [
        proposal
        for proposal, _ in placed
        if proposal.lesson is not None
        and proposals.proposal_id(proposal) not in known
        and not any(same_text(entry.text, proposal.text) for entry in known.values())
    ]
    if not found:
        return list(placed), _Unchecked()
    folders = {session.session_id: session.folder for session in read}
    wanted: list[lesson_sources.Folder] = []
    for proposal in found:
        assert proposal.lesson is not None
        for key in (proposal.session, proposal.lesson.session):
            folder = folders.get(key, "")
            if folder and all(each.path != folder for each in wanted):
                wanted.append(lesson_sources.Folder(folder, tuple(sorted(_addresses(notes, folder, now)))))
    sources = lesson_sources.sources_for(wanted, environ)
    their_folders = [[folders.get(proposal.session, ""), folders.get(_second(proposal), "")] for proposal in found]
    loaded = [sources.of(each) for each in their_folders]
    complete = [not any(folder in sources.incomplete for folder in each) for each in their_folders]
    given = lesson_sources.step_input(found, sources.sources, loaded)
    run = model.text_step(config, machine, environ, lesson_sources.instruction(), given, pass_fds)
    if run.answer is None:
        return _without_lessons(placed), _Unchecked(len(found), f"their sources could not be checked ({run.failure()})")
    try:
        verdicts = lesson_sources.apply(run.answer, found, sources.sources, loaded, complete)
    except lesson_sources.LessonSourcesError as error:
        return _without_lessons(placed), _Unchecked(len(found), f"their sources could not be checked ({error})")
    checked = {(proposal.session, proposal.quote): proposal for proposal in verdicts.kept}
    kept = [
        (checked.get((proposal.session, proposal.quote), proposal), typed_at)
        for proposal, typed_at in placed
        if proposal.lesson is None or (proposal.session, proposal.quote) in checked
    ]
    why = "what their sources say could not be used"
    if sources.not_shown:
        why += f" (not shown to the model: {', '.join(sources.not_shown)})"
    return kept, _Unchecked(verdicts.left_out, why)


def _second(proposal: glean.Proposal) -> str:
    return proposal.lesson.session if proposal.lesson else ""


def _without_lessons(
    placed: Sequence[tuple[glean.Proposal, datetime.datetime]],
) -> list[tuple[glean.Proposal, datetime.datetime]]:
    return [(proposal, typed_at) for proposal, typed_at in placed if proposal.lesson is None]


def _new_lessons(
    placed: Sequence[tuple[glean.Proposal, datetime.datetime]],
    standing: Sequence[lessons.Lesson],
    zone: datetime.tzinfo,
) -> tuple[list[tuple[glean.Proposal, datetime.datetime]], int, int]:
    """The proposals without the lessons that could never be kept and those kept already, and the
    number of each left out.

    A lesson is kept the way one kept by hand is (``kept_lessons.checked``); one it refuses would
    wait with its answer on every run, so it is not proposed. A knowledge lesson for one project is
    the one refusal that stays: it is kept as a fix of that project's CLAUDE.md. A lesson is known
    when one of the same kind and target stands with the same words, or, for knowledge, the same text.
    """
    kept: list[tuple[glean.Proposal, datetime.datetime]] = []
    not_keepable = known = 0
    for proposal, typed_at in placed:
        lesson = proposal.lesson
        if lesson is None:
            kept.append((proposal, typed_at))
            continue
        day = typed_at.astimezone(zone).date().isoformat()
        given = kept_lessons.KeptLesson(
            proposal.text[:60], proposal.text, lesson.kind, lesson.target, day, lesson.words
        )
        try:
            kept_lessons.checked(given)
        except kept_lessons.LessonRefusedError:
            if lesson.kind != lessons.KNOWLEDGE or lesson.target == lessons.EVERY_PROJECT:
                not_keepable += 1
                continue
        if any(_same_lesson(proposal, lesson, other) for other in standing):
            known += 1
            continue
        kept.append((proposal, typed_at))
    return kept, not_keepable, known


def _kept_as_fixes(store: Store) -> list[glean.ShownLesson] | None:
    """The lessons kept as fixes of their source, by the fix's name, so their corrections go on being
    counted (B289); None where the fixes cannot be read: the reading goes on and counts nothing."""
    try:
        found = fixes.kept_from_lessons(store)
    except (StoreError, OSError):
        return None
    return [glean.ShownLesson(fix.name, fix.lesson, fix.kept) for fix in found if fix.lesson is not None]


def _within_the_start(
    placed: Sequence[tuple[glean.Proposal, datetime.datetime]],
    standing: Sequence[lessons.Lesson],
    store: Store,
    known: Mapping[str, proposals.Entry],
) -> list[tuple[glean.Proposal, datetime.datetime]]:
    """The proposals, each new lesson for every session's start with the kept lesson it would
    replace where the block of lessons, with the new ones, would pass its own limit
    (``lessons.MAX_BLOCK_CHARACTERS``) and leave a lesson out. The block is an output of its own
    beside the distillate, so how long the distillate is has no say in it.

    The lesson replaced is the weakest of those every session starts with: the one corrected again
    most often since it was kept, then the oldest; each is named for one new lesson at most, also
    across readings: one a waiting proposal names already is not named again. Where no kept lesson
    is left to name, the new one is proposed alone. A proposal like one that waits, is answered or
    expired is no new lesson: it would not be added.
    """
    named = {entry.lesson.replaces for entry in known.values() if entry.state == proposals.OPEN and entry.lesson}
    new = [proposal for proposal, _ in placed if _goes_into_the_start(proposal) and not _is_known(proposal, known)]
    if not new:
        return list(placed)
    # A new lesson is kept after every standing one, so it comes last in the block.
    with_new = [
        *standing,
        *(lessons.Lesson("", proposal.text, lessons.KNOWLEDGE, lessons.EVERY_PROJECT, "") for proposal in new),
    ]
    _, left_out = lessons.fitting(with_new)
    if not left_out:
        return list(placed)
    try:
        again = lesson_counts.corrected_again(store, {lesson.name: lesson.kept for lesson in standing})
    except (lesson_counts.LessonCountsError, ConfigError, StoreError):
        again = {}
    weakest = iter(
        sorted(
            (lesson for lesson in standing if lesson.in_the_block and lesson.name not in named),
            key=lambda lesson: (-again.get(lesson.name, 0), lesson.kept, lesson.name),
        )
    )
    result: list[tuple[glean.Proposal, datetime.datetime]] = []
    for proposal, typed_at in placed:
        replaced = next(weakest, None) if any(proposal is each for each in new) else None
        if replaced is not None and proposal.lesson is not None:
            proposal = dataclasses.replace(
                proposal, lesson=dataclasses.replace(proposal.lesson, replaces=replaced.name)
            )
        result.append((proposal, typed_at))
    return result


def _is_known(proposal: glean.Proposal, known: Mapping[str, proposals.Entry]) -> bool:
    return proposals.proposal_id(proposal) in known or any(
        same_text(entry.text, proposal.text) for entry in known.values()
    )


def _goes_into_the_start(proposal: glean.Proposal) -> bool:
    """A lesson kept as its own text for every session: no fix of a source, no pointer to one."""
    lesson = proposal.lesson
    return (
        lesson is not None
        and lesson.kind == lessons.KNOWLEDGE
        and lesson.target == lessons.EVERY_PROJECT
        and lesson.at_source is None
    )


def _same_lesson(proposal: glean.Proposal, lesson: glean.LessonPart, other: lessons.Lesson) -> bool:
    if (other.kind, other.target) != (lesson.kind, lesson.target):
        return False
    if lesson.kind == lessons.ACTION:
        return set(other.words) == set(lesson.words)
    return same_text(other.text, proposal.text)


def _addresses(notes: Path, folder: str, now: datetime.datetime) -> frozenset[str]:
    remotes = session_remotes.noted(notes, folder, now) if folder else None
    # Only addresses with a host: a local path would name a folder of this machine in a proposal.
    return frozenset(session_remotes.hosted_addresses(remotes or ()))


def _nothing_marked(found: Sequence[sessions.Session]) -> int:
    """How many texts have no mark of who sent them when nothing of the period has one, else 0.

    A text without the mark beside marked ones is a record the reader does not recognise, such as
    the output of a shell line that came in two blocks. When no prompt and nothing another
    sender sent shows the mark, the reader cannot tell what was typed; a slash
    command proves nothing, since it is taken by its form. The reading then fails at every run
    until the period holds a marked text or has moved past the unmarked ones.
    """
    marked = any(
        session.left_out.sent_by_others
        or session.left_out.suggested
        or any(prompt.pasted or not _COMMAND_NAME.fullmatch(prompt.text) for prompt in session.prompts)
        for session in found
    )
    return 0 if marked else sum(session.left_out.unmarked for session in found)


def _left_out_of(read: Sequence[sessions.Session]) -> list[str]:
    """What the reader left out of these sessions, as one note, or none when that is nothing."""
    others = sum(session.left_out.sent_by_others for session in read)
    suggested = sum(session.left_out.suggested for session in read)
    unmarked = sum(session.left_out.unmarked for session in read)
    counted = (
        (others, f"{_count(others, 'prompt')} that a plugin, a task or another agent sent"),
        (suggested, f"{_count(suggested, 'suggestion')} that {_were(suggested)} only accepted"),
        (
            unmarked,
            f"{_count(unmarked, 'text')} without Claude Code's mark of who sent {'it' if unmarked == 1 else 'them'}",
        ),
    )
    named = [text for number, text in counted if number]
    return [f"left out of these sessions: {', '.join(named)}"] if named else []


def _left_out_notes(reasons: Mapping[str, int]) -> list[str]:
    """How many sessions were not read for each reason: folder, repository, no known repository."""
    notes = []
    in_folder = reasons.get(folders_left_out.IN_A_FOLDER_LEFT_OUT, 0)
    of_repository = reasons.get(folders_left_out.OF_A_REPOSITORY_LEFT_OUT, 0)
    unknown = reasons.get(folders_left_out.OF_NO_KNOWN_REPOSITORY, 0)
    if in_folder:
        notes.append(f"{_count(in_folder, 'session')} in a folder that is left out {_were(in_folder)} not read")
    if of_repository:
        notes.append(
            f"{_count(of_repository, 'session')} of a repository that is left out {_were(of_repository)} not read"
        )
    if unknown:
        notes.append(
            f"{_count(unknown, 'session')} {_were(unknown)} not read, because no git remote is known for "
            f"{'its folder' if unknown == 1 else 'their folders'} "
            f"({'the folder is' if unknown == 1 else 'the folders are'} gone or git did not answer) "
            "and the profile leaves work out by git remote"
        )
    return notes


def _distillate(store: Store) -> str:
    try:
        return store.read_text(f"{MEMORY}/{MEMORY_INDEX}")
    except FileNotFoundError:
        return ""


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _wait(number: int) -> str:
    return "waits" if number == 1 else "wait"


def _were(number: int) -> str:
    return "was" if number == 1 else "were"
