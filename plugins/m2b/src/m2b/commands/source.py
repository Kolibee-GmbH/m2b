"""``source``: one fact file or note, read by its name, as text or as JSON.

A name that is no source's name ends with exit 2 and one line, a name nothing has with exit 1; a
store that cannot be reached with exit 3. A source that is not on this machine is answered with
exit 0 and the command that fetches it, as search answers the files it could not search.

As in search, nothing from the store is printed with a character that draws nothing: a session's
model reads this answer. Text loses such characters, a path or a name keeps them written out.
"""

from __future__ import annotations

import argparse
from pathlib import PurePosixPath

from m2b import corrections, viewer
from m2b.commands import Context, ProblemError, UsageError
from m2b.commands.backends import configured_store
from m2b.commands.output import print_json
from m2b.config.machine import load_machine_config
from m2b.notes.characters import with_hidden_written_out, without_hidden
from m2b.source import (
    Evidence,
    FactFile,
    NoteSource,
    NotRead,
    Source,
    SourceNotFoundError,
    SourceRefusedError,
    read_source,
)
from m2b.store.base import Store, fetch_command

FACT_FILE = "fact file"
NOT_READ = "not read"
_KIND_IN_WORDS = {"note": "a note", "picture": "a picture", "document": "a document"}


def source_command(arguments: argparse.Namespace, context: Context) -> int:
    store = configured_store(load_machine_config(context.machine), context.machine)
    try:
        source = read_source(store, arguments.name)
    except SourceRefusedError as error:
        raise UsageError(with_hidden_written_out(str(error))) from error
    except SourceNotFoundError as error:
        raise ProblemError(with_hidden_written_out(str(error))) from error
    name = with_hidden_written_out(arguments.name)
    if arguments.json:
        viewer_fields = _viewer_json(source, store, context) if arguments.viewer else {}
        print_json({"name": name, **_as_json(source), **viewer_fields})
    else:
        print("\n".join(_as_text(source)))
    return 0


def _as_json(source: Source) -> dict[str, object]:
    if isinstance(source, FactFile):
        return {
            "kind": FACT_FILE,
            "path": _name(source.path),
            "title": _text(source.title),
            "until": _text(source.until) if source.until is not None else None,
            "lines": [_text(line) for line in source.lines],
            "earlier": [_text(line) for line in source.earlier],
            "evidence": [_evidence_json(item) for item in source.evidence],
        }
    if isinstance(source, NoteSource):
        return {
            "kind": source.kind,
            "path": _name(source.path),
            "day": source.day,
            "captured": _text(source.captured),
            "added": [_text(line) for line in source.added],
            "original_name": _optional_name(source.original_name),
            "outline": [_text(line) for line in source.outline],
            "original": _optional_name(source.original),
            "original_here": source.original_here,
        }
    return {
        "kind": NOT_READ,
        "path": _name(source.path),
        "evicted": source.evicted,
        "fetch": fetch_command(_name(source.path)) if source.evicted else None,
        "reason": _name(source.reason) or None,
    }


def _viewer_json(source: Source, store: Store, context: Context) -> dict[str, object]:
    """For a picture's or a document's note, whether ``m2b store open`` opens the file, why not, and
    where it lies; the pane offers ``open the file`` or names the path. Only with ``--viewer``, which
    the pane passes: the skill ``m2b:search`` hands the JSON to a session's model, which is never
    given a path into the store. For a fact file, the corrections that wait for it in the inbox,
    each with its capture's name and first line."""
    if isinstance(source, FactFile):
        waiting = corrections.waiting_for(store, PurePosixPath(source.path).name)
        return {
            "corrections": [{"capture": _name(item.capture), "first_line": _text(item.first_line)} for item in waiting]
        }
    if not isinstance(source, NoteSource):
        return {}
    if source.original is None:
        return {"opens": False, "not_opened": None, "file": None}
    why_not = viewer.why_not_opened(source.original, bool(source.original_here), context.environ)
    return {
        "opens": why_not is None,
        "not_opened": _name(why_not) if why_not is not None else None,
        "file": _name(str(store.path(source.original))),
    }


def _evidence_json(item: Evidence) -> dict[str, object]:
    return {
        "name": _name(item.name),
        "state": item.state,
        "day": item.day,
        "kind": item.kind,
        "original_name": _optional_name(item.original_name),
        "first_line": _text(item.first_line) if item.first_line is not None else None,
        "path": _optional_name(item.path),
        "fetch": fetch_command(_name(item.path)) if item.state == "evicted" and item.path else None,
        "reason": _optional_name(item.reason),
    }


def _as_text(source: Source) -> list[str]:
    if isinstance(source, FactFile):
        return _fact_file_text(source)
    if isinstance(source, NoteSource):
        return _note_text(source)
    return _not_read_text(source)


def _fact_file_text(source: FactFile) -> list[str]:
    lines = [f"Fact file {_name(source.path)}: {_text(source.title)}"]
    if source.until is not None:
        lines.append(f"True until {_text(source.until)}.")
    lines.extend(["", *(_text(line) for line in source.lines)])
    if source.earlier:
        lines.extend(["", "Earlier:", *(f"  {_text(line)}" for line in source.earlier)])
    if source.evidence:
        lines.extend(["", "Evidence:", *(f"  {_evidence_text(item)}" for item in source.evidence)])
    return lines


def _evidence_text(item: Evidence) -> str:
    name = _name(item.name)
    if item.state == "missing":
        return f"{name}: no note of the archive has this name"
    if item.state == "evicted":
        return f"{name}: not downloaded to this machine; fetch it with: {fetch_command(_name(item.path or ''))}"
    if item.state == "unreadable":
        return f"{name}: could not be read: {_name(item.reason or '')}"
    what = _KIND_IN_WORDS.get(item.kind or "", "a note")
    if item.original_name:
        what += f", {_name(item.original_name)}"
    said = f": {_text(item.first_line)}" if item.first_line else ""
    return f"{item.day}  {what}{said} ({name})"


def _note_text(source: NoteSource) -> list[str]:
    what = _KIND_IN_WORDS.get(source.kind, "a note")
    head = f"{what[0].upper()}{what[1:]}, {_name(source.path)}, of {source.day}"
    if source.original_name:
        head += f", original name {_name(source.original_name)}"
    lines = [head]
    if source.original is not None:
        place = "on this machine" if source.original_here else "not downloaded to this machine"
        lines.append(f"The file itself: {_name(source.original)}, {place}.")
    captured = _text(source.captured).rstrip("\n")
    if captured:
        lines.extend(["", captured])
    if source.outline:
        lines.extend(["", "Outline:", *(f"  {_text(line)}" for line in source.outline)])
    if source.added:
        lines.extend(["", "Added by curation:", *(f"  {_text(line)}" for line in source.added)])
    return lines


def _not_read_text(source: NotRead) -> list[str]:
    path = _name(source.path)
    if source.evicted:
        return [
            "Not read, because not downloaded to this machine; fetch it, then ask again:",
            f"  {fetch_command(path)}",
        ]
    return [f"Not read, because it could not be read: {_name(source.reason)}"]


def _text(text: str) -> str:
    return without_hidden(text)


def _name(name: str) -> str:
    return with_hidden_written_out(name)


def _optional_name(name: str | None) -> str | None:
    return _name(name) if name is not None else None
