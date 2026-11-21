"""The tool hook: before a Bash call, the action lessons whose words the command holds (B263).

Claude Code runs it on ``PreToolUse`` for Bash. Where the command holds all of a lesson's words and
none of the words that silence it, in a repository the lesson is for, the first such call of a
session is denied with the lesson as the reason (B288): context a PreToolUse hook adds reaches
Claude only beside the tool's result, after the call ran, while a denial's reason is read before
anything runs. The next call of that session goes through, with the lesson as context; a lesson set
to ask has Claude Code ask the owner first (``permissionDecision: ask``), every time. Each firing is
counted, and so is each call while there are action lessons.

It reads machine state only: the list the session start wrote (``action_lessons``), the notes of
the remotes of the session's folder, and the machine config for the folders m2b is off in. No file
of the store, no git, and in the folder of each session one small file of the lessons that denied a
call there. It never fails a call: on any error it prints nothing and exits 0, and the call runs.
It has its own small command, as the prompt hook has, because the core's command line loads every
command first.
"""

from __future__ import annotations

import datetime
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TextIO

from m2b import action_lessons, session_remotes
from m2b.config.machine import load_machine_config
from m2b.hook_input import PROJECT_DIR_VARIABLE
from m2b.paths import machine_paths

CURATION_RUN_VARIABLE = "M2B_CURATION_RUN"
LESSON_LINE = "m2b lesson for this command: the owner corrected Claude on it and kept the correction: "
SECOND_CALL = (
    "The call did not run, so that this is read first; change the command, or explain why it holds here, "
    "and the same call goes through in this session."
)


def main(environ: Mapping[str, str] | None = None, stdin: TextIO | None = None) -> int:
    environ = os.environ if environ is None else environ
    if environ.get(CURATION_RUN_VARIABLE) == "1":
        return 0
    try:
        answer = _answer(environ, sys.stdin if stdin is None else stdin)
    # A Bash call must never fail or wait for a lesson.
    except Exception:
        return 0
    if answer is not None:
        print(json.dumps(answer, ensure_ascii=False))
    return 0


def _answer(environ: Mapping[str, str], stdin: TextIO) -> dict[str, object] | None:
    given = json.loads(stdin.read())
    if not isinstance(given, dict) or given.get("tool_name") != "Bash":
        return None
    tool_input = given.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    # The session's folder, as the session start noted its remotes; the call's cwd moves with a cd.
    folder = environ.get(PROJECT_DIR_VARIABLE) or given.get("cwd")
    if not isinstance(command, str) or not isinstance(folder, str):
        return None
    machine = machine_paths(environ)
    lessons = action_lessons.read(machine)
    if not lessons:
        return None
    if load_machine_config(machine).distillate.covering(Path(folder)) is not None:
        return None
    now = datetime.datetime.now(datetime.timezone.utc)
    action_lessons.count_call(machine, now)
    remotes = session_remotes.noted(machine.state_dir / session_remotes.NOTES_FOLDER, folder, now) or frozenset()
    addresses = {session_remotes.address_of(remote) for remote in remotes}
    firing = [lesson for lesson in lessons if lesson.fires_on(command, addresses)]
    if not firing:
        return None
    action_lessons.count_fired(machine, [lesson.name for lesson in firing], now)
    session = given.get("session_id")
    if isinstance(session, str) and action_lessons.is_session_id(session):
        already = action_lessons.denied_in(machine, session)
        stopping = [lesson for lesson in firing if not lesson.ask and lesson.name not in already]
        if not stopping and already:
            action_lessons.keep_marks(machine, session)
        # Only a noted denial is a first one: unnoted, the same call would be denied again and again.
        if stopping and action_lessons.mark_denied(machine, session, [lesson.name for lesson in stopping], now):
            reason = " ".join(LESSON_LINE + lesson.text for lesson in stopping)
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"{reason} {SECOND_CALL}",
                }
            }
    said = "\n".join(LESSON_LINE + lesson.text for lesson in firing)
    output: dict[str, object] = {"hookEventName": "PreToolUse", "additionalContext": said}
    asking = [lesson for lesson in firing if lesson.ask]
    if asking:
        output["permissionDecision"] = "ask"
        output["permissionDecisionReason"] = " ".join(LESSON_LINE + lesson.text for lesson in asking)
    return {"hookSpecificOutput": output}
