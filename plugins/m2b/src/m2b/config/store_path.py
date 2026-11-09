"""Which store paths a curation run can work in.

Every model step of a curation run is fenced with permission rules that name the store by its
absolute path (``curate.model.store_rules``). A rule reads some characters as its own syntax or as
a pattern, so a store path holding one cannot be named, and every curation run would refuse it.
Only the curating machine fences with its path: setup refuses such a path for a machine that is to
curate, take-over refuses to move curation onto one, and doctor names it on the curating machine.
A machine that only captures may keep its store in such a folder, ``Dropbox (Personal)`` for one.
"""

from __future__ import annotations

from pathlib import Path

# The characters a permission rule reads as syntax or as a pattern.
UNSAFE_CHARACTERS = ",()[]*?\\\n"


def unsafe_characters(path: Path | str) -> str:
    """The characters of ``path`` a permission rule cannot name, each once, in path order."""
    found = ""
    for character in str(path):
        if character in UNSAFE_CHARACTERS and character not in found:
            found += character
    return found


def problem(path: Path | str) -> str | None:
    """One line saying why a curation run cannot work in ``path``; None when it can."""
    found = unsafe_characters(path)
    if not found:
        return None
    return (
        f"the store path {str(path)!r} holds {_named(found, 'and')}, which a curation run cannot name in the rules "
        f"that fence its model steps; choose a folder without {_named(UNSAFE_CHARACTERS, 'or')}"
    )


def _named(characters: str, conjunction: str) -> str:
    """The characters as one line of text; a backslash and a line break by their names."""
    names = {"\\": "a backslash", "\n": "a line break"}
    symbols = " ".join(character for character in characters if character not in names)
    parts = ([symbols] if symbols else []) + [names[character] for character in characters if character in names]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + f" {conjunction} " + parts[-1]
