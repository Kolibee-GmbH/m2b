"""``rediscover``: old notes back into view, each with its reason; ``--json`` for the skill.

Without a seed the pick comes from the system's random source, so two sessions do not bring back
the same note. Nothing to bring back is said in words.
"""

from __future__ import annotations

import argparse
import datetime
import random
from typing import Any

from m2b.commands import Context, UsageError
from m2b.commands.backends import configured_store
from m2b.commands.output import print_json
from m2b.commands.times import parse_day
from m2b.config.machine import load_machine_config
from m2b.rediscover import Months, RediscoverResult, rediscover
from m2b.store.base import fetch_command


def rediscover_command(arguments: argparse.Namespace, context: Context) -> int:
    today = parse_day(arguments.today, "--today") if arguments.today else datetime.date.today()
    if arguments.count < 1:
        raise UsageError(f"--count must be at least 1, not {arguments.count}")
    months = _months(arguments.month) if arguments.month is not None else None
    store = configured_store(load_machine_config(context.machine), context.machine)
    result = rediscover(store, today, random.SystemRandom(), count=arguments.count, months=months)
    if arguments.json:
        print_json(_as_json(result))
    else:
        _print_text(result, months)
    return 0


def _months(text: str) -> Months:
    try:
        return Months.parse(text)
    except ValueError as error:
        raise UsageError(f"--month: {error}") from error


def _as_json(result: RediscoverResult) -> dict[str, Any]:
    return {
        "picks": [
            {
                "path": pick.path,
                "why": pick.why,
                "reason": pick.reason,
                "word": pick.word,
                "current_item": pick.current_item,
                "text": pick.text,
                "truncated": pick.truncated,
            }
            for pick in result.picks
        ],
        "evicted": [{"path": path, "fetch": fetch_command(path)} for path in result.evicted],
        "unreadable": [{"path": item.path, "reason": item.reason} for item in result.unreadable],
    }


def _print_text(result: RediscoverResult, months: Months | None) -> None:
    if not result.picks:
        nothing = f"No notes from {months.label()}" if months is not None else "No old notes to bring back"
        left_out = result.evicted or result.unreadable
        print(f"{nothing} among the notes that could be read." if left_out else f"{nothing}.")
    for pick in result.picks:
        print(f"{pick.path} ({pick.reason})")
        for line in pick.text.split("\n"):
            print(f"  {line}".rstrip())
        if pick.truncated:
            print("  [...]")
    if result.evicted:
        print("\nNot looked at, because not downloaded to this machine:")
        for path in result.evicted:
            print(f"  {fetch_command(path)}")
    if result.unreadable:
        print("\nNot looked at, because they could not be read:")
        for item in result.unreadable:
            print(f"  {item.reason}")
