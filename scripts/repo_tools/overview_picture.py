"""Writes the README's overview picture of m2b, light and dark: docs/images/overview-{light,dark}.svg.

Run it through ``scripts/overview-picture <folder of the .ttf files>``, which brings fontTools. With
``--stills <folder>`` it also writes the picture frozen at a few seconds of its loop, to look at
each step without waiting for it; those files are for looking, not for the repository.

Layout: three columns on one grid. Two terminals at the same height open and close each story, what
is said and what a later session gets back; between them the folder with its real file names. One
thick line in the logo's color carries what is said through; everything else is quiet. Words in the
picture are labels; the sentences stand in the caption below it.

Three stories play one after the other in the same picture, each one of m2b's promises: a fact said
once that a session in another project knows; a correction made while working, which m2b proposes
as a lesson and which then stops the command it is about; a sentence that becomes a task due on its
day. Then the picture rests on the first story's last frame, which is also all a reader who asked
for reduced motion sees, with every row and label of the three in place. Every second of the stories
stands in the tables below; every keyframe is computed from them, and the dot's way from the same
points as the lines it travels on.

Color: ink and the logo's petrol, a petrol tint for the folder, one neutral for the quiet lines.
Type: Montserrat, the social preview's face, for labels; JetBrains Mono for what is typed and for
file names (both SIL Open Font License), drawn as outlines so every machine shows the same picture.
Every text is measured against the room it has; one that does not fit ends the script.

The fonts are not part of the repository. The folder given holds ``Montserrat-Regular.ttf``,
``-Medium``, ``-SemiBold`` and ``-Bold`` (github.com/JulietaUla/Montserrat) and
``JetBrainsMono-Medium.ttf`` and ``-Bold`` (github.com/JetBrains/JetBrainsMono).
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

THEMES = {
    "light": {
        "ink": "#0d1117",
        "dim": "#57606a",
        "petrol": "#1B8188",
        "bright": "#4cc3c6",
        "tint": "#e6f2f2",
        "band": "#c9e4e4",
        "line": "#9aa4ad",
        "terminal": "#0d1117",
        "on-terminal": "#f5f5f7",
        "on-terminal-dim": "#8b949e",
        "on-petrol": "#ffffff",
        "on-petrol-dim": "#d3ecec",
        "ground": "#ffffff",
    },
    "dark": {
        "ink": "#f5f5f7",
        "dim": "#9aa4ad",
        "petrol": "#34A8AB",
        "bright": "#4cc3c6",
        "tint": "#10282a",
        "band": "#17474a",
        "line": "#6b7682",
        "terminal": "#1a212b",
        "on-terminal": "#f5f5f7",
        "on-terminal-dim": "#8b949e",
        "on-petrol": "#0d1117",
        "on-petrol-dim": "#0c3133",
        "ground": "#0d1117",
    },
}
FACES = {
    ("sans", 400): "Montserrat-Regular.ttf",
    ("sans", 500): "Montserrat-Medium.ttf",
    ("sans", 600): "Montserrat-SemiBold.ttf",
    ("sans", 700): "Montserrat-Bold.ttf",
    ("mono", 500): "JetBrainsMono-Medium.ttf",
    ("mono", 700): "JetBrainsMono-Bold.ttf",
}
# style: (family, size, weight, color)
STYLES = {
    "zone": ("sans", 15, 700, "ink"),
    "badge": ("sans", 12.5, 700, "on-petrol"),
    "typed": ("mono", 13, 500, "on-terminal"),
    "reply": ("mono", 12.5, 500, "on-terminal-dim"),
    "answer": ("mono", 13, 700, "bright"),
    "name": ("mono", 13, 500, "ink"),
    "name-strong": ("mono", 13, 700, "ink"),
    "folder": ("mono", 13, 700, "petrol"),
    "note": ("sans", 12, 400, "dim"),
    "title": ("sans", 14.5, 600, "ink"),
    "sub": ("sans", 12.5, 400, "dim"),
    "pill": ("sans", 9.5, 700, "petrol"),
    "curator": ("sans", 15, 600, "on-petrol"),
    "curator-sub": ("sans", 12, 500, "on-petrol-dim"),
    "band": ("mono", 12, 500, "on-terminal"),
    "band-name": ("mono", 12, 700, "bright"),
}
WIDTH, HEIGHT = 960, 470
LEFT, PANEL, RIGHT = 24, 312, 696
COLUMN = 240
PANEL_WIDTH = 336
LOOP_SECONDS = 30
# A shape that comes or goes fades over this long.
FADE = 0.15

MARK_COLOR = ("M -150,-120 H -60 A 30 30 0 0 1 -60,-60 H -120 A 30 30 0 0 0 -120,0 H -30", "M 34,-120 V 120")
MARK_CIRCLE = (124, 30, 90)
MARK_INK = "M -150,122 V 90 A 30 30 0 0 1 -90,90 V 122 M -90,90 A 30 30 0 0 1 -30,90 V 122"

ICONS = {
    "file": "M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z M14 3v5h5",
    "passing": "M4 6a3 3 0 0 1 3-3h10a3 3 0 0 1 3 3v6a3 3 0 0 1-3 3h-6l-4 4v-4a3 3 0 0 1-3-3z",
    "lesson": "M8 3h8l5 5v8l-5 5H8l-5-5V8z M12 8v5 M12 16.5v.01",
    "task": "M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z M8.5 12l2.5 2.5 4.5-5",
    "band": "M5 4h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z M15 4v16 M6 9h6",
}
ZONES = [(LEFT, "1", "What goes in"), (PANEL, "2", "m2b keeps it, on your machine"), (RIGHT, "3", "What comes back")]
TRUNK = 344
# The folder's rows: (y, name, note, kind, glow). A row with a glow lights when the dot reaches it.
ROWS = [
    (124, "inbox/", "new, as you gave it", "plain", ""),
    (242, "memory/MEMORY.md", "starts every session", "strong", "memory"),
    (274, "memory/lessons/", "corrections you kept", "strong", "lessons"),
    (306, "memory/dana.md", "a file per subject", "plain", ""),
    (338, "corpus/2026/11/", "your words and files", "plain", ""),
    (370, "tasks/", "or Apple Reminders", "plain", "tasks"),
]
Point = tuple[float, float]
Window = tuple[float, float]
# The typographic apostrophe, as the typefaces draw it.
APOSTROPHE = "\u2019"
CORNER = 9

# The lines. ``main`` carries what is said, ``lesson`` and ``task`` the second and third story's own
# way out of the folder, ``quiet`` and ``dotted`` the rows beside the story.
WAYS: dict[str, tuple[list[Point], str, bool]] = {
    "file": ([(264, 207), (300, 207), (300, 128)], "quiet", False),
    "passing": ([(264, 289), (300, 289), (300, 215)], "dotted", False),
    "trunk": ([(TRUNK, 252), (TRUNK, 366)], "quiet", False),
    "lessons-known": ([(632, 269), (668, 269), (668, 237)], "lesson", False),
    "tasks-band": ([(632, 365), (660, 365), (660, 347), (690, 347)], "task", True),
    "said-inbox": ([(264, 98), (288, 98), (288, 120), (TRUNK, 120), (TRUNK, 142)], "main", True),
    "curator-memory": ([(TRUNK, 202), (TRUNK, 237), (TRUNK + 14, 237)], "main", True),
    "memory-known": ([(632, 237), (668, 237), (668, 98), (692, 98)], "main", True),
}
# The dot's travels: (points, seconds it sets out, seconds it arrives). Between two travels it is
# hidden in the shape it reached.
TRAVELS: list[tuple[list[Point], float, float]] = [
    (WAYS["said-inbox"][0], 2.7, 3.5),
    (WAYS["curator-memory"][0], 4.5, 5.0),
    (WAYS["memory-known"][0], 5.8, 6.7),
    ([(264, 289), (300, 289), (300, 120), (TRUNK, 120), (TRUNK, 142)], 12.6, 13.5),
    ([(TRUNK, 202), (TRUNK, 270), (TRUNK + 12, 270)], 14.2, 14.7),
    ([(632, 269), (668, 269), (668, 98), (692, 98)], 15.4, 16.2),
    (WAYS["said-inbox"][0], 20.8, 21.6),
    ([(TRUNK, 202), (TRUNK, 366), (TRUNK + 12, 366)], 22.3, 23.0),
    (WAYS["tasks-band"][0], 23.6, 24.1),
]
# What glows when.
GLOWS: dict[str, list[Window]] = {
    "curator": [(3.5, 4.5), (13.5, 14.2), (21.6, 22.3)],
    "memory": [(5.0, 5.8)],
    "answer": [(7.6, 9.0), (16.8, 18.0)],
    "passing": [(11.6, 12.6)],
    "lessons": [(14.7, 15.4)],
    "tasks": [(23.0, 23.6)],
    "band": [(24.1, 25.5)],
}
# The stories: (seconds it starts, seconds it ends). The first story's last frame comes back for the
# rest, until just before the loop starts again empty.
STORIES = [(0.0, 9.5), (9.5, 18.5), (18.5, 25.5)]
REST = (25.5, 29.7)


@dataclass(frozen=True)
class Line:
    """A line in one of the two terminals: which story, which terminal and row, what, how it looks,
    and when it shows. ``typed`` is the seconds it is typed in; a line without it comes whole."""

    story: int
    terminal: str
    row: int
    text: str
    style: str
    shows: float
    typed: Window | None = None
    chevron: bool = False


LINES = [
    Line(1, "said", 0, f"remember that Dana{APOSTROPHE}s", "typed", 0.5, (0.5, 1.6), True),
    Line(1, "said", 1, "birthday is on 3 March", "typed", 1.6, (1.6, 2.6)),
    Line(1, "known", 0, f"when is Dana{APOSTROPHE}s birthday?", "typed", 6.8, (6.8, 7.6), True),
    Line(1, "known", 1, "3 March (dana.md)", "answer", 7.6),
    Line(2, "said", 0, "no, use --quick here", "typed", 10.0, (10.0, 11.2), True),
    Line(2, "said", 1, "\u2514 m2b proposes a lesson", "reply", 11.6),
    Line(2, "known", 0, "\u25cf Bash(scripts/check)", "plain-typed", 16.3),
    Line(2, "known", 1, "\u2514 stopped by a lesson", "answer", 16.8),
    Line(3, "said", 0, "remind me to call the", "typed", 19.0, (19.0, 19.9), True),
    Line(3, "said", 1, "plumber on Friday", "typed", 19.9, (19.9, 20.6)),
]
# The band's row after "m2b": (text, story, windows). The first is also the still picture's.
BAND = [
    # A proposal waits from the second story on, so the band says so until the third story.
    ("1 waits for you", 1, [(0.0, STORIES[1][1]), REST]),
    ("due: Call the plumber", 3, [(24.0, STORIES[2][1])]),
]
ALT = (
    "How m2b works, from left to right, in three stories. 1, what goes in: in any Claude Code session you "
    "say remember that Dana's birthday is on 3 March; or you just work, and m2b proposes what you said in "
    "passing, a correction too, and you keep or drop it; or you give it a file. 2, m2b keeps it on your "
    "machine, as plain files in a folder you own, ~/m2b: the inbox; the curator, which files it at your next "
    "session start; memory/MEMORY.md, which starts every session; memory/lessons/, the corrections you kept; "
    "a file per subject; your words and files; and tasks/ or Apple Reminders. 3, what comes back: a later "
    "session in any project answers 3 March (dana.md); a lesson stops a command before it runs; a task is "
    "due on its day in the band."
)
# Seconds at which --stills freezes the picture.
STILLS = (2.0, 4.0, 5.4, 7.2, 8.8, 11.0, 12.2, 13.0, 14.9, 16.5, 17.4, 19.5, 21.0, 22.6, 23.3, 24.8, 27.0)


class Text(Protocol):
    """What the picture needs of its type: a width to measure and a group of outlines to draw."""

    def width(self, text: str, style: str) -> float: ...

    def draw(self, x: float, y: float, text: str, style: str, anchor: str = "start") -> str: ...

    def defs(self) -> str: ...

    def fit(self, text: str, style: str, room: float) -> None: ...


class Type:
    """Two faces as outlines: each glyph once under <defs>, each text a row of uses."""

    def __init__(self, folder: Path) -> None:
        # fontTools comes with the run (scripts/overview-picture) and is no part of the repository's
        # checks, which import this module for its tables.
        from fontTools.ttLib import TTFont  # type: ignore[import-not-found]

        self.faces = {key: TTFont(str(folder / name)) for key, name in FACES.items()}
        self.used: dict[tuple[str, int, str], str] = {}

    def _glyphs(self, text: str, face: Any) -> list[tuple[str, int]]:
        cmap, widths = face.getBestCmap(), face["hmtx"]
        missing = sorted({char for char in text if ord(char) not in cmap})
        if missing:
            raise SystemExit(f"{text!r}: the face has no glyph for {missing}")
        return [(cmap[ord(char)], widths[cmap[ord(char)]][0]) for char in text]

    def width(self, text: str, style: str) -> float:
        family, size, weight, _ = STYLES[style]
        face = self.faces[(family, weight)]
        return float(sum(advance for _, advance in self._glyphs(text, face)) * size / face["head"].unitsPerEm)

    def draw(self, x: float, y: float, text: str, style: str, anchor: str = "start") -> str:
        family, size, weight, color = STYLES[style]
        face = self.faces[(family, weight)]
        scale = size / face["head"].unitsPerEm
        width = self.width(text, style)
        left = x - (width if anchor == "end" else width / 2 if anchor == "middle" else 0)
        uses, at = [], 0
        for name, advance in self._glyphs(text, face):
            if name != "space":
                key = (family, weight, name)
                self.used.setdefault(key, f"{family[0]}{weight // 100}{len(self.used)}")
                uses.append(f'<use href="#{self.used[key]}" x="{at}"/>')
            at += advance
        move = f"translate({left:.2f} {y}) scale({scale:.5f} -{scale:.5f})"
        return f'<g class="{color}" transform="{move}">{"".join(uses)}</g>'

    def defs(self) -> str:
        from fontTools.pens.svgPathPen import SVGPathPen  # type: ignore[import-not-found]

        paths = []
        for (family, weight, name), identity in self.used.items():
            glyphs = self.faces[(family, weight)].getGlyphSet()
            pen = SVGPathPen(glyphs, lambda number: f"{number:.0f}")
            glyphs[name].draw(pen)
            paths.append(f'<path id="{identity}" d="{pen.getCommands()}"/>')
        return "".join(paths)

    def fit(self, text: str, style: str, room: float) -> None:
        if self.width(text, style) > room:
            raise SystemExit(f"{text!r} is {self.width(text, style):.0f} px wide, {room:.0f} px are free")


def rounded(points: Sequence[Point]) -> str:
    """A path through the points with round corners, as the logo turns its lines."""
    path = [f"M{points[0][0]},{points[0][1]}"]
    for index in range(1, len(points) - 1):
        (ax, ay), (bx, by), (cx, cy) = points[index - 1], points[index], points[index + 1]
        into = min(CORNER, (abs(bx - ax) + abs(by - ay)) / 2)
        out = min(CORNER, (abs(cx - bx) + abs(cy - by)) / 2)
        sx, sy = bx - into * ((bx > ax) - (bx < ax)), by - into * ((by > ay) - (by < ay))
        ex, ey = bx + out * ((cx > bx) - (cx < bx)), by + out * ((cy > by) - (cy < by))
        path.append(f"L{sx},{sy} Q{bx},{by} {ex},{ey}")
    path.append(f"L{points[-1][0]},{points[-1][1]}")
    return " ".join(path)


def percent(seconds: float) -> str:
    return f"{100 * seconds / LOOP_SECONDS:.2f}".rstrip("0").rstrip(".") + "%"


def shown_in(story: int, shows: float) -> list[Window]:
    """The windows a story's shape shows in: until its story ends, the first story's also in the rest."""
    windows = [(shows, STORIES[story - 1][1])]
    return [*windows, REST] if story == 1 else windows


def window_frames(windows: Iterable[Window], prop: str) -> list[tuple[float, str]]:
    """Keyframes that set ``prop`` to 1 inside each window and 0 outside, with a short fade."""
    frames: list[tuple[float, str]] = [(0.0, f"{prop}:0")]
    for start, end in windows:
        frames += [(start, f"{prop}:0"), (start + FADE, f"{prop}:1"), (end, f"{prop}:1")]
        frames.append((min(end + FADE, LOOP_SECONDS), f"{prop}:0"))
    frames.append((LOOP_SECONDS, f"{prop}:0"))
    return frames


def keyframes(name: str, frames: Sequence[tuple[float, str]]) -> str:
    """One @keyframes rule; of frames at the same second the last one written holds."""
    by_percent: dict[str, str] = {}
    for seconds, declarations in sorted(frames, key=lambda frame: frame[0]):
        by_percent[percent(seconds)] = declarations
    body = "".join(f"{at}{{{declarations}}}" for at, declarations in by_percent.items())
    return f"@keyframes {name}{{{body}}}.{name}{{animation:{name} {LOOP_SECONDS}s linear infinite}}"


def dot_frames() -> list[tuple[float, float, float, int]]:
    """The dot's (seconds, x, y, opacity): along each travel's points at an even speed, hidden between."""
    frames: list[tuple[float, float, float, int]] = []
    for points, start, end in TRAVELS:
        lengths = [abs(bx - ax) + abs(by - ay) for (ax, ay), (bx, by) in zip(points, points[1:])]
        total = sum(lengths)
        frames.append((start - 0.01, *points[0], 0))
        travelled = 0.0
        for point, length in zip(points, [0.0, *lengths]):
            travelled += length
            frames.append((start + (end - start) * travelled / total, *point, 1))
        frames.append((end + 0.01, *points[-1], 0))
    return frames


def drawn_ways() -> list[list[Point]]:
    """Every line the picture draws: the ways, and the tree's short guides to the rows below the fact's."""
    guides: list[list[Point]] = [[(TRUNK, y - 4), (TRUNK + 12, y - 4)] for y, *_ in ROWS if y > 250]
    return [points for points, _, _ in WAYS.values()] + guides


def on_a_way(point: Point) -> bool:
    """Whether a point lies on a drawn line; every line runs only across or down."""
    x, y = point
    for points in drawn_ways():
        for (ax, ay), (bx, by) in zip(points, points[1:]):
            if min(ax, bx) <= x <= max(ax, bx) and min(ay, by) <= y <= max(ay, by):
                return True
    return False


def mark_white(x: float, y: float, height: float) -> str:
    """The mark in one color, for the curator: m2b itself is what files the inbox."""
    scale = height / 264
    cx, cy, r = MARK_CIRCLE
    paths = "".join(f'<path d="{d}"/>' for d in (*MARK_COLOR, MARK_INK))
    return (
        f'<g class="stroke-on-petrol" transform="translate({x + 161 * scale:.1f} {y + 131 * scale:.1f}) '
        f'scale({scale:.4f})" fill="none" stroke-width="24" stroke-linecap="round" stroke-linejoin="round">'
        f'{paths}<circle cx="{cx}" cy="{cy}" r="{r}"/></g>'
    )


class Picture:
    """The SVG's body and the animations it needs, built up shape by shape."""

    def __init__(self, type_: Text) -> None:
        self.type = type_
        self.body: list[str] = []
        self.animations: list[str] = []

    def animated(self, name: str, frames: Sequence[tuple[float, str]]) -> str:
        """The classes of an animated shape: ``anim`` for reduced motion, and its own keyframes."""
        self.animations.append(keyframes(name, frames))
        return f"anim {name}"

    def glow(self, name: str, x: float, y: float, width: float, height: float, radius: float) -> str:
        classes = self.animated(f"glow-{name}", window_frames(GLOWS[name], "stroke-opacity"))
        return f'<rect class="glow {classes}" x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}"/>'

    def terminal(self, name: str, x: int, y: int) -> None:
        """A session as Claude Code shows it, with each story's lines in turn."""
        box = f'x="{x}" y="{y}" width="{COLUMN}" height="84" rx="12"'
        self.body.append(f'<rect class="terminal" {box}/>')
        if name == "known":
            self.body.append(self.glow("answer", x, y, COLUMN, 84, 12))
        # A cover moved off its text stays inside the terminal.
        self.body.append(f'<clipPath id="in-{name}"><rect {box}/></clipPath><g clip-path="url(#in-{name})">')
        for index, line in enumerate(line for line in LINES if line.terminal == name):
            self.line(f"{name}-{index}", line, x, y)
        self.body.append("</g>")

    def line(self, name: str, line: Line, x0: int, y0: int) -> None:
        """A typed line stands after the prompt's chevron; an answer, a reply or a tool call under it."""
        base = y0 + 34 + line.row * 23
        style = "typed" if line.style == "plain-typed" else line.style
        x = x0 + (34 if line.style == "typed" else 16)
        self.type.fit(line.text, style, x0 + COLUMN - x - 12)
        story_class = "story-one" if line.story == 1 else "story-later"
        classes = self.animated(f"line-{name}", window_frames(shown_in(line.story, line.shows), "opacity"))
        parts = [f'<g class="{story_class} {classes}">']
        if line.chevron:
            parts.append(f'<path class="prompt" d="M{x0 + 17},{base - 9} l5,4.5 l-5,4.5"/>')
        parts.append(self.type.draw(x, base, line.text, style))
        if line.typed:
            parts.extend(self.typing(name, line, x, base))
        parts.append("</g>")
        self.body.append("".join(parts))

    def typing(self, name: str, line: Line, x: float, base: float) -> list[str]:
        """A cover in the terminal's color over the text, moved off it a letter at a time, and a cursor
        ahead of it; both go once the line is typed."""
        assert line.typed is not None
        start, end = line.typed
        width = self.type.width(line.text, line.style)
        steps = f"animation-timing-function:steps({len(line.text)},end)"
        moved = f"transform:translateX({width:.1f}px)"
        cover = self.animated(
            f"cover-{name}",
            [
                (0.0, "transform:translateX(0);opacity:1"),
                (start, f"transform:translateX(0);opacity:1;{steps}"),
                (end, f"{moved};opacity:1"),
                (end + 0.01, f"{moved};opacity:0"),
                (LOOP_SECONDS, f"{moved};opacity:0"),
            ],
        )
        cursor = self.animated(
            f"cursor-{name}",
            [
                (0.0, "transform:translateX(0);opacity:0"),
                (start - 0.01, "transform:translateX(0);opacity:0"),
                (start, f"transform:translateX(0);opacity:1;{steps}"),
                (end, f"{moved};opacity:1"),
                (end + 0.25, f"{moved};opacity:0"),
                (LOOP_SECONDS, f"{moved};opacity:0"),
            ],
        )
        return [
            f'<rect class="terminal cover {cover}" x="{x - 1}" y="{base - 14}" width="{width + 10:.1f}" height="19"/>',
            f'<rect class="cursor {cursor}" x="{x}" y="{base - 12}" width="7.5" height="15"/>',
        ]

    def pill(self, right: float, y: float) -> list[str]:
        return [
            f'<rect class="pill" x="{right - 62}" y="{y - 13}" width="62" height="18" rx="9"/>',
            self.type.draw(right - 31, y - 0.6, "OPTIONAL", "pill", "middle"),
        ]

    def side_row(
        self, x: int, y: int, icon: str, title: str, subs: list[str], optional: bool = False, glow: str = ""
    ) -> None:
        """A quiet row beside the story: an icon, a title of a few words, a line of what it is."""
        inset = 14 if optional else 0
        if optional:
            height = 46 + len(subs) * 18
            box = f'x="{x}" y="{y - 26}" width="{COLUMN}" height="{height}" rx="14"'
            self.body.append(f'<rect class="dotted-box" {box}/>')
            if glow:
                self.body.append(self.glow(glow, x, y - 26, COLUMN, height, 14))
            self.body.extend(self.pill(x + COLUMN - 14, y + 1))
        transform = f"translate({x + inset} {y - 16}) scale(0.88)"
        self.body.append(f'<path class="icon" transform="{transform}" d="{ICONS[icon]}"/>')
        self.type.fit(title, "title", COLUMN - inset * 2 - 30 - (70 if optional else 0))
        self.body.append(self.type.draw(x + inset + 30, y, title, "title"))
        for index, sub in enumerate(subs):
            self.type.fit(sub, "sub", COLUMN - inset * 2)
            self.body.append(self.type.draw(x + inset, y + 22 + index * 18, sub, "sub"))

    def folder(self) -> None:
        right = PANEL + PANEL_WIDTH - 24
        where = "plain files, in a folder you own"
        self.type.fit(where, "note", right - (PANEL + 24) - self.type.width("~/m2b", "folder") - 12)
        row_left, row_width = PANEL + 18, PANEL_WIDTH - 36
        self.body += [
            f'<rect class="tint" x="{PANEL}" y="56" width="{PANEL_WIDTH}" height="390" rx="22"/>',
            self.type.draw(PANEL + 24, 88, "~/m2b", "folder"),
            self.type.draw(right, 88, where, "note", "end"),
            f'<rect class="band-row" x="{row_left}" y="222" width="{row_width}" height="30" rx="15"/>',
        ]
        for points in drawn_ways()[len(WAYS) :]:
            self.body.append(f'<path class="way quiet" d="{rounded(points)}"/>')
        for y, name, note, kind, glow in ROWS:
            if glow:
                self.body.append(self.glow(glow, row_left, y - 20, row_width, 30, 15))
            style = "name-strong" if kind == "strong" else "name"
            self.type.fit(note, "note", right - (PANEL + 52) - self.type.width(name, style) - 12)
            self.body.append(self.type.draw(PANEL + 52, y, name, style))
            self.body.append(self.type.draw(right, y, note, "note", "end"))
        # The curator: the one filled shape, with the mark, because m2b itself does this step.
        self.body.append(f'<rect class="curator-box" x="{row_left}" y="144" width="{row_width}" height="58" rx="29"/>')
        self.body.append(self.glow("curator", row_left, 144, row_width, 58, 29))
        self.body.append(mark_white(PANEL + 38, 159, 28))
        for text, style, base in (
            ("The curator", "curator", 170),
            ("files it at your next session start", "curator-sub", 188),
        ):
            self.type.fit(text, style, row_width - 76 - 18)
            self.body.append(self.type.draw(PANEL + 94, base, text, style))
        # The optional worklog, a row of the same tree.
        self.body.append(f'<rect class="dotted-box" x="{row_left}" y="396" width="{row_width}" height="30" rx="15"/>')
        self.body.append(f'<path class="way dotted" d="M{TRUNK},372 V396"/>')
        self.body.append(self.type.draw(PANEL + 52, 416, "worklog", "name"))
        note_x = PANEL + 52 + self.type.width("worklog", "name") + 10
        self.type.fit("a daily log, via herdr", "note", right - 2 - 62 - 10 - note_x)
        self.body.append(self.type.draw(note_x, 416, "a daily log, via herdr", "note"))
        self.body.extend(self.pill(right - 2, 416.5))

    def band(self) -> None:
        """The band in a later session: what waits, and in the third story the task due that day."""
        y = 332
        self.body.append(f'<rect class="terminal" x="{RIGHT}" y="{y}" width="{COLUMN}" height="30" rx="9"/>')
        self.body.append(self.glow("band", RIGHT, y, COLUMN, 30, 9))
        self.body.append(self.type.draw(RIGHT + 12, y + 19.5, "m2b", "band-name"))
        text_x = RIGHT + 12 + self.type.width("m2b  ", "band")
        for index, (text, story, windows) in enumerate(BAND):
            classes = self.animated(f"band-{index}", window_frames(windows, "opacity"))
            drawn = self.type.draw(text_x, y + 19.5, text, "band")
            if story == 1:
                drawn += self.type.draw(RIGHT + COLUMN - 12, y + 19.5, "[ open ]", "band", "end")
                self.type.fit(f"m2b  {text}  [ open ]", "band", COLUMN - 24)
            else:
                self.type.fit(f"m2b  {text}", "band", COLUMN - 24)
            story_class = "story-one" if story == 1 else "story-later"
            self.body.append(f'<g class="{story_class} {classes}">{drawn}</g>')
        self.type.fit("keep or drop, tick tasks, see facts", "sub", COLUMN)
        self.body.append(self.type.draw(RIGHT, y + 50, "keep or drop, tick tasks, see facts", "sub"))

    def dot(self) -> None:
        frames = [
            (seconds, f"transform:translate({x}px,{y}px);opacity:{opacity}") for seconds, x, y, opacity in dot_frames()
        ]
        classes = self.animated("dot", [(0.0, frames[0][1]), *frames, (LOOP_SECONDS, frames[-1][1])])
        self.body.append(
            f'<g class="dot {classes}"><circle r="7"/>'
            '<circle r="12.5" fill="none" stroke-opacity="0.35" stroke-width="3"/></g>'
        )

    def build(self) -> list[str]:
        for x, number, label in ZONES:
            self.body.append(f'<circle class="disc" cx="{x + 11}" cy="31" r="11"/>')
            self.body.append(self.type.draw(x + 11, 35.4, number, "badge", "middle"))
            following = min((other for other, _, _ in ZONES if other > x), default=WIDTH)
            self.type.fit(label, "zone", following - (x + 30) - 12)
            self.body.append(self.type.draw(x + 30, 36.2, label, "zone"))
        self.folder()
        # Quiet ways first, the stories' ways over them.
        for points, kind, head in WAYS.values():
            marker = f' marker-end="url(#head-{"main" if kind == "main" else kind})"' if head else ""
            self.body.append(f'<path class="way {kind}" d="{rounded(points)}"{marker}/>')
        self.terminal("said", LEFT, 56)
        self.type.fit("any session, any project", "note", COLUMN)
        self.body.append(self.type.draw(LEFT, 160, "any session, any project", "note"))
        self.side_row(LEFT, 207, "file", "or give it a file", ["a PDF, a scan, a photo"])
        self.side_row(LEFT, 289, "passing", "or just work", ["m2b proposes, you keep or drop"], True, "passing")
        self.terminal("known", RIGHT, 56)
        self.type.fit("every later session, any project", "note", COLUMN)
        self.body.append(self.type.draw(RIGHT, 160, "every later session, any project", "note"))
        self.side_row(RIGHT, 205, "lesson", "A lesson you kept", ["right before its command"])
        self.side_row(RIGHT, 262, "task", "A task on its day", ["due today, in the band"])
        self.side_row(RIGHT, 319, "band", "The band and the pane", [])
        self.band()
        self.dot()
        return self.body


def style(theme: dict[str, str], animations: Sequence[str], frozen_at: float | None = None) -> str:
    fills = "".join(
        f".{name}{{fill:{theme[name]}}}"
        for name in ("ink", "dim", "petrol", "bright", "on-terminal", "on-terminal-dim", "on-petrol", "on-petrol-dim")
    )
    # Without motion, and before the first keyframe, the picture is the first story's last frame.
    still = ".story-later,.cover,.cursor,.dot{opacity:0}.glow{stroke-opacity:0}"
    frozen = ""
    if frozen_at is not None:
        frozen = f".anim{{animation-play-state:paused!important;animation-delay:-{frozen_at}s!important}}"
    return (
        fills + f".disc{{fill:{theme['petrol']}}}.tint{{fill:{theme['tint']}}}.band-row{{fill:{theme['band']}}}"
        f".terminal{{fill:{theme['terminal']}}}.curator-box{{fill:{theme['petrol']}}}"
        f".cursor{{fill:{theme['bright']}}}"
        f".stroke-on-petrol{{stroke:{theme['on-petrol']}}}"
        f".glow{{fill:none;stroke:{theme['bright']};stroke-width:3}}"
        f".prompt{{fill:none;stroke:{theme['bright']};stroke-width:2;stroke-linecap:round;stroke-linejoin:round}}"
        f".icon{{fill:none;stroke:{theme['petrol']};stroke-width:2.3;stroke-linecap:round;stroke-linejoin:round}}"
        f".pill{{fill:{theme['ground']};stroke:{theme['petrol']};stroke-width:1.2}}"
        f".dotted-box{{fill:none;stroke:{theme['line']};stroke-width:2;stroke-linecap:round;stroke-dasharray:0.1 6.5}}"
        f".way{{fill:none;stroke-linecap:round;stroke-linejoin:round}}"
        f".main{{stroke:{theme['petrol']};stroke-width:5}}.quiet{{stroke:{theme['line']};stroke-width:2}}"
        f".lesson,.task{{stroke:{theme['petrol']};stroke-width:3}}"
        f".dotted{{stroke:{theme['line']};stroke-width:2.4;stroke-dasharray:0.1 6.5}}"
        f".dot circle:first-child{{fill:{theme['petrol']}}}.dot circle:last-child{{stroke:{theme['petrol']}}}"
        + still
        + "".join(animations)
        + "@media (prefers-reduced-motion:reduce){.anim{animation:none}}"
        + frozen
    )


def svg(theme: dict[str, str], type_: Text, frozen_at: float | None = None) -> str:
    picture = Picture(type_)
    body = picture.build()
    heads = "".join(
        f'<marker id="head-{kind}" markerUnits="userSpaceOnUse" markerWidth="{size + 4}" '
        f'markerHeight="{size * 2 + 4}" refX="{size}" refY="{size + 2}" orient="auto">'
        f'<path d="M2,2 L{size},{size + 2} L2,{size * 2 + 2}" fill="none" '
        f'stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/></marker>'
        for kind, size, width, color in (
            ("main", 7, 5, theme["petrol"]),
            ("task", 6, 3, theme["petrol"]),
            ("quiet", 5, 2, theme["line"]),
        )
    )
    return (
        "\n".join(
            [
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" '
                f'height="{HEIGHT}" role="img" aria-labelledby="t d">',
                '<title id="t">How m2b works</title>',
                f'<desc id="d">{ALT.replace(chr(39), "&#39;")}</desc>',
                f"<style>{style(theme, picture.animations, frozen_at)}</style>",
                f"<defs>{heads}{type_.defs()}</defs>",
                *body,
                "</svg>",
            ]
        )
        + "\n"
    )


def main(arguments: list[str]) -> int:
    if len(arguments) not in (1, 3) or (len(arguments) == 3 and arguments[1] != "--stills"):
        print("usage: overview-picture <folder of the .ttf files> [--stills <folder>]", file=sys.stderr)
        return 2
    fonts = Path(arguments[0])
    images = Path(__file__).resolve().parents[2] / "docs" / "images"
    for name, theme in THEMES.items():
        text = svg(theme, Type(fonts))
        (images / f"overview-{name}.svg").write_text(text, encoding="utf-8")
        print(f"docs/images/overview-{name}.svg: {len(text)} bytes")
    if len(arguments) == 3:
        stills = Path(arguments[2])
        stills.mkdir(parents=True, exist_ok=True)
        for name, theme in THEMES.items():
            for seconds in STILLS:
                frozen = svg(theme, Type(fonts), seconds)
                (stills / f"{name}-{seconds:04.1f}s.svg").write_text(frozen, encoding="utf-8")
        print(f"{stills}: {len(STILLS) * len(THEMES)} stills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
