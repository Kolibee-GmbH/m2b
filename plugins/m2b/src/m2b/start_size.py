"""How large everything is that a session in a folder starts with (B268): each file Claude Code loads
at the start and m2b's own part, in KB and list points, with the sum, for ``m2b status``.

Most of a session's start is not m2b's: the owner's CLAUDE.md files, the rules and the output style
are often larger than the distillate. Shown side by side, the owner sees where to cut. Which files
Claude Code loads, and under which conditions, is listed in ``claude_code``.

It only reads and starts no program and no model. A file that is there and cannot be read is named
with the reason and counts in no sum, so it never passes for an empty file; a file that is not there
is left out, because Claude Code loads nothing from it either. A rule with ``paths`` in its
frontmatter is listed but stays out of the sum: Claude Code loads it only when a matching file is
read. m2b's part is what its session start prints after the notices, measured with the same code;
the notices themselves (a failed run, a fix to apply) come and go and are not counted.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from m2b import claude_code, hooks, lessons
from m2b.config.machine import MachineConfig
from m2b.notes.characters import without_hidden
from m2b.notes.frontmatter import Note
from m2b.paths import MachinePaths
from m2b.store.base import EvictedFileError, Store, StoreError
from m2b.store.factory import open_store

# The files Claude Code reads in the folder and in each folder above it.
FOLDER_FILES = ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md")
RULES_FOLDER = "rules"
OUTPUT_STYLES_FOLDER = "output-styles"
SETTINGS_FILES = ("settings.json",)
PROJECT_SETTINGS_FILES = (".claude/settings.json", ".claude/settings.local.json")
DEFAULT_STYLE = "default"
# What Claude Code loads of the auto memory's index at the start.
MEMORY_INDEX_LINES = 200
MEMORY_INDEX_BYTES = 25 * 1024
# A list point: a line starting with a bullet or a number, indented or not.
LIST_POINT = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+\S", re.M)
_FIELD = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):(.*)$")
ONLY_WITH_A_MATCHING_FILE = "only when a matching file is read"
OFF_IN_THIS_FOLDER = "off in this folder"
NOT_FOUND = "not found"


@dataclass(frozen=True)
class Part:
    """One file or part a session starts with; ``size`` and ``points`` are None when it could not be read."""

    name: str
    size: int | None
    points: int | None
    not_read: str | None = None
    when: str | None = None

    @property
    def counts(self) -> bool:
        return self.size is not None and self.when is None

    def as_json(self) -> dict[str, object]:
        answer: dict[str, object] = {"name": self.name}
        if self.not_read is not None:
            answer["not_read"] = self.not_read
            return answer
        answer.update(kb=_kb(self.size or 0), list_points=self.points)
        if self.when is not None:
            answer["when"] = self.when
        return answer


def measure(
    config: MachineConfig, machine: MachinePaths, environ: Mapping[str, str], folder: Path
) -> dict[str, object]:
    """The part of ``status --json`` that names what a session in ``folder`` starts with."""
    home = environ.get("HOME")
    claude = claude_code.claude_folder(environ)
    parts = [
        *_claude_code_parts(claude, folder, home, environ),
        *_m2b_parts(config, machine, environ, folder, home),
    ]
    counted = [part for part in parts if part.counts]
    return {
        "folder": _shown(folder, home),
        "parts": [part.as_json() for part in parts],
        "kb": _kb(sum(part.size or 0 for part in counted)),
        "list_points": sum(part.points or 0 for part in counted),
        "not_read": sum(1 for part in parts if part.not_read is not None),
    }


def text_lines(answer: Mapping[str, object]) -> list[str]:
    """The lines ``m2b status`` prints for the part, the sum first."""
    parts = answer["parts"]
    assert isinstance(parts, list)
    not_read = f", {answer['not_read']} not read" if answer["not_read"] else ""
    lines = [f"session start in {answer['folder']}: {answer['kb']} KB, {answer['list_points']} list points{not_read}"]
    for part in parts:
        if "not_read" in part:
            lines.append(f"  {part['name']}: not read ({part['not_read']})")
            continue
        when = f", {part['when']}" if "when" in part else ""
        lines.append(f"  {part['name']}: {part['kb']} KB, {part['list_points']} list points{when}")
    return lines


def _claude_code_parts(claude: Path, folder: Path, home: str | None, environ: Mapping[str, str]) -> Iterator[Part]:
    seen: set[Path] = set()
    yield from _files([claude / "CLAUDE.md"], home, seen)
    yield from _files(_rules(claude / RULES_FOLDER), home, seen, rules=True)
    for above in _folders_up_to_home(folder, home):
        yield from _files([above / name for name in FOLDER_FILES], home, seen)
        yield from _files(_rules(above / ".claude" / RULES_FOLDER), home, seen, rules=True)
    style = _output_style(claude, folder, home, environ)
    if style is not None:
        yield style
    index = _memory_index(environ, folder)
    yield from _files([index], home, seen, lines=MEMORY_INDEX_LINES, max_bytes=MEMORY_INDEX_BYTES)


def _folders_up_to_home(folder: Path, home: str | None) -> list[Path]:
    """The folder and each one above it, up to the home folder when it lies below it, else up to
    the folder below the root."""
    chain = [folder, *folder.parents]
    if home is not None and Path(home) in chain:
        return chain[: chain.index(Path(home)) + 1]
    return [above for above in chain if above.parent != above]


def _rules(rules: Path) -> list[Path]:
    try:
        return sorted(path for path in rules.rglob("*.md") if not path.is_dir())
    except OSError:
        return []


def _files(
    paths: Sequence[Path],
    home: str | None,
    seen: set[Path],
    rules: bool = False,
    lines: int | None = None,
    max_bytes: int | None = None,
) -> Iterator[Part]:
    for path in paths:
        try:
            key = path.resolve()
        except OSError:
            key = path
        if key in seen:
            continue
        seen.add(key)
        name = _shown(path, home)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            continue
        except OSError as error:
            yield Part(name, None, None, not_read=error.strerror or type(error).__name__)
            continue
        if lines is not None:
            text = "".join(text.splitlines(keepends=True)[:lines])
        if max_bytes is not None:
            text = text.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
        if not rules:
            yield _part(name, text)
            continue
        fields, body = _split_frontmatter(text)
        yield _part(name, body, ONLY_WITH_A_MATCHING_FILE if "paths" in fields else None)


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """The top-level fields of a file's frontmatter and the text after it, which is what Claude Code
    passes on. Its keys may hold a hyphen (``force-for-plugin``), which a note's keys never do."""
    note = Note.parse(text)
    if note.frontmatter is None:
        return {}, text
    fields = {}
    for line in note.frontmatter.render().splitlines()[1:-1]:
        match = _FIELD.match(line)
        if match and match.group(1) not in fields:
            fields[match.group(1)] = _unquoted(match.group(2).strip())
    return fields, note.body


def _unquoted(value: str) -> str:
    """A YAML value as meant: ``"Brief"`` and ``'true'`` are ``Brief`` and ``true``."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _part(name: str, text: str, when: str | None = None) -> Part:
    return Part(name, len(text.encode("utf-8")), len(LIST_POINT.findall(text)), when=when)


def _output_style(claude: Path, folder: Path, home: str | None, environ: Mapping[str, str]) -> Part | None:
    """The active output style: one an enabled plugin forces, else the one the settings name; a name
    whose file cannot be found, such as a style built into Claude Code, is named as not read."""
    chosen: str | None = None
    enabled: dict[str, object] = {}
    for path in [*(claude / name for name in SETTINGS_FILES), *(folder / name for name in PROJECT_SETTINGS_FILES)]:
        try:
            settings = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as error:
            return Part("output style", None, None, not_read=f"{_shown(path, home)} could not be read: {error}")
        if not isinstance(settings, dict):
            continue
        plugins = settings.get("enabledPlugins")
        if isinstance(plugins, dict):
            enabled.update(plugins)
        if isinstance(settings.get("outputStyle"), str):
            chosen = settings["outputStyle"]
    styles = [
        *_styles_in(claude / OUTPUT_STYLES_FOLDER, ""),
        *_styles_in(folder / ".claude" / OUTPUT_STYLES_FOLDER, ""),
        *_plugin_styles(environ, folder, enabled),
    ]
    forced = next((style for style in styles if style.forced), None)
    if forced is None and (chosen is None or chosen.lower() == DEFAULT_STYLE):
        return None
    style = forced or next((style for style in styles if style.name == chosen), None)
    if style is None:
        return Part(f"output style {chosen}", None, None, not_read=NOT_FOUND)
    return _part(f"output style {style.name} ({_shown(style.path, home)})", style.text)


@dataclass(frozen=True)
class _Style:
    name: str
    path: Path
    text: str
    forced: bool


def _styles_in(styles: Path, prefix: str, may_force: bool = False) -> Iterator[_Style]:
    try:
        paths = sorted(styles.glob("*.md"))
    except OSError:
        return
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fields, body = _split_frontmatter(text)
        forced = may_force and fields.get("force-for-plugin") == "true"
        yield _Style(prefix + (fields.get("name") or path.stem), path, body, forced)


def _plugin_styles(environ: Mapping[str, str], folder: Path, enabled: Mapping[str, object]) -> Iterator[_Style]:
    try:
        installed = json.loads(claude_code.installed_plugins_file(environ).read_text(encoding="utf-8"))["plugins"]
    except (OSError, ValueError, KeyError, TypeError):
        return
    if not isinstance(installed, dict):
        return
    for key, entries in sorted(installed.items()):
        if enabled.get(key) is not True or not isinstance(entries, list):
            continue
        entry = next(
            (
                entry
                for entry in entries
                if isinstance(entry, dict)
                and (entry.get("scope") == "user" or entry.get("projectPath") == str(folder))
                and isinstance(entry.get("installPath"), str)
            ),
            None,
        )
        if entry is not None:
            plugin = key.split("@", 1)[0]
            yield from _styles_in(Path(entry["installPath"]) / OUTPUT_STYLES_FOLDER, f"{plugin}:", may_force=True)


def _memory_index(environ: Mapping[str, str], folder: Path) -> Path:
    key = re.sub(r"[^A-Za-z0-9]", "-", str(_repository_root(folder)))
    return claude_code.transcripts_folder(environ) / key / "memory" / "MEMORY.md"


def _repository_root(folder: Path) -> Path:
    """The folder of the git repository ``folder`` lies in; for a worktree the main one, whose auto
    memory every worktree shares. Read from the files, without git; outside a repository the folder."""
    for above in [folder, *folder.parents]:
        marker = above / ".git"
        if marker.is_dir():
            return above
        if marker.is_file():
            return _main_of_worktree(marker) or above
    return folder


def _main_of_worktree(marker: Path) -> Path | None:
    try:
        line = marker.read_text(encoding="utf-8").strip()
        if not line.startswith("gitdir:"):
            return None
        git_dir = (marker.parent / line[len("gitdir:") :].strip()).resolve()
        common = (git_dir / (git_dir / "commondir").read_text(encoding="utf-8").strip()).resolve()
    except OSError:
        return None
    return common.parent if common.name == ".git" else None


def _m2b_parts(
    config: MachineConfig, machine: MachinePaths, environ: Mapping[str, str], folder: Path, home: str | None
) -> list[Part]:
    if config.distillate.covering(folder) is not None:
        return [Part(f"m2b distillate ({OFF_IN_THIS_FOLDER})", 0, 0)]
    try:
        store: Store = open_store(config.store, machine.temp_dir)
        text = without_hidden(store.read_bytes(hooks.MEMORY_INDEX_PATH).decode("utf-8", errors="replace"))
    except EvictedFileError:
        return [Part("m2b distillate", None, None, not_read="not downloaded to this machine")]
    except FileNotFoundError:
        return []
    except (OSError, StoreError) as error:
        return [Part("m2b distillate", None, None, not_read=str(error))]
    view = hooks.start_view(text, lessons.read_all(store), machine, environ, folder)
    parts = [_part("m2b distillate", view.distillate)]
    if view.lessons:
        parts.append(_part("m2b lessons", view.lessons))
    return parts


def _shown(path: Path, home: str | None) -> str:
    if home:
        try:
            return str(Path("~") / path.relative_to(home))
        except ValueError:
            pass
    return str(path)


def _kb(size: int) -> float:
    return round(size / 1024, 1)
