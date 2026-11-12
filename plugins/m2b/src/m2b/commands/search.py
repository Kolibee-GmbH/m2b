"""``search``: hits as ``path:line: text``, then what could not be searched and why.

No hits is said in words, so empty output never stands for an answer; a store that cannot be
reached ends with exit 3 before anything is printed.

Nothing from the store is printed with a character that draws nothing (``notes.characters``): a
session's model reads this output, as text or as JSON, and nobody sees what such a character
carries. A hit's text loses them. A path keeps them written out, and so does what is said of a
file that was not searched, because a name without its hidden character is another file's name.
The terms are the caller's own and are answered as given.
"""

from __future__ import annotations

import argparse
import dataclasses

from m2b.commands import Context, UsageError
from m2b.commands.backends import configured_store
from m2b.commands.output import print_json
from m2b.config.machine import load_machine_config
from m2b.notes.characters import with_hidden_written_out, without_hidden
from m2b.search import Hit, SearchResult, search
from m2b.store.base import fetch_command
from m2b.store.reading import Unreadable


def search_command(arguments: argparse.Namespace, context: Context) -> int:
    store = configured_store(load_machine_config(context.machine), context.machine)
    try:
        terms = arguments.terms if arguments.any else [" ".join(arguments.terms)]
        result = _as_printed(search(store, *terms, whole_words=arguments.word))
    except ValueError as error:
        raise UsageError(str(error)) from error
    if arguments.json:
        print_json(_as_json(result))
    else:
        _print_text(result)
    return 0


def _as_printed(result: SearchResult) -> SearchResult:
    """The result with no character that draws nothing: taken out of a hit's text, written out in a
    path and in why a file was not read."""
    return dataclasses.replace(
        result,
        hits=[Hit(with_hidden_written_out(hit.path), hit.line, without_hidden(hit.text)) for hit in result.hits],
        evicted=[with_hidden_written_out(path) for path in result.evicted],
        unreadable=[
            Unreadable(with_hidden_written_out(item.path), with_hidden_written_out(item.reason))
            for item in result.unreadable
        ],
    )


def _as_json(result: SearchResult) -> dict[str, object]:
    return {
        "terms": list(result.terms),
        "whole_words": result.whole_words,
        "hits": [{"path": hit.path, "line": hit.line, "text": hit.text} for hit in result.hits],
        "evicted": [{"path": path, "fetch": fetch_command(path)} for path in result.evicted],
        "unreadable": [{"path": item.path, "reason": item.reason} for item in result.unreadable],
    }


def _print_text(result: SearchResult) -> None:
    for hit in result.hits:
        print(f"{hit.path}:{hit.line}: {hit.text}")
    left_out = result.evicted or result.unreadable
    if not result.hits:
        searched = " or ".join(repr(term) for term in result.terms)
        print("No hits in the files that could be searched." if left_out else f"No hits for {searched}.")
    if result.evicted:
        print("\nNot searched, because not downloaded to this machine; fetch them, then search again:")
        for command in result.fetch_commands():
            print(f"  {command}")
    if result.unreadable:
        print("\nNot searched, because they could not be read:")
        for item in result.unreadable:
            print(f"  {item.reason}")
