"""Writes the README's overview picture of m2b, light and dark: docs/images/overview-{light,dark}.svg.

Run it through ``scripts/overview-picture <folder of the .ttf files>``, which brings fontTools.

Layout: three columns on one grid. Two terminals at the same height open and close the story, the
sentence as it is typed and the answer a later session gives; between them the folder with its
real file names. One thick line in the logo's color carries the sentence through; everything else
is quiet. Words in the picture are labels; the sentences stand in the caption below it.

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
from pathlib import Path

# fontTools comes with the run (scripts/overview-picture) and is no part of the repository's checks.
from fontTools.pens.svgPathPen import SVGPathPen  # type: ignore[import-not-found]
from fontTools.ttLib import TTFont  # type: ignore[import-not-found]

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
WIDTH, HEIGHT = 960, 436
LEFT, PANEL, RIGHT = 24, 312, 696
COLUMN = 240
PANEL_WIDTH = 336

MARK_COLOR = ("M -150,-120 H -60 A 30 30 0 0 1 -60,-60 H -120 A 30 30 0 0 0 -120,0 H -30", "M 34,-120 V 120")
MARK_CIRCLE = (124, 30, 90)
MARK_INK = "M -150,122 V 90 A 30 30 0 0 1 -90,90 V 122 M -90,90 A 30 30 0 0 1 -30,90 V 122"

ICONS = {
    "file": "M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z M14 3v5h5",
    "passing": "M4 6a3 3 0 0 1 3-3h10a3 3 0 0 1 3 3v6a3 3 0 0 1-3 3h-6l-4 4v-4a3 3 0 0 1-3-3z",
    "ask": "M11 4a7 7 0 1 0 0 14a7 7 0 0 0 0-14z M20 20l-4-4",
    "band": "M5 4h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z M15 4v16 M6 9h6",
}
ZONES = [(LEFT, "1", "What goes in"), (PANEL, "2", "m2b keeps it, on your machine"), (RIGHT, "3", "What comes back")]
# The folder's rows: (y, name, note, kind)
ROWS = [
    (124, "inbox/", "new, as you gave it", "plain"),
    (242, "memory/MEMORY.md", "starts every session", "strong"),
    (274, "memory/dana.md", "a file per subject", "plain"),
    (306, "corpus/2026/11/", "your words and files", "plain"),
    (338, "tasks/", "or Apple Reminders", "plain"),
]
Point = tuple[float, float]
TRUNK = 344
# The typographic apostrophe, as the typefaces draw it.
APOSTROPHE = "\u2019"
CORNER = 9
# The dot's way, once, on the thick line alone: (percent, x, y, opacity).
PATH = [
    (0, 264, 98, 0),
    (3, 264, 98, 1),
    (7, 288, 98, 1),
    (11, 288, 120, 1),
    (20, 344, 120, 1),
    (25, 344, 144, 1),
    (28, 344, 144, 0),
    (40, 344, 202, 0),
    (43, 344, 202, 1),
    (50, 344, 237, 1),
    (53, 358, 237, 1),
    (56, 358, 237, 0),
    (62, 632, 237, 0),
    (65, 632, 237, 1),
    (69, 668, 237, 1),
    (84, 668, 98, 1),
    (89, 692, 98, 1),
    (93, 692, 98, 0),
    (100, 692, 98, 0),
]
LIT = {"curator": (25, 43), "memory": (53, 65), "answer": (89, 100)}
SECONDS = 9


class Type:
    """Two faces as outlines: each glyph once under <defs>, each text a row of uses."""

    def __init__(self, folder: Path) -> None:
        self.faces = {key: TTFont(str(folder / name)) for key, name in FACES.items()}
        self.used: dict[tuple[str, int, str], str] = {}

    def _glyphs(self, text: str, face: TTFont) -> list[tuple[str, int]]:
        cmap, widths = face.getBestCmap(), face["hmtx"]
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


def rounded(points: list[Point]) -> str:
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


def way(points: list[Point], kind: str, head: bool = True) -> str:
    marker = f' marker-end="url(#head-{"main" if kind == "main" else "quiet"})"' if head else ""
    return f'<path class="way {kind}" d="{rounded(points)}"{marker}/>'


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


def terminal(type_: Type, x: int, y: int, lines: list[tuple[str, str, bool]], lit: str = "") -> list[str]:
    """A prompt as Claude Code shows it: the chevron, what is typed, and below it what is answered."""
    parts = [f'<rect class="terminal" x="{x}" y="{y}" width="{COLUMN}" height="84" rx="12"/>']
    if lit:
        parts.append(f'<rect class="glow lit-{lit}" x="{x}" y="{y}" width="{COLUMN}" height="84" rx="12"/>')
    for index, (text, style, has_prompt) in enumerate(lines):
        base = y + 34 + index * 23
        indent = 34 if style == "typed" else 16
        if has_prompt:
            parts.append(f'<path class="prompt" d="M{x + 17},{base - 9} l5,4.5 l-5,4.5"/>')
        type_.fit(text, style, COLUMN - indent - 12)
        parts.append(type_.draw(x + indent, base, text, style))
    return parts


def pill(type_: Type, right: float, y: float) -> list[str]:
    return [
        f'<rect class="pill" x="{right - 62}" y="{y - 13}" width="62" height="18" rx="9"/>',
        type_.draw(right - 31, y - 0.6, "OPTIONAL", "pill", "middle"),
    ]


def side_row(type_: Type, x: int, y: int, icon: str, title: str, subs: list[str], optional: bool = False) -> list[str]:
    """A quiet row beside the story: an icon, a title of a few words, a line of what it is."""
    parts = []
    inset = 14 if optional else 0
    if optional:
        height = 46 + len(subs) * 18
        parts.append(f'<rect class="dotted-box" x="{x}" y="{y - 26}" width="{COLUMN}" height="{height}" rx="14"/>')
        parts.extend(pill(type_, x + COLUMN - 14, y + 1))
    parts.append(f'<path class="icon" transform="translate({x + inset} {y - 16}) scale(0.88)" d="{ICONS[icon]}"/>')
    type_.fit(title, "title", COLUMN - inset * 2 - 30 - (70 if optional else 0))
    parts.append(type_.draw(x + inset + 30, y, title, "title"))
    for index, sub in enumerate(subs):
        type_.fit(sub, "sub", COLUMN - inset * 2)
        parts.append(type_.draw(x + inset, y + 22 + index * 18, sub, "sub"))
    return parts


def folder(type_: Type) -> list[str]:
    right = PANEL + PANEL_WIDTH - 24
    type_.fit("plain files, in a folder you own", "note", right - (PANEL + 24) - type_.width("~/m2b", "folder") - 12)
    parts = [
        f'<rect class="tint" x="{PANEL}" y="56" width="{PANEL_WIDTH}" height="356" rx="22"/>',
        type_.draw(PANEL + 24, 88, "~/m2b", "folder"),
        type_.draw(right, 88, "plain files, in a folder you own", "note", "end"),
        f'<rect class="band-row" x="{PANEL + 18}" y="222" width="{PANEL_WIDTH - 36}" height="30" rx="15"/>',
        f'<rect class="glow lit-memory" x="{PANEL + 18}" y="222" width="{PANEL_WIDTH - 36}" height="30" rx="15"/>',
        # The tree's quiet guides below the fact's row.
        f'<path class="way quiet" d="M{TRUNK},252 V338"/>',
    ]
    for y, name, note, kind in ROWS:
        style = "name-strong" if kind == "strong" else "name"
        type_.fit(note, "note", right - (PANEL + 52) - type_.width(name, style) - 12)
        parts.append(type_.draw(PANEL + 52, y, name, style))
        parts.append(type_.draw(right, y, note, "note", "end"))
        if y > 250:
            parts.append(f'<path class="way quiet" d="M{TRUNK},{y - 4} H{TRUNK + 12}"/>')
    # The curator: the one filled shape, with the mark, because m2b itself does this step.
    parts.append(f'<rect class="curator-box" x="{PANEL + 18}" y="144" width="{PANEL_WIDTH - 36}" height="58" rx="29"/>')
    parts.append(
        f'<rect class="glow lit-curator" x="{PANEL + 18}" y="144" width="{PANEL_WIDTH - 36}" height="58" rx="29"/>'
    )
    parts.append(mark_white(PANEL + 38, 159, 28))
    type_.fit("The curator", "curator", PANEL_WIDTH - 36 - 76 - 18)
    parts.append(type_.draw(PANEL + 94, 170, "The curator", "curator"))
    type_.fit("files it at your next session start", "curator-sub", PANEL_WIDTH - 36 - 76 - 18)
    parts.append(type_.draw(PANEL + 94, 188, "files it at your next session start", "curator-sub"))
    # The optional worklog, a row of the same tree.
    parts.append(f'<rect class="dotted-box" x="{PANEL + 18}" y="362" width="{PANEL_WIDTH - 36}" height="30" rx="15"/>')
    parts.append(f'<path class="way dotted" d="M{TRUNK},342 V362"/>')
    parts.append(type_.draw(PANEL + 52, 382, "worklog", "name"))
    note_x = PANEL + 52 + type_.width("worklog", "name") + 10
    type_.fit("a daily log, via herdr", "note", right - 2 - 62 - 10 - note_x)
    parts.append(type_.draw(note_x, 382, "a daily log, via herdr", "note"))
    parts.extend(pill(type_, right - 2, 382.5))
    return parts


def svg(theme: dict[str, str], type_: Type) -> str:
    keyframes = " ".join(f"{p}%{{transform:translate({x}px,{y}px);opacity:{o}}}" for p, x, y, o in PATH)
    lit = "".join(
        f"@keyframes lit-{name}{{0%,{start - 1}%{{stroke-opacity:0}}{start}%,{end - 1}%{{stroke-opacity:1}}"
        f"{end}%,100%{{stroke-opacity:0}}}}.lit-{name}{{animation:lit-{name} {SECONDS}s linear 1s 1 both}}"
        for name, (start, end) in LIT.items()
    )
    fills = "".join(
        f".{name}{{fill:{theme[name]}}}"
        for name in ("ink", "dim", "petrol", "bright", "on-terminal", "on-petrol", "on-petrol-dim")
    )
    style = (
        fills + f".disc{{fill:{theme['petrol']}}}.tint{{fill:{theme['tint']}}}.band-row{{fill:{theme['band']}}}"
        f".terminal{{fill:{theme['terminal']}}}.curator-box{{fill:{theme['petrol']}}}"
        f".stroke-on-petrol{{stroke:{theme['on-petrol']}}}"
        f".glow{{fill:none;stroke:{theme['bright']};stroke-width:3;stroke-opacity:0}}"
        f".prompt{{fill:none;stroke:{theme['bright']};stroke-width:2;stroke-linecap:round;stroke-linejoin:round}}"
        f".icon{{fill:none;stroke:{theme['petrol']};stroke-width:2.3;stroke-linecap:round;stroke-linejoin:round}}"
        f".pill{{fill:{theme['ground']};stroke:{theme['petrol']};stroke-width:1.2}}"
        f".dotted-box{{fill:none;stroke:{theme['line']};stroke-width:2;stroke-linecap:round;stroke-dasharray:0.1 6.5}}"
        f".way{{fill:none;stroke-linecap:round;stroke-linejoin:round}}"
        f".main{{stroke:{theme['petrol']};stroke-width:5}}.quiet{{stroke:{theme['line']};stroke-width:2}}"
        f".dotted{{stroke:{theme['line']};stroke-width:2.4;stroke-dasharray:0.1 6.5}}"
        f".dot circle:first-child{{fill:{theme['petrol']}}}.dot circle:last-child{{stroke:{theme['petrol']}}}"
        f".dot{{animation:travel {SECONDS}s linear 1s 1 both}}@keyframes travel{{{keyframes}}}"
        + lit
        + "@media (prefers-reduced-motion:reduce){.dot{animation:none;opacity:0}.glow{animation:none}}"
    )
    desc = (
        "How m2b works, from left to right. 1, what goes in: in any Claude Code session you say remember that "
        "Dana's birthday is on 3 March; or you give it a file, a PDF, a scan, a photo; or, optional, m2b proposes "
        "what was said in passing and you keep or drop it. 2, m2b keeps it on your machine, as plain files in a "
        "folder you own, ~/m2b: what is new lands in inbox/ as you gave it; the curator files it at your next "
        "session start, into memory/MEMORY.md, which starts every session, a file per subject such as "
        "memory/dana.md, the archive corpus/2026/11/ with your words and files, and tasks/ or Apple Reminders; "
        "optional: a worklog, a daily log, via herdr. 3, what comes back: a later session in any project is asked "
        "when is Dana's birthday and answers 3 March (dana.md); you can ask for more, a search or the note behind "
        "a fact; and the band and the pane show what waits for you: m2b, 1 waits for you, open."
    )
    heads = "".join(
        f'<marker id="head-{kind}" markerUnits="userSpaceOnUse" markerWidth="{size + 4}" markerHeight="{size * 2 + 4}" '
        f'refX="{size}" refY="{size + 2}" orient="auto">'
        f'<path d="M2,2 L{size},{size + 2} L2,{size * 2 + 2}" fill="none" '
        f'stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/></marker>'
        for kind, size, width, color in (("main", 7, 5, theme["petrol"]), ("quiet", 5, 2, theme["line"]))
    )
    body = []
    for x, number, label in ZONES:
        body.append(f'<circle class="disc" cx="{x + 11}" cy="31" r="11"/>')
        body.append(type_.draw(x + 11, 35.4, number, "badge", "middle"))
        following = min((other for other, _, _ in ZONES if other > x), default=WIDTH)
        type_.fit(label, "zone", following - (x + 30) - 12)
        body.append(type_.draw(x + 30, 36.2, label, "zone"))
    body.extend(folder(type_))
    # Quiet ways first, the sentence's way over them.
    body.append(way([(264, 207), (300, 207), (300, 128)], "quiet", head=False))
    body.append(way([(264, 289), (300, 289), (300, 215)], "dotted", head=False))
    body.append(way([(648, 268), (690, 268)], "quiet"))
    body.append(way([(648, 331), (690, 331)], "quiet"))
    body.append(way([(264, 98), (288, 98), (288, 120), (TRUNK, 120), (TRUNK, 142)], "main"))
    body.append(way([(TRUNK, 202), (TRUNK, 237), (TRUNK + 14, 237)], "main"))
    body.append(way([(632, 237), (668, 237), (668, 98), (692, 98)], "main"))
    body.extend(
        terminal(
            type_,
            LEFT,
            56,
            [(f"remember that Dana{APOSTROPHE}s", "typed", True), ("birthday is on 3 March", "typed", False)],
        )
    )
    type_.fit("any session, any project", "note", COLUMN)
    body.append(type_.draw(LEFT, 160, "any session, any project", "note"))
    body.extend(side_row(type_, LEFT, 207, "file", "or give it a file", ["a PDF, a scan, a photo"]))
    body.extend(side_row(type_, LEFT, 289, "passing", "said in passing", ["m2b proposes, you keep or drop"], True))
    body.extend(
        terminal(
            type_,
            RIGHT,
            56,
            [(f"when is Dana{APOSTROPHE}s birthday?", "typed", True), ("3 March (dana.md)", "answer", False)],
            lit="answer",
        )
    )
    type_.fit("every later session, any project", "note", COLUMN)
    body.append(type_.draw(RIGHT, 160, "every later session, any project", "note"))
    body.extend(side_row(type_, RIGHT, 268, "ask", "Ask for more", ["search, or the note behind a fact"]))
    body.extend(side_row(type_, RIGHT, 331, "band", "The band and the pane", []))
    body.append(f'<rect class="terminal" x="{RIGHT}" y="344" width="{COLUMN}" height="30" rx="9"/>')
    body.append(type_.draw(RIGHT + 12, 363.5, "m2b", "band-name"))
    body.append(type_.draw(RIGHT + 12 + type_.width("m2b  ", "band"), 363.5, "1 waits for you", "band"))
    body.append(type_.draw(RIGHT + COLUMN - 12, 363.5, "[ open ]", "band", "end"))
    type_.fit("m2b  1 waits for you  [ open ]", "band", COLUMN - 24)
    type_.fit("keep or drop, tick tasks, see facts", "sub", COLUMN)
    body.append(type_.draw(RIGHT, 394, "keep or drop, tick tasks, see facts", "sub"))
    body.append(
        '<g class="dot" transform="translate(264 98)" opacity="0"><circle r="7"/>'
        '<circle r="12.5" fill="none" stroke-opacity="0.35" stroke-width="3"/></g>'
    )
    return (
        "\n".join(
            [
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" '
                f'height="{HEIGHT}" '
                'role="img" aria-labelledby="t d">',
                '<title id="t">How m2b works</title>',
                f'<desc id="d">{desc.replace(chr(39), "&#39;")}</desc>',
                f"<style>{style}</style>",
                f"<defs>{heads}{type_.defs()}</defs>",
                *body,
                "</svg>",
            ]
        )
        + "\n"
    )


def main(arguments: list[str]) -> int:
    if len(arguments) != 1:
        print("usage: overview-picture <folder of the .ttf files>", file=sys.stderr)
        return 2
    images = Path(__file__).resolve().parents[2] / "docs" / "images"
    for name, theme in THEMES.items():
        text = svg(theme, Type(Path(arguments[0])))
        (images / f"overview-{name}.svg").write_text(text, encoding="utf-8")
        print(f"docs/images/overview-{name}.svg: {len(text)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
