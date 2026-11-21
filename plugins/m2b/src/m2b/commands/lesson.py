"""``lesson add``: keep a lesson the owner said in a session, for the next curation run to file.

It reads one JSON object from standard input: ``text`` (the lesson as one sentence), ``kind``
(``knowledge`` or ``action``), optionally ``title``, for an action ``words`` (what a command holds
when the lesson applies), ``unless`` (what keeps it silent) and ``ask`` (Claude Code asks the owner
before the command instead of only reminding), and ``for``: ``every project`` (the default) or
``this project``, the repository of the working folder by its remote. A lesson for this project in
a folder without a remote is refused, as is one that is no lesson; both end with exit 2.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

from m2b import kept_lessons, session_remotes
from m2b.commands import Context, UsageError
from m2b.commands.backends import configured_store
from m2b.config.machine import load_machine_config
from m2b.config.store_settings import require_store_writable
from m2b.lessons import EVERY_PROJECT, KNOWLEDGE

ADD = "add"
THIS_PROJECT = "this project"
INPUT_LENGTH = 8 * 1024


def lesson_command(arguments: argparse.Namespace, context: Context) -> int:
    given = _read_input()
    lesson = _lesson(given, context)
    config = load_machine_config(context.machine)
    store = configured_store(config, context.machine)
    require_store_writable(store)
    try:
        is_new = kept_lessons.keep(store, lesson)
    except kept_lessons.LessonRefusedError as error:
        raise UsageError(str(error)) from error
    where = "every project" if lesson.target == EVERY_PROJECT else f"the repository {lesson.target}"
    print(("Kept" if is_new else "Kept before") + f": a lesson for {where}; the next curation run files it.")
    return 0


def _read_input() -> dict[str, object]:
    written = sys.stdin.buffer.read(INPUT_LENGTH + 1)
    try:
        if len(written) > INPUT_LENGTH:
            raise ValueError("longer than a lesson")
        given = json.loads(written.decode("utf-8"))
    except (ValueError, RecursionError) as error:
        raise UsageError("m2b lesson add reads one JSON object from standard input") from error
    if not isinstance(given, dict):
        raise UsageError("m2b lesson add reads one JSON object from standard input")
    return given


def _lesson(given: dict[str, object], context: Context) -> kept_lessons.KeptLesson:
    text, kind, title = given.get("text"), given.get("kind", KNOWLEDGE), given.get("title", "")
    words, unless, ask, target = (
        given.get("words", []),
        given.get("unless", []),
        given.get("ask", False),
        given.get("for"),
    )
    if not isinstance(text, str) or not isinstance(kind, str) or not isinstance(title, str):
        raise UsageError("a lesson gives text, kind and title as text")
    if not _texts(words) or not _texts(unless) or not isinstance(ask, bool):
        raise UsageError("a lesson gives words and unless as lists of text, and ask as true or false")
    if target not in (None, EVERY_PROJECT, THIS_PROJECT):
        raise UsageError(f"a lesson is for {EVERY_PROJECT!r} or {THIS_PROJECT!r}")
    return kept_lessons.KeptLesson(
        title,
        text,
        kind,
        _repository_here(context) if target == THIS_PROJECT else EVERY_PROJECT,
        datetime.date.today().isoformat(),
        tuple(words),  # type: ignore[arg-type]
        tuple(unless),  # type: ignore[arg-type]
        ask,
    )


def _texts(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _repository_here(context: Context) -> str:
    folder = Path(os.getcwd())
    try:
        return session_remotes.repository_of(folder, context.environ).addresses[0]
    except session_remotes.RepositoryNotKnownError as error:
        raise UsageError(
            f"a lesson for this project names its repository by its remote, and {folder} has none m2b can read; "
            "nothing was kept"
        ) from error
