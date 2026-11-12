"""Records the README's moving picture: one sentence followed from a prompt into a later session.

Three acts, each drawn by the real programs in a hidden terminal: a Claude Code session in one demo
project is told to remember a sentence, the start of the next session begins the curation run that
files it with a real model, in the background and without a key typed, and a session in another
project is asked for it. The demo machine, its environment and the way a session is started are the
screenshots' (``readme_images``); the store starts empty, so the fact the last act answers with can
only come from the run in the second. It costs two model turns and one curation run on the user's
Claude login.

What the terminals drew is kept with its times. The picture shortens the waits (a session's start, the
model's answer, the run), puts a line of words before each act and is rendered by ``agg``.
"""

from __future__ import annotations

import argparse
import codecs
import getpass
import json
import os
import re
import socket
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from repo_tools import readme_images
from repo_tools.readme_images import DOWN, ENTER, ESCAPES, IMAGES, REPO_ROOT, ImagesError, Recording, Wait

GIF = IMAGES / "demo.gif"
PROJECTS = {
    "invoice-tool": {"README.md": "# invoice-tool\n\nTurns time entries into PDF invoices.\n"},
    "garden-site": {"README.md": "# garden-site\n\nThe website of the allotment club.\n"},
}
SENTENCE = "remember that Dana's birthday is on 3 March"
QUESTION = "when is Dana's birthday?"
TOOLS = ("claude", "agg", "git")
COLUMNS = 90
ROWS = 22
FONT_SIZE = 16
FRAMES_PER_SECOND = 12
# agg's own list of text fonts. Named for the emoji too, it draws Claude Code's dot and its pause sign
# as a terminal does, where agg would otherwise take the pictures of the emoji font.
FONTS = "JetBrains Mono,Fira Code,SF Mono,Menlo,Consolas,DejaVu Sans Mono,Liberation Mono"
# The colors of the screenshots: xterm.js's own palette on their background.
THEME = {
    "fg": "#ffffff",
    "bg": readme_images.BACKGROUND,
    "palette": "#2e3436:#cc0000:#4e9a06:#c4a000:#3465a4:#75507b:#06989a:#d3d7cf"
    ":#555753:#ef2929:#8ae234:#fce94f:#729fcf:#ad7fa8:#34e2e2:#eeeeec",
}
KEY_SECONDS = 0.05
LOOK_SECONDS = 1.0
ANSWER_SECONDS = 4.0
RUN_SECONDS = 3.0
# The status line looks at the store when a session starts, before the run that start begins has
# registered, and then once a minute. A run over one note takes well under a minute, so the look a
# minute after the start shows it done; the wait passes that look with room to spare.
RUN_WAIT_SECONDS = 105
# A wait is over at the first spell this long without anything drawn; what is drawn later, when the
# band looks at the store again, follows within TAIL_SECONDS.
QUIET_SECONDS = 2.0
TAIL_SECONDS = 1.0
CARD_SECONDS = 2.5
HOLD_SECONDS = 2.5
LAST_HOLD_SECONDS = 4
LARGE_BYTES = 2_000_000
RESET = "\x1bc"
NO_BREAK_SPACE = "\u00a0"
HIDE_CURSOR = "\x1b[?25l"


@dataclass(frozen=True)
class Beat:
    """One wait of an act and the keys typed after it. ``shown`` is the most seconds of the picture
    the wait may take, None for as long as it took and 0 for unseen. ``settles`` says that the wait
    ends in a spell without anything drawn: then a positive ``shown`` holds for the time up to that
    spell, and what is drawn after it follows within ``TAIL_SECONDS``."""

    seconds: float
    keys: str = ""
    until: bytes = b""
    shown: float | None = None
    settles: bool = False

    @property
    def wait(self) -> Wait:
        return Wait(self.seconds, self.keys, self.until)


@dataclass(frozen=True)
class Act:
    title: str
    command: tuple[str, ...]
    cwd: Path
    environ: Mapping[str, str]
    beats: tuple[Beat, ...]


Events = list[tuple[float, bytes]]


def typed(text: str) -> list[Beat]:
    return [Beat(KEY_SECONDS, key) for key in text]


# Trust the demo folder and let the start settle, unseen.
SESSION_START = (Beat(8, DOWN, shown=0), Beat(1, ENTER, shown=0), Beat(13, shown=0))


def session_beats(prompt: str, answer_seconds: float) -> tuple[Beat, ...]:
    """Start a session, then type the prompt and wait."""
    return (
        *SESSION_START,
        Beat(LOOK_SECONDS),
        *typed(prompt),
        Beat(0.5, ENTER),
        Beat(answer_seconds, shown=ANSWER_SECONDS, settles=True),
    )


def start_beats() -> tuple[Beat, ...]:
    """Start a session and type nothing: the run its start began files the note meanwhile, and the
    status line under the prompt is where that shows."""
    return (*SESSION_START, Beat(LOOK_SECONDS), Beat(RUN_WAIT_SECONDS, shown=RUN_SECONDS))


def with_the_real_model(environ: Mapping[str, str]) -> dict[str, str]:
    """The demo machine's environment without the stand-in for the model, so the run a session start
    begins files the note."""
    return {key: value for key, value in environ.items() if key != "M2B_MODEL_RUNNER"}


def acts_for(environ: Mapping[str, str]) -> list[Act]:
    claude = tuple(readme_images.claude_command())
    first, second = (readme_images.DEMO / "projects" / name for name in PROJECTS)
    return [
        Act("Tell Claude Code once, in any project", claude, first, environ, session_beats(SENTENCE, 45)),
        Act(
            "The next session start files the note in the background: 1 in inbox becomes 0",
            claude,
            first,
            with_the_real_model(environ),
            start_beats(),
        ),
        Act(
            "Every later session starts knowing it, in any project",
            claude,
            second,
            environ,
            session_beats(QUESTION, 30),
        ),
    ]


def build_first_note_demo(environ: Mapping[str, str]) -> None:
    """A fresh demo machine whose store holds nothing yet, and two unrelated projects."""
    readme_images.set_up_machine(environ)
    for name, files in PROJECTS.items():
        readme_images.make_project(readme_images.DEMO / "projects" / name, files, environ)


def waiting_captures() -> list[str]:
    """The notes the demo store's inbox still holds."""
    return sorted(path.name for path in (readme_images.DEMO / "notes" / "inbox").glob("*.md"))


def retimed(recording: Recording, beats: Sequence[Beat]) -> Events:
    """What was drawn, on the picture's clock: each beat's wait takes at most its ``shown`` seconds,
    one that settles with a positive ``shown`` up to ``TAIL_SECONDS`` more for what came after the
    quiet, and one without ``shown`` its own time."""
    events: Events = []
    clock = start = 0.0
    for beat, end in zip(beats, recording.typed_at):
        inside = [(at, drawn) for at, drawn in recording.chunks if start <= at < end]
        busy_end = _busy_end([at for at, _ in inside], end) if beat.settles else end
        busy, tail = busy_end - start, end - busy_end
        if beat.shown is None:
            busy_shown, tail_shown = busy, tail
        else:
            busy_shown = min(busy, beat.shown)
            tail_shown = min(tail, TAIL_SECONDS) if beat.shown else 0.0
        for at, drawn in inside:
            if at <= busy_end:
                shown_at = (at - start) * (busy_shown / busy if busy else 0.0)
            else:
                shown_at = busy_shown + (at - busy_end) * (tail_shown / tail)
            events.append((clock + shown_at, drawn))
        clock += busy_shown + tail_shown
        start = end
    return events


def _busy_end(times: Sequence[float], end: float) -> float:
    """The last moment something was drawn before the first quiet spell, or the end without one."""
    for at, following in zip(times, [*times[1:], end]):
        if following - at >= QUIET_SECONDS:
            return at
    return end


def cast(acts: Sequence[tuple[str, Events]]) -> str:
    """An asciicast (version 2) of the acts in a row, each after a card with its number and title."""
    lines = [json.dumps({"version": 2, "width": COLUMNS, "height": ROWS, "theme": THEME})]
    clock = 0.0
    for number, (title, events) in enumerate(acts, start=1):
        card = f"{RESET}{HIDE_CURSOR}\r\n\r\n   \x1b[1m{number}\x1b[0m  {title}"
        lines.append(json.dumps([round(clock, 3), "o", card]))
        clock += CARD_SECONDS
        lines.append(json.dumps([round(clock, 3), "o", RESET]))
        # A chunk can end inside a character of several bytes.
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        last = 0.0
        for at, drawn in events:
            # agg draws a no-break space, which Claude Code puts after its prompt sign, as a missing glyph.
            text = decoder.decode(drawn).replace(NO_BREAK_SPACE, " ")
            if text:
                lines.append(json.dumps([round(clock + at, 3), "o", text]))
            last = at
        clock += last + HOLD_SECONDS
    return "\n".join(lines) + "\n"


def machine_names() -> dict[str, str]:
    return {
        "the home folder": str(Path.home()),
        "the user name": getpass.getuser(),
        "the host name": socket.gethostname().split(".")[0],
    }


def leaks(drawn: bytes, names: Mapping[str, str]) -> list[str]:
    """Which of this machine's names the terminal drew, as far as plain text shows it. A program that
    draws a word in pieces gets past this, so it is a net under looking at the picture, not a proof."""
    plain = ESCAPES.sub(b"", drawn).decode("utf-8", errors="replace").lower()
    return [
        what
        for what, name in names.items()
        if len(name) >= 3 and re.search(rf"(?<![a-z0-9]){re.escape(name.lower())}(?![a-z0-9])", plain)
    ]


def agg_command(recording: Path, gif: Path) -> list[str]:
    return [
        "agg",
        "--quiet",
        "--font-size",
        str(FONT_SIZE),
        "--emoji-font-family",
        FONTS,
        "--fps-cap",
        str(FRAMES_PER_SECOND),
        "--idle-time-limit",
        str(max(HOLD_SECONDS, CARD_SECONDS) + 1),
        "--last-frame-duration",
        str(LAST_HOLD_SECONDS),
        str(recording),
        str(gif),
    ]


def record_acts(acts: Sequence[Act], record: Callable[..., Recording] = readme_images.record_timed) -> list[Recording]:
    """Each act's recording. An act whose command ended before its last wait fails with what it drew
    last, which is where a command says why it ended."""
    recordings = []
    for number, act in enumerate(acts, start=1):
        recording = record(act.command, act.cwd, act.environ, ROWS, COLUMNS, [beat.wait for beat in act.beats])
        if len(recording.typed_at) < len(act.beats):
            drawn = ESCAPES.sub(b"", b"".join(chunk for _, chunk in recording.chunks)).decode("utf-8", errors="replace")
            last = " | ".join(line.strip() for line in drawn.splitlines() if line.strip())[-300:]
            raise ImagesError(
                f"act {number} ({Path(act.command[0]).name}) ended after {len(recording.typed_at)} of"
                f" {len(act.beats)} waits; it drew last: {last or 'nothing'}"
            )
        recordings.append(recording)
    return recordings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="readme-demo", description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("--cast", type=Path, help="also keep the asciicast the picture is rendered from")
    arguments = parser.parse_args(argv)
    try:
        missing = readme_images.missing_tools(tools=TOOLS)
        if missing:
            raise ImagesError(f"not found on PATH: {', '.join(missing)}")
        environ = readme_images.demo_environment(os.environ)
        build_first_note_demo(environ)
        acts = acts_for(environ)
        recordings = record_acts(acts)
        waiting = waiting_captures()
        if waiting:
            raise ImagesError(
                f"the run of the second act left {' and '.join(waiting)} in the inbox, so the last act"
                " did not start with the note; no picture written"
            )
        named = leaks(b"".join(drawn for recording in recordings for _, drawn in recording.chunks), machine_names())
        if named:
            raise ImagesError(f"the terminal drew {' and '.join(named)} of this machine; no picture written")
        text = cast([(act.title, retimed(recording, act.beats)) for act, recording in zip(acts, recordings)])
        with tempfile.TemporaryDirectory(prefix="sb-test-readme-demo-") as work:
            recording_file = arguments.cast or Path(work) / "demo.cast"
            recording_file.write_text(text, encoding="utf-8")
            IMAGES.mkdir(parents=True, exist_ok=True)
            readme_images.run(agg_command(recording_file, GIF), os.environ)
    except ImagesError as error:
        print(f"readme-demo: {error}", file=sys.stderr)
        return 1
    size = GIF.stat().st_size
    print(f"readme-demo: {GIF.relative_to(REPO_ROOT)}, {size // 1000} kB")
    if size > LARGE_BYTES:
        print(f"readme-demo: over {LARGE_BYTES // 1_000_000} MB, which loads slowly in the README", file=sys.stderr)
    print("readme-demo: watch it through before committing it; the answers are the model's")
    return 0


if __name__ == "__main__":
    sys.exit(main())
