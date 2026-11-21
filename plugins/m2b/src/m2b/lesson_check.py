"""Still needed? A lesson that went quiet goes to the owner as a question.

A lesson about a command fires when Claude is about to run that command (``tool_hook``). One that
has not fired since it was kept, for ``QUIET_AFTER``, may be about a command nobody runs any more,
or its words may never match. A lesson of the block, how to name or judge a thing, that the owner
has not corrected Claude on again for ``KNOWLEDGE_QUIET_AFTER`` since it was kept may have done its
work, or may be about something that no longer comes up, and every session still starts with it.
Whether either still holds only the owner knows, so the run asks, through the ledger a current item
that went quiet is asked through too (``question_ledger``): one task per quiet lesson,
``"<prefix> <the lesson's text>"``, with the marker ``m2b:lesson <key>``, the key a short hash of
the lesson's name, the questions asked in ``state/core/lesson-questions.json`` with the day the
owner last said each lesson still holds; a question whose lesson is gone is closed.

``settle`` runs at the start of the next run: a ticked question keeps the lesson and counts its quiet
time anew from that day; a dropped or deleted one removes the lesson's file from ``memory/lessons/``,
in code, as every lesson is written. No lesson ends without the owner's answer.

An action lesson's firings are counted on this machine (``action_lessons``), so its questions are
the curating machine's: a lesson that fires on another machine only can be asked about, and the
owner keeps it. A knowledge lesson's corrections are counted by the reading of the sessions
(``lesson_counts``, the day of the last run that counted one); while the sessions are not read, or
where those counts cannot be read, whether it went quiet is not known and it is not asked about. A
lesson a source states is out of the block and costs no session anything, so it is not asked about
either.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from dataclasses import dataclass

from m2b import action_lessons, lesson_counts, lessons
from m2b.config.errors import ConfigError
from m2b.notes.layout import STATE
from m2b.paths import MachinePaths
from m2b.question_ledger import Ledger, Wanted, key_of
from m2b.store.base import Store, StoreError
from m2b.tasks import markers
from m2b.tasks.base import Tasks

PREFIX_KEY = "lesson.prefix"
QUESTIONS_FILE = f"{STATE}/core/lesson-questions.json"
# A lesson's name to the day the owner last said it still holds.
STILL_HOLDS = "still_holds"
LEDGER = Ledger(markers.LESSON, QUESTIONS_FILE, extra=(STILL_HOLDS,))
QUIET_AFTER = datetime.timedelta(days=30)
KNOWLEDGE_QUIET_AFTER = datetime.timedelta(days=60)


@dataclass(frozen=True)
class QuietLesson:
    name: str
    text: str


def quiet(store: Store, machine: MachinePaths, today: datetime.date, *, corrections_counted: bool) -> list[QuietLesson]:
    """The action lessons that did not fire on this machine in the last ``QUIET_AFTER``, and the
    lessons of the block not corrected again for ``KNOWLEDGE_QUIET_AFTER``, each kept, or last said
    by the owner to still hold, at least that long ago. ``corrections_counted`` says whether the
    sessions are read, the one thing that counts corrections: without it a knowledge lesson's quiet is
    not known."""
    still_holds = LEDGER.load(store).extra[STILL_HOLDS]
    recent = action_lessons.fired(machine, today - QUIET_AFTER)
    standing = lessons.read_all(store)
    corrected = _last_corrected(store, standing)
    found = []
    for lesson in standing:
        kept = _day(lesson.kept)
        if kept is None:
            continue
        held = _day(still_holds.get(lesson.name, ""))
        since = max(kept, held) if held is not None else kept
        if lesson.kind == lessons.ACTION:
            if today - since >= QUIET_AFTER and recent.get(lesson.name, 0) == 0:
                found.append(QuietLesson(lesson.name, lesson.text))
        elif lesson.in_the_block and corrections_counted and corrected is not None:
            last = _day(corrected.get(lesson.name, ""))
            if last is not None:
                since = max(since, last)
            if today - since >= KNOWLEDGE_QUIET_AFTER:
                found.append(QuietLesson(lesson.name, lesson.text))
    return found


def _last_corrected(store: Store, standing: Sequence[lessons.Lesson]) -> dict[str, str] | None:
    try:
        return lesson_counts.last_corrected(store, {lesson.name: lesson.kept for lesson in standing})
    except (lesson_counts.LessonCountsError, ConfigError, StoreError):
        return None


def ask(store: Store, tasks: Tasks, found: Sequence[QuietLesson], prefix: str, *, task_list: str) -> list[str]:
    """Closes questions whose lesson is gone, then asks about each quiet lesson not asked yet; the
    names asked now. ``task_list`` names the list the tasks are in, ``<backend>:<list name>``."""
    wanted = [Wanted(key_of(lesson.name), lesson.name, lesson.text) for lesson in found]

    # Closed only where the lesson's file is gone: one that cannot be read now, not downloaded from
    # the cloud, still waits for its answer.
    def gone(_: str, name: str | None) -> bool:
        return name is not None and not store.exists(f"{lessons.FOLDER}/{name}")

    return LEDGER.ask(store, tasks, wanted, prefix, task_list=task_list, gone=gone)


def settle(store: Store, tasks: Tasks, today: datetime.date, *, task_list: str) -> list[str]:
    """Applies the owner's answers: a kept lesson is quiet anew from today, a dropped or deleted one is
    removed. The names of the lessons removed."""
    answers = LEDGER.answers(store, tasks, task_list=task_list)
    if answers is None:
        return []
    asked = answers.recorded.asked
    still_holds = dict(answers.recorded.extra[STILL_HOLDS])
    removed = []
    for key in answers.kept:
        name = asked.get(key)
        if name is not None:
            still_holds[name] = today.isoformat()
    for key in answers.dropped:
        name = asked.get(key)
        if name is not None and _remove(store, name):
            removed.append(name)
            still_holds.pop(name, None)
    LEDGER.forget(store, tasks, answers, {STILL_HOLDS: still_holds})
    return removed


def _remove(store: Store, name: str) -> bool:
    path = f"{lessons.FOLDER}/{name}"
    if not store.exists(path):
        return False
    store.delete(path)
    return True


def _day(text: str) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        return None
