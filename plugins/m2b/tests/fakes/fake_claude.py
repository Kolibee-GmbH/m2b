"""A stand-in for ``claude -p`` that replays a scenario's model actions under the given fence.

It reads the actions file, checks every tool call against ``--allowedTools`` the way the real run
would under ``--permission-mode dontAsk``, carries out the allowed ones and denies the rest, and
writes ``stream-json`` lines with a final ``result`` that lists the denials. ``<store>`` in an
action stands for the folder in ``M2B_STUB_STORE``, ``<m2b-home>`` for ``M2B_HOME``, the folder the
machine paths lie under, ``<capture:cli>`` for the one inbox capture
with that source, whose name the scenario cannot know in advance (fixed at its first use).

The rules behave as measured with Claude Code 2.1.319 on 2026-11-07: an ``Edit(...)``
rule covers Edit and Write, a ``Write(<path>)`` rule covers nothing, and a path rule is the absolute
``//path/**`` form. That a ``Read(...)`` rule also covers Glob and Grep follows Claude Code's
documentation and was not measured.

The actions file: ``{"actions": [...], "outcome": "success"}``, or for a curation run with several
model steps ``{"skills": {"/m2b:ingest": {"actions": [...]}, "/m2b:lint": {...}}}``, chosen by the
prompt (a skill not listed does nothing and succeeds); a skill's entry may also be a list of such
scripts, the n-th for its n-th call and the last for every later one. Actions:
``{"tool": "Bash", "command": "..."}`` (run without a shell), ``{"tool": "Read", "file_path": "..."}``,
``{"tool": "Write", "file_path": "...", "content": "..."}``, ``{"tool": "Edit", "file_path": "...",
"old_string": "...", "new_string": "..."}`` (the old text must occur exactly once, as in the real
tool), ``Glob`` and ``Grep`` with a ``path``
(checked, not carried out), any other ``{"tool": name, ...}``
(checked, not carried out), ``{"sleep": <seconds>}``, and ``{"hang": "<pid file>"}``: start a child
process, write its pid and wait for ever. ``outcome`` is ``success``, ``error`` (a result with ``is_error``),
``not-logged-in`` (the result Claude Code 2.1.319 prints without a login: subtype ``success`` with
``is_error``), ``over-budget`` (the result at ``--max-budget-usd``) or ``no-result`` (exit 1 without a
result line). Each call is appended to ``<actions file>.calls``
as one JSON line: the arguments, the working folder and the variables the fence sets.

As Claude Code does, the ``bin/`` folder of each ``--plugin-dir`` comes first on ``PATH`` for Bash
calls, so a module's skill calls the module's own command by its name.

Usage: python3 fake_claude.py <actions file> <claude arguments...>
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

OPTIONS_WITH_VALUES = ("-p", "--setting-sources", "--permission-mode", "--output-format", "--max-turns", "--model")
STORE_VARIABLE = "M2B_STUB_STORE"
COVERED_BY = {"Read": ("Read", "Glob", "Grep"), "Edit": ("Edit", "Write")}
SHELL_OPERATORS = re.compile(r"^[;&|<>()]+$")
_RULE = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)(?:\((.*)\))?$", re.DOTALL)


def parse_arguments(arguments: list[str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {"plugin_dirs": [], "allowed": [], "flags": []}
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument in OPTIONS_WITH_VALUES:
            parsed[argument.lstrip("-").replace("-", "_")] = arguments[index + 1]
            index += 2
        elif argument == "--plugin-dir":
            parsed["plugin_dirs"].append(arguments[index + 1])
            index += 2
        elif argument == "--allowedTools":
            index += 1
            while index < len(arguments) and not arguments[index].startswith("--"):
                parsed["allowed"].append(arguments[index])
                index += 1
        else:
            parsed["flags"].append(argument)
            index += 1
    return parsed


def _path_pattern(specifier: str) -> re.Pattern[str] | None:
    """A ``//absolute/**`` rule as a regular expression; ``dir/**`` also covers ``dir`` itself."""
    if not specifier.startswith("//"):
        return None
    pattern = re.escape(specifier[1:]).replace(r"\*\*", "\0").replace(r"\*", "[^/]*").replace("\0", ".*")
    if pattern.endswith("/.*"):
        pattern = pattern[:-3] + "(/.*)?"
    return re.compile(pattern + r"\Z")


def _command_allowed(command: str, specifier: str) -> bool:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    if any(SHELL_OPERATORS.match(token) for token in lexer):
        return False
    if specifier.endswith(" *"):
        prefix = specifier[:-2]
        return command == prefix or command.startswith(prefix + " ")
    return command == specifier


def allowed(action: dict[str, Any], rules: list[str]) -> bool:
    tool = action["tool"]
    for rule in rules:
        match = _RULE.match(rule)
        if match is None:
            continue
        name, specifier = match.group(1), match.group(2)
        if tool not in COVERED_BY.get(name, (name,)):
            continue
        if specifier is None:
            return True
        if tool == "Bash" and _command_allowed(action["command"], specifier):
            return True
        if name in COVERED_BY:
            pattern = _path_pattern(specifier)
            path = os.path.abspath(action.get("file_path") or action.get("path") or ".")
            if pattern is not None and pattern.match(path):
                return True
    return False


def _carry_out(action: dict[str, Any]) -> tuple[str, bool]:
    """The tool's output and whether it failed."""
    tool = action["tool"]
    try:
        if tool == "Bash":
            result = subprocess.run(shlex.split(action["command"]), capture_output=True, text=True, check=False)
            return result.stdout + result.stderr, result.returncode != 0
        if tool == "Read":
            return Path(action["file_path"]).read_text(encoding="utf-8"), False
        if tool == "Write":
            Path(action["file_path"]).write_text(action.get("content", ""), encoding="utf-8")
            return "written", False
        if tool == "Edit":
            path = Path(action["file_path"])
            text = path.read_text(encoding="utf-8")
            if text.count(action["old_string"]) != 1:
                return "old_string must occur exactly once", True
            path.write_text(text.replace(action["old_string"], action["new_string"]), encoding="utf-8")
            return "edited", False
    except OSError as error:
        return str(error), True
    return "done", False


def _hang(pid_file: str) -> None:
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
    Path(pid_file).write_text(str(child.pid), encoding="utf-8")
    while True:
        time.sleep(1)


def _emit(message: dict[str, Any]) -> None:
    print(json.dumps(message), flush=True)


_CAPTURE = re.compile(r"<capture:([a-z][a-z0-9-]*)>")


class PlaceholderError(Exception):
    """A ``<capture:source>`` that does not name exactly one capture."""


def _replace_placeholders(value: Any, store: str, captures: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: _replace_placeholders(item, store, captures) for key, item in value.items()}
    if not isinstance(value, str):
        return value

    def capture(match: re.Match[str]) -> str:
        source = match.group(1)
        if source not in captures:
            found = sorted(path.name for path in Path(store, "inbox").glob(f"*-{source}-????.md"))
            if len(found) != 1:
                raise PlaceholderError(f"{match.group(0)} matches {len(found)} inbox files")
            captures[source] = found[0]
        return captures[source]

    if "<m2b-home>" in value:
        home = os.environ.get("M2B_HOME")
        if not home:
            raise PlaceholderError("<m2b-home> without M2B_HOME")
        value = value.replace("<m2b-home>", home)
    value = value.replace("<store>", store)
    return _CAPTURE.sub(capture, value)


def _script_for_call(skills: dict[str, Any], prompt: str, actions_file: Path) -> dict[str, Any]:
    """The script for this call of the skill: the n-th of a list for its n-th call, the last after."""
    entry = skills.get(prompt, {"actions": []})
    if not isinstance(entry, list):
        return dict(entry)
    lines = Path(f"{actions_file}.calls").read_text(encoding="utf-8").splitlines()
    calls = [json.loads(line)["arguments"] for line in lines]
    number = sum(1 for arguments in calls if parse_arguments(arguments).get("p") == prompt)
    return dict(entry[min(number, len(entry)) - 1])


def main(argv: list[str]) -> int:
    actions_file, arguments = Path(argv[0]), argv[1:]
    parsed = parse_arguments(arguments)
    with Path(f"{actions_file}.calls").open("a", encoding="utf-8") as calls:
        seen = {
            "arguments": arguments,
            "cwd": os.getcwd(),
            "cwd_entries": sorted(os.listdir(".")),
            "environment": {
                key: os.environ.get(key) for key in ("M2B_CURATION_RUN", "M2B_RUN_TOKEN", "M2B_REFRESH_ALL")
            },
        }
        calls.write(json.dumps(seen) + "\n")
    script = json.loads(actions_file.read_text(encoding="utf-8"))
    if "skills" in script:
        script = _script_for_call(script["skills"], parsed.get("p", ""), actions_file)
    bins = [str(Path(folder, "bin")) for folder in parsed["plugin_dirs"] if Path(folder, "bin").is_dir()]
    os.environ["PATH"] = os.pathsep.join([*bins, os.environ.get("PATH", "")])
    store = os.environ.get(STORE_VARIABLE, "")
    captures: dict[str, str] = {}
    _emit({"type": "system", "subtype": "init", "cwd": os.getcwd(), "skills": []})
    denials = []
    # As Claude Code does, a tool call past --max-turns ends the run with error_max_turns.
    max_turns = int(parsed["max_turns"]) if "max_turns" in parsed else None
    tool_calls = 0
    for number, raw in enumerate(script.get("actions", []), 1):
        try:
            action = _replace_placeholders(raw, store, captures)
        except PlaceholderError as error:
            print(f"fake claude: {error}", file=sys.stderr)
            return 2
        if "hang" in action:
            _hang(action["hang"])
        if "sleep" in action:
            time.sleep(float(action["sleep"]))
            continue
        tool_calls += 1
        if max_turns is not None and tool_calls > max_turns:
            _emit({"type": "result", "subtype": "error_max_turns", "is_error": True, "permission_denials": denials})
            return 0
        tool_use_id = f"toolu_{number:04d}"
        tool_input = {key: value for key, value in action.items() if key != "tool"}
        _emit(
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "tool_use", "id": tool_use_id, "name": action["tool"], "input": tool_input}]
                },
            }
        )
        if allowed(action, parsed["allowed"]):
            content, is_error = _carry_out(action)
        else:
            denials.append({"tool_name": action["tool"], "tool_use_id": tool_use_id, "tool_input": tool_input})
            content, is_error = f"Permission to use {action['tool']} has been denied.", True
        _emit(
            {
                "type": "user",
                "message": {
                    "content": [
                        {"type": "tool_result", "tool_use_id": tool_use_id, "content": content, "is_error": is_error}
                    ]
                },
            }
        )
    outcome = script.get("outcome", "success")
    if outcome == "no-result":
        print("fake claude: crashed", file=sys.stderr)
        return 1
    if outcome == "over-budget":
        _emit({"type": "result", "subtype": "error_max_budget_usd", "is_error": True})
        return 1
    if outcome == "not-logged-in":
        _emit({"type": "result", "subtype": "success", "is_error": True, "result": "Not logged in · Please run /login"})
        return 1
    _emit(
        {
            "type": "result",
            "subtype": "success" if outcome == "success" else "error_during_execution",
            "is_error": outcome != "success",
            "result": "done",
            "permission_denials": denials,
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
