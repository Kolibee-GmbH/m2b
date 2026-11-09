"""Records the README screenshots from real Claude Code sessions against a demo store.

Each shot starts Claude Code in a hidden terminal inside an unrelated demo project, with m2b from this
checkout (``--plugin-dir``), its own ``M2B_HOME`` and ``--setting-sources project``, so neither the
user's settings and plugins nor their real store can show up. Every byte the session draws is
recorded, replayed into xterm.js in headless Chrome and trimmed with ImageMagick; the way of
recording and replaying follows the live check of prismantis (MIT). A shot with a prompt is one
real model turn on the user's Claude login.

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
import select
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
# a child session (no transcript, a warning line) and point m2b's herdr add-on at the real herdr.
INHERITED_PREFIXES = ("CLAUDE", "HERDR_", "M2B_")
# Where the user keeps Claude Code's config and login, when not in ~/.claude; the recording needs it.
KEPT = frozenset({"CLAUDE_CONFIG_DIR"})
DOWN = "\x1b[B"
ENTER = "\r"


@dataclass(frozen=True)
class Shot:
    name: str
    rows: int
    answer_seconds: int
    prompt: str
    fresh_store: bool


# In this order: todos runs on the store the capture left, so it lists the task just captured.
SHOTS = (
    Shot("session-start", 30, 30, "When does Sam bring the plywood, and where is the spare key for the shed?", True),
    Shot(
        "capture",
        34,
        45,
        "remember that the shed roof needs 40 screws, 5 x 60 mm, and remind me on Thursday to buy them",
        True,
    ),
    Shot("todos", 40, 40, "what's on my list?", False),
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
- Sam repairs boats at the harbour; brings plywood for the shed roof on 14 November (sam.md)
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
# (title, due or None)
TASKS = (
    ("Pick up the paint for the shed door", "2026-11-13"),
    ("Return Sam's ladder", "2026-11-07"),
    ("Book the train to Porto", None),
)
INBOX = (
    "The plumber said the shed tap needs a new washer, size 3/4 inch",
    "Porto: Dana recommends the bookshop Lello, book tickets online",
)


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
    """A fresh demo machine: setup, the band on, filed notes and memory, tasks, two captures waiting,
    and one curation run without a model, which asks whether the Porto trip, untouched since September,
    is still current: the band's question comes from the core, not from the experimental worklog."""
    if DEMO.exists():
        shutil.rmtree(DEMO)
    store = DEMO / "notes"
    for folder in (DEMO / "home", store, PROJECT / "src"):
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
    _m2b(environ, "addons", "on", "band")
    for relative, (created, source, text) in CORPUS.items():
        _write(store / "corpus" / relative, f"---\ncreated: {created}\nsource: {source}\n---\n{text}\n")
    # Recent on any day the pictures are taken, so only the Porto trip is quiet enough to be asked about.
    recent = (datetime.date.today() - datetime.timedelta(days=5)).isoformat()
    for name, text in MEMORY.items():
        _write(store / "memory" / name, text.replace("{recent}", recent))
    for title, due in TASKS:
        _m2b(environ, "tasks", "add", *(["--due", due] if due else []), title)
    for text in INBOX:
        _m2b(environ, "capture", text)
    _m2b(environ, "curate", "--force")
    _write(PROJECT / "README.md", "# invoice-tool\n\nTurns time entries into PDF invoices.\n")
    _write(PROJECT / "src" / "invoice.py", "def total(entries):\n    return sum(e.hours * e.rate for e in entries)\n")
    git = ["git", "-C", str(PROJECT), "-c", "user.name=Alex", "-c", "user.email=alex@example.com"]
    for arguments in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "first draft"]):
        _run([*git, *arguments], environ)


def shots_for(only: str | None) -> list[Shot]:
    """All shots, or the one asked for with the shots before it back to the last fresh store: todos
    lists the task the capture shot made, so recording it alone would contradict its picture."""
    if only is None:
        return list(SHOTS)
    index = next(i for i, shot in enumerate(SHOTS) if shot.name == only)
    start = max(i for i in range(index + 1) if SHOTS[i].fresh_store)
    return list(SHOTS[start : index + 1])


def steps_for(shot: Shot) -> list[tuple[float, str]]:
    """Trust the demo folder (the dialog defaults to "No, exit"), let the start settle, ask, wait."""
    return [(8, DOWN), (1, ENTER), (14, shot.prompt), (1, ENTER), (shot.answer_seconds, "")]


def record(
    command: Sequence[str], cwd: Path, environ: Mapping[str, str], rows: int, steps: Sequence[tuple[float, str]]
) -> bytes:
    """Every byte the command draws in a terminal of ``COLUMNS`` x ``rows`` while the keys are typed."""
    pid, fd = pty.fork()
    if pid == 0:  # pragma: no cover - the child process
        # A child that cannot start the command must not unwind into the parent's cleanup.
        try:
            os.chdir(cwd)
            os.execvpe(command[0], list(command), dict(environ))
        finally:
            os._exit(127)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, COLUMNS, 0, 0))
    drawn = bytearray()
    try:
        for seconds, keys in [*steps, (1, "")]:
            if not _read_for(fd, seconds, rows, drawn):
                break
            if keys:
                os.write(fd, keys.encode())
    finally:
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
        os.close(fd)
    return bytes(drawn)


def _read_for(fd: int, seconds: float, rows: int, drawn: bytearray) -> bool:
    """Reads for ``seconds``, answering cursor position queries; False once the command has ended."""
    end = time.monotonic() + seconds
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
        drawn.extend(data)
        if b"\x1b[6n" in data:
            os.write(fd, f"\x1b[{rows};1R".encode())
    return True


def render(recording: Path, image: Path, rows: int, xterm: Path) -> None:
    _run(
        ["node", str(RENDERER), str(recording), str(image), str(COLUMNS), str(rows), str(xterm), BACKGROUND], os.environ
    )
    _run(
        ["magick", str(image), "-trim", "+repage", "-bordercolor", BACKGROUND, "-border", "18", str(image)], os.environ
    )


def missing_tools(which: Callable[[str], str | None] = shutil.which) -> list[str]:
    return [tool for tool in ("claude", "node", "npm", "magick", "git") if which(tool) is None]


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
                    build_demo(environ)
                recording = Path(work) / f"{shot.name}.bin"
                recording.write_bytes(record(_claude(), PROJECT, environ, shot.rows, steps_for(shot)))
                IMAGES.mkdir(parents=True, exist_ok=True)
                render(recording, IMAGES / f"{shot.name}.png", shot.rows, xterm)
                print(f"readme-images: {IMAGES.relative_to(REPO_ROOT) / shot.name}.png")
    except ImagesError as error:
        print(f"readme-images: {error}", file=sys.stderr)
        return 1
    print("readme-images: look at each picture before committing it; the answers are the model's")
    return 0


def _claude() -> list[str]:
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
    _run(["npm", "install", "--silent", "--no-audit", "--no-fund", "--prefix", str(work), XTERM], os.environ)
    return work / "node_modules" / "@xterm" / "xterm"


def _m2b(environ: Mapping[str, str], *arguments: str) -> None:
    _run([str(PLUGIN / "bin" / "m2b"), *arguments], environ)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _run(command: Sequence[str], environ: Mapping[str, str]) -> None:
    result = subprocess.run(list(command), env=dict(environ), capture_output=True, text=True, check=False)
    if result.returncode != 0:
        lines = [line for line in (result.stderr or result.stdout).strip().splitlines() if line.strip()]
        # The first lines name the cause; the last ones are a stack trace or a log pointer.
        detail = " | ".join(lines[:3]) if lines else f"exit {result.returncode}"
        raise ImagesError(f"{' '.join(Path(part).name for part in command[:2])} failed: {detail}")


if __name__ == "__main__":
    sys.exit(main())
