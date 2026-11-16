"""``capture``: the text as an argument, or on standard input with ``-`` or no argument;
``capture-file``: a file of the machine with words beside it, which no skill runs without asking.

The skill passes its text on standard input, so quotes, dollar signs and line breaks arrive as
written; a capture from Claude Code carries the source ``claude``, one typed on the command line
``cli``. The source names where a capture came from, not a device, so it is right on Linux too.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

from m2b.capture import capture
from m2b.capture_file import CaptureFileRefusedError, capture_file
from m2b.commands import Context, UsageError
from m2b.commands.backends import configured_store
from m2b.commands.output import print_json
from m2b.commands.times import parse_day
from m2b.config.machine import load_machine_config
from m2b.config.store_settings import STORE_SETTINGS_FILE_NAME, load_store_settings, require_inbox_writable
from m2b.store.base import FetchError
from m2b.tasks.factory import open_tasks

DEFAULT_SOURCE = "cli"
# How long a capture waits for an evicted ``store.json`` to download. A capture is interactive and
# the skill cannot fetch on its own, so it asks once for a while; past it the refusal names the
# command that downloads the file.
STORE_SETTINGS_FETCH_SECONDS = 20.0


def capture_command(arguments: argparse.Namespace, context: Context) -> int:
    text = sys.stdin.read() if arguments.text in (None, "-") else arguments.text
    follow_up = parse_day(arguments.follow_up, "--follow-up") if arguments.follow_up else None
    if not text.strip():
        raise UsageError("there is nothing to capture: the text is empty")
    config = load_machine_config(context.machine)
    store = configured_store(config, context.machine)
    with contextlib.suppress(FetchError):
        store.fetch([STORE_SETTINGS_FILE_NAME], STORE_SETTINGS_FETCH_SECONDS)
    require_inbox_writable(store)
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
