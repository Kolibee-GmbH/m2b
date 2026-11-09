"""A stand-in for ``reminders`` (reminders-cli) that keeps its lists in a JSON state file.

It answers the subcommands the Apple backend uses, in the shape reminders-cli uses: items carry
``externalId``, ``title``, ``isCompleted``, ``list``, ``priority``, and ``notes``, ``dueDate``
and ``completionDate`` only when set. The state's ``mode`` simulates failures: ``no-lists``
(no access: zero lists, exit 0), ``hang``, ``garbage`` (a reply that is not JSON), and
``no-id-on-add`` (an ``add`` that prints no id) and ``lose-notes-on-add`` (an ``add`` that
prints no id and drops the notes, so the new reminder cannot be found again).

Usage: python3 fake_reminders.py <state file> <subcommand> ...
"""

from __future__ import annotations

import datetime
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _due(text: str) -> str:
    """reminders-cli reads a local date or time and reports the instant in UTC."""
    local = (
        datetime.datetime.fromisoformat(text)
        if " " in text or "T" in text
        else datetime.datetime.fromisoformat(f"{text}T00:00")
    )
    return local.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _option(arguments: list[str], name: str) -> str | None:
    """Takes ``--name value`` or ``--name=value`` out of the arguments before a ``--``."""
    end = arguments.index("--") if "--" in arguments else len(arguments)
    for index, argument in enumerate(arguments[:end]):
        if argument.startswith(f"{name}="):
            del arguments[index]
            return argument[len(name) + 1 :]
        if argument == name:
            value = arguments[index + 1]
            del arguments[index : index + 2]
            return value
    return None


def _flag(arguments: list[str], name: str) -> bool:
    if name in arguments:
        arguments.remove(name)
        return True
    return False


def _find(state: dict[str, Any], list_name: str, item_id: str, completed: bool = False) -> dict[str, Any]:
    """Like reminders-cli: edit, complete and delete see open reminders only, uncomplete completed ones."""
    for item in _list(state, list_name):
        if item["externalId"] == item_id and item["isCompleted"] == completed:
            return item
    _fail(f"No reminder at index {item_id} on {list_name}")
    raise AssertionError


def _list(state: dict[str, Any], list_name: str) -> list[dict[str, Any]]:
    if list_name not in state["lists"]:
        _fail(f"No reminders list matching {list_name}")
    items: list[dict[str, Any]] = state["items"].setdefault(list_name, [])
    return items


def _fail(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(1)


def main(state_path: Path, arguments: list[str]) -> int:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    mode = state.get("mode", "normal")
    if mode == "hang":
        time.sleep(60)
    if mode == "garbage":
        print("Error Domain=EKErrorDomain Code=29 (null)")
        return 0
    command, *rest = arguments
    output_json = _option(rest, "--format") == "json"

    if command == "show-lists":
        print(json.dumps([] if mode == "no-lists" else state["lists"]))
        return 0
    if mode == "no-lists":
        _fail("No reminders list matching " + (rest[0] if rest else ""))

    if command == "show":
        only_completed = _flag(rest, "--only-completed")
        include_completed = _flag(rest, "--include-completed")
        items = _list(state, rest[0])
        if only_completed:
            items = [i for i in items if i["isCompleted"]]
        elif not include_completed:
            items = [i for i in items if not i["isCompleted"]]
        print(json.dumps(items) if output_json else "\n".join(i["title"] for i in items))
        return 0

    if command == "add":
        notes, due = _option(rest, "--notes"), _option(rest, "--due-date")
        list_name, *words = [argument for argument in rest if argument != "--"]
        item: dict[str, Any] = {
            "externalId": str(uuid.uuid4()).upper(),
            "title": " ".join(words),
            "isCompleted": False,
            "list": list_name,
            "priority": 0,
        }
        if notes and mode != "lose-notes-on-add":
            item["notes"] = notes
        if due:
            item["dueDate"] = _due(due)
        _list(state, list_name).append(item)
        state_path.write_text(json.dumps(state), encoding="utf-8")
        if output_json and mode not in ("no-id-on-add", "lose-notes-on-add"):
            print(json.dumps(item))
        else:
            print(f"Added '{item['title']}' to '{list_name}'")
        return 0

    list_name, item_id, *words = rest
    if command == "edit":
        notes = _option(words, "--notes")
        item = _find(state, list_name, item_id)
        if notes is not None:
            if notes:
                item["notes"] = notes
            else:
                item.pop("notes", None)
        if words:
            item["title"] = " ".join(words)
    elif command == "complete":
        item = _find(state, list_name, item_id)
        item["isCompleted"], item["completionDate"] = True, _now()
    elif command == "uncomplete":
        item = _find(state, list_name, item_id, completed=True)
        item["isCompleted"] = False
        item.pop("completionDate", None)
    elif command == "delete":
        _list(state, list_name).remove(_find(state, list_name, item_id))
    else:
        _fail(f"unknown subcommand {command}")
    state_path.write_text(json.dumps(state), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), sys.argv[2:]))
