"""Records the README screenshots from real Claude Code sessions against a demo store.

Each shot starts Claude Code in a hidden terminal inside an unrelated demo project, with m2b from this
checkout (``--plugin-dir``), its own ``M2B_HOME`` and ``--setting-sources project``, so neither the
user's settings and plugins nor their real store can show up. Every byte the session draws is
recorded, replayed into xterm.js in headless Chrome and trimmed with ImageMagick; the way of
recording and replaying follows the live check of prismantis (MIT). A shot with a prompt is one
real model turn on the user's Claude login; a shot that types a command of the band, which opens
its pane at once, is none.

Two demo stores stand behind the shots. The everyday one holds memory, tasks and two notes waiting.
The other is the first after a curation run that changed a fact and left proposals from the
person's sessions waiting; a scripted model plays that run, the stub the end-to-end scenarios use,
over invented sessions in a Claude Code folder of the demo's own, so the user's sessions are never
read and the two pictures show the same fact and proposals on every recording, under the day's
dates.

The demo machine lives under ``/tmp/sb-test-m2b-demo``, its owner is the invented Alex, and its
machine id is invented too. Claude Code itself still keeps its own records of these sessions in the
user's Claude Code folder (the trusted demo folder, transcripts), as for any session.
"""

from __future__ import annotations

import argparse
import datetime
import fcntl
import json
import os
import pty
import re
import select
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN = REPO_ROOT / "plugins" / "m2b"
IMAGES = REPO_ROOT / "docs" / "images"
RENDERER = Path(__file__).resolve().parent / "render_terminal.mjs"
DEMO = Path("/tmp/sb-test-m2b-demo")
PROJECT = DEMO / "projects" / "invoice-tool"
MACHINE_ID = "a1b2-alex-macbook"
XTERM = "@xterm/xterm@6.0.0"
COLUMNS = 100
BACKGROUND = "#1e1e2e"
# Variables of the session that runs this script; inherited, they mark the recorded Claude Code as
# a child session (no transcript, a warning line) and point m2b's worklog add-on at the real herdr.
INHERITED_PREFIXES = ("CLAUDE", "HERDR_", "M2B_")
# Where the user keeps Claude Code's config and login, when not in ~/.claude; the recording needs it.
KEPT = frozenset({"CLAUDE_CONFIG_DIR"})
TOOLS = ("claude", "node", "npm", "magick", "git")
DOWN = "\x1b[B"
# What a terminal takes as a command, not as text: a title, a color or a cursor move, a single key.
ESCAPES = re.compile(rb"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]|\x1b[@-Z\\-_]")
ENTER = "\r"


EVERYDAY = "everyday"
AFTER_A_RUN = "after-a-run"
WEEKDAY = "{weekday}"
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
REMINDER_DAYS_AHEAD = 3


@dataclass(frozen=True)
class Shot:
    """One picture: a session in a terminal of ``rows`` rows that types ``prompt`` and is drawn
    ``answer_seconds`` later. ``fresh_store`` builds the demo store named by ``store`` first;
    without it the shot runs on the store the shot before it left."""

    name: str
    rows: int
    answer_seconds: int
    prompt: str
    fresh_store: bool
    store: str = EVERYDAY


@dataclass(frozen=True)
class Wait:
    """Read what the command draws for ``seconds``, or only until it drew ``until``, then type ``keys``.
    ``until`` is looked for in the text alone: a shell with line editing draws an escape sequence
    between a line's end and its prompt."""

    seconds: float
    keys: str = ""
    until: bytes = b""


@dataclass(frozen=True)
class Recording:
    """What a command drew, each chunk with the seconds since its start, and the moment each wait ended."""

    chunks: tuple[tuple[float, bytes], ...]
    typed_at: tuple[float, ...]


# In this order: todos runs on the store the capture left, so it lists the task just captured, and
# both panes show the same run. The last two type a command of the band and wait for no model.
SHOTS = (
    Shot("session-start", 30, 30, "When does Sam bring the plywood, and where is the spare key for the shed?", True),
    Shot(
        "capture",
        34,
        45,
        f"remember that the shed roof needs 40 screws, 5 x 60 mm, and remind me on {WEEKDAY} to buy them",
        True,
    ),
    Shot("todos", 46, 40, "what's on my list?", False),
    Shot("review", 40, 6, "/m2b-review", True, AFTER_A_RUN),
    Shot("proposals", 40, 6, "/m2b-proposals", False, AFTER_A_RUN),
)

CORPUS = {
    "2026/10/20261012T081500Z-claude-3f2a.md": (
        "2026-10-12T10:15:00+02:00",
        "claude",
        "Dana's birthday is on 3 March. She would love a good fountain pen.",
    ),
    "2026/10/20261019T164000Z-cli-8c1d.md": (
        "2026-10-19T18:40:00+02:00",
        "cli",
        "Sam repairs boats at the harbour and has a spare sheet of marine plywood for the shed roof.",
    ),
    "2026/11/20261103T120500Z-claude-b71e.md": (
        "2026-11-03T13:05:00+01:00",
        "claude",
        "Agreed with Sam: he brings the plywood on Saturday 14 November, I pay for the screws.",
    ),
    "2026/11/20261105T071000Z-claude-0d9c.md": (
        "2026-11-05T08:10:00+01:00",
        "claude",
        "The spare key for the shed is under the blue pot by the back door.",
    ),
}
MEMORY = {
    "MEMORY.md": """# Memory

## Facts

- Dana, my sister: birthday 3 March, wants a fountain pen (dana.md)
- Sam, who repairs boats at the harbour, brings plywood for the shed roof on 14 November (sam.md)
- Spare shed key: under the blue pot by the back door (house.md)

## Current

- Rebuilding the garden shed roof before winter (since {recent})
- Planning the trip to Porto in spring (since 2026-09-14)
""",
    "dana.md": """# Dana

My sister. Birthday on 3 March. Would love a good fountain pen.

## Evidence

- [[20261012T081500Z-claude-3f2a.md]]
""",
    "sam.md": """# Sam

Repairs boats at the harbour. Brings marine plywood for the shed roof on Saturday 14 November;
I pay for the screws.

## Evidence

- [[20261019T164000Z-cli-8c1d.md]]
- [[20261103T120500Z-claude-b71e.md]]
""",
    "house.md": """# House

The spare key for the shed is under the blue pot by the back door.

## Evidence

- [[20261105T071000Z-claude-0d9c.md]]
""",
}
# (title, the days from the day of the recording to the day it is due, or None): one task due today
# and one overdue on any day the pictures are taken, which the band shows as two rows.
TASKS = (
    ("Pick up the paint for the shed door", 0),
    ("Return Sam's ladder", -5),
    ("Book the train to Porto", None),
)
INBOX = (
    "The plumber said the shed tap needs a new washer, size 3/4 inch",
    "Porto: Dana recommends the bookshop Lello, book tickets online",
)

# The store after a run. A note changes when Sam brings the plywood, and the run's ingest step
# rewrites his line in the facts list: the review names that fact with the old and the new day.
SAM_BEFORE = "- Sam, who repairs boats at the harbour, brings plywood for the shed roof on 14 November (sam.md)\n"
SAM_AFTER = SAM_BEFORE.replace("14 November", "21 November")
CHANGED_PLAN = "Sam called: he brings the plywood a week later, on Saturday 21 November"
# What Alex typed in a session of the last day, invented, and what the run proposes from it:
# (kind, the proposal, its words in the prompt, the days from the recording to its due day or None).
SESSION_FOLDER = "/home/alex/projects/invoice-tool"
SESSION_PROMPTS = (
    "Nora Lind runs IT at Northwind and signs off the renewals, so the export has to match her template.",
    "I promised Dana to send her the photos of the shed within three days, keep that in mind.",
    "We agreed with Sam that he keeps the old ladder until the roof is done.",
)
PROPOSALS = (
    (
        "person",
        "Nora Lind runs IT at Northwind and signs off the renewals.",
        "Nora Lind runs IT at Northwind and signs off the renewals",
        None,
    ),
    (
        "commitment",
        "Send Dana the photos of the shed.",
        "I promised Dana to send her the photos of the shed within three days",
        3,
    ),
    (
        "agreement",
        "Sam keeps the old ladder until the roof is done.",
        "We agreed with Sam that he keeps the old ladder until the roof is done",
        None,
    ),
)
MODEL_STUB = REPO_ROOT / "tests" / "unit" / "fakes" / "fake_claude.py"


class ImagesError(Exception):
    """A tool is missing or a step failed; the message says which."""


def demo_environment(environ: Mapping[str, str]) -> dict[str, str]:
    """The user's environment without the running session's variables, with the demo machine's."""
    kept = {key: value for key, value in environ.items() if key in KEPT or not key.startswith(INHERITED_PREFIXES)}
    kept.update(
        {
            "M2B_HOME": str(DEMO / "home"),
            "M2B_CORE_ROOT": str(PLUGIN),
            # A run the session start begins in the background must not file the demo inbox.
            "M2B_MODEL_RUNNER": str(REPO_ROOT / "scripts" / "no-model"),
            "TERM": "xterm-256color",
            "COLORTERM": "truecolor",
        }
    )
    return kept


def build_demo(environ: Mapping[str, str]) -> None:
    """A fresh demo machine: setup, filed notes and memory, tasks, two captures waiting,
    and one curation run without a model, which asks whether the Porto trip, untouched since September,
    is still current: the band's question comes from the core, not from the worklog."""
    store = set_up_machine(environ)
    _fill(store, environ, datetime.date.today())
    for text in INBOX:
        _m2b(environ, "capture", text)
    _m2b(environ, "curate", "--force")
    _make_demo_project(environ)


def build_demo_after_a_run(environ: Mapping[str, str]) -> None:
    """A fresh demo machine whose last curation run changed a fact and proposed three things from
    Alex's sessions: the review names the fact, and the proposals wait for keep or drop.

    A scripted model plays the run. It reads the sessions from a Claude Code folder of the demo's
    own, which holds invented prompts only; reading them is on for this one run and off again
    before any session starts, so no run a recording begins reads the user's sessions."""
    today = datetime.date.today()
    store = set_up_machine(environ)
    _fill(store, environ, today)
    _m2b(environ, "capture", CHANGED_PLAN)
    claude_code = DEMO / "claude-code"
    _write_sessions(claude_code, datetime.datetime.now(datetime.timezone.utc))
    scripted = {
        **environ,
        "M2B_MODEL_RUNNER": str(_scripted_model(_run_script(today))),
        "M2B_STUB_STORE": str(store),
        "CLAUDE_CONFIG_DIR": str(claude_code),
    }
    _m2b(environ, "config", "set", "curation.read_sessions", "true")
    try:
        _m2b(scripted, "curate", "--force")
    finally:
        _m2b(environ, "config", "set", "curation.read_sessions", "false")
    _make_demo_project(environ)


STORES: Mapping[str, Callable[[Mapping[str, str]], None]] = {
    EVERYDAY: build_demo,
    AFTER_A_RUN: build_demo_after_a_run,
}


def _fill(store: Path, environ: Mapping[str, str], today: datetime.date) -> None:
    """Filed notes, memory and tasks, the same in both demo stores."""
    for relative, (created, source, text) in CORPUS.items():
        _write(store / "corpus" / relative, f"---\ncreated: {created}\nsource: {source}\n---\n{text}\n")
    # Recent on any day the pictures are taken, so only the Porto trip is quiet enough to be asked about.
    recent = (today - datetime.timedelta(days=5)).isoformat()
    for name, text in MEMORY.items():
        _write(store / "memory" / name, text.replace("{recent}", recent))
    for title, days in TASKS:
        due = [] if days is None else ["--due", (today + datetime.timedelta(days=days)).isoformat()]
        _m2b(environ, "tasks", "add", *due, title)


def _make_demo_project(environ: Mapping[str, str]) -> None:
    make_project(
        PROJECT,
        {
            "README.md": "# invoice-tool\n\nTurns time entries into PDF invoices.\n",
            "src/invoice.py": "def total(entries):\n    return sum(e.hours * e.rate for e in entries)\n",
        },
        environ,
    )


def _write_sessions(claude_code: Path, now: datetime.datetime) -> None:
    """One invented session an hour old, as Claude Code keeps it: a run reads what was typed since the day before."""
    typed_at = (now - datetime.timedelta(hours=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    records = [
        {
            "type": "user",
            "timestamp": typed_at,
            "cwd": SESSION_FOLDER,
            "entrypoint": "cli",
            "promptSource": "typed",
            "origin": {"kind": "human"},
            "message": {"role": "user", "content": prompt},
        }
        for prompt in SESSION_PROMPTS
    ]
    folder = claude_code / "projects" / SESSION_FOLDER.replace("/", "-")
    _write(folder / "session.jsonl", "".join(json.dumps(record) + "\n" for record in records))


def _run_script(today: datetime.date) -> dict[str, object]:
    """What the scripted model does in the run: the step without tools answers with the proposals,
    and the ingest step files the one note by rewriting Sam's line and his fact file."""
    proposals = [
        {
            "kind": kind,
            "text": text,
            "quote": quote,
            "session": 1,
            "topic": None,
            "due": None if days is None else (today + datetime.timedelta(days=days)).isoformat(),
        }
        for kind, text, quote, days in PROPOSALS
    ]
    ingest = [
        {"tool": "Bash", "command": "m2b ingest list --json"},
        {"tool": "Edit", "file_path": "<store>/memory/MEMORY.md", "old_string": SAM_BEFORE, "new_string": SAM_AFTER},
        {
            "tool": "Edit",
            "file_path": "<store>/memory/sam.md",
            "old_string": "on Saturday 14 November",
            "new_string": "on Saturday 21 November",
        },
        {"tool": "Bash", "command": "m2b ingest note <capture:cli> 'filed: fact sam.md'"},
        {"tool": "Bash", "command": "m2b ingest finish <capture:cli>"},
    ]
    return {"text": {"answer": json.dumps({"proposals": proposals})}, "skills": {"/m2b:ingest": {"actions": ingest}}}


def _scripted_model(script: Mapping[str, object]) -> Path:
    """An executable that plays the model of a curation run from this script."""
    folder = DEMO / "scripted-model"
    _write(folder / "script.json", json.dumps(script))
    runner = folder / "claude"
    stub = " ".join(shlex.quote(str(part)) for part in (sys.executable, MODEL_STUB, folder / "script.json"))
    runner.write_text(f'#!/bin/sh\nexec {stub} "$@"\n', encoding="utf-8")
    runner.chmod(0o755)
    return runner


def set_up_machine(environ: Mapping[str, str]) -> Path:
    """A fresh demo machine, set up for the invented Alex with an empty store, whose folder it returns."""
    if DEMO.exists():
        shutil.rmtree(DEMO)
    store = DEMO / "notes"
    for folder in (DEMO / "home", store):
        folder.mkdir(parents=True)
    answers = {
        "store": {"backend": "folder", "path": str(store)},
        "tasks": {"backend": "markdown"},
        "owner": "Alex",
        "language": "en",
        "calendar": "none",
        "curates": True,
        # The id setup would derive from the host name would name the user's computer in a picture.
        "machine_id": MACHINE_ID,
    }
    _m2b(environ, "setup", "apply", "--answers", json.dumps(answers))
    return store


def make_project(project: Path, files: Mapping[str, str], environ: Mapping[str, str]) -> None:
    """An unrelated project for a session to start in: a git repository of Alex's with one commit."""
    for relative, text in files.items():
        _write(project / relative, text)
    git = ["git", "-C", str(project), "-c", "user.name=Alex", "-c", "user.email=alex@example.com"]
    for arguments in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "first draft"]):
        run([*git, *arguments], environ)


def shots_for(only: str | None) -> list[Shot]:
    """All shots, or the one asked for with the shots before it back to the last fresh store: todos
    lists the task the capture shot made, so recording it alone would contradict its picture."""
    if only is None:
        return list(SHOTS)
    index = next(i for i, shot in enumerate(SHOTS) if shot.name == only)
    start = max(i for i in range(index + 1) if SHOTS[i].fresh_store)
    return list(SHOTS[start : index + 1])


def reminder_weekday(today: datetime.date) -> str:
    """The weekday the capture shot asks to be reminded on: a few days ahead and never today, when
    "on Thursday" could mean this day or the one a week later and the model asks which."""
    return WEEKDAYS[(today + datetime.timedelta(days=REMINDER_DAYS_AHEAD)).weekday()]


def steps_for(shot: Shot, today: datetime.date | None = None) -> list[tuple[float, str]]:
    """Trust the demo folder (the dialog defaults to "No, exit"), let the start settle, ask, wait."""
    prompt = shot.prompt.replace(WEEKDAY, reminder_weekday(today or datetime.date.today()))
    return [(8, DOWN), (1, ENTER), (14, prompt), (1, ENTER), (shot.answer_seconds, "")]


def record(
    command: Sequence[str], cwd: Path, environ: Mapping[str, str], rows: int, steps: Sequence[tuple[float, str]]
) -> bytes:
    """Every byte the command draws in a terminal of ``COLUMNS`` x ``rows`` while the keys are typed."""
    waits = [Wait(seconds, keys) for seconds, keys in [*steps, (1, "")]]
    return b"".join(drawn for _, drawn in record_timed(command, cwd, environ, rows, COLUMNS, waits).chunks)


def record_timed(
    command: Sequence[str], cwd: Path, environ: Mapping[str, str], rows: int, columns: int, waits: Sequence[Wait]
) -> Recording:
    """What the command draws in a terminal of ``columns`` x ``rows`` while the waits pass and their
    keys are typed, with its times. It ends early when the command does, and fails when a wait does
    not see what it waits for."""
    pid, fd = pty.fork()
    if pid == 0:  # pragma: no cover - the child process
        # A child that cannot start the command must not unwind into the parent's cleanup.
        try:
            os.chdir(cwd)
            os.execvpe(command[0], list(command), dict(environ))
        finally:
            os._exit(127)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))
    start = time.monotonic()
    chunks: list[tuple[float, bytes]] = []
    typed_at: list[float] = []
    try:
        for wait in waits:
            if not _read_for(fd, wait, rows, start, chunks):
                break
            typed_at.append(time.monotonic() - start)
            if wait.keys:
                os.write(fd, wait.keys.encode())
    finally:
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
        os.close(fd)
    return Recording(tuple(chunks), tuple(typed_at))


def _read_for(fd: int, wait: Wait, rows: int, start: float, chunks: list[tuple[float, bytes]]) -> bool:
    """Reads until the wait is over, answering cursor position queries; False once the command has ended."""
    end = time.monotonic() + wait.seconds
    seen = b""
    while time.monotonic() < end:
        ready, _, _ = select.select([fd], [], [], 0.1)
        if not ready:
            continue
        try:
            data = os.read(fd, 65536)
        except OSError:
            return False
        if not data:
            return False
        chunks.append((time.monotonic() - start, data))
        if b"\x1b[6n" in data:
            os.write(fd, f"\x1b[{rows};1R".encode())
        if wait.until:
            seen += data
            if wait.until in ESCAPES.sub(b"", seen):
                return True
    if wait.until:
        raise ImagesError(f"the terminal did not draw {wait.until!r} within {wait.seconds:g} seconds")
    return True


def render(recording: Path, image: Path, rows: int, xterm: Path) -> None:
    run(
        ["node", str(RENDERER), str(recording), str(image), str(COLUMNS), str(rows), str(xterm), BACKGROUND], os.environ
    )
    run(["magick", str(image), "-trim", "+repage", "-bordercolor", BACKGROUND, "-border", "18", str(image)], os.environ)


def missing_tools(which: Callable[[str], str | None] = shutil.which, tools: Sequence[str] = TOOLS) -> list[str]:
    return [tool for tool in tools if which(tool) is None]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="readme-images", description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--only", choices=[shot.name for shot in SHOTS], help="this shot and the ones its store depends on"
    )
    arguments = parser.parse_args(argv)
    try:
        missing = missing_tools()
        if missing:
            raise ImagesError(f"not found on PATH: {', '.join(missing)}")
        environ = demo_environment(os.environ)
        with tempfile.TemporaryDirectory(prefix="sb-test-readme-images-") as work:
            xterm = _install_xterm(Path(work))
            for shot in shots_for(arguments.only):
                if shot.fresh_store:
                    STORES[shot.store](environ)
                recording = Path(work) / f"{shot.name}.bin"
                recording.write_bytes(record(claude_command(), PROJECT, environ, shot.rows, steps_for(shot)))
                IMAGES.mkdir(parents=True, exist_ok=True)
                render(recording, IMAGES / f"{shot.name}.png", shot.rows, xterm)
                print(f"readme-images: {IMAGES.relative_to(REPO_ROOT) / shot.name}.png")
    except ImagesError as error:
        print(f"readme-images: {error}", file=sys.stderr)
        return 1
    print("readme-images: look at each picture before committing it; the answers are the model's")
    return 0


def claude_command() -> list[str]:
    allowed = ["Skill(m2b:todos)", "Skill(m2b:capture)", "Skill(m2b:search)"]
    return [
        "claude",
        "--setting-sources",
        "project",
        "--plugin-dir",
        str(PLUGIN),
        "--permission-mode",
        "default",
        "--allowedTools",
        *allowed,
    ]


def _install_xterm(work: Path) -> Path:
    run(["npm", "install", "--silent", "--no-audit", "--no-fund", "--prefix", str(work), XTERM], os.environ)
    return work / "node_modules" / "@xterm" / "xterm"


def _m2b(environ: Mapping[str, str], *arguments: str) -> None:
    run([str(PLUGIN / "bin" / "m2b"), *arguments], environ)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run(command: Sequence[str], environ: Mapping[str, str]) -> None:
    result = subprocess.run(list(command), env=dict(environ), capture_output=True, text=True, check=False)
    if result.returncode != 0:
        lines = [line for line in (result.stderr or result.stdout).strip().splitlines() if line.strip()]
        # The first lines name the cause; the last ones are a stack trace or a log pointer.
        detail = " | ".join(lines[:3]) if lines else f"exit {result.returncode}"
        raise ImagesError(f"{' '.join(Path(part).name for part in command[:2])} failed: {detail}")


if __name__ == "__main__":
    sys.exit(main())
