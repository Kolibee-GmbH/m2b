#!/usr/bin/env python3
"""Stands in for ``herdr`` in the worklog's tests; never touches a real herdr.

It keeps its linked plugins in the JSON file ``FAKE_HERDR_STATE`` (``{"linked": {id: path}}``) and
answers ``api snapshot`` from the file ``FAKE_HERDR_REPLY``. ``plugin link`` reads the manifest's
``id`` line from the linked folder. Every call is
appended to ``FAKE_HERDR_CALLS``, one line of arguments.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


def _state() -> dict[str, dict[str, str]]:
    path = Path(os.environ["FAKE_HERDR_STATE"])
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"linked": {}}


def _save(state: dict[str, dict[str, str]]) -> None:
    Path(os.environ["FAKE_HERDR_STATE"]).write_text(json.dumps(state), encoding="utf-8")


def main() -> int:
    arguments = sys.argv[1:]
    calls = os.environ.get("FAKE_HERDR_CALLS")
    if calls:
        with Path(calls).open("a", encoding="utf-8") as log:
            log.write(" ".join(arguments) + "\n")
    if arguments == ["api", "snapshot"]:
        reply = os.environ.get("FAKE_HERDR_REPLY")
        if not reply or not Path(reply).exists():
            print("fake herdr: no server is running", file=sys.stderr)
            return 1
        print(Path(reply).read_text(encoding="utf-8"), end="")
        return 0
    state = _state()
    # Answers as herdr 0.9.3 does: an unknown id is an empty list,
    # a second link replaces the first, unlinking an unknown id says "removed": false; all exit 0.
    if arguments[:2] == ["plugin", "list"]:
        wanted = arguments[arguments.index("--plugin") + 1] if "--plugin" in arguments else None
        plugins = [
            {"plugin_id": key, "plugin_root": value, "enabled": True}
            for key, value in state["linked"].items()
            if wanted in (None, key)
        ]
        print(json.dumps({"id": "cli:plugin", "result": {"plugins": plugins, "type": "plugin_list"}}))
        return 0
    if arguments[:2] == ["plugin", "link"] and len(arguments) == 3:
        manifest = Path(arguments[2]) / "herdr-plugin.toml"
        match = re.search(r'^id = "([^"]+)"', manifest.read_text(encoding="utf-8"), re.MULTILINE)
        if match is None:
            print("fake herdr: no id in the manifest", file=sys.stderr)
            return 1
        state["linked"][match.group(1)] = arguments[2]
        _save(state)
        print(
            json.dumps(
                {"id": "cli:plugin", "result": {"plugin": {"plugin_id": match.group(1)}, "type": "plugin_linked"}}
            )
        )
        return 0
    if arguments[:2] == ["plugin", "unlink"] and len(arguments) == 3:
        removed = state["linked"].pop(arguments[2], None) is not None
        _save(state)
        result = {"plugin_id": arguments[2], "removed": removed, "type": "plugin_unlinked"}
        print(json.dumps({"id": "cli:plugin", "result": result}))
        return 0
    print(f"fake herdr: unexpected arguments {arguments}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
