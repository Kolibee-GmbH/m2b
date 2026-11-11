"""A fenced headless ``claude -p`` run, the form every check with a real model uses.

From an empty working folder, with ``--setting-sources project`` (so the user's own settings,
permission rules and plugins stay out), one ``--plugin-dir`` for the core, and
``--permission-mode dontAsk`` (so nothing runs that is not pre-approved). The output is read as
``stream-json`` line by line, so a caller can stop the run as soon as it has seen what it needs.

A check that asks the model to read a text and answer, with nothing to call, uses the core's own
run for that, ``m2b.curate.model.text_command`` and ``run_text``.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAX_TURNS = 3
STDERR_TAIL_CHARACTERS = 400


@dataclass(frozen=True)
class SkillRun:
    """What one run showed: the first skill it called, the skills it had, or why it failed."""

    skill: str | None
    loaded_skills: list[str] | None
    error: str | None
    seconds: float


def fenced_command(
    prompt: str, plugin_dir: Path, claude: str = "claude", max_turns: int = DEFAULT_MAX_TURNS
) -> list[str]:
    return [
        claude,
        "-p",
        prompt,
        "--setting-sources",
        "project",
        "--plugin-dir",
        str(plugin_dir),
        "--permission-mode",
        "dontAsk",
        "--max-turns",
        str(max_turns),
        "--output-format",
        "stream-json",
        "--verbose",
    ]


def skill_in(line: str) -> str | None:
    """The skill a ``Skill`` tool call in this stream line names, if it holds one."""
    message = _parse(line)
    if message is None or message.get("type") != "assistant":
        return None
    body = message.get("message")
    content = body.get("content") if isinstance(body, dict) else None
    for block in content if isinstance(content, list) else []:
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Skill":
            skill = (block.get("input") or {}).get("skill")
            return str(skill) if skill else None
    return None


def loaded_skills_in(line: str) -> list[str] | None:
    """The skills the session started with, from its init line."""
    message = _parse(line)
    if message is None or message.get("type") != "system" or message.get("subtype") != "init":
        return None
    skills = message.get("skills")
    return [str(skill) for skill in skills] if isinstance(skills, list) else None


def run_until_skill(command: Sequence[str], cwd: Path, environ: Mapping[str, str], timeout_seconds: float) -> SkillRun:
    """Runs the command and stops it at its first ``Skill`` call; a run without one is no error."""
    started = time.monotonic()
    skill: str | None = None
    loaded: list[str] | None = None
    with (
        tempfile.TemporaryFile() as stderr,
        subprocess.Popen(
            list(command), cwd=cwd, env=dict(environ), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=stderr
        ) as process,
    ):
        timer = threading.Timer(timeout_seconds, process.kill)
        timer.start()
        try:
            assert process.stdout is not None
            for raw in process.stdout:
                line = raw.decode("utf-8", errors="replace")
                loaded = loaded_skills_in(line) or loaded
                skill = skill_in(line)
                if skill is not None:
                    process.terminate()
                    break
            process.wait()
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill()
                process.wait()
        seconds = time.monotonic() - started
        if skill is not None:
            return SkillRun(skill, loaded, None, seconds)
        if seconds >= timeout_seconds:
            return SkillRun(None, loaded, f"no answer within {timeout_seconds:g} seconds", seconds)
        if process.returncode != 0:
            stderr.seek(0)
            tail = stderr.read().decode("utf-8", errors="replace").strip()[-STDERR_TAIL_CHARACTERS:]
            return SkillRun(None, loaded, f"exit {process.returncode}: {tail}", seconds)
    return SkillRun(None, loaded, None, seconds)


def _parse(line: str) -> dict[str, object] | None:
    try:
        message = json.loads(line)
    except ValueError:
        return None
    return message if isinstance(message, dict) else None
