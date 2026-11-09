"""``search``: hits as ``path:line: text``, then what could not be searched and why.

No hits is said in words, so empty output never stands for an answer; a store that cannot be
reached ends with exit 3 before anything is printed.
"""

from __future__ import annotations

import argparse

from m2b.commands import Context, UsageError
from m2b.commands.backends import configured_store
from m2b.commands.output import print_json
from m2b.config.machine import load_machine_config
from m2b.search import SearchResult, search
from m2b.store.base import fetch_command


def search_command(arguments: argparse.Namespace, context: Context) -> int:
    store = configured_store(load_machine_config(context.machine), context.machine)
    try:
        terms = arguments.terms if arguments.any else [" ".join(arguments.terms)]
        result = search(store, *terms, whole_words=arguments.word)
    except ValueError as error:
        raise UsageError(str(error)) from error
    if arguments.json:
        print_json(_as_json(result))
    else:
        _print_text(result)
    return 0


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
