"""A fix the owner keeps for a file Claude reads: kept in the store, applied by a session in its place.

A lesson often has a source already: a CLAUDE.md, a rule file, that says the matter wrongly, out of
date or in the wrong place. Then the lesson is a fix of that source, not a second statement beside
it that contradicts it. m2b writes no file of a repository: those are committed, shared and
sometimes public, and the owner commits them himself. So a kept fix waits in the store, and the
session start in a clone of that repository says that one waits and names the file; the session
applies it there, where the owner sees the change. A fix for a file under ``~/.claude/`` waits in
every session on the machine it was kept on, since each machine has its own.

A repository is named by the addresses of its remotes (``session_remotes.address_of``), the same
on every machine; a path on this machine never goes into the store. A fix is one file,
``state/core/fixes/<name>.json``, created exclusively: a client only adds to the store. Its name
is drawn from what it changes, so keeping the same fix twice finds the first one. What became of it
is an empty file of its own beside it, added as exclusively: ``<name>.done`` once the owner
confirmed it applied, ``<name>.dropped`` when he gave it up.

Whether the line a fix replaces is still in the file is looked at in the checkout a session starts
in, which can be on any branch. So what is found there is only said, never settled: a fix whose
line one checkout lacks may still be right for another, and only the owner knows which.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from m2b.notes.layout import STATE
from m2b.store.base import EvictedFileError, Store

FOLDER = f"{STATE}/core/fixes"
VERSION = 1
HOME_PREFIX = "~/.claude/"
# The files of a repository Claude Code loads by name, in any of its folders.
REPOSITORY_FILES = ("CLAUDE.md", "CLAUDE.local.md")

WAITING = "waiting"
DONE = "done"
DROPPED = "dropped"
# The order decides where two clients settled one fix differently: a fix applied stands.
SETTLED = (DONE, DROPPED)

# What ``look`` finds in the file a fix is for.
WAITS = "waits"
APPLIED = "applied"
GONE = "gone"

MAX_WORDING = 4000
MAX_LINE = 1000
_NAME = re.compile(r"fix-[0-9a-f]{12}")
_FILE = re.compile(rf"({_NAME.pattern})\.(json|{'|'.join(SETTLED)})")
_LINE_BREAK = re.compile("[\r\n\u2028\u2029\x85]")
# A path holds no character that ends a line or that a file system refuses.
_NOT_IN_A_PATH = re.compile("[\x00-\x1f\x7f\u2028\u2029\x85]")
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


class FixRefusedError(ValueError):
    """What was given is no fix; nothing was kept."""


class UnknownFixError(LookupError):
    """No kept fix has this name."""


@dataclass(frozen=True)
class Fix:
    """``path`` is the file's path in the repository, or from ``~`` for a file under ``~/.claude/``.

    ``repositories`` are the addresses of the repository's remotes, empty for a home file, which
    is ``machine``'s. ``line`` is the line the fix replaces, None for a fix that only adds.
    ``lesson`` is the lesson's sentence where a curation run kept a lesson as this fix: the reading
    of sessions goes on counting corrections of it under the fix's name (B289).
    """

    name: str
    path: str
    repositories: tuple[str, ...]
    machine: str | None
    line: str | None
    wording: str
    why: str
    kept: str
    lesson: str | None = None

    @property
    def for_home(self) -> bool:
        return not self.repositories

    @property
    def place(self) -> str:
        """The file in words: ``CLAUDE.md in github.com/acme/portal``, or ``~/.claude/CLAUDE.md``."""
        return self.path if self.for_home else f"{self.path} in {', '.join(self.repositories)}"


@dataclass(frozen=True)
class Kept:
    fix: Fix
    state: str


def new_fix(
    path: str,
    repositories: Sequence[str],
    machine: str | None,
    line: str | None,
    wording: str,
    why: str,
    kept: str,
    lesson: str | None = None,
) -> Fix:
    """A fix with its name, or ``FixRefusedError`` for one that cannot be applied as given."""
    path = _checked_path(path, home=not repositories)
    if not repositories and not machine:
        raise FixRefusedError("a fix for a file under ~/.claude/ names the machine it is for")
    if line is not None:
        line = line.strip()
        if not line or _LINE_BREAK.search(line) or len(line) > MAX_LINE:
            raise FixRefusedError(f"the line a fix replaces is one line of the file, at most {MAX_LINE} characters")
    wording = wording.strip("\n")
    if not wording.strip() or len(wording) > MAX_WORDING:
        raise FixRefusedError(f"a fix needs its new wording, at most {MAX_WORDING} characters")
    why = why.strip()
    if not why or _LINE_BREAK.search(why):
        raise FixRefusedError("a fix says in one line what is wrong")
    if not _DAY.fullmatch(kept):
        raise FixRefusedError("a fix says the day it was kept as YYYY-MM-DD")
    addresses = tuple(sorted(set(repositories)))
    machine = None if addresses else machine
    drawn = json.dumps([path, addresses, machine, line, wording], ensure_ascii=False)
    name = "fix-" + hashlib.sha256(drawn.encode("utf-8")).hexdigest()[:12]
    if lesson is not None:
        lesson = " ".join(lesson.split()) or None
    return Fix(name, path, addresses, machine, line, wording, why, kept, lesson)


def _checked_path(path: str, home: bool) -> str:
    if home:
        if not path.startswith(HOME_PREFIX):
            raise FixRefusedError(f"a fix outside a repository is for a file under {HOME_PREFIX}")
        inner = path[len(HOME_PREFIX) :]
    else:
        inner = path
    if _NOT_IN_A_PATH.search(path):
        raise FixRefusedError("a file's path is one line, without control characters")
    # Split by hand: ``PurePosixPath`` drops empty and ``.`` parts, which would let ``a/./b`` and
    # ``a//b`` stand beside ``a/b`` as another fix, and a folder's own ``.`` pass as a file.
    if "\\" in inner or any(part in ("", ".", "..") for part in inner.split("/")):
        raise FixRefusedError(f"{path!r} is no path of a file in its repository")
    if not _is_instructions(inner.split("/"), home):
        raise FixRefusedError(
            f"{path!r} is no file Claude Code reads as instructions: a fix is for a CLAUDE.md, a rule, "
            "an output style or Claude Code's memory"
        )
    return path


def _is_instructions(parts: Sequence[str], home: bool) -> bool:
    """Whether Claude Code loads the file as instructions (B286). A fix is applied by a session from a
    text kept in a store that syncs, so a settings file, a hook or a workflow, which run code once
    written, is never one."""
    parts = list(parts)
    if home:
        if parts == ["CLAUDE.md"]:
            return True
        if parts[0] in ("rules", "output-styles") and len(parts) > 1:
            return parts[-1].endswith(".md")
        return len(parts) == 4 and parts[0] == "projects" and parts[2] == "memory" and parts[3].endswith(".md")
    if parts[-1] in REPOSITORY_FILES:
        return True
    rules = [at for at in range(len(parts) - 2) if parts[at : at + 2] == [".claude", "rules"]]
    return bool(rules) and parts[-1].endswith(".md")


def keep(store: Store, fix: Fix) -> bool:
    """Adds the fix; False when the same fix is kept already, which is left as it was."""
    try:
        store.create_exclusive(f"{FOLDER}/{fix.name}.json", _as_json(fix))
    except FileExistsError:
        return False
    return True


def _as_json(fix: Fix) -> bytes:
    target: dict[str, object] = (
        {"home": fix.path, "machine": fix.machine}
        if fix.for_home
        else {"repositories": list(fix.repositories), "path": fix.path}
    )
    raw = {
        "version": VERSION,
        "name": fix.name,
        "file": target,
        "line": fix.line,
        "wording": fix.wording,
        "why": fix.why,
        "kept": fix.kept,
    }
    if fix.lesson is not None:
        raw["lesson"] = fix.lesson
    return (json.dumps(raw, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def read_all(store: Store) -> list[Kept]:
    """Every kept fix that can be read, with what became of it, the oldest first.

    A fix not downloaded to this machine, or one that is no fix, is left out; a folder that is not
    downloaded raises, since then nobody can say what waits.
    """
    scan = store.scan(FOLDER)
    if FOLDER in scan.evicted:
        raise EvictedFileError(FOLDER)
    marks: dict[str, set[str]] = {}
    for path in (*scan.files, *scan.evicted):
        named = _FILE.fullmatch(PurePosixPath(path).name)
        if named is not None and str(PurePosixPath(path).parent) == FOLDER:
            marks.setdefault(named.group(1), set()).add(named.group(2))
    found: list[Kept] = []
    for name, kinds in sorted(marks.items()):
        if "json" not in kinds or f"{FOLDER}/{name}.json" in scan.evicted:
            continue
        fix = _parsed(store, name)
        if fix is None:
            continue
        found.append(Kept(fix, next((kind for kind in SETTLED if kind in kinds), WAITING)))
    found.sort(key=lambda kept: (kept.fix.kept, kept.fix.name))
    return found


def _parsed(store: Store, name: str) -> Fix | None:
    try:
        raw = json.loads(store.read_bytes(f"{FOLDER}/{name}.json").decode("utf-8"))
        target = raw["file"]
        repositories = tuple(str(address) for address in target.get("repositories", ()))
        path = target["path"] if repositories else target["home"]
        line = raw.get("line")
        fix = new_fix(
            str(path),
            repositories,
            target.get("machine"),
            None if line is None else str(line),
            str(raw["wording"]),
            str(raw["why"]),
            str(raw.get("kept", "")),
            raw["lesson"] if isinstance(raw.get("lesson"), str) else None,
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    # A file whose content is not the fix its name says was not written by ``keep``.
    return fix if fix.name == name else None


def find(store: Store, name: str) -> Kept:
    if not _NAME.fullmatch(name):
        raise FixRefusedError(f"{name!r} is no name of a fix: it is fix- and twelve letters and digits")
    for kept in read_all(store):
        if kept.fix.name == name:
            return kept
    raise UnknownFixError(f"no kept fix has the name {name}; m2b fix list shows those that wait")


def settle(store: Store, name: str, state: str) -> bool:
    """Says what became of a waiting fix; False when it was settled before, which stands."""
    if state not in SETTLED:
        raise ValueError(f"no state of a fix: {state}")
    if find(store, name).state != WAITING:
        return False
    try:
        store.create_exclusive(f"{FOLDER}/{name}.{state}", b"")
    except FileExistsError:
        return False
    return True


def kept_from_lessons(store: Store) -> list[Fix]:
    """The fixes whose lessons are counted (``counted``). A folder or a fix that is not downloaded
    raises ``EvictedFileError``, as a folder that cannot be read raises: without it the counts of a
    fix would be written as those of a fix given up, and lost."""
    scan = store.scan(FOLDER)
    for path in scan.evicted:
        if path == FOLDER or path.endswith(".json"):
            raise EvictedFileError(path)
    return counted(read_all(store))


def counted(found: Iterable[Kept]) -> list[Fix]:
    """The fixes a curation run kept from a lesson and the owner did not give up: their lessons are
    counted on (B289), so the counts show whether the fix works."""
    return [kept.fix for kept in found if kept.fix.lesson is not None and kept.state != DROPPED]


def waiting_for(kept: Iterable[Kept], addresses: Collection[str], machine_id: str) -> list[Fix]:
    """The fixes that wait for a session whose folder's repository has remotes of ``addresses``,
    on the machine ``machine_id``: those for that repository and those for this machine's home."""
    return [
        item.fix
        for item in kept
        if item.state == WAITING
        and (
            (item.fix.for_home and item.fix.machine == machine_id)
            or any(address in addresses for address in item.fix.repositories)
        )
    ]


def local_file(fix: Fix, top: Path | None, home: Path | None) -> Path | None:
    """Where the file lies on this machine: below the repository's top, or below the home folder."""
    if fix.for_home:
        return None if home is None else home / fix.path[len("~/") :]
    return None if top is None else top / fix.path


def look(fix: Fix, file: Path) -> str:
    """Whether the file still holds what the fix replaces (``WAITS``), holds the new wording
    (``APPLIED``), or holds neither (``GONE``). Lines are compared without the white space at their
    ends; a file that is not there holds nothing."""
    try:
        text = file.read_text(encoding="utf-8", errors="replace")
    # A path the file system refuses holds nothing either, as a file that is not there.
    except (OSError, ValueError):
        text = ""
    lines = {line.strip() for line in text.splitlines()}
    wording = [line.strip() for line in fix.wording.splitlines() if line.strip()]
    if all(line in lines for line in wording):
        return APPLIED
    if fix.line is None or fix.line in lines:
        return WAITS
    return GONE
