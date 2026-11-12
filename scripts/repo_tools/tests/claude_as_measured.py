"""A stand-in for ``claude -p`` that treats the probe skill as Claude Code 2.1.322 did when it was
measured on 2026-11-12, for the tests of the fence probe. It asks no model.

It reads the skill named by the prompt from the ``--plugin-dir``, makes the call of each numbered
step, refuses what the real one refused and prints ``stream-json`` lines of the same shape:

- the start line lists the tools of ``--tools``, names the model of ``--model`` and, unless
  ``CLAUDE_CODE_DISABLE_AUTO_MEMORY`` is set, the memory folder of the git repository above the
  working folder;
- unless ``CLAUDE_CODE_DISABLE_CLAUDE_MDS`` is set, the ``CLAUDE.md``, ``.claude/CLAUDE.md`` and
  ``.claude/rules/*.md`` of that repository are in the context, and with a memory folder its
  ``MEMORY.md`` is too;
- a Bash command runs when a rule of ``--allowedTools`` names its start and it is one command;
  every other Bash, Read and Write call is refused and listed in the result's
  ``permission_denials``; a tool that is not among ``--tools`` does not exist, which is no denial;
- the answer is every word after ``canary-`` in the context and the skill.

``CLAUDE_AS_MEASURED_EXCEPT`` names what it does differently, separated by commas:
``reads-claude-mds`` and ``keeps-memory`` (it ignores that switch), ``skips-cat`` (it leaves the
plain ``cat`` out) and ``writes`` (it carries out every Write).

Usage: python3 claude_as_measured.py <claude arguments...>
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

EXCEPT_VARIABLE = "CLAUDE_AS_MEASURED_EXCEPT"
CANARY = re.compile(r"canary-[0-9a-f]+")
BASH_STEP = re.compile(r"^\d+\. Run in Bash[^:]*: `(.+)`$")
READ_STEP = re.compile(r"^\d+\. Read the file `(.+)` with the Read tool\.$")
WRITE_STEP = re.compile(r"^\d+\. Write the single word `(\w+)` to the file `(.+)` with the Write tool\.$")
OTHER_TOOL_STEP = re.compile(r"^\d+\. Call the (\w+) tool ")
SEVERAL_COMMANDS = (";", "$(", "&", "|", "`")


def _values(arguments: Sequence[str], flag: str) -> list[str]:
    """What follows ``flag`` up to the next flag, for each time it is given."""
    found = []
    for position, argument in enumerate(arguments):
        if argument != flag:
            continue
        for value in arguments[position + 1 :]:
            if value.startswith("--"):
                break
            found.append(value)
    return found


def _repository_above(folder: Path) -> Path:
    return next((above for above in (folder, *folder.parents) if (above / ".git").exists()), folder)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _calls(skill: str) -> list[tuple[str, dict[str, str]]]:
    calls: list[tuple[str, dict[str, str]]] = []
    for line in skill.splitlines():
        bash, read, write, other = (step.match(line) for step in (BASH_STEP, READ_STEP, WRITE_STEP, OTHER_TOOL_STEP))
        if bash:
            calls.append(("Bash", {"command": bash.group(1)}))
        elif read:
            calls.append(("Read", {"file_path": read.group(1)}))
        elif write:
            calls.append(("Write", {"file_path": write.group(2), "content": write.group(1)}))
        elif other:
            calls.append((other.group(1), {}))
    return calls


def _allowed_command(command: str, rules: Sequence[str]) -> bool:
    starts = [rule[len("Bash(") : -len(" *)")] for rule in rules if rule.startswith("Bash(") and rule.endswith(" *)")]
    one_command = not any(sign in command for sign in SEVERAL_COMMANDS)
    return one_command and any(command.startswith(f"{start} ") for start in starts)


def main(arguments: Sequence[str]) -> int:
    different = set(filter(None, os.environ.get(EXCEPT_VARIABLE, "").split(",")))
    reads_claude_mds = os.environ.get("CLAUDE_CODE_DISABLE_CLAUDE_MDS") != "1" or "reads-claude-mds" in different
    keeps_memory = os.environ.get("CLAUDE_CODE_DISABLE_AUTO_MEMORY") != "1" or "keeps-memory" in different
    tools = _values(arguments, "--tools")[0].split(",")
    rules = _values(arguments, "--allowedTools")
    skill_name = arguments[arguments.index("-p") + 1].rpartition(":")[2]
    skill = _read(Path(_values(arguments, "--plugin-dir")[0]) / "skills" / skill_name / "SKILL.md")

    repository = _repository_above(Path.cwd())
    claude_folder = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    memory = claude_folder / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(repository)) / "memory"
    context = skill
    if reads_claude_mds:
        above = [repository / "CLAUDE.md", repository / ".claude" / "CLAUDE.md"]
        above += sorted((repository / ".claude" / "rules").glob("*.md"))
        context += "".join(_read(path) for path in above)
        if keeps_memory:
            context += _read(memory / "MEMORY.md")

    start: dict[str, Any] = {"type": "system", "subtype": "init", "tools": tools, "mcp_servers": []}
    start["claude_code_version"] = "as measured"
    start["model"] = _values(arguments, "--model")[0]
    if keeps_memory:
        start["memory_paths"] = {"auto": f"{memory}/"}
    lines = [start]
    denials = []
    for number, (tool, tool_input) in enumerate(_calls(skill), start=1):
        if "skips-cat" in different and tool_input.get("command", "").startswith("cat "):
            continue
        call = {"type": "tool_use", "id": f"call-{number}", "name": tool, "input": tool_input}
        lines.append({"type": "assistant", "message": {"content": [call]}})
        answer: dict[str, Any] = {"type": "tool_result", "tool_use_id": call["id"]}
        if tool not in tools:
            answer.update(is_error=True, content=f"No such tool available: {tool}.")
        elif tool == "Bash" and _allowed_command(tool_input["command"], rules):
            answer.update(is_error=False, content="one note")
        elif tool == "Write" and "writes" in different:
            Path(tool_input["file_path"]).write_text(tool_input["content"], encoding="utf-8")
            answer.update(is_error=False, content="written")
        else:
            answer.update(is_error=True, content=f"Permission to use {tool} has been denied.")
            denials.append({"tool_name": tool, "tool_use_id": call["id"], "tool_input": tool_input})
        lines.append({"type": "user", "message": {"content": [answer]}})
    words = "\n".join(dict.fromkeys(CANARY.findall(context)))
    lines.append({"type": "assistant", "message": {"content": [{"type": "text", "text": words}]}})
    lines.append({"type": "result", "subtype": "success", "is_error": False, "permission_denials": denials})
    for line in lines:
        print(json.dumps(line), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
