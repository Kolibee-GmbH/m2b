"""The ledger of the questions a curation run asks the owner in the task list: ask, remember, settle.

"Still current?" (``current_check``) and "Still needed?" (``lesson_check``) ask the same way. Each
question is one task, ``"<prefix> <text>"``, with a marker ``m2b:<kind> <key>``; the key is a short
hash, because a marker argument is one word. The keys asked, with what each asks about, are kept in
a file of the store with the task list they were asked in, so nothing is asked twice. What a
question is about, when it is due, when what it asks about is gone and what an answer does stay
with the module that asks it.

A question missing from the task list counts as deleted, the owner's no, only in the list it was
asked in and only where the list can say it holds every task. After setup switched to another
list, the questions still waiting are forgotten instead, so they are asked again in the new list
and nothing ends without an answer.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from m2b.config.json_file import read_store_json_object, write_store_json_object
from m2b.store.base import Store
from m2b.tasks import markers
from m2b.tasks.base import Task, Tasks

FORMAT = 1
_KEY_LENGTH = 12


def key_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:_KEY_LENGTH]


@dataclass(frozen=True)
class Wanted:
    """A question due now: its key, what the ledger keeps for it, and the text the task says."""

    key: str
    about: str
    text: str


@dataclass(frozen=True)
class Recorded:
    """The ledger's file: key to what it asks about, the list asked in (None for a file written
    before lists were kept), and the further maps of text a kind of question keeps."""

    asked: dict[str, str]
    task_list: str | None
    extra: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass(frozen=True)
class Answers:
    """The questions the owner answered since, and those deleted in the list they were asked in."""

    recorded: Recorded
    answered: dict[str, Task]
    deleted: list[str]

    @property
    def kept(self) -> list[str]:
        return [key for key, task in self.answered.items() if not task.dropped]

    @property
    def dropped(self) -> list[str]:
        """Dropped and deleted alike: a reminders app without a dropped state says no by deleting."""
        return [key for key, task in self.answered.items() if task.dropped] + self.deleted


@dataclass(frozen=True)
class Ledger:
    """One kind of question: its marker, its file, and the further maps of text that file keeps."""

    marker: str
    path: str
    extra: tuple[str, ...] = ()

    def load(self, store: Store) -> Recorded:
        raw = read_store_json_object(store, self.path) or {}
        task_list = raw.get("list")
        return Recorded(
            _texts(raw.get("asked")),
            task_list if isinstance(task_list, str) else None,
            {name: _texts(raw.get(name)) for name in self.extra},
        )

    def save(self, store: Store, recorded: Recorded) -> None:
        data: dict[str, object] = {"format": FORMAT, "asked": dict(sorted(recorded.asked.items()))}
        for name in self.extra:
            data[name] = dict(sorted(recorded.extra.get(name, {}).items()))
        if recorded.task_list is not None:
            data["list"] = recorded.task_list
        write_store_json_object(store, self.path, data)

    def questions(self, tasks: Tasks) -> dict[str, Task]:
        """The questions in the task list by key, answered ones too."""
        found: dict[str, Task] = {}
        for task in tasks.items(marker=self.marker, include_completed=True):
            marker = markers.marker_of(task.notes)
            if marker is not None and marker[1]:
                found[marker[1][0]] = task
        return found

    def ask(
        self,
        store: Store,
        tasks: Tasks,
        wanted: Sequence[Wanted],
        prefix: str,
        *,
        task_list: str,
        gone: Callable[[str, str | None], bool] | None,
    ) -> list[str]:
        """Closes each open question ``gone`` says has nothing left to answer (with its key and what
        the ledger keeps for it), then asks each wanted question not asked yet; what the new ones
        are about. ``gone`` is None where that cannot be told now: nothing is closed then."""
        recorded = self.load(store)
        # Questions asked in another list are asked again here; the old list is not read. A copy,
        # so that the comparison below sees what this run changed.
        asked = dict(recorded.asked) if recorded.task_list == task_list else {}
        questions = self.questions(tasks)
        if gone is not None:
            for key, task in questions.items():
                if not task.completed and gone(key, asked.get(key)):
                    tasks.delete(task.id)
                    asked.pop(key, None)
        new = []
        for question in wanted:
            if question.key in asked or question.key in questions:
                asked.setdefault(question.key, question.about)
                continue
            tasks.add(f"{prefix} {question.text}", markers.with_marker(self.marker, "", question.key))
            asked[question.key] = question.about
            new.append(question.about)
        if asked != recorded.asked or (asked and recorded.task_list != task_list):
            self.save(store, Recorded(asked, task_list, recorded.extra))
        return new

    def answers(self, store: Store, tasks: Tasks, *, task_list: str) -> Answers | None:
        """The answers to apply, or None where there are none. A question not in the list it was
        asked in was never seen there, and one a list cannot answer for may be a task the backend
        cannot read: neither counts as deleted."""
        recorded = self.load(store)
        questions = self.questions(tasks)
        answered = {key: task for key, task in questions.items() if task.completed}
        certain = recorded.task_list == task_list and tasks.lists_every_task()
        deleted = [key for key in recorded.asked if key not in questions] if certain else []
        if not answered and not deleted:
            return None
        return Answers(recorded, answered, deleted)

    def forget(
        self, store: Store, tasks: Tasks, answers: Answers, extra: Mapping[str, dict[str, str]] | None = None
    ) -> None:
        """After the answers are applied: forgets them, then removes the answered tasks, so a crash in
        between leaves at most a question whose answer is applied already, and applying it again
        changes nothing."""
        settled = set(answers.answered) | set(answers.deleted)
        asked = {key: about for key, about in answers.recorded.asked.items() if key not in settled}
        kept_extra = dict(answers.recorded.extra) if extra is None else dict(extra)
        self.save(store, Recorded(asked, answers.recorded.task_list, kept_extra))
        for task in answers.answered.values():
            tasks.delete(task.id)


def _texts(value: object) -> dict[str, str]:
    return {str(key): str(text) for key, text in value.items()} if isinstance(value, dict) else {}
