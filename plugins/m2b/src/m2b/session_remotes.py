"""The git remotes of the folders sessions start in, and the work the owner names by them.

The owner names work that must reach no worklog and no reading of the sessions by a part of its
repository's remote URL (``worklog_leave_out.git_remote_contains`` in the profile). A worktree is
often gone by the time anything reads its sessions, and a git that does not answer names nothing,
so the remotes are noted while the folder is there: the session-start hook asks git once and keeps
the answer per folder in machine state, never in the store. A remote stays noted for ``KEEP_FOR``
after it was last seen, so a repository pointed elsewhere since is still known by its old remote.

The same notes say where a project's repository lies on this machine (``repository_places``): a
note names its folder and the top of the repository it lies in. For that a note is kept while its
folder is there, however old; only for leaving work out does it say nothing after ``KEEP_FOR``.

Known of a folder is what was noted for it and what git says there now. When neither says anything
the folder's repository is unknown, and whoever leaves work out by remote leaves it out: work that
cannot be shown to be other work is not read.

A URL is kept and compared without the user and password it may carry, where a token sits, and
both as the repository's configuration writes it and as git rewrites it (``url.<base>.insteadOf``):
the owner names the address they see, which may be either.

Standard library and ``git_program`` only, nothing else of m2b: the worklog add-on imports both.
"""

from __future__ import annotations

import contextlib
import datetime
import enum
import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from m2b.git_program import git_command, git_environment, usable_git

NOTES_FOLDER = "session-remotes"
KEEP_FOR = datetime.timedelta(days=30)
GIT_TIMEOUT_SECONDS = 10.0
# The remotes' URLs, the address a remote is pushed to when that is another one, and the rules by
# which git rewrites the beginning of a URL.
_ASKED_KEYS = r"^(remote\..*\.(push)?url|url\..*\.(push)?insteadof)$"
_NO_SUCH_KEY = 1
_CREDENTIALS = re.compile(r"\A([A-Za-z][A-Za-z0-9+.-]*://)[^/]*@")
# ``git@host:owner/repo`` or ``git@host:/path``, the short spelling of an SSH remote; a host has
# more than the one letter of a drive.
_SHORT_SSH = re.compile(r"\A(?:[^@/:]+@)?([^@/:]{2,}):/?(.+)\Z", re.S)
_PORT = re.compile(r"\A([a-z][a-z0-9+.-]*://[^/:]+):\d+(?=/|\Z)")

Runner = Callable[..., "subprocess.CompletedProcess[str]"]
Writer = Callable[[Path, str], None]


def remotes_in(
    folder: Path,
    git: str = "git",
    run: Runner = subprocess.run,
    timeout: float = GIT_TIMEOUT_SECONDS,
    environ: Mapping[str, str] | None = None,
) -> frozenset[str] | None:
    """The URL of every remote of the repository that holds ``folder``, without credentials, as
    written and as git rewrites it.

    Empty for a repository without a remote and for a folder in no repository; None when git
    cannot say: the folder is gone or may not be looked at, git is missing, fails or does not
    answer in time.
    """
    given = os.environ if environ is None else environ
    try:
        if not folder.is_dir():
            return None
        result = run(
            # A repository another user owns is read too: git would leave its configuration out and
            # answer as for a folder in no repository, and reading a URL starts nothing from it.
            git_command(git, folder, ["config", "-z", "--get-regexp", _ASKED_KEYS], ["safe.directory=*"]),
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            env=git_environment(given),
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if result.returncode == _NO_SUCH_KEY:
        return frozenset()
    if result.returncode != 0:
        return None
    return _urls(result.stdout)


def _urls(listed: str) -> frozenset[str]:
    """The remotes' URLs in what ``git config -z`` listed: each key, a newline, its value, a NUL.

    A URL counts as written and with every rewriting rule applied whose prefix it begins with, not
    only the longest, which git takes: one spelling more can only leave more work out.
    """
    written: list[str] = []
    rewrites: list[tuple[str, str]] = []
    for entry in listed.split("\0"):
        key, _, value = entry.partition("\n")
        if not value:
            continue
        if key.startswith("remote."):
            written.append(value)
        else:
            rewrites.append((value, key[len("url.") : key.rindex(".")]))
    rewritten = [base + url[len(prefix) :] for url in written for prefix, base in rewrites if url.startswith(prefix)]
    return frozenset(_CREDENTIALS.sub(r"\1", url) for url in (*written, *rewritten))


def names_one(parts: Iterable[str], remotes: Iterable[str]) -> bool:
    """Whether one of the remotes holds one of ``parts``, letters compared without regard to case.

    An SSH remote in the short spelling also counts as ``host/owner/repo``, and a URL also without
    its port, so a part written for one spelling of a repository's address finds the others.
    """
    wanted = [part.casefold() for part in parts if part]
    return any(part in spelling for remote in remotes for spelling in _spellings(remote) for part in wanted)


def _spellings(remote: str) -> tuple[str, ...]:
    lowered = remote.casefold()
    short = _SHORT_SSH.match(lowered) if "://" not in lowered else None
    if short is not None:
        return lowered, f"{short.group(1)}/{short.group(2)}"
    return lowered, _PORT.sub(r"\1", lowered)


def note(
    notes: Path,
    folder: str,
    remotes: frozenset[str],
    now: datetime.datetime,
    write: Writer,
    top: str | None = None,
) -> None:
    """Notes that ``folder``'s repository has ``remotes`` now, beside those seen there in the last ``KEEP_FOR``.

    ``top`` is the folder the repository's checkout begins at, where it is known. ``write`` puts a
    text in a file as a whole.
    """
    notes.mkdir(mode=0o700, parents=True, exist_ok=True)
    still_known = _last_seen(notes, folder, now) or {}
    seen = {**still_known, **dict.fromkeys(sorted(remotes), now.isoformat(timespec="seconds"))}
    noted_now: dict[str, object] = {"folder": folder, "noted": now.isoformat(timespec="seconds"), "remotes": seen}
    if top is not None:
        noted_now["top"] = top
    write(_note_path(notes, folder), json.dumps(noted_now, ensure_ascii=False) + "\n")


def repository_top(folder: Path) -> Path | None:
    """The nearest folder at or above ``folder`` that holds ``.git``, a clone's folder or a worktree's
    file; None in no repository. Read from the file system alone, so no git is started for it."""
    for candidate in (folder, *folder.parents):
        with contextlib.suppress(OSError):
            if (candidate / ".git").exists():
                return candidate
    return None


class RepositoryNotKnownError(Exception):
    """A folder's repository cannot be named by its remotes; ``reason`` says why, ``top`` is the
    repository's folder where there is one."""

    def __init__(self, reason: str, top: Path | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.top = top


NOT_IN_A_REPOSITORY = "not in a repository"
REMOTES_NOT_SAID = "git could not say the remotes"
NO_REMOTE = "no remote"


@dataclass(frozen=True)
class Repository:
    """The repository a folder lies in: the folder its checkout begins at, and the addresses of its
    remotes (``address_of``), which name it on every machine."""

    top: Path
    addresses: tuple[str, ...]

    @property
    def name(self) -> str:
        """The repository's own name, the last part of its first address: ``portal`` for
        ``github.com/acme/portal``."""
        return self.addresses[0].rsplit("/", 1)[-1]


def repository_of(folder: Path, environ: Mapping[str, str], timeout: float = GIT_TIMEOUT_SECONDS) -> Repository:
    """The repository ``folder`` lies in, named by its remotes, or ``RepositoryNotKnownError``: in
    no repository, git missing or silent, or a repository without a remote, which no other machine
    could find again."""
    top = repository_top(folder)
    if top is None:
        raise RepositoryNotKnownError(NOT_IN_A_REPOSITORY)
    git = usable_git(environ, timeout=timeout)
    remotes = None if git is None else remotes_in(folder, git, timeout=timeout, environ=environ)
    if remotes is None:
        raise RepositoryNotKnownError(REMOTES_NOT_SAID, top)
    if not remotes:
        raise RepositoryNotKnownError(NO_REMOTE, top)
    return Repository(top, tuple(sorted({address_of(remote) for remote in remotes})))


@dataclass(frozen=True)
class NotedFolder:
    """A folder a session started in, as its note says, whatever its age."""

    folder: str
    # The top of its repository where the note says it, else the folder itself.
    top: str
    noted: datetime.datetime
    remotes: frozenset[str]


def noted_folders(notes: Path) -> list[NotedFolder]:
    """Every note that can be read, old ones included; no folder is looked at."""
    found: list[NotedFolder] = []
    for path in notes.glob("*.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(raw, dict) or not isinstance(raw.get("remotes"), dict):
            continue
        folder, top, written = raw.get("folder"), raw.get("top"), _moment(raw.get("noted"))
        if not isinstance(folder, str) or written is None:
            continue
        found.append(
            NotedFolder(folder, top if isinstance(top, str) else folder, written, frozenset(map(str, raw["remotes"])))
        )
    return found


def address_of(remote: str) -> str:
    """A remote's address as host and path, the same for every spelling of it: no scheme, user,
    password or port, no ``.git`` and no slash at the end, letters in lower case.
    ``git@github.com:acme/portal.git`` and ``https://github.com/acme/portal`` are both
    ``github.com/acme/portal``."""
    lowered = remote.strip().casefold()
    if "://" in lowered:
        rest = lowered.split("://", 1)[1]
        host, _, path = rest.partition("/")
        host = host.rsplit("@", 1)[-1].split(":", 1)[0]
    else:
        short = _SHORT_SSH.match(lowered)
        host, path = (short.group(1).rsplit("@", 1)[-1], short.group(2)) if short else ("", lowered)
    path = path.strip("/").removesuffix(".git")
    return f"{host}/{path}" if host else path


def noted(notes: Path, folder: str, now: datetime.datetime) -> frozenset[str] | None:
    """The remotes noted for ``folder`` and seen there in the last ``KEEP_FOR``; None without a note that young."""
    seen = _last_seen(notes, folder, now)
    return None if seen is None else frozenset(seen)


def _last_seen(notes: Path, folder: str, now: datetime.datetime) -> dict[str, str] | None:
    """Each remote of the folder's note with the time it was last seen, those older than ``KEEP_FOR`` left out.

    None when the folder has no note that can be read, or none written in the last ``KEEP_FOR``.
    """
    try:
        raw = json.loads(_note_path(notes, folder).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict) or raw.get("folder") != folder or not isinstance(raw.get("remotes"), dict):
        return None
    oldest = now - KEEP_FOR
    written = _moment(raw.get("noted"))
    if written is None or written < oldest:
        return None
    return {
        remote: seen
        for remote, seen in raw["remotes"].items()
        if (moment := _moment(seen)) is not None and moment >= oldest
    }


def _moment(value: object) -> datetime.datetime | None:
    try:
        moment = datetime.datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None
    return moment if moment is not None and moment.tzinfo is not None else None


def _note_path(notes: Path, folder: str) -> Path:
    # A folder's path does not fit a file name; its hash does, and the note names the folder itself.
    return notes / f"{hashlib.sha256(folder.encode('utf-8', 'surrogatepass')).hexdigest()[:32]}.json"


def forget_old_notes(notes: Path, now: datetime.datetime) -> None:
    """Removes the notes nobody renewed for ``KEEP_FOR`` whose folder is not there any more.

    A note whose folder is there stays, however old: it still says where that repository lies on
    this machine. For leaving work out it says nothing after ``KEEP_FOR`` all the same (``noted``).
    """
    oldest = (now - KEEP_FOR).timestamp()
    for path in notes.glob("*.json"):
        with contextlib.suppress(OSError):
            if path.stat().st_mtime >= oldest or _folder_is_there(path):
                continue
            path.unlink()


def _folder_is_there(path: Path) -> bool:
    try:
        folder = json.loads(path.read_text(encoding="utf-8")).get("folder")
    except (OSError, ValueError, AttributeError):
        return False
    return isinstance(folder, str) and Path(folder).is_dir()


class ByRemote(enum.Enum):
    """What the remotes of a folder's repository say about the work in it."""

    LEFT_OUT = "left out"
    NOT_NAMED = "not named"
    # Nothing noted and nothing git says now: not shown to be other work than the one left out.
    UNKNOWN = "unknown"


@dataclass
class RemoteRule:
    """The parts of remote URLs by which the owner leaves work out, and what is known of each folder asked about."""

    parts: tuple[str, ...]
    notes: Path
    now: datetime.datetime
    # What git says in a folder now; asked once per folder.
    ask: Callable[[Path], frozenset[str] | None] = remotes_in
    _judged: dict[str | None, ByRemote] = field(default_factory=dict)

    @property
    def names_any(self) -> bool:
        return bool(self.parts)

    def judge(self, folder: str | None) -> ByRemote:
        """Whether the work in ``folder`` is left out; nothing is looked up while no remote is named."""
        if not self.names_any:
            return ByRemote.NOT_NAMED
        if folder not in self._judged:
            self._judged[folder] = self._judge(folder)
        return self._judged[folder]

    def _judge(self, folder: str | None) -> ByRemote:
        if folder is None or not Path(folder).is_absolute():
            return ByRemote.UNKNOWN
        written_down = noted(self.notes, folder, self.now)
        if written_down is not None and names_one(self.parts, written_down):
            return ByRemote.LEFT_OUT
        said_now = self.ask(Path(folder))
        if written_down is None and said_now is None:
            return ByRemote.UNKNOWN
        return ByRemote.LEFT_OUT if names_one(self.parts, said_now or ()) else ByRemote.NOT_NAMED
