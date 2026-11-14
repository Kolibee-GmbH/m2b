"""One git commit per curation run, when the store folder is the top of a git work tree.

A run changes the store by itself. Whoever keeps the store in a git repository gets each run as
one commit, which ``git revert`` takes back. m2b makes no repository, changes no git configuration
and never pushes: without a ``.git`` in the store folder, or without git on the machine, nothing
here runs and nothing is said.

A capture that came in after the last commit is a file git does not know. Filed by the run, it
would be in the run's commit only as a new file of the archive, and a revert would delete it
instead of putting it back into the inbox. So the captures git does not know are committed where
they wait, in a commit of their own before the run's first step (``commit_waiting_captures``):
the files of the inbox that are neither in the index nor in HEAD, and nothing else. A capture git
knows is left as it is, changed or not, like everything the owner has not committed. Only a
capture the run's listing holds goes in, because the run's commit takes a path out of the inbox
by that listing: one that came in later would stay in the repository's inbox after it was filed.

The commit holds what changed in the store while the run ran. A run has no list of its own writes,
because model steps and child processes write too, so the store is listed with each file's size
and modification time before the run's first write and again after its last one, without opening
a file, and the paths that differ go to git by name. Whatever else lies uncommitted in the work
tree is not in the commit. Hidden files are not content (``store.base``) and never go in.

One change stays out: a capture that was not in the inbox when the run began and still lies there
when it ends. It was taken or synced in during those minutes, and no step filed it. In the run's
commit it would be a new file, which a revert deletes: from the store folder, and through a sync
service from every device. A capture the run wrote itself and left in the inbox, a kept candidate
that was not filed for one, cannot be told from it and is left out with it; harvest and the
worklog know their own captures again, so nothing is written twice. Either waits where it is, a
file git does not know, and the next run commits it before its first step.

A new file of the inbox that belongs to a capture from before the run is no such capture, and it
goes in: left out, a revert would put ``memory/`` back and leave that capture as the run changed
it. Normalize makes such files in two ways. It puts a sidecar and a reading copy beside a file,
which share that file's schema name up to the extension. And it gives a capture whose name is
outside the schema a new one; without the new name the commit would hold the removal of the old
one alone, and HEAD no copy of the capture until the next run. The first listing cannot show that
a new name is an old capture, so the caller names the files that took another's place, each with
the name the other had (``carried_on``), and one counts when a file of that name was in the inbox
before the run and is gone after it. A name that more new captures claim than files of it left
the inbox ties none of them: in doubt a file stays out, where nothing can delete it.

git never looks at the work tree as a whole. ``git commit`` and ``git add -A`` stat every tracked
file and read each one whose stat changed, which for a file a sync service has evicted means a
download or a hang, and they take along what the owner staged. The commit is built from plumbing
instead: HEAD's tree into a temporary index outside the store, ``update-index`` for the named
paths alone, ``write-tree``, ``commit-tree``, and ``update-ref`` with the old value, so a HEAD that
moved in between fails the commit instead of losing the owner's. Each path is checked to be
downloaded just before git gets it, and so are the ``.gitignore`` and ``.gitattributes`` files git
reads on the way to it. A changed file that is evicted is left out: a run's own writes are on this
machine, so it is not one of them. An evicted ignore or attributes file stops the commit, because
without it git would commit what was meant to be left out or filtered. On macOS git is the child of
a process that turned the download of placeholder files off (``store.guard``), so a read nobody
foresaw, in the repository's own files for example, fails at once as well.

The commit is m2b's, not the owner's: author and committer come from the environment, so no
identity has to be configured, ``git log --author=m2b`` lists the runs, and whatever counts the
owner's commits does not count these. No hook runs and nothing is signed, because a run has nobody
to answer a prompt. The filters the repository configures for adding a file (encryption, line
endings) do run, for the named files, as they do when the owner adds one.

Which repository that is must not be for the store to say. The ``.git`` of a store kept in a
synced folder is best a file of one line that names a git directory outside the folder, and
whoever writes the store can write that line: pointed at another repository of the owner, a run
would commit the notes there, and pointed at a folder made for it, git would run what that
folder's configuration names. So the line is read here, not by git, and it is followed only to
the directory this machine's config names (``curation.git_directory``). git is then given that
directory by name with every call and never reads the line itself, so a line rewritten between two
calls changes nothing. A ``.git`` that is a folder is the store's own repository and needs no
naming. Everything in it lies in the store, its configuration and whatever it says about where its
objects and branches are kept, and is as trusted as the owner's own: naming a directory does nothing for such a
store, keeping it where only the owner writes does.

Nothing a run starts reaches a remote (``git_program``), and a repository that is a partial clone
is not committed into: git would fetch the objects it lacks as soon as it needed one.
"""

from __future__ import annotations

import datetime
import os
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
from collections import Counter
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from m2b import git_program
from m2b.notes.layout import INBOX, bundle_stem
from m2b.notes.names import NoteName
from m2b.run_record import FAILED, SKIPPED, SUCCEEDED, StepResult
from m2b.store.base import Store, fetch_command

GIT_FOLDER = ".git"
IDENTITY_NAME = "m2b"
IDENTITY_EMAIL = "m2b@localhost"
GIT_TIMEOUT_SECONDS = 60.0
# What git reads from the work tree to decide how, and whether, a path goes in.
RULE_FILES = (".gitignore", ".gitattributes")
# How the ``.git`` file of a work tree names the git directory kept elsewhere.
GITFILE_PREFIX = b"gitdir: "
# More than any path is long.
GITFILE_MAX_BYTES = 8192
SHOWN_PATH_LENGTH = 200
# Unicode categories of the characters a shown path must not carry: controls, halves of a
# surrogate pair, and the separators of lines and paragraphs.
NOT_SHOWN = ("Cc", "Cs", "Zl", "Zp")
NAMING_KEY = "curation.git_directory"
THROUGH_THE_STORE = "lies in the store folder or is reached through it"
OPEN_TO_EVERY_WRITER = "where everything that writes the store can write the repository's configuration"
# What a system follows before it gives a path up as a loop.
MAX_LINKS_FOLLOWED = 40
# What marks a repository that lacks objects by design and fetches each when it is needed.
PARTIAL_CLONE_KEYS = r"^(extensions\.partialclone|remote\..*\.(promisor|partialclonefilter))$"
# What an operation the owner has not finished leaves in the git directory; a commit onto HEAD
# in the middle of one would become part of it.
UNFINISHED_OPERATIONS = {
    "MERGE_HEAD": "merge",
    "CHERRY_PICK_HEAD": "cherry-pick",
    "REVERT_HEAD": "revert",
    "BISECT_LOG": "bisect",
    "rebase-merge": "rebase",
    "rebase-apply": "rebase",
}
SHOWN_ID_LENGTH = 12
# ``--replace``: a file where a folder was, or a folder where a file was, takes the old entry's place.
UPDATE_INDEX = ("update-index", "-z", "--add", "--remove", "--replace", "--stdin")
# For paths that must be new to the index: without ``--replace`` a path that would take a tracked
# file's or folder's place stops the command instead of taking the tracked entry out.
ADD_TO_INDEX = ("update-index", "-z", "--add", "--remove", "--stdin")

Runner = Callable[..., Any]


class CommitError(Exception):
    """The run could not be committed; the text says why."""


class StaleIndexError(CommitError):
    """The commit is made, but the owner's index was not brought up to date for its paths."""


@dataclass(frozen=True)
class StoreListing:
    """The store's visible files at one moment, each with its size and modification time."""

    files: Mapping[str, tuple[int, int]] = field(default_factory=dict)
    # Folders that were only placeholders then, so what they hold could not be listed.
    unlisted_folders: tuple[str, ...] = ()
    taken_at_ns: int = 0


@dataclass(frozen=True)
class Message:
    subject: str
    body: str


@dataclass(frozen=True)
class Repository:
    """The git repository whose work tree the store folder is, and how git is started in it."""

    store: Store
    git: str
    environ: Mapping[str, str]
    pass_fds: Sequence[int] = ()
    run: Runner = subprocess.run
    # The git directory this machine's config names for the store; None when it names none.
    named_directory: Path | None = None

    def call(
        self,
        arguments: Sequence[str],
        index: Path | None = None,
        paths: Sequence[str] | None = None,
        allowed: Collection[int] = (0,),
    ) -> tuple[int, str]:
        """Runs one git command in the store folder; its exit code and what it printed.

        ``index`` is the temporary index to work on, ``paths`` go to standard input, each ended by
        a NUL. An exit code outside ``allowed``, a timeout or a git that cannot start raises, and
        so does a ``.git`` that leads where a run must not commit: no git is started then.
        """
        kept_elsewhere = directory_kept_elsewhere(self.store, self.named_directory)
        command = git_program.git_command(self.git, self.store.root, arguments, git_directory=kept_elsewhere)
        environ = dict(self.environ)
        if index is not None:
            environ["GIT_INDEX_FILE"] = str(index)
        try:
            result = self.run(
                command,
                input=b"".join(os.fsencode(path) + b"\0" for path in paths or ()),
                capture_output=True,
                env=environ,
                timeout=GIT_TIMEOUT_SECONDS,
                pass_fds=tuple(self.pass_fds),
            )
        except subprocess.TimeoutExpired as error:
            raise CommitError(f"git {arguments[0]} did not answer within {GIT_TIMEOUT_SECONDS:g} seconds") from error
        except OSError as error:
            raise CommitError(f"git could not be run: {error}") from error
        if result.returncode not in allowed:
            reason = os.fsdecode(result.stderr).strip().splitlines()[:1]
            raise CommitError(f"git {arguments[0]} failed" + (f": {reason[0]}" if reason else ""))
        return result.returncode, os.fsdecode(result.stdout)


def holds_git_folder(store: Store) -> bool:
    """Whether the store folder holds a ``.git``: a folder, or the file a git directory kept elsewhere
    leaves in its place."""
    return os.path.lexists(store.root / GIT_FOLDER)


def find_repository(
    store: Store,
    environ: Mapping[str, str],
    pass_fds: Sequence[int] = (),
    platform: str = sys.platform,
    run: Runner = subprocess.run,
    named_directory: Path | None = None,
) -> Repository | None:
    """The repository to commit a run into; None without a ``.git`` in the store folder and
    without a git to start, which are the two cases in which nothing is done. ``named_directory``
    is the git directory the machine config names. A ``.git`` that leads to another one, or whose
    work tree turns out to be another folder, is found here and fails the commit, which says so."""
    if not holds_git_folder(store):
        return None
    git = git_program.usable_git(environ, platform, run, GIT_TIMEOUT_SECONDS)
    if git is None:
        return None
    return Repository(store, git, _git_environment(environ), pass_fds, run, named_directory)


def _git_environment(environ: Mapping[str, str]) -> dict[str, str]:
    return {
        **git_program.git_environment(environ),
        "GIT_AUTHOR_NAME": IDENTITY_NAME,
        "GIT_AUTHOR_EMAIL": IDENTITY_EMAIL,
        "GIT_COMMITTER_NAME": IDENTITY_NAME,
        "GIT_COMMITTER_EMAIL": IDENTITY_EMAIL,
    }


def directory_kept_elsewhere(store: Store, named: Path | None) -> Path | None:
    """The git directory the store folder's ``.git`` file points at, when a run may commit into it;
    None when ``.git`` is a folder, the git directory itself, which git finds without being told.

    Read without starting git. A ``CommitError`` says why a run must not commit: the file points
    at another directory than ``named``, the one the machine config names, the config names none,
    or it names one that lies in the store folder or is reached through it, which would be as open
    to every writer of the store as the file is.
    """
    if store.is_evicted(GIT_FOLDER):
        raise CommitError(f"{GIT_FOLDER} is not downloaded to this machine; run: {fetch_command(GIT_FOLDER)}")
    own = store.root / GIT_FOLDER
    pointed_at = _pointed_at(store)
    if named is None:
        if pointed_at is None:
            return None
        if _leads_through_store(store, pointed_at):
            raise CommitError(
                f"{GIT_FOLDER} in the store folder points at {_shown(pointed_at)}, which {THROUGH_THE_STORE}, "
                f"{OPEN_TO_EVERY_WRITER}; a run commits into the store's own {GIT_FOLDER} folder or into a "
                f"directory outside the store folder that {NAMING_KEY} names"
            )
        raise CommitError(
            f"{GIT_FOLDER} in the store folder points at {_shown(pointed_at)}, and this machine's config names "
            f"no git directory to commit into; when that is the repository you keep the store in, name it with "
            f"m2b config set {NAMING_KEY} and its path"
        )
    if not named.is_dir():
        missing = "is not there" if not os.path.lexists(named) else "is not a directory"
        raise CommitError(f"{named}, the git directory this machine's config names ({NAMING_KEY}), {missing}")
    if _leads_through_store(store, named) and not _same_folder(named, own):
        raise CommitError(
            f"{named}, the git directory this machine's config names ({NAMING_KEY}), {THROUGH_THE_STORE}, "
            f"{OPEN_TO_EVERY_WRITER}; name a directory outside the store folder, by a path with no link in the "
            "store on its way"
        )
    found = own if pointed_at is None else pointed_at
    if not _same_folder(found, named):
        raise CommitError(
            f"{GIT_FOLDER} in the store folder leads to {_shown(found)}, not to {named}, the git directory "
            f"this machine's config names ({NAMING_KEY})"
        )
    return None if pointed_at is None else named


def _pointed_at(store: Store) -> Path | None:
    """Where the store folder's ``.git`` file points, as git reads such a file; None for a ``.git`` folder."""
    entry = store.root / GIT_FOLDER
    if entry.is_symlink():
        raise CommitError(f"{GIT_FOLDER} in the store folder is a symbolic link, and m2b follows none below the store")
    if entry.is_dir():
        return None
    try:
        # Not followed either when a link took the file's place since the look above, and not
        # waited for when the name is a pipe, which nobody may ever write to.
        descriptor = os.open(entry, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as file:
            content = file.read(GITFILE_MAX_BYTES + 1) if stat.S_ISREG(os.fstat(descriptor).st_mode) else b""
    except OSError as error:
        raise CommitError(f"{GIT_FOLDER} in the store folder could not be read: {error}") from error
    if not content.startswith(GITFILE_PREFIX) or len(content) > GITFILE_MAX_BYTES or b"\0" in content:
        raise CommitError(f"{GIT_FOLDER} in the store folder is neither a git directory nor a file that names one")
    written = os.fsdecode(content[len(GITFILE_PREFIX) :].rstrip(b"\r\n"))
    # A path that does not start at the root of the file system starts at the store folder.
    return store.root / written


def _leads_through_store(store: Store, path: Path) -> bool:
    """Whether the way to the path leads through the store folder, or ends at the store folder itself.

    The way is walked as the system walks it, a name at a time and each link followed, and it leads
    through the store when a folder or a link on it lies in the store folder. Whoever writes the
    store writes what lies in it, so such a way leads wherever they point it next: a link in the
    store to a directory outside is no directory outside. Where the way ends says too little, and
    so does the path as it is written, which a link outside the store can hide the store behind.
    A step back up out of the store folder itself (``<store>/../history.git``) leads through
    nothing in it. A folder is told by itself, so another letter case or Unicode form of a name is
    the same folder. A way with more links than a system follows leads nowhere, and a
    ``CommitError`` says so.
    """
    reached = Path(path.anchor)
    names = list(path.parts[1:])
    links_followed = 0
    while names:
        name = names.pop(0)
        if name == "..":
            reached = reached.parent
            continue
        step = reached / name
        # ``reached`` holds no link, so the folders above the step are the ones it really lies in.
        if any(_same_folder(folder, store.root) for folder in step.parents):
            return True
        try:
            target = Path(os.readlink(step)) if step.is_symlink() else None
        except OSError:
            target = None
        if target is None:
            reached = step
            continue
        links_followed += 1
        if links_followed > MAX_LINKS_FOLLOWED:
            raise CommitError(
                f"the way to {_shown(path)} follows more than {MAX_LINKS_FOLLOWED} links, so it leads to no "
                "git directory"
            )
        if target.is_absolute():
            reached, names = Path(target.anchor), [*target.parts[1:], *names]
        else:
            names = [*target.parts, *names]
    return _same_folder(reached, store.root)


def _same_folder(one: Path, other: Path) -> bool:
    try:
        return os.path.samefile(one, other)
    except OSError:
        return False


def _shown(path: Path) -> str:
    """A path from the ``.git`` file as it goes into a reason: in one line and of a bounded length.

    The reason is printed by ``m2b doctor`` and written into the review task, and whoever writes
    the store wrote this path: a line break in it would start a line of its own there, and an
    escape sequence would reach the terminal. git writes a ``?`` for such a character too. A byte
    that is no text comes out of the file as half a surrogate pair, which no output can encode.
    """
    text = "".join("?" if unicodedata.category(character) in NOT_SHOWN else character for character in str(path))
    return text if len(text) <= SHOWN_PATH_LENGTH else f"{text[:SHOWN_PATH_LENGTH]}..."


def listing(store: Store) -> StoreListing:
    """Every visible file of the store with its size and modification time; no file is opened.

    An evicted file is listed by its placeholder, which carries the file's size and time, so a
    download during the run is no change. What an evicted folder holds cannot be listed without
    downloading it; the folder is remembered, so that its files are not taken for new ones once
    the run has downloaded it (``_only_downloaded``).
    """
    taken_at_ns = time.time_ns()
    scan = store.scan("")
    files = {}
    folders = []
    for relative in (*scan.files, *scan.evicted):
        try:
            info = os.lstat(store.path(relative))
        except OSError:
            continue
        if stat.S_ISDIR(info.st_mode):
            folders.append(relative)
        else:
            files[relative] = (info.st_size, info.st_mtime_ns)
    return StoreListing(files, tuple(folders), taken_at_ns)


def _only_downloaded(path: str, before: StoreListing, after: StoreListing) -> bool:
    """Whether a file is new to the listing only because the run downloaded its folder: it lies
    below a folder that was evicted before the run and was last written before the run began. A
    download keeps a file's modification time."""
    if path in before.files or path not in after.files:
        return False
    below = any(path.startswith(f"{folder}/") for folder in before.unlisted_folders)
    return below and after.files[path][1] < before.taken_at_ns


def _came_in_and_wait(before: StoreListing, after: StoreListing, carried_on: Mapping[str, str]) -> set[str]:
    """The files of the inbox that belong to no capture that was there when the run began: the
    next run commits them where they wait (``commit_waiting_captures``).

    A new file belongs to a capture from before the run when it has that capture's schema name up
    to the extension, as the sidecar and the reading copy beside a file have, or when
    ``carried_on`` holds for it the name of a file the run took out of the inbox, in whatever
    folder below it that file lay. A name outside the schema ties nothing: two files a person
    named alike are two captures.
    """
    was_there = [path for path in before.files if _in_inbox(path)]
    bundles = {bundle_stem(path) for path in was_there}
    came_in = {path for path in after.files if _in_inbox(path) and path not in before.files}
    beside = {path for path in came_in if _has_schema_name(path) and bundle_stem(path) in bundles}
    taken_out = [path for path in was_there if path not in after.files]
    return came_in - beside - _renamed(came_in, taken_out, carried_on)


def _renamed(came_in: Collection[str], taken_out: Sequence[str], carried_on: Mapping[str, str]) -> set[str]:
    """The new files that are a capture the run took out of the inbox, under a new name.

    The old name is all there is to go by, read as the trailer holds it, without space around it.
    Two captures of one name cannot be told apart by it, so when more new captures claim a name
    than files of that name left the inbox, none of them counts: one that stays out by mistake
    waits for the next run's commit, one that went in by mistake would be deleted by a revert.
    The files of one capture share their name up to the extension and claim once.
    """
    left = Counter(PurePosixPath(path).name.strip() for path in taken_out)
    claims: dict[str, set[str]] = {}
    for path in came_in:
        if path in carried_on:
            claims.setdefault(carried_on[path], set()).add(bundle_stem(path))
    return {path for path in came_in if path in carried_on and len(claims[carried_on[path]]) <= left[carried_on[path]]}


def _in_inbox(path: str) -> bool:
    return path.startswith(f"{INBOX}/")


def _has_schema_name(path: str) -> bool:
    return NoteName.parse(PurePosixPath(path).name) is not None


def message(started: datetime.datetime, steps: Sequence[StepResult]) -> Message:
    """The commit message of a run: when it started, and how each of its steps ended, by name."""
    lines = []
    for result in (SUCCEEDED, FAILED, SKIPPED):
        names = [step.name for step in steps if step.result == result]
        if names:
            lines.append(f"{result}: {', '.join(names)}")
    return Message(f"m2b: curation run {_minute(started)}", "\n".join(lines))


def captures_message(started: datetime.datetime) -> Message:
    """The message of the commit before a run, which names the run by its start as the run's own does."""
    return Message(f"m2b: captures before the curation run {_minute(started)}", "")


def _minute(moment: datetime.datetime) -> str:
    return f"{moment.astimezone():%Y-%m-%d %H:%M}"


def commit(
    repository: Repository,
    before: StoreListing,
    text: Message,
    temp_dir: Path,
    no_reason_alone: Collection[str] = (),
    carried_on: Mapping[str, str] | None = None,
) -> str | None:
    """Commits what changed in the store since ``before``; the commit's id, or None without one.

    No commit is made when nothing changed, when every changed path is one git ignores, and when
    only paths of ``no_reason_alone`` changed: the run record changes with every run, and a run
    that did nothing else is not worth a commit. With another change they go in like any path.
    Changed means other bytes: a file written again as it was is no change, whatever its time says.
    A capture that came into the inbox since ``before`` and still lies there is no change of the
    run. ``carried_on`` holds, for a file that took another's place, the name the other had
    (``ingest.carried_on``): a capture from before the run under a new name is a change.
    """
    store = repository.store
    after = listing(store)
    waiting = _came_in_and_wait(before, after, carried_on or {})
    changed = sorted(
        path
        for path in before.files.keys() | after.files.keys()
        if before.files.get(path) != after.files.get(path)
        and not _only_downloaded(path, before, after)
        and path not in waiting
    )
    written = [path for path in changed if path in after.files and not store.is_evicted(path)]
    removed = [path for path in changed if path not in after.files and not os.path.lexists(store.path(path))]
    if set(written + removed) <= set(no_reason_alone):
        return None
    _refuse_evicted_rule_files(store, written)
    _refuse_unfinished_operation(git_directory(repository))
    with _index_of_head(repository, temp_dir) as (head, index):
        paths = [*_not_ignored(repository, index, written), *removed]
        repository.call(UPDATE_INDEX, index, [path for path in paths if path not in no_reason_alone])
        if _written_tree(repository, index) == _tree_without_the_run(repository, head):
            return None
        repository.call(UPDATE_INDEX, index, paths)
        tree = _written_tree(repository, index)
    return _commit_onto(repository, head, tree, paths, text, "the run is", "the files of the run")


def commit_waiting_captures(repository: Repository, before: StoreListing, text: Message, temp_dir: Path) -> str | None:
    """Commits the captures in the inbox that git does not know; the commit's id, or None without one.

    Those are the files below ``inbox/`` that ``before``, the run's listing, holds and that are on
    this machine, not hidden, not ignored, and neither in the owner's index nor in HEAD. A file in
    one of the two is the owner's to commit: staged, changed since its commit, or taken out of the
    index, it stays as it is. Without such a capture nothing is committed, and an unfinished merge
    of the owner's is no failure then. The listing leaves out what lies behind a link to a folder,
    so an inbox that is such a link has no capture to commit here.
    """
    store = repository.store
    waiting = [path for path in store.scan(INBOX).files if path in before.files]
    if not waiting:
        return None
    directory = git_directory(repository)
    unstaged = _unknown_to(repository, None, waiting)
    if not unstaged:
        return None
    with _index_of_head(repository, temp_dir) as (head, index):
        unknown = _unknown_to(repository, index, unstaged)
        if not unknown:
            return None
        _refuse_evicted_rule_files(store, unknown)
        captures = _not_ignored(repository, index, unknown)
        if not captures:
            return None
        _refuse_unfinished_operation(directory)
        repository.call(ADD_TO_INDEX, index, captures)
        tree = _written_tree(repository, index)
        # A capture that was removed since the inbox was read leaves nothing to commit.
        if tree == _tree_without_the_run(repository, head):
            return None
    return _commit_onto(repository, head, tree, captures, text, "the captures are", "them")


@contextmanager
def _index_of_head(repository: Repository, temp_dir: Path) -> Iterator[tuple[str | None, Path]]:
    """HEAD's commit, None on a branch without one, and its tree in a temporary index outside the store."""
    _, found = repository.call(["rev-parse", "--verify", "--quiet", "HEAD^{commit}"], allowed=(0, 1))
    head = found.strip() or None
    temp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="commit-", dir=temp_dir) as work:
        index = Path(work) / "index"
        if head is not None:
            repository.call(["read-tree", head], index)
        yield head, index


def _commit_onto(
    repository: Repository,
    head: str | None,
    tree: str,
    paths: Sequence[str],
    text: Message,
    committed: str,
    shown_as_changed: str,
) -> str:
    """Makes ``tree`` the commit after ``head`` and brings the owner's index up to date for ``paths``.

    ``committed`` and ``shown_as_changed`` name the commit in the one failure that leaves it made.
    """
    parent = ["-p", head] if head is not None else []
    body = ["-m", text.body] if text.body else []
    # ``--no-gpg-sign``: a git before 2.22 signs in commit-tree when ``commit.gpgSign`` is set.
    new = repository.call(["commit-tree", tree, *parent, "--no-gpg-sign", "-m", text.subject, *body])[1].strip()
    # The old value, empty for a branch without a commit: a HEAD the owner moved meanwhile fails here.
    repository.call(["update-ref", "-m", text.subject, "HEAD", new, head or ""])
    try:
        # The owner's index still holds these paths as they were; only they are brought up to date.
        repository.call(UPDATE_INDEX, paths=paths)
    except CommitError as error:
        raise StaleIndexError(
            f"{committed} committed as {new[:SHOWN_ID_LENGTH]}, but the repository's index was not brought "
            f"up to date, so git status shows {shown_as_changed} as changed: {error}"
        ) from error
    return new


def git_directory(repository: Repository) -> Path:
    """The git directory a run commits into, for a store folder that is the top of its work tree; a
    ``CommitError`` says why there is none to commit into. Asked before anything reads an object."""
    answer = repository.call(["rev-parse", "--absolute-git-dir", "--show-toplevel"])[1].splitlines()
    if len(answer) != 2 or Path(answer[1]).resolve() != repository.store.root.resolve():
        raise CommitError("the store folder is not the top of the repository's work tree")
    _refuse_partial_clone(repository)
    return Path(answer[0])


def _refuse_partial_clone(repository: Repository) -> None:
    found, _ = repository.call(["config", "--get-regexp", PARTIAL_CLONE_KEYS], allowed=(0, 1))
    if found == 0:
        raise CommitError(
            "the repository is a partial clone, which fetches the objects it lacks from a remote when git "
            "needs one; m2b starts nothing that reaches a remote and commits nothing there"
        )


def _refuse_unfinished_operation(git_directory: Path) -> None:
    for name, operation in UNFINISHED_OPERATIONS.items():
        if (git_directory / name).exists():
            raise CommitError(f"the repository is in the middle of a {operation}")


def _refuse_evicted_rule_files(store: Store, paths: Sequence[str]) -> None:
    """Stops before git would read an ignore or attributes file that is only a placeholder."""
    folders = {parent.as_posix() for path in paths for parent in PurePosixPath(path).parents}
    for folder in sorted(folders):
        for name in RULE_FILES:
            rule_file = name if folder == "." else f"{folder}/{name}"
            if store.exists(rule_file) and store.is_evicted(rule_file):
                raise CommitError(
                    f"{rule_file} is not downloaded to this machine, and git reads it to know what to "
                    f"leave out or filter; run: {fetch_command(rule_file)}"
                )


def _not_ignored(repository: Repository, index: Path, paths: Sequence[str]) -> list[str]:
    """The paths git would take: a file the repository tracks stays, whatever an ignore rule says.

    ``check-ignore`` reads each path as a pathspec, so a file name that starts with ``:`` would be
    taken for pathspec magic and stop the command or be checked as another path. Behind ``./`` a
    name is only a name; ``update-index`` takes its paths literally and needs no such care.
    """
    if not paths:
        return []
    literal = [f"./{path}" for path in paths]
    code, printed = repository.call(["check-ignore", "-z", "--stdin"], index, literal, allowed=(0, 1))
    ignored = {found[2:] for found in printed.split("\0") if found} if code == 0 else set()
    return [path for path in paths if path not in ignored]


def _unknown_to(repository: Repository, index: Path | None, paths: Sequence[str]) -> list[str]:
    """The paths of the inbox an index knows nothing of: the temporary one, or the owner's for None.

    git reads the index alone for this and no file of the work tree. Names are compared in one
    Unicode form and without their letter case: a git that composes names keeps ``ü`` as one
    character where the folder may spell it as two, and a folder that ignores case shows a tracked
    ``Note.md`` as ``note.md`` once it is renamed. Both are files git knows, and so is a path where
    the index holds a folder, or below a file the index holds. Taking one name too many for known
    only leaves a capture out.
    """
    printed = repository.call(["ls-files", "-z", "--cached", "--", INBOX], index)[1]
    known = {_compared(path) for path in printed.split("\0") if path}
    known_folders = {folder for path in known for folder in _folders_above(path)}
    return [
        path
        for path in paths
        if _compared(path) not in known | known_folders and known.isdisjoint(_folders_above(_compared(path)))
    ]


def _compared(path: str) -> str:
    return unicodedata.normalize("NFC", path).casefold()


def _folders_above(path: str) -> set[str]:
    return {folder.as_posix() for folder in PurePosixPath(path).parents}


def _written_tree(repository: Repository, index: Path) -> str:
    return repository.call(["write-tree"], index)[1].strip()


def _tree_without_the_run(repository: Repository, head: str | None) -> str:
    """The tree a commit would repeat: HEAD's, or the empty tree on a branch without a commit."""
    if head is None:
        return repository.call(["mktree"])[1].strip()
    return repository.call(["rev-parse", f"{head}^{{tree}}"])[1].strip()
