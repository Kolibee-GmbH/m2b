"""Still needed? An action lesson that did not fire for a month goes to the owner as a question.

A lesson about a command fires when Claude is about to run that command (``tool_hook``). One that
has not fired since it was kept, for ``QUIET_AFTER``, may be about a command nobody runs any more,
or its words may never match: whether it still holds only the owner knows, so the run asks, the
same way it asks about a current item that went quiet (``current_check``). ``ask`` makes one task per
quiet lesson, ``"<prefix> <the lesson's text>"``, with the marker ``m2b:lesson <key>``, the key a short
hash of the lesson's name, because a marker argument is one word. The questions asked are kept in
``state/core/lesson-questions.json``, so a lesson is never asked twice; a question whose lesson is
gone is closed.

``settle`` runs at the start of the next run: a ticked question keeps the lesson and counts its quiet
time anew from that day; a dropped or deleted one removes the lesson's file from ``memory/lessons/``,
in code, as every lesson is written. No lesson ends without the owner's answer.

Only lessons about a command are asked about: their firings are counted. Whether a period touched a
lesson about how to name or judge a thing would take a model's judgement, which is not asked for
here. The firings are this machine's (``action_lessons``), so the questions are the curating
machine's: a lesson that fires on another machine only can be asked about, and the owner keeps it.
"""

from __future__ import annotations

import datetime
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

from m2b import action_lessons, lessons
from m2b.config.json_file import read_store_json_object, write_store_json_object
from m2b.notes.layout import STATE
from m2b.paths import MachinePaths
from m2b.store.base import Store
from m2b.tasks import markers
from m2b.tasks.base import Task, Tasks

PREFIX_KEY = "lesson.prefix"
QUESTIONS_FILE = f"{STATE}/core/lesson-questions.json"
FORMAT = 1
QUIET_AFTER = datetime.timedelta(days=30)


@dataclass(frozen=True)
class QuietLesson:
    name: str
    text: str


def key_of(name: str) -> str:
    return hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]


def quiet(store: Store, machine: MachinePaths, today: datetime.date) -> list[QuietLesson]:
    """The action lessons that did not fire on this machine in the last ``QUIET_AFTER`` and were kept,
    or last said by the owner to still hold, at least that long ago."""
    still_holds = _load(store).still_holds
    recent = action_lessons.fired(machine, today - QUIET_AFTER)
    found = []
    for lesson in lessons.read_all(store):
        if lesson.kind != lessons.ACTION:
            continue
        kept = _day(lesson.kept)
        if kept is None:
            continue
        held = _day(still_holds.get(lesson.name, ""))
        since = max(kept, held) if held is not None else kept
        if today - since < QUIET_AFTER:
            continue
        if recent.get(lesson.name, 0) == 0:
            found.append(QuietLesson(lesson.name, lesson.text))
    return found


def ask(store: Store, tasks: Tasks, found: Sequence[QuietLesson], prefix: str, *, task_list: str) -> list[str]:
    """Closes questions whose lesson is gone, then asks about each quiet lesson not asked yet; the
    names asked now. ``task_list`` names the list the tasks are in, ``<backend>:<list name>``."""
    state = _load(store)
    # A copy: what was asked before is compared with what is asked now.
    asked = dict(state.asked) if state.task_list == task_list else {}
    questions = _questions(tasks)
    for key, task in questions.items():
        # Closed only where the lesson's file is gone: one that cannot be read now, not downloaded
        # from the cloud, still waits for its answer.
        name = asked.get(key)
        if not task.completed and name is not None and not store.exists(f"{lessons.FOLDER}/{name}"):
            tasks.delete(task.id)
            asked.pop(key, None)
    new = []
    for lesson in found:
        key = key_of(lesson.name)
        if key in asked or key in questions:
            asked.setdefault(key, lesson.name)
            continue
        tasks.add(f"{prefix} {lesson.text}", markers.with_marker(markers.LESSON, "", key))
        asked[key] = lesson.name
        new.append(lesson.name)
    if asked != state.asked or (asked and state.task_list != task_list):
        _save(store, _State(asked, state.still_holds, task_list))
    return new


def settle(store: Store, tasks: Tasks, today: datetime.date, *, task_list: str) -> list[str]:
    """Applies the owner's answers: a kept lesson is quiet anew from today, a dropped or deleted one is
    removed. The names of the lessons removed."""
    state = _load(store)
    questions = _questions(tasks)
    answered = {key: task for key, task in questions.items() if task.completed}
    # A question not in the list it was asked in was never seen there, so it is not taken as deleted.
    certain = state.task_list == task_list and tasks.lists_every_task()
    deleted = [key for key in state.asked if key not in questions] if certain else []
    if not answered and not deleted:
        return []
    still_holds = dict(state.still_holds)
    removed = []
    for key, task in answered.items():
        name = state.asked.get(key)
        if name is not None and not task.dropped:
            still_holds[name] = today.isoformat()
    for key in [key for key, task in answered.items() if task.dropped] + deleted:
        name = state.asked.get(key)
        if name is not None and _remove(store, name):
            removed.append(name)
            still_holds.pop(name, None)
    asked = {key: name for key, name in state.asked.items() if key not in answered and key not in deleted}
    _save(store, _State(asked, still_holds, state.task_list))
    for task in answered.values():
        tasks.delete(task.id)
    return removed


def _remove(store: Store, name: str) -> bool:
    path = f"{lessons.FOLDER}/{name}"
    if not store.exists(path):
        return False
    store.delete(path)
    return True


def _questions(tasks: Tasks) -> dict[str, Task]:
    found: dict[str, Task] = {}
    for task in tasks.items(marker=markers.LESSON, include_completed=True):
        marker = markers.marker_of(task.notes)
        if marker is not None and marker[1]:
            found[marker[1][0]] = task
    return found


@dataclass(frozen=True)
class _State:
    # Key of a question to the name of the lesson it asks about.
    asked: dict[str, str]
    # A lesson's name to the day the owner last said it still holds.
    still_holds: dict[str, str]
    task_list: str | None


def _load(store: Store) -> _State:
    raw = read_store_json_object(store, QUESTIONS_FILE) or {}
    asked, holds, task_list = raw.get("asked"), raw.get("still_holds"), raw.get("list")
    return _State(
        {str(key): str(name) for key, name in asked.items()} if isinstance(asked, dict) else {},
        {str(name): str(day) for name, day in holds.items()} if isinstance(holds, dict) else {},
        task_list if isinstance(task_list, str) else None,
    )


def _save(store: Store, state: _State) -> None:
    data: dict[str, object] = {
        "format": FORMAT,
        "asked": dict(sorted(state.asked.items())),
        "still_holds": dict(sorted(state.still_holds.items())),
    }
    if state.task_list is not None:
        data["list"] = state.task_list
    write_store_json_object(store, QUESTIONS_FILE, data)


def _day(text: str) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        return None
