"""``status``: the state of curation in one answer, on any machine, so the band can show a
hanging or failed run at once.

Inbox count, the run record, whether a run is due (only on the curating machine, the only one
where that question has an answer), whether the backends can be reached, where sessions are
read for proposals or were, how many of the proposals the person kept lately, and how many
proposals sessions handed in wait for the next run to take them in, and how large everything is
that a session in this folder starts with (``start_size``). The backend probes
start other programs, so their answer is kept for 5 minutes in the machine state; the rest is read
fresh. Each part that cannot be looked at says why instead of disappearing.

A ``running`` record counts as running until its deadline; on this machine, also only while a run
holds the lock, since a runner killed with nothing left holding the lock cannot finish its run.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime
import json
from typing import Any

from m2b import handed_in, lessons, proposal_answers, proposals, start_size
from m2b.addons import ADDONS, is_on
from m2b.atomic_file import replace_atomically
from m2b.commands import Context
from m2b.commands.backends import configured_store, configured_tasks
from m2b.commands.doctor import Check, calendar_check, probe
from m2b.commands.output import print_json
from m2b.config import store_settings
from m2b.config.errors import ConfigError
from m2b.config.machine import MachineConfig, load_machine_config
from m2b.config.store_settings import describe_format, format_state, load_store_settings
from m2b.curate import machine_state
from m2b.curate.due import PAUSED_NOTE, check_due
from m2b.glean import AGENT, KINDS, PASTED, TOOL, TYPED, WORKED
from m2b.hook_input import project_folder
from m2b.notes.characters import with_hidden_written_out
from m2b.notes.layout import INBOX
from m2b.paths import MachinePaths
from m2b.run_record import RUNNING, RunRecordError, is_interrupted, load_run_record
from m2b.store.base import Store, StoreError

CACHE_FILE = "status-cache.json"
PROBE_MAX_AGE = datetime.timedelta(minutes=5)
INTERRUPTED = "interrupted"


def status_command(arguments: argparse.Namespace, context: Context) -> int:
    config = load_machine_config(context.machine)
    answer = status_answer(config, context)
    # Only here, not in the band's answer: it reads files outside the store and changes only when
    # the owner edits them. The worklog's session start runs ``status --json`` too; the part costs
    # it about a millisecond for Claude Code's files and one read of the distillate.
    folder = project_folder(context.environ)
    answer["session_start"] = start_size.measure(config, context.machine, context.environ, folder)
    if arguments.json:
        print_json(answer)
    else:
        _print_text(answer)
        for line in start_size.text_lines(answer["session_start"]):
            print(line)
    return 0


def status_answer(config: MachineConfig, context: Context, tasks_check: Check | None = None) -> dict[str, Any]:
    """The answer of ``status --json``; ``tasks_check`` is a probe of the task list the caller just made,
    used in place of probing it again."""
    store = configured_store(config, context.machine)
    now = datetime.datetime.now().astimezone()
    answer: dict[str, Any] = {"machine_id": config.machine_id}
    answer["addons"] = {addon.name: is_on(config.addons, addon.name) for addon in ADDONS}
    try:
        settings = load_store_settings(store)
        curating: str | None = settings.curating_machine
        answer["store_format"] = {
            "store": settings.format,
            "known": store_settings.KNOWN_STORE_FORMAT,
            "state": format_state(settings),
            "detail": describe_format(settings),
        }
    except (ConfigError, StoreError) as error:
        curating = None
        answer["store_error"] = str(error)
    answer["curating_machine"] = curating
    answer["this_machine_curates"] = curating == config.machine_id
    answer["inbox"] = _inbox(store)
    answer["run"] = _run(store, context.machine, config.machine_id, now)
    answer["last_attempt"] = _last_attempt(context.machine, answer["run"])
    if curating == config.machine_id:
        due = check_due(store, context.machine, now)
        answer["due"] = {"due": due.due, "reason": due.reason}
    else:
        answer["due"] = None
    answer["paused"] = config.curation.paused
    checked_at, backends = _backends(config, context, now, tasks_check)
    answer["backends"] = backends
    answer["backends_checked_at"] = checked_at
    answers = _proposal_answers(store, config, now)
    if answers is not None:
        answer["proposal_answers"] = answers
    answer["handed_in"] = _handed_in(store)
    answer["lessons"] = _lessons(store)
    return answer


def _lessons(store: Store) -> dict[str, Any]:
    """How many lessons every session starts with, and those left out because their source states
    them now, by name and source (B258)."""
    found = lessons.read_all(store)
    return {
        "in_every_session": len(lessons.fitting(found)[0]),
        "kept_at_source": [
            {"name": with_hidden_written_out(lesson.name), "source": with_hidden_written_out(lesson.kept_at or "")}
            for lesson in lessons.kept_at_source(found)
        ],
    }


def probe_backends(
    config: MachineConfig, context: Context, tasks_check: Check | None = None
) -> dict[str, dict[str, str]]:
    checks = [
        probe("store", lambda: _check_store(config, context.machine)),
        tasks_check
        if tasks_check is not None
        else probe("tasks", lambda: configured_tasks(config, context.machine).check_reachable()),
        calendar_check(config),
    ]
    return {check.name: {"state": check.state, "detail": check.detail} for check in checks}


def _check_store(config: MachineConfig, machine: MachinePaths) -> None:
    load_store_settings(configured_store(config, machine))


def _inbox(store: Store) -> dict[str, Any]:
    try:
        scan = store.scan(INBOX)
    except StoreError as error:
        return {"error": str(error)}
    return {"count": len(scan.files) + len(scan.evicted), "evicted": len(scan.evicted)}


def _handed_in(store: Store) -> dict[str, Any]:
    """How many proposals sessions handed in wait for the next run, counted like the inbox.

    Between the call of a session and the run nothing else shows that a session proposed anything.
    """
    try:
        waiting = handed_in.waiting(store)
    except StoreError as error:
        return {"error": str(error)}
    return {"count": waiting.count, "evicted": waiting.evicted}


def _run(store: Store, machine: MachinePaths, this_machine: str, now: datetime.datetime) -> dict[str, Any]:
    try:
        record = load_run_record(store)
    except (RunRecordError, StoreError) as error:
        return {"error": str(error)}
    if record is None:
        return {"state": "none"}
    state = record.state
    if state == RUNNING and (
        is_interrupted(record, now) or (record.machine_id == this_machine and not machine_state.lock_is_held(machine))
    ):
        state = INTERRUPTED
    run: dict[str, Any] = {"state": state, "machine_id": record.machine_id, "started_at": _iso(record.started_at)}
    if record.finished_at:
        run["finished_at"] = _iso(record.finished_at)
    if record.last_success:
        run["last_succeeded_at"] = _iso(record.last_success)
    if record.message:
        run["message"] = record.message
    return run


def _proposal_answers(store: Store, config: MachineConfig, now: datetime.datetime) -> dict[str, Any] | None:
    """How the proposals from the sessions ended lately, and the counts per kind since the first one.

    None, so the part is left out, on a machine that neither reads sessions nor lets them hand in,
    in a store that never held a proposal: there the part would say nothing to anyone.
    ``keep_rate`` is null without an answer in the period, which is not a rate of 0. ``ways`` says
    the same per way a proposal came, a reading or a session that handed it in, and per source of
    its words, with how many wait for an answer and how many have one that waits for the next run:
    whether sessions hand in, and whether what they hand in is kept.
    """
    try:
        current = proposals.load(store)
        answered = proposal_answers.awaiting_a_run(current.entries, proposal_answers.read(store))
    except (ConfigError, proposals.ProposalsError, StoreError) as error:
        return {"error": str(error)}
    if not (config.curation.read_sessions or config.sessions.propose or current.entries or current.counts):
        return None
    start = now - proposals.KEEP_RATE_PERIOD
    outcomes = proposals.outcomes_since(current, start)
    ways = proposals.by_way_and_source(current, start, answered)
    rate = outcomes.keep_rate
    return {
        "days": proposals.KEEP_RATE_PERIOD.days,
        "kept": outcomes.kept,
        "dropped": outcomes.dropped,
        "expired": outcomes.expired,
        "keep_rate": None if rate is None else round(rate, 2),
        "counts": {kind: dataclasses.asdict(current.tally(kind)) for kind in KINDS},
        "ways": {
            way: {source: dataclasses.asdict(counts) for source, counts in sorted(sources.items())}
            for way, sources in sorted(ways.items())
        },
    }


def _last_attempt(machine: MachinePaths, run: dict[str, Any]) -> dict[str, str] | None:
    """An attempt after the last recorded run that started none, because none was due or the machine
    is paused, so a scheduled attempt shows it reached m2b."""
    attempt = machine_state.last_attempt(machine)
    if attempt is None or attempt.time is None:
        return None
    last_run = run.get("finished_at") or run.get("started_at")
    if last_run is not None and attempt.time <= datetime.datetime.fromisoformat(last_run):
        return None
    return {"kind": attempt.kind, "at": _iso(attempt.time), "message": attempt.message}


def _backends(
    config: MachineConfig, context: Context, now: datetime.datetime, tasks_check: Check | None = None
) -> tuple[str, dict[str, Any]]:
    cache = context.machine.state_dir / CACHE_FILE
    try:
        raw = json.loads(cache.read_text(encoding="utf-8"))
        checked_at = datetime.datetime.fromisoformat(raw["checked_at"])
        if datetime.timedelta(0) <= now - checked_at < PROBE_MAX_AGE and isinstance(raw["backends"], dict):
            return raw["checked_at"], raw["backends"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    backends = probe_backends(config, context, tasks_check)
    checked = _iso(now)
    data = json.dumps({"checked_at": checked, "backends": backends}) + "\n"
    # A cache that cannot be written only means probing again next time.
    with contextlib.suppress(OSError):
        replace_atomically(cache, data.encode("utf-8"), context.machine.temp_dir)
    return checked, backends


def _print_text(answer: dict[str, Any]) -> None:
    inbox = answer["inbox"]
    if "error" in inbox:
        print(f"inbox: could not look: {inbox['error']}")
    else:
        print(f"inbox: {inbox['count']}" + (f" ({inbox['evicted']} not downloaded)" if inbox["evicted"] else ""))
    run = answer["run"]
    if "error" in run:
        print(f"run: could not look: {run['error']}")
    elif run["state"] == "none":
        print("run: no curation run yet")
    else:
        when = run.get("finished_at") or run["started_at"]
        line = f"run: {run['state']} on {run['machine_id']} at {when}"
        print(line + (f": {run['message']}" if run.get("message") else ""))
    attempt = answer["last_attempt"]
    if attempt is not None:
        print(f"last attempt: {attempt['kind'].replace('_', ' ')} at {attempt['at']}")
    curating = answer["curating_machine"] or "unknown"
    due = answer["due"]
    if due is None:
        print(f"due: asked on {curating}, the curating machine")
    else:
        print(f"due: {'yes' if due['due'] else 'no'} ({due['reason']})")
    if answer["paused"]:
        print(f"paused: {PAUSED_NOTE}")
    for name, check in answer["backends"].items():
        print(f"{name}: {check['state']}" + (f" ({check['detail']})" if check.get("detail") else ""))
    store_format = answer.get("store_format")
    if store_format is not None:
        print(f"store format: {store_format['state']} ({store_format['detail']})")
    answers = answer.get("proposal_answers")
    if answers is not None:
        print(f"proposals: {_proposal_answers_text(answers)}")
        for line in _proposal_ways_lines(answers):
            print(line)
    handed = answer["handed_in"]
    if "error" in handed:
        print(f"handed in: could not look: {handed['error']}")
    elif handed["count"]:
        not_downloaded = f" ({handed['evicted']} not downloaded)" if handed["evicted"] else ""
        print(f"handed in: {handed['count']} waiting for the next curation run{not_downloaded}")
    kept = answer["lessons"]
    if kept["in_every_session"] or kept["kept_at_source"]:
        at_source = "".join(
            f"; {item['name']} is kept at its source, {item['source']}" for item in kept["kept_at_source"]
        )
        print(f"lessons: {kept['in_every_session']} in every session{at_source}")
    on = [name for name, is_addon_on in answer["addons"].items() if is_addon_on]
    print(f"add-ons on: {', '.join(on) if on else 'none'}")


def _proposal_answers_text(answers: dict[str, Any]) -> str:
    if "error" in answers:
        return f"could not look: {answers['error']}"
    answered = answers["kept"] + answers["dropped"]
    if answered:
        text = (
            f"kept {answers['kept']} of {answered} answered in the last {answers['days']} days "
            f"({round(100 * answers['kept'] / answered)}%)"
        )
    else:
        text = f"no answer in the last {answers['days']} days"
    return text + (f", {answers['expired']} expired without an answer" if answers["expired"] else "")


# How a line names the way a proposal came and where its words stand; another word is shown as it is.
_WAYS = {proposals.READING: "a reading found in", proposals.SESSION: "sessions handed in from"}
_SOURCES = {
    TYPED: "typed words",
    PASTED: "pasted text",
    TOOL: "a tool's result",
    AGENT: "an answer of Claude",
    WORKED: "repositories worked in on two days",
}


def _proposal_ways_lines(answers: dict[str, Any]) -> list[str]:
    """One line per way and source with something: what waits, and how the period's answers ended."""
    lines = []
    for way, sources in answers.get("ways", {}).items():
        for source, counts in sources.items():
            answered = f"{counts['answered']} answered for the next run, " if counts["answered"] else ""
            lines.append(
                f"proposals {_WAYS.get(way, f'{way} from')} {_SOURCES.get(source, source)}: "
                f"{counts['waiting']} waiting, {answered}{counts['kept']} kept, {counts['dropped']} dropped, "
                f"{counts['expired']} expired in the last {answers['days']} days"
            )
    return lines


def _iso(moment: datetime.datetime) -> str:
    return moment.isoformat(timespec="seconds")
