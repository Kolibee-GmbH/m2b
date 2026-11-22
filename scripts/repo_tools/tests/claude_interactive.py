"""A stand-in for an interactive Claude Code session, for the tests of the session step of the model
level. It asks no model.

It draws a prompt and reads one line per turn from its terminal. For each line it writes what
Claude Code 2.1.330 wrote for a typed turn on 2026-11-21 into a transcript under
``$CLAUDE_CONFIG_DIR/projects/``: the prompt marked as a human's, an answer that runs the Bash
command ``scripts/check``, and the record of the turn's end. ``/exit`` ends it.

``CLAUDE_INTERACTIVE_MODE`` changes that: ``silent`` never ends a turn, ``logged-out`` draws Claude
Code's message for a session without a login and ends the turn without an answer.

Usage: python3 claude_interactive.py <claude arguments...>
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import uuid
from pathlib import Path

NOT_LOGGED_IN = "Not logged in · Please run /login"


def main() -> None:
    mode = os.environ.get("CLAUDE_INTERACTIVE_MODE", "")
    session = str(uuid.uuid4())
    cwd = str(Path.cwd().resolve())
    transcript = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / "-sb-test-fake" / f"{session}.jsonl"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    print("\u276f ", end="", flush=True)
    for line in sys.stdin:
        typed = line.strip()
        if typed == "/exit":
            return
        if mode == "silent":
            continue
        records = [_record("user", cwd, session, message={"role": "user", "content": typed}, origin={"kind": "human"})]
        if mode == "logged-out":
            print(NOT_LOGGED_IN, flush=True)
        else:
            call = {"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"command": "scripts/check"}}
            records.append(_record("assistant", cwd, session, message={"role": "assistant", "content": [call]}))
        records.append(_record("system", cwd, session, subtype="turn_duration", durationMs=10))
        with transcript.open("a", encoding="utf-8") as handle:
            handle.writelines(json.dumps(record) + "\n" for record in records)
        print("done\n\u276f ", end="", flush=True)


def _record(kind: str, cwd: str, session: str, **fields: object) -> dict[str, object]:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    return {"type": kind, "timestamp": now, "cwd": cwd, "sessionId": session, "entrypoint": "cli", **fields}


if __name__ == "__main__":
    main()
