"""The proposals task: the one task that says proposals from the sessions wait for an answer.

However many proposals wait, the task list holds one task for them, never one per proposal, so a
phone shows that something waits without a reminder for each. Like the review task it is found by
its marker, open or completed, so a title the person changed keeps it the same task. Its notes
say, in the profile's language, how many wait and where they are answered; a task list has no
operation to change a title, so the number is in the notes and the title stays.

The task is a sign and no answer: completing, dropping or deleting it changes no proposal. A task
the person put away comes back only with a proposal added since the task last told of them, not
with every run while the old ones wait. ``announced_until`` in the proposals file is that moment:
the newest addition an open task has shown. While the task is open, a run brings its number up to
date, and a run after which nothing waits completes it.

What waits is what ``proposal_answers.waiting`` says: the open proposals without an answer file.
When that cannot be looked at, this raises and the task stays as it is.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from m2b import proposal_answers, proposals
from m2b.locale import Locale
from m2b.review import COMPLETED, CREATED, NONE, REOPENED, UPDATED
from m2b.store.base import Store
from m2b.tasks import markers
from m2b.tasks.base import Task, Tasks

TITLE_KEY = "proposals.title"
ONE_KEY = "proposals.one"
MANY_KEY = "proposals.many"


@dataclass(frozen=True)
class TaskOutcome:
    """What happened to the task, and how many proposals wait."""

    change: str
    waiting: int

    @property
    def had_nothing_to_do(self) -> bool:
        """Nothing waits and no open task had to be completed."""
        return self.waiting == 0 and self.change == NONE


def update(store: Store, tasks: Tasks, locale: Locale) -> TaskOutcome:
    waiting = [entry for _, entry in proposal_answers.waiting(store).proposals]
    existing = _proposals_task(tasks)
    is_open = existing is not None and not existing.completed
    if not waiting:
        if existing is not None and is_open:
            tasks.complete(existing.id)
            return TaskOutcome(COMPLETED, 0)
        return TaskOutcome(NONE, 0)
    kept = proposals.load(store)
    newest = max(entry.since for entry in waiting)
    is_news = kept.announced_until is None or newest > kept.announced_until
    if not is_open and not is_news:
        return TaskOutcome(NONE, len(waiting))
    change = _show(tasks, existing, locale, len(waiting))
    # After the task, so a task list that failed leaves the proposals to be told of by the next run.
    if is_news:
        proposals.save(store, dataclasses.replace(kept, announced_until=newest))
    return TaskOutcome(change, len(waiting))


def _show(tasks: Tasks, existing: Task | None, locale: Locale, count: int) -> str:
    """Leaves an open task that says how many wait; a task that says so already is not written again."""
    text = locale.text(ONE_KEY) if count == 1 else locale.text(MANY_KEY, count=count)
    notes = markers.with_marker(markers.PROPOSALS, text)
    if existing is None:
        tasks.add(locale.text(TITLE_KEY), notes=notes)
        return CREATED
    if existing.completed:
        # Apple Reminders takes no new notes on a completed reminder.
        tasks.uncomplete(existing.id)
        tasks.set_notes(existing.id, notes)
        return REOPENED
    if existing.notes == notes:
        return NONE
    tasks.set_notes(existing.id, notes)
    return UPDATED


def _proposals_task(tasks: Tasks) -> Task | None:
    """The task, an open one first; there is only one unless the person copied it by hand."""
    found = tasks.items(marker=markers.PROPOSALS, include_completed=True)
    return next((task for task in found if not task.completed), found[0] if found else None)
