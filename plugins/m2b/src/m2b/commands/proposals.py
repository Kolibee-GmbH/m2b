"""``proposals``, ``proposals keep``, ``proposals drop`` and ``proposals add``: the proposals, answered and handed in.

The listing shows what still waits for an answer, and how many proposals sessions handed in
wait for the next run to take them in; keep and drop add the answer as a file and leave the
filing to the next curation run, like every client. A proposals file or an answers
folder that is not downloaded ends the command with the line that names what to fetch: could not
look is never an empty list.

``add`` is how a session hands in a proposal of its own (``handed_in``): it reads one JSON object
from standard input, so no word of it passes a shell, and answers with one line. A proposal that
is not taken ends the command with the line that says why, which never repeats its words. The
answer says nothing of where the quote was found: a caller that could ask would try wordings
until one reads as the person's own.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from collections.abc import Mapping
from typing import Any

from m2b import handed_in, proposal_answers, proposals
from m2b.commands import Context, ProblemError, UsageError
from m2b.commands.backends import configured_store
from m2b.commands.output import print_json
from m2b.config.machine import MachineConfig, load_machine_config
from m2b.config.store_settings import require_store_writable
from m2b.notes.characters import CONTROL
from m2b.proposal_answers import KEEP, Given, Waiting
from m2b.proposals import Entry
from m2b.store.base import Store, StoreError

NONE_WAITS = "no proposal waits for an answer"
HOW_TO_ANSWER = "keep with: m2b proposals keep <id>... (or keep --all); drop with: m2b proposals drop <id>..."
ADD = "add"
HANDED_IN = "handed in; go on with the task"
HANDED_IN_BEFORE = "handed in before: this proposal of the session is there already; go on with the task"
# A proposal is a few hundred characters; more bytes than this are no proposal and are not read.
INPUT_LENGTH = 64 * 1024


def proposals_command(arguments: argparse.Namespace, context: Context) -> int:
    config = load_machine_config(context.machine)
    store = configured_store(config, context.machine)
    try:
        if arguments.action is None:
            return _list(store, arguments.json)
        if arguments.action == ADD:
            return _add(store, config, context)
        return _answer(store, arguments.action, arguments.ids, arguments.all, arguments.json)
    except (proposals.ProposalsError, proposal_answers.UnknownProposalError, handed_in.RefusedError) as error:
        raise ProblemError(str(error)) from error


def _list(store: Store, as_json: bool) -> int:
    waiting = proposal_answers.waiting(store)
    handed, not_counted = _handed_in(store)
    if as_json:
        print_json(_waiting_json(waiting, handed))
        return 0
    if waiting.proposals:
        one = len(waiting.proposals) == 1
        print(f"{len(waiting.proposals)} {'proposal waits' if one else 'proposals wait'} for an answer:\n")
        for key, entry in waiting.proposals:
            said = proposals.said_line(entry, _shown(entry.quote))
            print(f"{key}  {_heading(entry)}\n  {_shown(entry.text)}\n  {said}\n")
        print(HOW_TO_ANSWER)
    else:
        print(NONE_WAITS)
    if waiting.answered:
        one = waiting.answered == 1
        print(f"{waiting.answered} {'answer waits' if one else 'answers wait'} for the next curation run")
    if handed:
        print(handed_in.waiting_line(handed))
    if not_counted is not None:
        print(f"handed in: could not look: {not_counted}")
    return 0


def waiting_answer(store: Store) -> dict[str, Any]:
    """What ``proposals --json`` answers: the proposals that wait, how many answers wait for a run,
    and how many proposals sessions handed in wait for a run to take them in."""
    return _waiting_json(proposal_answers.waiting(store), _handed_in(store)[0])


def _handed_in(store: Store) -> tuple[int | None, str | None]:
    """How many handed-in proposals wait for a run, or None and why their folder could not be listed.

    A count that fails is said for itself: the proposals that could be read are still listed.
    """
    try:
        return handed_in.waiting(store).count, None
    except StoreError as error:
        return None, str(error)


def _waiting_json(waiting: Waiting, handed: int | None) -> dict[str, Any]:
    return {
        "proposals": [_as_json(key, entry) for key, entry in waiting.proposals],
        "answered": waiting.answered,
        # The number alone: what was handed in has not been through the run's checks. Null where
        # the folder could not be listed, which is not none.
        "handed_in": handed,
    }


def _add(store: Store, config: MachineConfig, context: Context) -> int:
    # Before anything is read: a caller hears that handing in is off, not what is wrong with its input.
    handed_in.require_on(config, context.environ)
    written = sys.stdin.buffer.read(INPUT_LENGTH + 1)
    try:
        if len(written) > INPUT_LENGTH:
            raise ValueError("longer than a proposal")
        given = json.loads(written.decode("utf-8"))
    # Bytes that are no text, and a text nested deeper than this Python reads, are no proposal either.
    except (ValueError, RecursionError) as error:
        raise UsageError("m2b proposals add reads one JSON object from standard input") from error
    now = datetime.datetime.now().astimezone()
    outcome = handed_in.hand_in(store, config, context.machine, context.environ, handed_in.parse(given), now)
    print(HANDED_IN if outcome.is_new else HANDED_IN_BEFORE)
    return 0


def _answer(store: Store, answer: str, named: list[str], every: bool, as_json: bool) -> int:
    if every == bool(named):
        raise UsageError(f"m2b proposals {answer} takes the ids of proposals" + (" or --all" if answer == KEEP else ""))
    require_store_writable(store)
    waiting = dict(proposal_answers.waiting(store).proposals) if every else {}
    # What a session handed in is kept one by one: an agent worded it from what it read, and
    # `--all` answers without a look at each.
    left = [key for key, entry in waiting.items() if proposals.proposer_of(entry) is not None]
    entries = (
        {key: entry for key, entry in waiting.items() if key not in left} if every else proposals.load(store).entries
    )
    given = proposal_answers.give(store, list(entries) if every else named, answer)
    other = {key: stands for key, stands in given.already.items() if stands != answer}
    if as_json:
        answered = {"given": list(given.given), "already": dict(given.already)}
        print_json({**answered, "left": left} if every else answered)
    else:
        _say(answer, given, entries, every, len(left))
    return 1 if other else 0


def _say(answer: str, given: Given, entries: Mapping[str, Entry], every: bool, left: int = 0) -> None:
    for key in given.given:
        print(f"{answer} {key}: {_shown(entries[key].text)}")
    if given.given and answer == KEEP:
        print("the next curation run files what is kept")
    if every and not given.given and not left:
        print(NONE_WAITS)
    if left:
        one = left == 1
        print(
            f"{left} {'proposal' if one else 'proposals'} a session handed in "
            f"{'waits' if one else 'wait'}: --all leaves {'it' if one else 'them'}, keep or drop by id"
        )
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
    return CONTROL.sub(lambda found: f"\\x{ord(found.group()):02x}", " ".join(text.split()))


def _heading(entry: Entry) -> str:
    parts = [entry.kind]
    if entry.due is not None:
        parts.append(f"due {entry.due.isoformat()}")
    if entry.topic:
        parts.append(f"topic {_shown(entry.topic)}")
    proposer = proposals.proposer_of(entry)
    if proposer is not None:
        # Also where its words were typed: an agent worded its text, having read more than those words.
        parts.append(_shown(proposer))
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
        "source": entry.source,
        "tool": entry.tool,
        "by": entry.by,
    }
