"""The review task, run step 8: the one task that holds what the owner must do after a run (B14, B15).

Action findings and failed steps go into its notes, after the marker line and the time of the run,
one paragraph each; the words around them are in the profile's language, the findings themselves
as the steps wrote them. Info findings stay in the run record. The task is found by its marker,
open or completed, so a title the owner changed keeps it the same task, and a completed one is
reopened rather than a second made. A run with nothing for the owner completes an open one.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from dataclasses import dataclass

from m2b.curate.report import INFO, Finding, one_line
from m2b.locale import Locale
from m2b.tasks import markers
from m2b.tasks.base import Task, Tasks

TITLE_KEY = "review.title"
RUN_KEY = "review.run"
FAILURE_KEY = "review.failure"
CREATED = "created"
UPDATED = "updated"
REOPENED = "reopened"
COMPLETED = "completed"
NONE = "none"


@dataclass(frozen=True)
class StepFailure:
    step: str
    error: str


@dataclass(frozen=True)
class ReviewOutcome:
    task_id: str | None
    change: str


def update_review(
    tasks: Tasks,
    findings: Sequence[Finding],
    failures: Sequence[StepFailure],
    run_at: datetime.datetime,
    locale: Locale,
) -> ReviewOutcome:
    existing = _review_task(tasks)
    # Everything but info reaches the owner, a kind nobody knows included.
    paragraphs = [f"{finding.step}: {one_line(finding.text)}" for finding in findings if finding.kind != INFO]
    paragraphs += [locale.text(FAILURE_KEY, step=failure.step, error=one_line(failure.error)) for failure in failures]
    if not paragraphs:
        if existing is not None and not existing.completed:
            tasks.complete(existing.id)
            return ReviewOutcome(existing.id, COMPLETED)
        return ReviewOutcome(existing.id if existing else None, NONE)
    notes = "\n\n".join(
        [
            "\n".join(
                [
                    markers.marker_line(markers.REVIEW),
                    locale.text(RUN_KEY, time=f"{run_at.astimezone():%Y-%m-%d %H:%M}"),
                ]
            ),
            *paragraphs,
        ]
    )
    if existing is None:
        return ReviewOutcome(tasks.add(locale.text(TITLE_KEY), notes=notes), CREATED)
    change = UPDATED
    if existing.completed:
        # Apple Reminders takes no new notes on a completed reminder.
        tasks.uncomplete(existing.id)
        change = REOPENED
    tasks.set_notes(existing.id, notes)
    return ReviewOutcome(existing.id, change)


def review_is_open(tasks: Tasks) -> bool:
    """Whether the owner has a review task they have not completed or deleted yet."""
    existing = _review_task(tasks)
    return existing is not None and not existing.completed


def _review_task(tasks: Tasks) -> Task | None:
    """The review task, an open one first; there is only one unless the owner copied it by hand."""
    found = tasks.items(marker=markers.REVIEW, include_completed=True)
    return next((task for task in found if not task.completed), found[0] if found else None)
