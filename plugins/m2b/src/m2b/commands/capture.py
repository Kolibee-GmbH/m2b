"""``capture``: the text as an argument, or on standard input with ``-`` or no argument;
``capture-file``: a file of the machine with words beside it, which no skill runs without asking.

With ``--project`` the capture makes the project of the working folder known: it names the
repository by its remote (``project_capture``), and a folder in no repository or in one without a
remote ends with exit 2 and nothing captured. A project that already has a topic, or whose capture
waits in the inbox, is said to be so with exit 0, and nothing is captured.

The skill passes its text on standard input, so quotes, dollar signs and line breaks arrive as
written; a capture from Claude Code carries the source ``claude``, one typed on the command line
``cli``. The source names where a capture came from, not a device, so it is right on Linux too.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
from pathlib import Path

from m2b import project_capture, session_remotes
from m2b.capture import capture
from m2b.capture_file import CaptureFileRefusedError, capture_file
from m2b.commands import Context, UsageError
from m2b.commands.backends import configured_store
from m2b.commands.output import print_json
from m2b.commands.times import parse_day
from m2b.config.machine import load_machine_config
from m2b.config.store_settings import STORE_SETTINGS_FILE_NAME, load_store_settings, require_inbox_writable
from m2b.notes.characters import with_hidden_written_out
from m2b.store.base import FetchError, Store
from m2b.tasks.factory import open_tasks

DEFAULT_SOURCE = "cli"
# How long a capture waits for an evicted ``store.json`` to download. A capture is interactive and
# the skill cannot fetch on its own, so it asks once for a while; past it the refusal names the
# command that downloads the file.
STORE_SETTINGS_FETCH_SECONDS = 20.0


def capture_command(arguments: argparse.Namespace, context: Context) -> int:
    text = sys.stdin.read() if arguments.text in (None, "-") else arguments.text
    follow_up = parse_day(arguments.follow_up, "--follow-up") if arguments.follow_up else None
    if arguments.project and follow_up is not None:
        raise UsageError("a project is captured without a follow-up")
    repository = _repository_here(context) if arguments.project else None
    if repository is None and not text.strip():
        raise UsageError("there is nothing to capture: the text is empty")
    config = load_machine_config(context.machine)
    store = configured_store(config, context.machine)
    with contextlib.suppress(FetchError):
        store.fetch([STORE_SETTINGS_FILE_NAME], STORE_SETTINGS_FETCH_SECONDS)
    require_inbox_writable(store)
    if repository is not None:
        topic, waiting = _already_there(store, repository)
        if topic is not None or waiting is not None:
            if arguments.json:
                print_json({"path": None, "known_as": topic, "waiting": waiting})
            elif topic is not None:
                print(f"The project is already known as the topic {topic}; nothing was captured.")
            else:
                print(
                    f"The project's capture waits in the inbox ({waiting}) for the next curation run; "
                    "nothing was captured."
                )
            return 0
        text = project_capture.capture_text(repository, text)
    tasks = open_tasks(load_store_settings(store).tasks, store, config.executables) if follow_up else None
    try:
        result = capture(store, text, arguments.source, quiet=arguments.quiet, follow_up=follow_up, tasks=tasks)
    except ValueError as error:
        raise UsageError(str(error)) from error
    if result.notice:
        print(f"m2b: {result.notice}", file=sys.stderr)
    if arguments.json:
        print_json(
            {
                "path": result.path,
                "task_id": result.task_id,
                "follow_up": result.follow_up.isoformat() if result.follow_up else None,
            }
        )
    else:
        print(result.path)
    return 0


def _repository_here(context: Context) -> session_remotes.Repository:
    folder = Path(os.getcwd())
    try:
        return session_remotes.repository_of(folder, context.environ)
    except session_remotes.RepositoryNotKnownError as error:
        if error.reason == session_remotes.NOT_IN_A_REPOSITORY:
            raise UsageError(f"{folder} lies in no git repository; nothing was captured") from error
        if error.reason == session_remotes.NO_REMOTE:
            raise UsageError(
                f"the repository at {error.top} has no remote, and m2b needs a remote to know the project on "
                "another machine; nothing was captured"
            ) from error
        raise UsageError(
            f"git could not say the remotes of the repository at {error.top}; nothing was captured"
        ) from error


def _already_there(store: Store, repository: session_remotes.Repository) -> tuple[str | None, str | None]:
    """The topic the project is known as, else the name of its capture that waits in the inbox; both
    come from the store, so a character that draws nothing is written out."""
    topic = project_capture.known_as(store, repository)
    if topic is not None:
        return with_hidden_written_out(topic), None
    waiting = project_capture.waiting_capture(store, repository)
    return None, None if waiting is None else with_hidden_written_out(waiting)


def capture_file_command(arguments: argparse.Namespace, context: Context) -> int:
    """Prints the note and the copy it wrote, each on a line; a path m2b does not copy ends with exit 2."""
    words = sys.stdin.read() if arguments.words == "-" else arguments.words or ""
    config = load_machine_config(context.machine)
    store = configured_store(config, context.machine)
    with contextlib.suppress(FetchError):
        store.fetch([STORE_SETTINGS_FILE_NAME], STORE_SETTINGS_FETCH_SECONDS)
    require_inbox_writable(store)
    try:
        captured = capture_file(store, Path(arguments.path), words, arguments.source, config.capture.file_limit_mb)
    except (CaptureFileRefusedError, ValueError) as error:
        raise UsageError(str(error)) from error
    print(captured.note)
    print(captured.file)
    return 0
