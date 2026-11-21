"""Dates and times as commands take them: ``YYYY-MM-DD`` and ``YYYY-MM-DD HH:MM`` in local time, strictly.

``strptime`` accepts unpadded fields, so the shape is checked first; impossible dates such as
30 February are refused by ``strptime`` itself. Leniency belongs where a person can be asked
again, not where a calendar or a task list is written.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Mapping

from m2b.commands import UsageError
from m2b.curate.model import CURATION_RUN_VARIABLE, TODAY_VARIABLE

_DAY = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")
_MOMENT = re.compile(r"\A\d{4}-\d{2}-\d{2} \d{2}:\d{2}\Z")


def parse_day(text: str, option: str) -> datetime.date:
    if not _DAY.match(text):
        raise UsageError(f"{option} takes a date as YYYY-MM-DD, not {text!r}")
    try:
        return datetime.datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as error:
        raise UsageError(f"{option}: {text!r} is no date") from error


def parse_moment(text: str, option: str) -> datetime.datetime:
    """A local time; the result is timezone-aware."""
    if not _MOMENT.match(text):
        raise UsageError(f"{option} takes a time as YYYY-MM-DD HH:MM, not {text!r}")
    try:
        return datetime.datetime.strptime(text, "%Y-%m-%d %H:%M").astimezone()
    except ValueError as error:
        raise UsageError(f"{option}: {text!r} is no time") from error


def parse_day_or_moment(text: str, option: str) -> datetime.date:
    """A date, or a ``datetime`` when the text carries a time."""
    return parse_moment(text, option) if " " in text else parse_day(text, option)


def run_day(environ: Mapping[str, str]) -> datetime.date | None:
    """Inside a curation run, the day the run counts as today (``TODAY_VARIABLE``); outside one, None."""
    day = environ.get(TODAY_VARIABLE)
    if environ.get(CURATION_RUN_VARIABLE) != "1" or not day:
        return None
    return parse_day(day, TODAY_VARIABLE)


def run_moment(environ: Mapping[str, str]) -> datetime.datetime | None:
    """The run's day at the time of day it is, inside a curation run; outside one, None."""
    day = run_day(environ)
    return None if day is None else datetime.datetime.combine(day, datetime.datetime.now().astimezone().timetz())
