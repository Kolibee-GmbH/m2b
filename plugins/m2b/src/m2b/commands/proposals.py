"""``proposals``, ``proposals keep`` and ``proposals drop``: what a reading of the sessions proposed, answered.

The listing shows what still waits for an answer; keep and drop add the answer as a file and
leave the filing to the next curation run, like every client. A proposals file or an answers
folder that is not downloaded ends the command with the line that names what to fetch: could not
look is never an empty list.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Mapping
from typing import Any

from m2b import proposal_answers, proposals
from m2b.commands import Context, ProblemError, UsageError
from m2b.commands.backends import configured_store
from m2b.commands.output import print_json
from m2b.config.machine import load_machine_config
from m2b.config.store_settings import require_store_writable
from m2b.proposal_answers import KEEP, Given, Waiting
from m2b.proposals import Entry
from m2b.store.base import Store

_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
NONE_WAITS = "no proposal waits for an answer"
HOW_TO_ANSWER = "keep with: m2b proposals keep <id>... (or keep --all); drop with: m2b proposals drop <id>..."


def proposals_command(arguments: argparse.Namespace, context: Context) -> int:
    store = configured_store(load_machine_config(context.machine), context.machine)
    try:
        if arguments.action is None:
            return _list(store, arguments.json)
        return _answer(store, arguments.action, arguments.ids, arguments.all, arguments.json)
    except (proposals.ProposalsError, proposal_answers.UnknownProposalError) as error:
        raise ProblemError(str(error)) from error


def _list(store: Store, as_json: bool) -> int:
    waiting = proposal_answers.waiting(store)
    if as_json:
        print_json(_waiting_json(waiting))
        return 0
    if waiting.proposals:
        one = len(waiting.proposals) == 1
        print(f"{len(waiting.proposals)} {'proposal waits' if one else 'proposals wait'} for an answer:\n")
        for key, entry in waiting.proposals:
            said = f'said on {entry.day.isoformat()}: "{_shown(entry.quote)}"'
            print(f"{key}  {_heading(entry)}\n  {_shown(entry.text)}\n  {said}\n")
        print(HOW_TO_ANSWER)
    else:
        print(NONE_WAITS)
    if waiting.answered:
        one = waiting.answered == 1
        print(f"{waiting.answered} {'answer waits' if one else 'answers wait'} for the next curation run")
    return 0


def waiting_answer(store: Store) -> dict[str, Any]:
    """What ``proposals --json`` answers: the proposals that wait, and how many answers wait for a run."""
    return _waiting_json(proposal_answers.waiting(store))


def _waiting_json(waiting: Waiting) -> dict[str, Any]:
    return {
        "proposals": [_as_json(key, entry) for key, entry in waiting.proposals],
        "answered": waiting.answered,
    }


def _answer(store: Store, answer: str, named: list[str], every: bool, as_json: bool) -> int:
    if every == bool(named):
        raise UsageError(f"m2b proposals {answer} takes the ids of proposals" + (" or --all" if answer == KEEP else ""))
    require_store_writable(store)
    entries = dict(proposal_answers.waiting(store).proposals) if every else proposals.load(store).entries
    given = proposal_answers.give(store, list(entries) if every else named, answer)
    other = {key: stands for key, stands in given.already.items() if stands != answer}
    if as_json:
        print_json({"given": list(given.given), "already": dict(given.already)})
    else:
        _say(answer, given, entries, every)
    return 1 if other else 0


def _say(answer: str, given: Given, entries: Mapping[str, Entry], every: bool) -> None:
    for key in given.given:
        print(f"{answer} {key}: {_shown(entries[key].text)}")
    if given.given and answer == KEEP:
        print("the next curation run files what is kept")
    if every and not given.given:
        print(NONE_WAITS)
    for key, stands in given.already.items():
        if stands == answer:
            print(f"{key} is answered with {stands} already")
        else:
            print(f"m2b: {key} is answered with {stands} already; that answer stands", file=sys.stderr)


def _shown(text: str) -> str:
    """The text on one line, each control character written out instead of sent to the terminal.

    What the person keeps is what the listing showed them: a text that hid part of itself from
    the terminal would be kept unseen.
    """
    return _CONTROL.sub(lambda found: f"\\x{ord(found.group()):02x}", " ".join(text.split()))


def _heading(entry: Entry) -> str:
    parts = [entry.kind]
    if entry.due is not None:
        parts.append(f"due {entry.due.isoformat()}")
    if entry.topic:
        parts.append(f"topic {_shown(entry.topic)}")
    return ", ".join(parts)


def _as_json(key: str, entry: Entry) -> dict[str, Any]:
    return {
        "id": key,
        "kind": entry.kind,
        "text": entry.text,
        "quote": entry.quote,
        "day": entry.day.isoformat(),
        "topic": entry.topic,
        "due": entry.due.isoformat() if entry.due else None,
    }
