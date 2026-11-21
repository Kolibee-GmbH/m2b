"""Records the moving pictures of the README and the docs, each drawn by the real programs in a hidden terminal.

The README's follows one sentence from a prompt into a later session, in three acts: a Claude Code
session in one demo project is told to remember a sentence, the start of the next session begins the
curation run that files it with a real model, in the background and without a key typed, then a
command of the band shows that run in the pane, and a session in another project is asked for it.
The store starts empty, so the fact the last act answers with can only come from the run in the
second. It costs two model turns and one curation run on the user's Claude login.

The two of the pane ask no model: one session each, in Claude Code's fullscreen layout, where the
pane sits beside the chat, on the store after a curation run. Keys alone drive them, a command of
the band, then Tab, Shift+Tab and Enter: one answers a proposal in the pane, the other sets a value
in the settings. The five seconds a press waits with its undo pass as
recorded.

The demo machine, its environment and the way a session is started are the screenshots'
(``readme_images``). What the terminals drew is kept with its times. A picture cuts a session's
start, the README's also shortens the model's answer and the run; a line of words stands before
each act, and ``agg`` renders it. After a recording the demo machine is asked whether what the
picture shows was written; if not, no picture is.
"""

from __future__ import annotations

import argparse
import codecs
import getpass
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from repo_tools import readme_images
from repo_tools.readme_images import DOWN, ENTER, IMAGES, REPO_ROOT, ImagesError
from repo_tools.terminal import ESCAPES, Recording, TerminalError, Wait, record_timed

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
# The pane's pictures are wider than the README's, so their letters are smaller: the file stays small.
PANE_ROWS = 26
# Enough rows that the value just written stays in sight when the focus rests on the row below the settings.
SETTINGS_ROWS = 38
PANE_FONT_SIZE = 14
TAB = "\t"
SHIFT_TAB = "\x1b[Z"
# A press in the pane writes after five seconds, in which it can be taken back.
PRESS_SECONDS = 6.5
KEPT_MODEL = "sonnet"
# The proposal the pane lists first, the one with a due day.
KEPT_PROPOSAL = "Send Dana the photos of the shed."
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
# A run over one note takes well under a minute; the wait gives it room to spare. Nothing shows
# while it runs: the status line speaks only of trouble, and the band only of what waits.
RUN_WAIT_SECONDS = 105
# The command that shows the last curation run in the pane, and the time the pane takes to draw it;
# the picture then rests on the act's last frame like on every other.
SHOW_THE_RUN = "/m2b-review"
SHOWN_RUN_SECONDS = 2.0
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


@dataclass(frozen=True)
class Picture:
    """One moving picture, ``<name>.gif``: the terminal it is recorded in, the demo machine it starts
    on, its acts, and ``refused``, which looks at the demo machine after the recording and gives the
    reason to write no picture, or None."""

    name: str
    columns: int
    rows: int
    font_size: int
    build: Callable[[Mapping[str, str]], None]
    acts: Callable[[Mapping[str, str]], list[Act]]
    refused: Callable[[Mapping[str, str]], str | None]


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
    """Start a session and type nothing while the run its start began files the note; then ask the
    band for the last curation run, which the pane shows with its times."""
    return (
        *SESSION_START,
        Beat(LOOK_SECONDS),
        Beat(RUN_WAIT_SECONDS, shown=RUN_SECONDS),
        *typed(SHOW_THE_RUN),
        Beat(0.5, ENTER),
        Beat(SHOWN_RUN_SECONDS),
    )


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
            "The next session start files the note in the background; /m2b-review shows that run",
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


def pressed(keys: Sequence[str], look_seconds: float) -> list[Beat]:
    """Look, then press the keys one after another."""
    return [Beat(look_seconds if index == 0 else 0.4, key) for index, key in enumerate(keys)]


def pane_beats(command: str, presses: Sequence[Beat]) -> tuple[Beat, ...]:
    """Start a session, type a command of the band, which gives the pane the keys, then press."""
    return (*SESSION_START, Beat(LOOK_SECONDS), *typed(command), Beat(0.5, ENTER), *presses)


def answering_beats() -> tuple[Beat, ...]:
    """To the proposals by their tab, keep the first and take that back, keep it again and let it be
    written, back to the start view by its tab.

    The tabs are the first buttons of every view: ``Proposals`` is one Tab into the start view, the
    first ``keep`` six Tabs past ``Overview``, where the focus stands after the turn, and from the
    row that moved up once the answer is written ``Overview`` is six back."""
    return pane_beats(
        "/m2b-pane",
        (
            *pressed([TAB, ENTER], 2.0),
            *pressed([*[TAB] * 6, ENTER], 2.5),
            Beat(1.5, ENTER),
            Beat(1.5, ENTER),
            *pressed([*[SHIFT_TAB] * 6, ENTER], PRESS_SECONDS + 1.5),
            Beat(3.0),
        ),
    )


# How many Tabs lead from the prompt to ``sonnet`` of the model of curation in the settings of the
# demo store: five tabs of the pane, then every value that is not in force of the settings above
# it (two each of where the band stands and of the tasks in the band, one each of the topics, of
# reading the sessions and of handing in), then it.
TABS_TO_THE_MODEL = 13
# How many Shift+Tabs lead back to it from the row of "About this setup", the last button of the
# view: every value that is not in force of the settings below the model (one each of the pause,
# of the run after the answers, of the git commit and of the language), then it.
BACK_TO_THE_MODEL = 5


def settings_beats() -> tuple[Beat, ...]:
    """Set the model of curation with a press on its other value and take that back, press it again
    and let it be written, then open what only informs.

    The focus goes to ``undo`` with the press. Once ``undo`` is gone it goes to the nearest button
    that sets nothing, which for the model is the row of "About this setup" below the settings:
    from there the value is a few Shift+Tabs back, and after the write Enter on the row opens the
    rest under its own tab."""
    return pane_beats(
        "/m2b-settings",
        (
            *pressed([*[TAB] * TABS_TO_THE_MODEL, ENTER], 2.5),
            Beat(1.5, ENTER),
            *pressed([*[SHIFT_TAB] * BACK_TO_THE_MODEL, ENTER], 1.5),
            Beat(PRESS_SECONDS + 1.5, ENTER),
            Beat(3.0),
        ),
    )


def pane_acts(title: str, beats: tuple[Beat, ...]) -> Callable[[Mapping[str, str]], list[Act]]:
    """One act in the demo project, in the fullscreen layout and with the stand-in for the model."""

    def acts(environ: Mapping[str, str]) -> list[Act]:
        session = {**environ, **readme_images.FULL_SCREEN}
        return [Act(title, tuple(readme_images.claude_command()), readme_images.PROJECT, session, beats)]

    return acts


def build_first_note_demo(environ: Mapping[str, str]) -> None:
    """A fresh demo machine whose store holds nothing yet, and two unrelated projects."""
    readme_images.set_up_machine(environ)
    for name, files in PROJECTS.items():
        readme_images.make_project(readme_images.DEMO / "projects" / name, files, environ)


def waiting_captures() -> list[str]:
    """The notes the demo store's inbox still holds."""
    return sorted(path.name for path in (readme_images.DEMO / "notes" / "inbox").glob("*.md"))


def note_left_in_the_inbox(environ: Mapping[str, str]) -> str | None:
    waiting = waiting_captures()
    if not waiting:
        return None
    left = " and ".join(waiting)
    return f"the run of the second act left {left} in the inbox, so the last act did not start with the note"


def kept_proposal_not_written(environ: Mapping[str, str]) -> str | None:
    """The picture keeps the proposal the pane lists first: every other one still waits, and the
    one answer the store holds is a keep. A count alone would pass a drop, which a button added
    before ``keep`` would turn the press into."""
    answer = subprocess.run(
        [str(readme_images.PLUGIN / "bin" / "m2b"), "band", "--json"],
        env=dict(environ),
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        waiting = sorted(proposal["text"] for proposal in json.loads(answer.stdout)["proposals"]["proposals"])
    except (ValueError, KeyError, TypeError):
        return "m2b band --json did not say which proposals wait on the demo machine"
    others = sorted(text for _, text, _, _ in readme_images.PROPOSALS if text != KEPT_PROPOSAL)
    if waiting != others:
        return f"{len(waiting)} proposals wait on the demo machine, not all but {KEPT_PROPOSAL!r}: it was not answered"
    answers = readme_images.DEMO / "notes" / "state" / "core" / "proposal-answers"
    kinds = sorted(path.suffix for path in answers.glob("*"))
    if kinds != [".keep"]:
        return f"the demo machine holds {' and '.join(kinds) or 'no answer'}, not one keep: the press was no keep"
    return None


def model_not_written(environ: Mapping[str, str]) -> str | None:
    """The picture sets the model of curation with a press."""
    config = readme_images.DEMO / "home" / ".config" / "m2b" / "config.json"
    try:
        model = json.loads(config.read_text(encoding="utf-8"))["curation"].get("model")
    except (OSError, ValueError, KeyError, AttributeError):
        return "the demo machine's config could not be read"
    if model == KEPT_MODEL:
        return None
    now = "not set" if model is None else repr(model)
    return f"the demo machine's curation.model is {now}, not {KEPT_MODEL!r}: the press was not written"


PICTURES = (
    Picture("demo", COLUMNS, ROWS, FONT_SIZE, build_first_note_demo, acts_for, note_left_in_the_inbox),
    Picture(
        "pane-answers",
        readme_images.WIDE,
        PANE_ROWS,
        PANE_FONT_SIZE,
        readme_images.build_demo_after_a_run,
        pane_acts("Answer what waits for you, in the pane beside the chat", answering_beats()),
        kept_proposal_not_written,
    ),
    Picture(
        "pane-settings",
        readme_images.WIDE,
        SETTINGS_ROWS,
        PANE_FONT_SIZE,
        readme_images.build_demo_after_a_run,
        pane_acts("Set a value with a press, take it back, set it again, open the rest", settings_beats()),
        model_not_written,
    ),
)


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


def cast(acts: Sequence[tuple[str, Events]], columns: int, rows: int) -> str:
    """An asciicast (version 2) of the acts in a row, each after a card with its title, and with its
    number when there are several."""
    lines = [json.dumps({"version": 2, "width": columns, "height": rows, "theme": THEME})]
    clock = 0.0
    for number, (title, events) in enumerate(acts, start=1):
        numbered = f"\x1b[1m{number}\x1b[0m  " if len(acts) > 1 else ""
        card = f"{RESET}{HIDE_CURSOR}\r\n\r\n   {numbered}{title}"
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


def longest_pause(acts: Sequence[Act]) -> float:
    """The longest spell without anything drawn the picture may show: a hold, a card, or a wait an
    act shows as recorded, such as the seconds a press can be taken back. agg cuts what is longer."""
    as_recorded = [beat.seconds for act in acts for beat in act.beats if beat.shown is None]
    return max([HOLD_SECONDS, CARD_SECONDS, *as_recorded])


def agg_command(
    recording: Path, gif: Path, font_size: int = FONT_SIZE, pause_seconds: float = max(HOLD_SECONDS, CARD_SECONDS)
) -> list[str]:
    return [
        "agg",
        "--quiet",
        "--font-size",
        str(font_size),
        "--emoji-font-family",
        FONTS,
        "--fps-cap",
        str(FRAMES_PER_SECOND),
        "--idle-time-limit",
        str(pause_seconds + 1),
        "--last-frame-duration",
        str(LAST_HOLD_SECONDS),
        str(recording),
        str(gif),
    ]


def record_acts(
    acts: Sequence[Act], columns: int, rows: int, record: Callable[..., Recording] = record_timed
) -> list[Recording]:
    """Each act's recording in a terminal of ``columns`` x ``rows``. An act whose command ended before
    its last wait fails with what it drew last, which is where a command says why it ended."""
    recordings = []
    for number, act in enumerate(acts, start=1):
        recording = record(act.command, act.cwd, act.environ, rows, columns, [beat.wait for beat in act.beats])
        if len(recording.typed_at) < len(act.beats):
            drawn = ESCAPES.sub(b"", b"".join(chunk for _, chunk in recording.chunks)).decode("utf-8", errors="replace")
            last = " | ".join(line.strip() for line in drawn.splitlines() if line.strip())[-300:]
            raise ImagesError(
                f"act {number} ({Path(act.command[0]).name}) ended after {len(recording.typed_at)} of"
                f" {len(act.beats)} waits; it drew last: {last or 'nothing'}"
            )
        recordings.append(recording)
    return recordings


def record_picture(picture: Picture, environ: Mapping[str, str], kept_cast: Path | None) -> Path:
    """Builds the picture's demo machine, records its acts and renders them; the picture's file.
    Nothing is written when the demo machine does not hold what the picture shows, or when the
    terminal drew a name of this machine."""
    picture.build(environ)
    acts = picture.acts(environ)
    recordings = record_acts(acts, picture.columns, picture.rows)
    reason = picture.refused(environ)
    if reason:
        raise ImagesError(f"{picture.name}: {reason}; no picture written")
    named = leaks(b"".join(drawn for recording in recordings for _, drawn in recording.chunks), machine_names())
    if named:
        raise ImagesError(
            f"{picture.name}: the terminal drew {' and '.join(named)} of this machine; no picture written"
        )
    text = cast(
        [(act.title, retimed(recording, act.beats)) for act, recording in zip(acts, recordings)],
        picture.columns,
        picture.rows,
    )
    gif = IMAGES / f"{picture.name}.gif"
    with tempfile.TemporaryDirectory(prefix="sb-test-readme-demo-") as work:
        recording_file = kept_cast or Path(work) / f"{picture.name}.cast"
        recording_file.write_text(text, encoding="utf-8")
        # Rendered beside the recording first: a render that fails leaves the picture in the repository whole.
        rendered = Path(work) / gif.name
        readme_images.run(agg_command(recording_file, rendered, picture.font_size, longest_pause(acts)), os.environ)
        IMAGES.mkdir(parents=True, exist_ok=True)
        shutil.move(str(rendered), gif)
    return gif


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="readme-demo", description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("--only", choices=[picture.name for picture in PICTURES], help="this picture alone")
    parser.add_argument("--cast", type=Path, help="with --only: also keep the asciicast the picture is rendered from")
    arguments = parser.parse_args(argv)
    if arguments.cast and not arguments.only:
        parser.error("--cast keeps one recording: name its picture with --only")
    missing = readme_images.missing_tools(tools=TOOLS)
    if missing:
        print(f"readme-demo: not found on PATH: {', '.join(missing)}", file=sys.stderr)
        return 1
    environ = readme_images.demo_environment(os.environ)
    failed = False
    for picture in PICTURES:
        if arguments.only not in (None, picture.name):
            continue
        # One picture that fails does not keep the others from being recorded: the README's needs a
        # model and a curation run, the pane's need neither.
        try:
            gif = record_picture(picture, environ, arguments.cast)
        except (ImagesError, TerminalError) as error:
            print(f"readme-demo: {error}", file=sys.stderr)
            failed = True
            continue
        size = gif.stat().st_size
        print(f"readme-demo: {gif.relative_to(REPO_ROOT)}, {size // 1000} kB")
        if size > LARGE_BYTES:
            print(f"readme-demo: over {LARGE_BYTES // 1_000_000} MB, which loads slowly in a page", file=sys.stderr)
    print("readme-demo: watch each picture through before committing it; where a model answers, the answer is its own")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
