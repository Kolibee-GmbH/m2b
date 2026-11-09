"""The daily worklog, the add-on's ``before_ingest`` step: once a day, in a fixed order, restart-safe.

Running it at every curation run would cut sessions into pieces, and an unordered write would
double bookings after a crash.

When the last worklog ended less than 20 hours ago, the step does nothing; a period without
sessions, with every source read, only moves the watermark. Otherwise it collects
the facts since the watermark, has the model judge them through ``m2b curate model`` (the skill
``m2b:worklog-verdict`` reads the facts with ``m2b-worklog facts`` and hands its verdict to
``m2b-worklog verdict``), checks the verdict and plans what to write. Then, in this order:

1. the plan is recorded as the intent in ``state/addons/worklog/intent.json``;
2. the note goes into the inbox, unless the inbox or the corpus holds it already (ingest files it
   later in the same run, so the distillate's current section sees the day);
3. the ledger gets the period's spans, unless it holds the period;
4. ``ledger.csv`` and ``ledger.xlsx`` are regenerated;
5. each candidate is proposed, and the intent notes it as proposed;
6. the watermark moves to the period's end;
7. the intent is removed.

A rerun that finds an intent carries out that plan, not a new one, so each missing piece is written
once and nothing twice (B28). Nothing is written outside the inbox, ``state/addons/worklog/`` and
the task list: bookings are proposals, because a wrong one ends up on an invoice.
"""

from __future__ import annotations

import contextlib
import datetime
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from m2b_worklog import facts, ledger, verdict, writeup
from m2b_worklog.core import Core
from m2b_worklog.files import create_file, replace_file
from m2b_worklog.paths import WorklogPaths
from m2b_worklog.sources import READ as SOURCE_READ
from m2b_worklog.sources import SourceState
from m2b_worklog.sources.inbox import is_evicted

STATE_DIR = "state/addons/worklog"
INTENT = "intent.json"
INTENT_VERSION = 1
WATERMARK_VERSION = 1
DUE_AFTER = datetime.timedelta(hours=20)
FACTS_FILE = "facts.json"
VERDICT_FILE = "verdict.json"
VERDICT_SKILL = "m2b:worklog-verdict"
# The verdict's fence: its own two commands, read-only core commands, reports, memory and inbox.
VERDICT_RULES = (
    "Bash(m2b-worklog facts *)",
    "Bash(m2b-worklog verdict *)",
    "Bash(m2b search *)",
    "Bash(m2b tasks list *)",
    "Bash(m2b curate report *)",
    "Read(<store>/memory/**)",
    "Read(<store>/inbox/**)",
)


class DailyError(Exception):
    """The worklog could not be written; what is written stays, and the next run continues."""


@dataclass(frozen=True)
class Sources:
    """What the facts are read from on this machine, besides the store."""

    transcripts: Path
    herdr: SourceState


def run(paths: WorklogPaths, core: Core, now: datetime.datetime, sources: Sources) -> str:
    store = core.store()
    folder = store / STATE_DIR
    intent = read_intent(folder)
    if intent is not None:
        return "worklog: resumed; " + carry_out(store, intent, core)
    watermark = facts.read_watermark(store)
    if watermark is not None and now - watermark < DUE_AFTER:
        return f"worklog: not due, the last one ended {watermark.isoformat(timespec='minutes')}"
    profile = core.profile()
    inputs = facts.Inputs(store, paths.state_dir, sources.transcripts, paths.home, profile, now, herdr=sources.herdr)
    collected = facts.collect(inputs)
    if _nothing_to_judge(collected):
        start, end = collected["period"]["start"], collected["period"]["end"]
        _write_watermark(folder, end, writeup.period_id(start, end))
        return f"worklog: no sessions since {start}, nothing to judge"
    language = str(profile.get("language") or "en")
    hand_to_model(paths, store, language, collected)
    try:
        core.model(VERDICT_SKILL, VERDICT_RULES)
        judged = _read_verdict(paths, collected)
    finally:
        # The facts hold the owner's prompts; once judged, or not, they are not kept on disk.
        clear_handed(paths)
    plan = writeup.build(collected, judged, language)
    intent = {"version": INTENT_VERSION, "plan": plan.as_json(), "proposed": []}
    _write_intent(folder, intent)
    return "worklog: " + carry_out(store, intent, core)


def carry_out(store: Path, intent: dict[str, Any], core: Core) -> str:
    folder = store / STATE_DIR
    plan = writeup.Plan.from_json(intent["plan"])
    wrote_note = _write_note(store, plan)
    added = ledger.add(folder, plan.period_id, plan.start, plan.end, plan.spans)
    ledger.export(folder)
    proposed: list[str] = intent["proposed"]
    for text in plan.candidates:
        if text in proposed:
            continue
        core.propose(text)
        proposed.append(text)
        _write_intent(folder, intent)
    _move_watermark(folder, plan)
    (folder / INTENT).unlink()
    parts = [
        f"note {'written' if wrote_note else 'already there'}: inbox/{plan.note_name}",
        f"{len(plan.spans)} spans {'added to' if added else 'already in'} the ledger",
        f"{len(plan.candidates)} candidates proposed",
    ]
    return ", ".join(parts)


def read_intent(folder: Path) -> dict[str, Any] | None:
    path = folder / INTENT
    if not path.exists():
        return None
    if is_evicted(path):
        raise DailyError(f"{STATE_DIR}/{INTENT} is not downloaded; m2b store fetch {STATE_DIR}/{INTENT} downloads it")
    try:
        intent: Any = json.loads(path.read_text(encoding="utf-8"))
        writeup.Plan.from_json(intent["plan"])
        if not isinstance(intent["proposed"], list):
            raise TypeError("proposed is not a list")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise DailyError(
            f"the unfinished worklog {STATE_DIR}/{INTENT} cannot be read ({error}); fix or remove it by hand"
        ) from error
    return dict(intent)


def facts_for_model(paths: WorklogPaths) -> dict[str, Any]:
    """What ``m2b-worklog facts`` prints: the facts being judged, with the store and the language."""
    path = paths.run_dir / FACTS_FILE
    try:
        handed: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise DailyError(f"no worklog is being judged ({error}); m2b-worklog run starts one") from error
    return dict(handed)


def accept_verdict(paths: WorklogPaths, raw: str) -> list[str]:
    """What ``m2b-worklog verdict`` does: the problems with the verdict, or none once it is stored."""
    try:
        judged = json.loads(raw)
    except ValueError as error:
        return [f"the verdict is not JSON: {error}"]
    problems = verdict.problems_of(judged, facts_for_model(paths)["facts"])
    if not problems:
        replace_file(paths.run_dir / VERDICT_FILE, (json.dumps(judged, ensure_ascii=False, indent=1) + "\n").encode())
    return problems


def hand_to_model(paths: WorklogPaths, store: Path, language: str, collected: Mapping[str, Any]) -> None:
    """The facts for ``m2b-worklog facts``; while they are there, a worklog is being judged."""
    paths.run_dir.mkdir(parents=True, exist_ok=True)
    clear_handed(paths)
    handed = {"store": str(store), "language": language, "facts": collected}
    replace_file(paths.run_dir / FACTS_FILE, (json.dumps(handed, ensure_ascii=False, indent=1) + "\n").encode())


def clear_handed(paths: WorklogPaths) -> None:
    for name in (FACTS_FILE, VERDICT_FILE):
        with contextlib.suppress(FileNotFoundError):
            (paths.run_dir / name).unlink()


def _read_verdict(paths: WorklogPaths, collected: Mapping[str, Any]) -> dict[str, Any]:
    path = paths.run_dir / VERDICT_FILE
    try:
        judged: Any = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise DailyError(f"the model step {VERDICT_SKILL} handed in no verdict") from error
    except (OSError, ValueError) as error:
        raise DailyError(f"the verdict cannot be read ({error})") from error
    problems = verdict.problems_of(judged, collected)
    if problems:
        raise DailyError(f"the verdict does not fit the facts: {problems[0]}")
    return dict(judged)


def _write_note(store: Path, plan: writeup.Plan) -> bool:
    """False when the note is in the inbox or already filed into the corpus by an earlier ingest."""
    end = datetime.datetime.fromisoformat(plan.end).astimezone(datetime.timezone.utc)
    if (store / "corpus" / f"{end:%Y}" / f"{end:%m}" / plan.note_name).exists():
        return False
    inbox = store / "inbox"
    inbox.mkdir(exist_ok=True)
    return create_file(inbox / plan.note_name, plan.note_text.encode("utf-8"))


def _nothing_to_judge(collected: Mapping[str, Any]) -> bool:
    """No session, and every source was read: a day without work costs no model run and no note.

    With a source that could not be read, no session may mean "could not look"; that period goes to
    the model, and its note names what was not read.
    """
    if collected["sessions"]:
        return False
    return all(source["state"] == SOURCE_READ for source in collected["sources"].values())


def _move_watermark(folder: Path, plan: writeup.Plan) -> None:
    _write_watermark(folder, plan.end, plan.period_id)


def _write_watermark(folder: Path, end: str, period: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    mark = {"version": WATERMARK_VERSION, "end": end, "period": period}
    replace_file(folder / "watermark.json", (json.dumps(mark) + "\n").encode())


def _write_intent(folder: Path, intent: Mapping[str, Any]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    replace_file(folder / INTENT, (json.dumps(intent, ensure_ascii=False, indent=1) + "\n").encode())
