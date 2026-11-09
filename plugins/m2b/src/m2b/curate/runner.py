"""The curation run, ``m2b curate``: preflight, the steps in their order, the review, the run record.

Only the machine ``store.json`` names curates, because iCloud gives no reliable lock shared between
machines; any other one refuses into its local log and never writes the run record. One run per
machine, held by the lock; the lock goes to every child, so a killed runner cannot leave a model
step editing ``memory/`` while a new run starts.

Preflight downloads what the run will read or write, checks the tasks backend and writes the run
record with ``state: running``; when any of that fails, the run stops with nothing else written,
records the cause (in the run record, or in the local log when even that cannot be written), and
the backoff makes the next attempt wait. After preflight every step runs whatever the one before
did (B13): a failing step is recorded and reported in the review, and the run counts as failed,
so the last successful run does not move. The one exception is a migration (``migrations``): the
due ones run first, and when one fails the run goes straight to the review, because every later
step follows rules the store does not hold yet. Ingest is skipped when the inbox holds nothing, refresh
when no fact is past its day.

``refresh_all`` is the one-time backfill for lines written before ingest dated them: the run starts
whether due or not, and the refresh step also gets the fact files without ``until`` and the current
items without ``since``, one model step per batch (B43).

``sort_facts`` is the one-time sorting of a distillate written before topics existed: the run
starts whether due or not, and after refresh a fenced step moves facts lines into topics and writes
their headings. It may edit ``MEMORY.md`` alone; code compares afterwards and puts the file back when
more than headings and order changed (B51).

Ingest, refresh and lint are checked the same way, each against a snapshot of ``memory/`` taken
just before its model step (``memory_guard``): refresh is held to its due facts, ingest and lint
have their removed and rewritten facts lines listed in the review, and a line holding characters
that hide text undoes any of them. A runner stopped by SIGTERM still checks; a run that never
finished is checked by the next one, against the copy of ``memory/`` it saved.
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime
import functools
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from m2b import current_check, expiry, ingest, launcher, lint
from m2b.candidates import PREFIX_KEY
from m2b.config.errors import ConfigError, NotSetUpError
from m2b.config.machine import MachineConfig, load_machine_config
from m2b.config.profile import PROFILE_FILE_NAME, require_profile
from m2b.config.store_settings import (
    STORE_SETTINGS_FILE_NAME,
    StoreSettings,
    load_store_settings,
    write_store_format,
)
from m2b.curate import machine_state, memory_guard, migrations, model, report
from m2b.curate.due import check_due
from m2b.harvest import harvest
from m2b.journal import write_journal
from m2b.locale import Locale, load_locale
from m2b.notes.characters import strip_unsafe
from m2b.notes.layout import (
    CORPUS,
    INBOX,
    MEMORY,
    MEMORY_INDEX,
    STATE,
    STORE_CONTRACT,
    TASKS,
    journal_name,
    waiting_on_evicted,
)
from m2b.parts import CURATION_SLOTS, Part, names_on, steps_in
from m2b.paths import MachinePaths
from m2b.review import StepFailure, review_is_open, update_review
from m2b.run_record import (
    FAILED,
    RUN_RECORD,
    RUNNING,
    SKIPPED,
    SUCCEEDED,
    RunRecord,
    RunRecordError,
    StepResult,
    load_run_record,
    write_run_record,
)
from m2b.setup import write_store_contract
from m2b.sort_facts import sorting_problem
from m2b.store.base import DEFAULT_FETCH_TIMEOUT_SECONDS, FetchError, Store, StoreError, fetch_command
from m2b.store.factory import open_store
from m2b.tasks.base import Tasks
from m2b.tasks.factory import open_tasks

__all__ = ["NotSetUpError", "RunOutcome", "RunRecordWriteError", "StoreError", "curate"]

PREFLIGHT = "preflight"
HARVEST = "harvest"
INGEST = "ingest"
REFRESH = "refresh"
SORT = "sort"
LINT = "lint"
JOURNAL = "journal"
REVIEW = "review"
# A failure between preflight and review that belongs to no step.
RUN = "run"

INGEST_SKILL = "m2b:ingest"
LINT_SKILL = "m2b:lint"
REFRESH_SKILL = "m2b:refresh"
SORT_SKILL = "m2b:sort-facts"
# The sorting step reads the fact files to judge a line and edits the distillate alone; ``m2b refresh
# due`` is read-only and tells the skill the store's folder and that it runs inside a curation run.
SORT_RULES = (
    "Bash(m2b refresh due *)",
    "Bash(m2b curate report *)",
    f"Read(<store>/{MEMORY}/**)",
    f"Edit(<store>/{MEMORY}/{MEMORY_INDEX})",
)
# The refresh step reads the archive for evidence and edits only the distillate and the fact files
# that are due; ``refresh_rules`` adds those files.
REFRESH_RULES = (
    "Bash(m2b refresh *)",
    "Bash(m2b curate report *)",
    f"Read(<store>/{MEMORY}/{MEMORY_INDEX})",
    f"Edit(<store>/{MEMORY}/{MEMORY_INDEX})",
    f"Read(<store>/{CORPUS}/**)",
)
# A backfill batch also searches for the captures about a current item; ``refresh_rules`` adds the
# batch's fact files.
REFRESH_ALL_RULES = (REFRESH_RULES[0], "Bash(m2b search *)", *REFRESH_RULES[1:])
# Lines per backfill model step: each costs about four tool calls, well inside ``curation.max_turns``.
BACKFILL_BATCH = 10
INGEST_RULES = (
    "Bash(m2b ingest *)",
    "Bash(m2b search *)",
    "Bash(m2b curate report *)",
    "Read(<store>/inbox/**)",
    "Read(<store>/memory/**)",
    "Edit(<store>/memory/**)",
)
LINT_RULES = (
    "Bash(m2b lint *)",
    "Bash(m2b search *)",
    "Bash(m2b curate report *)",
    "Read(<store>/memory/**)",
    "Edit(<store>/memory/**)",
)
MODEL_STEPS = 3
# Harvest, journal and review have no timeout of their own; they get this much in the deadline. The
# journal's fetch of evicted month files is counted with the preflight fetch.
CODE_STEPS_MARGIN = datetime.timedelta(minutes=10)

NOT_CURATING = "not-curating"
ALREADY_RUNNING = "already-running"
NOT_DUE = "not-due"


class RunRecordWriteError(StoreError):
    """The run record could not be written; the local run log holds the cause."""


class StepError(Exception):
    """A step ended without doing its work; the text says why."""


@dataclass(frozen=True)
class Skipped:
    """What a step returns when it had nothing to do."""

    reason: str


@dataclass(frozen=True)
class RefreshScope:
    """What a refresh model step may change: these fact files and their lines, and the current
    items the backfill gave it, by their ``(since ...)`` alone."""

    files: Sequence[str]
    current: Sequence[str] = ()


@dataclass(frozen=True)
class InboxBefore:
    """The inbox as an ingest step found it: its files, and the captures already marked ``facts_filed``."""

    files: set[str] = field(default_factory=set)
    facts_filed: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class RunOutcome:
    """``succeeded`` or ``failed`` for a run that happened, else why none did."""

    state: str
    message: str
    record: RunRecord | None = None


def now() -> datetime.datetime:
    return datetime.datetime.now().astimezone()


def curate(
    machine: MachinePaths,
    environ: Mapping[str, str],
    force: bool = False,
    clock: Callable[[], datetime.datetime] = now,
    fetch_timeout_seconds: float = DEFAULT_FETCH_TIMEOUT_SECONDS,
    refresh_all: bool = False,
    sort_facts: bool = False,
) -> RunOutcome:
    """Runs curation once when this machine curates, no run holds the lock and one is due (or forced,
    which ``refresh_all`` and ``sort_facts`` imply)."""
    config = load_machine_config(machine)
    store = open_store(config.store, machine.temp_dir)
    try:
        store.fetch([STORE_SETTINGS_FILE_NAME], fetch_timeout_seconds)
        settings = load_store_settings(store, for_writing=True)
    except (StoreError, ConfigError) as error:
        message = f"the curation run could not read {STORE_SETTINGS_FILE_NAME}: {error}"
        machine_state.log_event(machine, machine_state.UNRECORDED, message, clock())
        raise
    if settings.curating_machine != config.machine_id:
        message = (
            f"this machine ({config.machine_id}) is not the curating machine; {settings.curating_machine} is. "
            "m2b curate take-over moves curation here."
        )
        machine_state.log_event(machine, machine_state.REFUSED, message, clock())
        return RunOutcome(NOT_CURATING, message)
    if machine_state.lock_is_held(machine):
        return RunOutcome(ALREADY_RUNNING, "a curation run is already running on this machine")
    if not force and not refresh_all and not sort_facts:
        due = check_due(store, machine, clock())
        if not due.due:
            machine_state.record_attempt(machine, machine_state.NOT_DUE, due.reason, clock())
            return RunOutcome(NOT_DUE, f"no curation run is due: {due.reason}")
    lock = machine_state.RunLock(machine)
    if not lock.acquire():
        return RunOutcome(ALREADY_RUNNING, "a curation run is already running on this machine")
    try:
        return _Run(
            config, settings, store, machine, environ, lock, clock, fetch_timeout_seconds, refresh_all, sort_facts
        ).run()
    finally:
        lock.release()


@dataclass
class _Run:
    config: MachineConfig
    settings: StoreSettings
    store: Store
    machine: MachinePaths
    environ: Mapping[str, str]
    lock: machine_state.RunLock
    clock: Callable[[], datetime.datetime]
    fetch_timeout_seconds: float
    refresh_all: bool = False
    sort_facts: bool = False
    undated: expiry.Undated | None = None
    steps: list[StepResult] = field(default_factory=list)
    failures: list[StepFailure] = field(default_factory=list)
    findings: list[report.Finding] = field(default_factory=list)
    last_success: datetime.datetime | None = None
    started: datetime.datetime | None = None
    # The copy of ``memory/`` from before this run's first migration or model step, once it is saved.
    memory_copy: Path | None = None
    # Changed facts lines: those of earlier runs the owner has not seen yet, and this run's.
    carried_changes: list[report.Finding] = field(default_factory=list)
    fact_changes: list[report.Finding] = field(default_factory=list)

    def run(self) -> RunOutcome:
        started = self.clock()
        try:
            tasks, locale = self._preflight(started)
        # Whatever stops preflight is recorded, then raised again for the exit code.
        except Exception as error:
            self._stop_at_preflight(started, error)
            raise
        self.carried_changes = self._carried_changes(tasks)
        self._check_interrupted()
        self.started = started
        findings = self._run_steps(tasks, locale)
        self._keep_changes()
        self._step(REVIEW, lambda: update_review(tasks, findings, self.failures, started, locale), reported=False)
        return self._finish(started, findings)

    def _preflight(self, started: datetime.datetime) -> tuple[Tasks, Locale]:
        machine_state.clear_leftovers(self.machine, started)
        self.last_success = self._previous_success()
        paths = _preflight_paths(started)
        try:
            self.store.fetch(paths, self.fetch_timeout_seconds)
        except FetchError:
            # A capture that will not download waits in the inbox: ingest leaves it for the next run
            # and names it. Anything else the run reads or writes must be here.
            if self.store.check_local([path for path in paths if path != INBOX]):
                raise
        if self.last_success is None:
            self.last_success = self._previous_success()
        locale = load_locale(require_profile(self.store).language)
        tasks = open_tasks(self.settings.tasks, self.store, self.config.executables)
        tasks.check_reachable()
        if self.refresh_all:
            # Read here so the deadline counts the batches; the refresh step reads again if this fails.
            with contextlib.suppress(StoreError):
                self.undated = expiry.undated(self.store)
        self._write(self._record(RUNNING, started, deadline_at=started + self._step_timeouts()))
        return tasks, locale

    def _check_interrupted(self) -> None:
        """Compares what a run that never stored its changes left in ``memory/`` with its copy.

        A run stopped hard (SIGKILL, a machine that lost power, a second signal during its check)
        never compared ``memory/`` after its step; this run does: a line that hides text and every
        facts line removed or rewritten go to the review. The copy stays marked until this run
        stores the findings that name it, so a run stopped in between, at preflight or later,
        leaves the check to the next one, which compares the oldest marked copy and so loses
        nothing. ``memory/`` is not put back, since the owner may have edited it since.
        """
        # On this machine any run past preflight clears the marks, so a copy from before the last
        # successful run means another machine curated since; its edits are no interruption.
        copies = [
            copy
            for copy in machine_state.unchecked_copies(self.machine)
            if self.last_success is None or (_copy_started(copy) or self.last_success) >= self.last_success
        ]
        if copies:
            self.fact_changes += _interrupted_changes(copies[0], self.store)

    def _previous_success(self) -> datetime.datetime | None:
        try:
            previous = load_run_record(self.store)
        except (RunRecordError, StoreError):
            return None
        return previous.last_success if previous else None

    def _stop_at_preflight(self, started: datetime.datetime, error: Exception) -> None:
        self.steps = [StepResult(PREFLIGHT, FAILED, str(error))]
        message = f"{PREFLIGHT}: {error}"
        failed = self._record(FAILED, started, finished_at=self.clock(), message=message)
        self._close(failed, message)

    def _carried_changes(self, tasks: Tasks) -> list[report.Finding]:
        """Changed facts lines of earlier runs, while the review task that shows them is still open.

        A review task the owner completed or deleted means they have seen them. When the task list
        cannot say, the changes stay: losing them is worse than showing them once more.
        """
        try:
            if tasks.lists_every_task() and not review_is_open(tasks):
                return []
        except Exception:
            pass
        return machine_state.load_memory_changes(self.machine)

    def _keep_changes(self) -> None:
        """Stores the changed facts lines for the next run and removes the copies nothing names any more."""
        pending = self.carried_changes + self.fact_changes
        keep = {self.memory_copy} if self.memory_copy is not None else set()
        try:
            machine_state.save_memory_changes(self.machine, pending)
            machine_state.clear_unchecked(self.machine)
            copies = machine_state.memory_copies(self.machine)
            named = copies.iterdir() if copies.is_dir() else iter(())
            keep |= {copy for copy in named if any(str(copy) in finding.text for finding in pending)}
            machine_state.prune_memory_copies(self.machine, keep)
        except OSError as error:
            self.failures.append(StepFailure(RUN, f"the changed facts lines could not be kept: {error}"))

    def _run_steps(self, tasks: Tasks, locale: Locale) -> list[report.Finding]:
        """The steps between preflight and review, with the findings they left.

        Preflight wrote a ``running`` record, so whatever fails here outside a step must still
        end in a finished record and the backoff; it becomes a failed step named ``run``.
        """
        token: str | None = None
        try:
            token = report.open_run(self.machine)
            self._steps(tasks, locale, token)
            return self._changes_first() + report.read_findings(self.machine, token)
        except Exception as error:
            text = str(error) or type(error).__name__
            self.steps.append(StepResult(RUN, FAILED, text))
            self.failures.append(StepFailure(RUN, text))
            return self._changes_first()
        finally:
            if token is not None:
                with contextlib.suppress(OSError):
                    report.close_run(self.machine, token)

    def _changes_first(self) -> list[report.Finding]:
        return [*self.carried_changes, *self.findings, *self.fact_changes]

    def _steps(self, tasks: Tasks, locale: Locale, token: str) -> None:
        for migration in migrations.due(self.settings.format):
            self._step(migrations.step_name(migration), functools.partial(self._migrate, migration))
            if self.steps[-1].result == FAILED:
                return
            # The undated lines preflight read for ``--refresh-all`` are from before the migration.
            self.undated = None
        self._step(HARVEST, lambda: self._harvest(tasks, locale))
        self._parts("before_ingest", token)
        self._step(INGEST, lambda: self._ingest(token))
        self._parts("after_ingest", token)
        self._step(REFRESH, lambda: self._refresh(tasks, locale, token))
        if self.sort_facts:
            self._step(SORT, lambda: self._sort(token))
        self._step(LINT, lambda: self._lint(tasks, token))
        self._step(JOURNAL, lambda: self._journal(tasks))
        self._parts("after_journal", token)

    def _step(self, name: str, action: Callable[[], object], reported: bool = True) -> None:
        """Runs one step; a failure is recorded, and reported in the review unless it is the review.

        An action that returns ``Skipped`` did not need to run.
        """
        try:
            result = action()
        # A failing step must not stop the run (B13); whatever it raised is its result.
        except Exception as error:
            text = str(error) or type(error).__name__
            self.steps.append(StepResult(name, FAILED, text))
            if reported:
                self.failures.append(StepFailure(name, text))
            return
        if isinstance(result, Skipped):
            self.steps.append(StepResult(name, SKIPPED, result.reason))
        else:
            self.steps.append(StepResult(name, SUCCEEDED))

    def _save_memory_copy(self, before: memory_guard.Snapshot) -> None:
        """Keeps ``memory/`` as it was before the run's first step that may change it, in machine state."""
        if self.memory_copy is None:
            copy = machine_state.memory_copy(self.machine, self.started or self.clock())
            before.save(copy)
            machine_state.mark_unchecked(self.machine, copy)
            self.memory_copy = copy

    def _update_store_contract(self, store_format: int) -> None:
        """Keeps the format number in ``STORE.md`` current, before ``format`` is written.

        Setup creates the file; a migration only rewrites one that exists. Nothing in a run reads
        it, so on iCloud it may be in the cloud only: then it is named in the review instead of
        fetched, because a file that will not download must not stop the migration.
        """
        if not self.store.exists(STORE_CONTRACT):
            return
        if self.store.is_evicted(STORE_CONTRACT):
            self.findings.append(
                report.Finding(
                    RUN,
                    report.ACTION,
                    f"{STORE_CONTRACT} is not downloaded, so it still names an older store format; "
                    "run /m2b:m2b setup once to write it again",
                )
            )
            return
        write_store_contract(self.store, dataclasses.replace(self.settings, format=store_format))

    def _migrate(self, migration: migrations.Migration) -> None:
        """One migration, checked in code; on any failure ``memory/`` goes back and ``format`` stays."""
        before = memory_guard.Snapshot.take(self.store)
        self._save_memory_copy(before)
        try:
            migration.apply(self.store)
            after = memory_guard.Snapshot.take(self.store)
            problem = memory_guard.unsafe_line(before, after) or migration.problem(before, after)
            if problem is None:
                self._update_store_contract(migration.target)
                self.settings = write_store_format(self.store, migration.target)
        except Exception as error:
            before.restore(self.store)
            raise StepError(f"{migration.summary}: {error}; memory/ is as it was before the step") from error
        if problem is not None:
            before.restore(self.store)
            raise StepError(f"{migration.summary}: {problem}; memory/ is as it was before the step")
        self._report_fact_changes(migrations.step_name(migration), before, after, InboxBefore())

    def _harvest(self, tasks: Tasks, locale: Locale) -> None:
        result = harvest(self.store, tasks, locale.text(PREFIX_KEY), self.clock())
        self.findings += [report.Finding(HARVEST, report.ACTION, problem) for problem in result.problems]
        current_check.settle(self.store, tasks, self.clock().date(), task_list=self._task_list())

    def _journal(self, tasks: Tasks) -> None:
        result = write_journal(
            self.store,
            tasks,
            self.settings.journal_since,
            self.clock(),
            fetch_timeout_seconds=self.fetch_timeout_seconds,
        )
        self.findings += [report.Finding(JOURNAL, report.ACTION, problem) for problem in result.problems]

    def _task_list(self) -> str:
        return current_check.task_list_of(self.settings.tasks.backend, self.settings.tasks.list_name)

    def _ingest(self, token: str) -> Skipped | None:
        """The model only when something in the inbox can be filed: a file the last run could not file
        and that has not changed since is reported again, in code, and starts nothing."""
        inbox = self.store.scan(INBOX)
        # A capture that is not downloaded waits for a run that is due anyway: noted as it is now,
        # it makes no run due by itself (``due``), and no model step starts for it alone.
        machine_state.save_evicted_inbox(
            self.machine, {path: mtime for path in inbox.evicted if (mtime := self._mtime(path)) is not None}
        )
        if not inbox.files and not inbox.evicted:
            machine_state.save_stuck_inbox(self.machine, {})
            return Skipped("the inbox is empty")
        stuck = machine_state.load_stuck_inbox(self.machine)
        bundled = waiting_on_evicted(inbox.files, inbox.evicted)
        local = [path for path in inbox.files if path not in bundled]
        if all(self._mtime(path) == stuck.get(path) for path in local):
            # The ingest skill names evicted captures itself when it runs; here no model step does.
            self._name_evicted(inbox.evicted)
            self.findings += [
                report.Finding(INGEST, report.ACTION, text) for text in ingest.pending(self.store).problems
            ]
            if not local:
                return Skipped("only captures that are not downloaded wait in the inbox")
            return Skipped("only files the last run could not file wait in the inbox")
        # Only a step that ran to its end had normalize try every file; a failed one leaves them due.
        self._guarded(INGEST, INGEST_SKILL, INGEST_RULES, token)
        self._record_stuck(set(inbox.files))
        return None

    def _name_evicted(self, evicted: Sequence[str]) -> None:
        if evicted:
            text = f"not downloaded, left for the next run: {', '.join(evicted)}"
            self.findings.append(report.Finding(INGEST, report.INFO, text))

    def _record_stuck(self, seen: set[str]) -> None:
        """Notes the inbox files ingest saw and left because it cannot file them, so they make no run due.

        A file that came in during the step was never offered to normalize, so it stays due.
        """
        try:
            left = [path for path in ingest.pending(self.store).stuck if path in seen]
            machine_state.save_stuck_inbox(self.machine, {path: mtime for path in left if (mtime := self._mtime(path))})
        except (OSError, StoreError):
            # Without the note the file makes the next run due again, as it did before.
            machine_state.save_stuck_inbox(self.machine, {})

    def _mtime(self, path: str) -> int | None:
        try:
            return self.store.path(path).stat().st_mtime_ns
        except OSError:
            return None

    def _refresh(self, tasks: Tasks, locale: Locale, token: str) -> Skipped | None:
        """The model only for facts past their day, and allowed to edit those files alone (B41); quiet
        current items become questions to the owner (B42)."""
        found = expiry.due(self.store, self.clock().date())
        prefix = locale.text(current_check.PREFIX_KEY)
        current_check.ask(self.store, tasks, found.current, prefix, task_list=self._task_list())
        if self.refresh_all:
            return self._backfill([fact.path for fact in found.facts], token)
        if not found.facts:
            return Skipped("no fact is past its day")
        due_files = [fact.path for fact in found.facts]
        self._guarded(REFRESH, REFRESH_SKILL, refresh_rules(due_files), token, scope=RefreshScope(due_files))
        return None

    def _backfill(self, due_files: list[str], token: str) -> Skipped | None:
        """One model step per batch of undated lines, each allowed the due fact files and its own; a
        file that could not be read is reported, since no later run lists undated lines."""
        undated = self.undated if self.undated is not None else expiry.undated(self.store)
        self.findings += [
            report.Finding(REFRESH, report.ACTION, text)
            for text in [
                *(
                    f"{path} is not downloaded, so the backfill left it undated: run {fetch_command(path)}, "
                    "then m2b curate --refresh-all again"
                    for path in undated.evicted
                ),
                *(
                    f"{item.path} could not be read ({item.reason}), so the backfill left it undated"
                    for item in undated.unreadable
                ),
            ]
        ]
        work = expiry.batches(undated, BACKFILL_BATCH) or ([expiry.Batch([], [])] if due_files else [])
        if not work:
            return Skipped("no fact is past its day and no line read is undated")
        errors: list[str] = []
        for number, batch in enumerate(work, start=1):
            environ = {**self.environ, model.REFRESH_ALL_VARIABLE: batch.to_json()}
            files = due_files + batch.facts
            rules = refresh_rules(files, REFRESH_ALL_RULES)
            try:
                self._guarded(REFRESH, REFRESH_SKILL, rules, token, environ, RefreshScope(files, batch.current))
            except (StepError, StoreError) as error:
                errors.append(f"batch {number} of {len(work)}: {error}")
        if errors:
            raise StepError("; ".join(errors))
        return None

    def _sort(self, token: str) -> Skipped | None:
        """The fenced sorting step, then the check that it only moved lines and wrote headings."""
        path = f"{MEMORY}/{MEMORY_INDEX}"
        try:
            before = self.store.read_bytes(path)
        except FileNotFoundError:
            return Skipped(f"there is no {path} to sort")
        self._save_memory_copy(memory_guard.Snapshot.take(self.store))
        try:
            self._model(SORT_SKILL, SORT_RULES, token)
        # A step that failed after a bad edit still puts the file back, and says so; one stopped
        # by SIGTERM puts it back and lets the exit go on, also when that check fails.
        except BaseException as error:
            if not isinstance(error, Exception):
                with contextlib.suppress(Exception):
                    self._sorting_problem(path, before)
                raise
            problem = self._sorting_problem(path, before)
            if problem is None:
                raise
            raise StepError(f"{error}; {problem}; {path} is as it was before") from error
        problem = self._sorting_problem(path, before)
        if problem is not None:
            raise StepError(f"{problem}; {path} is as it was before")
        return None

    def _sorting_problem(self, path: str, before: bytes) -> str | None:
        """Whatever went wrong in the step, a file changed beyond sorting goes back."""
        try:
            after = self.store.read_bytes(path)
        except FileNotFoundError:
            after = b""
        problem = memory_guard.unsafe_line(
            memory_guard.Snapshot({path: before}), memory_guard.Snapshot({path: after})
        ) or sorting_problem(before.decode("utf-8", errors="replace"), after.decode("utf-8", errors="replace"))
        if problem is not None:
            self.store.replace(path, before)
        return problem

    def _lint(self, tasks: Tasks, token: str) -> None:
        """The model only for what needs reading: a broken memory link with exactly one candidate.

        Otherwise the code does what the lint skill would: the safe fixes, then every finding left
        goes to the run's review. A model step costs money and time at every run, so the code takes
        everything it can decide.
        """
        scanned = lint.scan(self.store, tasks)
        if any(finding.code == lint.BROKEN_LINK and len(finding.candidates) == 1 for finding in scanned.findings):
            self._guarded(LINT, LINT_SKILL, LINT_RULES, token)
            return
        if lint.fix(self.store, self.clock()):
            scanned = lint.scan(self.store, tasks)
        self.findings += [report.Finding(LINT, finding.kind, finding.text) for finding in scanned.findings]

    def _guarded(
        self,
        step: str,
        skill: str,
        rules: Sequence[str],
        token: str,
        environ: Mapping[str, str] | None = None,
        scope: RefreshScope | None = None,
    ) -> None:
        """A model step that may edit ``memory/``, compared with a snapshot afterwards, also when it failed.

        Without a snapshot there is nothing to compare with, so the model does not start.
        """
        before = memory_guard.Snapshot.take(self.store)
        inbox = self._inbox_before() if step == INGEST else InboxBefore()
        self._save_memory_copy(before)
        try:
            self._model(skill, rules, token, environ)
        # SIGTERM reaches here as ``SystemExit`` once the model is stopped: memory/ is checked and
        # put back before the runner goes, and the exit goes on.
        except BaseException as error:
            if not isinstance(error, Exception):
                # A check that fails must not keep the runner from stopping; the next run compares.
                with contextlib.suppress(Exception):
                    self._memory_problem(step, before, scope, inbox)
                raise
            problem = self._memory_problem(step, before, scope, inbox)
            if problem is None:
                raise
            raise StepError(f"{error}; {problem}") from error
        problem = self._memory_problem(step, before, scope, inbox)
        if problem is not None:
            raise StepError(problem)

    def _inbox_before(self) -> InboxBefore:
        files = set(self.store.scan(INBOX).files)
        flagged = {capture.file for capture in ingest.pending(self.store).captures if capture.facts_filed}
        return InboxBefore(files, flagged)

    def _memory_problem(
        self, step: str, before: memory_guard.Snapshot, scope: RefreshScope | None, inbox: InboxBefore
    ) -> str | None:
        """Why ``memory/`` went back to ``before``, or None when the step's edits stay (and are reported)."""
        after = memory_guard.Snapshot.take(self.store)
        problem = memory_guard.unsafe_line(before, after)
        if problem is None and scope is not None:
            problem = memory_guard.refresh_problem(before, after, scope.files, scope.current)
        if problem is not None:
            before.restore(self.store)
            # The captures are in the archive by now; what they said is found there, not in memory/.
            filed = self._filed(inbox)
            archived = f"; the captures it filed are in the archive: {', '.join(filed)}" if filed else ""
            # A capture still waiting must not tell the next run its facts are in memory/.
            unflagged = self._unflag(inbox)
            cleared = (
                f"; facts_filed was taken off {', '.join(unflagged)}, so the next run files their facts"
                if unflagged
                else ""
            )
            return f"{problem}; memory/ is as it was before the step{archived}{cleared}"
        if scope is None:
            self._report_fact_changes(step, before, after, inbox)
        return None

    def _filed(self, inbox: InboxBefore) -> list[str]:
        """The captures that left the inbox during the step, by name."""
        return sorted(PurePosixPath(path).name for path in inbox.files - set(self.store.scan(INBOX).files))

    def _unflag(self, inbox: InboxBefore) -> list[str]:
        """Takes ``facts_filed`` off the captures that gained it during the step; their names."""
        if not inbox.files:
            return []
        gained = [
            capture.file
            for capture in ingest.pending(self.store).captures
            if capture.facts_filed and capture.file not in inbox.facts_filed
        ]
        for name in gained:
            ingest.clear_facts_filed(self.store, name)
        return gained

    def _report_fact_changes(
        self, step: str, before: memory_guard.Snapshot, after: memory_guard.Snapshot, inbox: InboxBefore
    ) -> None:
        changes = memory_guard.fact_changes(before, after)
        if not changes:
            return
        self.fact_changes += [report.Finding(step, report.ACTION, change) for change in changes]
        filed = self._filed(inbox)
        captures = f"; captures filed in this step: {', '.join(filed)}" if filed else ""
        saved = self.memory_copy
        # The path comes first: the review cuts a finding at ``report.MAX_TEXT_CHARACTERS``, and a
        # long list of captures may lose its end, not the path the owner needs.
        self.fact_changes.append(
            report.Finding(
                step,
                report.ACTION,
                f"memory/ as it was before this run is in {saved}; check the changes above{captures}",
            )
        )

    def _model(self, skill: str, rules: Sequence[str], token: str, environ: Mapping[str, str] | None = None) -> None:
        plugin_dirs = {launcher.CORE_PLUGIN: launcher.PLUGIN_ROOT}
        run = model.model_step(
            self.config, self.machine, environ or self.environ, skill, rules, token, plugin_dirs, self.lock.pass_fds
        )
        if run.error:
            raise StepError(run.error)
        if run.denials:
            raise StepError(f"denied {len(run.denials)} tool call(s) outside its rules")

    def _parts(self, slot: str, token: str) -> None:
        for part in steps_in(slot, self.config.parts):
            self._step(part.name, functools.partial(self._part, part, token))

    def _part(self, part: Part, token: str) -> None:
        """A part's step, run from this plugin's folder while the part is on; a part that is off
        runs nothing."""
        assert part.step is not None
        command = [str(launcher.PLUGIN_ROOT / part.step.command[0]), *part.step.command[1:]]
        environ = {**self.environ, model.CURATION_RUN_VARIABLE: "1", report.RUN_TOKEN_VARIABLE: token}
        timeout = self.config.curation.model_timeout_minutes * 60
        with model.empty_folder(self.machine.temp_dir) as work:
            end = model.run_supervised(command, work, environ, timeout, pass_fds=self.lock.pass_fds)
        if end.timed_out:
            raise StepError(f"timed out after {self.config.curation.model_timeout_minutes} minutes")
        if end.returncode != 0:
            raise StepError(end.failure())

    def _finish(self, started: datetime.datetime, findings: list[report.Finding]) -> RunOutcome:
        failed = [step for step in self.steps if step.result == FAILED]
        message = "; ".join(f"{step.name}: {step.detail}" for step in failed)
        state = FAILED if failed else SUCCEEDED
        record = self._record(state, started, finished_at=self.clock(), message=message, findings=tuple(findings))
        self._close(record, message or "the run succeeded")
        return RunOutcome(state, message or "the curation run succeeded", record)

    def _close(self, record: RunRecord, message: str) -> None:
        """Writes the finished record, moves the backoff and logs the outcome once."""
        now = self.clock()
        if record.state == SUCCEEDED:
            machine_state.reset_backoff(self.machine)
        else:
            machine_state.record_failure(self.machine, now)
        try:
            self._write(record)
        except RunRecordWriteError as error:
            machine_state.log_event(
                self.machine, machine_state.UNRECORDED, f"{error}; the run {record.state}: {message}", now
            )
            return
        kind = machine_state.SUCCEEDED if record.state == SUCCEEDED else machine_state.FAILED
        machine_state.log_event(self.machine, kind, message, now)

    def _record(
        self,
        state: str,
        started: datetime.datetime,
        finished_at: datetime.datetime | None = None,
        message: str = "",
        deadline_at: datetime.datetime | None = None,
        findings: tuple[report.Finding, ...] = (),
    ) -> RunRecord:
        return RunRecord(
            state=state,
            machine_id=self.config.machine_id,
            started_at=started,
            finished_at=finished_at,
            message=message,
            deadline_at=deadline_at,
            last_succeeded_at=self.last_success,
            steps=tuple(self.steps),
            findings=findings,
            parts=names_on(self.config.parts),
        )

    def _write(self, record: RunRecord) -> None:
        try:
            write_run_record(self.store, record)
        except (OSError, StoreError) as error:
            raise RunRecordWriteError(f"the run record {RUN_RECORD} could not be written: {error}") from error

    def _step_timeouts(self) -> datetime.timedelta:
        """An upper bound on the run from its start: past it, a ``running`` record is an interrupted run."""
        part_steps = sum(len(steps_in(slot, self.config.parts)) for slot in CURATION_SLOTS)
        step = datetime.timedelta(
            minutes=self.config.curation.model_timeout_minutes, seconds=model.DEFAULT_GRACE_SECONDS
        )
        # Preflight fetches once, the journal once more for older month files.
        fetch = 2 * datetime.timedelta(seconds=self.fetch_timeout_seconds)
        backfill = len(expiry.batches(self.undated, BACKFILL_BATCH)) - 1 if self.undated is not None else 0
        model_steps = MODEL_STEPS + max(backfill, 0) + part_steps + (1 if self.sort_facts else 0)
        return fetch + step * model_steps + CODE_STEPS_MARGIN


def refresh_rules(due_files: Sequence[str], fixed: Sequence[str] = REFRESH_RULES) -> list[str]:
    """The refresh step's rules: the fixed ones, then Read and Edit for each fact file it works on."""
    rules = list(fixed)
    for relative in due_files:
        rules += [f"Read(<store>/{relative})", f"Edit(<store>/{relative})"]
    return rules


def _copy_started(copy: Path) -> datetime.datetime | None:
    """When the run that saved this copy started, from the copy's name (``machine_state.memory_copy``)."""
    try:
        return datetime.datetime.strptime(copy.name, "%Y%m%dT%H%M%SZ").replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return None


def _interrupted_changes(copy: Path, store: Store) -> list[report.Finding]:
    """The review findings for what ``memory/`` holds now against the copy a stopped run saved."""
    started = _copy_started(copy)
    run = f"the interrupted run of {started.astimezone():%Y-%m-%d %H:%M}" if started else "an interrupted run"
    try:
        before, after = memory_guard.Snapshot.load(copy), memory_guard.Snapshot.take(store)
    except (OSError, StoreError) as error:
        text = f"{run} could not be checked: memory/ could not be compared with its copy {copy}: {error}"
        return [report.Finding(RUN, report.ACTION, text)]
    # The lines are shown as the owner reads them: a character that hides text stays out of the review.
    changes = [f"{run}: {strip_unsafe(change)}" for change in memory_guard.fact_changes(before, after)]
    problem = memory_guard.unsafe_line(before, after)
    if problem is not None:
        changes.insert(0, f"{run}: {problem}")
    if not changes:
        return []
    check = f"memory/ as it was before that run is in {copy}; check the changes above"
    return [report.Finding(RUN, report.ACTION, text) for text in (*changes, check)]


def _preflight_paths(started: datetime.datetime) -> list[str]:
    """What the run reads or writes; ``state/integrations/`` belongs to integrations and is never read."""
    this_month = started.date().replace(day=1)
    last_month = (this_month - datetime.timedelta(days=1)).replace(day=1)
    journals = [
        f"{CORPUS}/{month.year:04d}/{month.month:02d}/{journal_name(month.year, month.month)}"
        for month in (last_month, this_month)
    ]
    return [
        STORE_SETTINGS_FILE_NAME,
        PROFILE_FILE_NAME,
        f"{STATE}/core",
        f"{STATE}/parts",
        MEMORY,
        TASKS,
        *journals,
        # Last: on a folder store a download is synchronous, so a capture that never downloads
        # must not use up the time before everything the run needs was asked for.
        INBOX,
    ]
