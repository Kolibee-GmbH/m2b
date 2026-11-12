"""One git commit per curation run, when the store folder is the top of a git work tree.

A run changes the store by itself. Whoever keeps the store in a git repository gets each run as
one commit, which ``git revert`` takes back. m2b makes no repository, changes no git configuration
and never pushes: without a ``.git`` in the store folder, or without git on the machine, nothing
here runs and nothing is said.

The commit holds what changed in the store while the run ran. A run has no list of its own writes,
because model steps and child processes write too, so the store is listed with each file's size
and modification time before the run's first write and again after its last one, without opening
a file, and the paths that differ go to git by name. A capture taken in those minutes is in the
commit as well; whatever else lies uncommitted in the work tree is not. Hidden files are not
content (``store.base``) and never go in.

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
"""

from __future__ import annotations

import datetime
import os
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from m2b.git_program import usable_git
from m2b.run_record import FAILED, SKIPPED, SUCCEEDED, StepResult
from m2b.store.base import Store, fetch_command

GIT_FOLDER = ".git"
IDENTITY_NAME = "m2b"
IDENTITY_EMAIL = "m2b@localhost"
GIT_TIMEOUT_SECONDS = 60.0
# What git reads from the work tree to decide how, and whether, a path goes in.
RULE_FILES = (".gitignore", ".gitattributes")
# Variables that would point git at another repository, index or work tree than the store's.
REDIRECTING_VARIABLES = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_PREFIX",
)
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

Runner = Callable[..., Any]


class CommitError(Exception):
    """The run could not be committed; the text says why."""


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

    def call(
        self,
        arguments: Sequence[str],
        index: Path | None = None,
        paths: Sequence[str] | None = None,
        allowed: Collection[int] = (0,),
    ) -> tuple[int, str]:
        """Runs one git command in the store folder; its exit code and what it printed.

        ``index`` is the temporary index to work on, ``paths`` go to standard input, each ended by
        a NUL. An exit code outside ``allowed``, a timeout or a git that cannot start raises.
        """
        command = [
            self.git,
            "-C",
            str(self.store.root),
            "-c",
            f"core.hooksPath={os.devnull}",
            "-c",
            "core.fsmonitor=false",
            *arguments,
        ]
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
) -> Repository | None:
    """The repository to commit a run into; None without a ``.git`` in the store folder and
    without a git to start, which are the two cases in which nothing is done. A ``.git`` whose work
    tree turns out to be another folder is found here and fails the commit, which says so."""
    if not holds_git_folder(store):
        return None
    git = usable_git(environ, platform, run, GIT_TIMEOUT_SECONDS)
    if git is None:
        return None
    return Repository(store, git, _git_environment(environ), pass_fds, run)


def _git_environment(environ: Mapping[str, str]) -> dict[str, str]:
    kept = {name: value for name, value in environ.items() if name not in REDIRECTING_VARIABLES}
    return {
        **kept,
        "GIT_AUTHOR_NAME": IDENTITY_NAME,
        "GIT_AUTHOR_EMAIL": IDENTITY_EMAIL,
        "GIT_COMMITTER_NAME": IDENTITY_NAME,
        "GIT_COMMITTER_EMAIL": IDENTITY_EMAIL,
        "GIT_TERMINAL_PROMPT": "0",
    }


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


def message(started: datetime.datetime, steps: Sequence[StepResult]) -> Message:
    """The commit message of a run: when it started, and how each of its steps ended, by name."""
    lines = []
    for result in (SUCCEEDED, FAILED, SKIPPED):
        names = [step.name for step in steps if step.result == result]
        if names:
            lines.append(f"{result}: {', '.join(names)}")
    return Message(f"m2b: curation run {started.astimezone():%Y-%m-%d %H:%M}", "\n".join(lines))


def commit(
    repository: Repository,
    before: StoreListing,
    text: Message,
    temp_dir: Path,
    no_reason_alone: Collection[str] = (),
) -> str | None:
    """Commits what changed in the store since ``before``; the commit's id, or None without one.

    No commit is made when nothing changed, when every changed path is one git ignores, and when
    only paths of ``no_reason_alone`` changed: the run record changes with every run, and a run
    that did nothing else is not worth a commit. With another change they go in like any path.
    Changed means other bytes: a file written again as it was is no change, whatever its time says.
    """
    store = repository.store
    after = listing(store)
    changed = sorted(
        path
        for path in before.files.keys() | after.files.keys()
        if before.files.get(path) != after.files.get(path) and not _only_downloaded(path, before, after)
    )
    written = [path for path in changed if path in after.files and not store.is_evicted(path)]
    removed = [path for path in changed if path not in after.files and not os.path.lexists(store.path(path))]
    if set(written + removed) <= set(no_reason_alone):
        return None
    _refuse_evicted_rule_files(store, written)
    _refuse_unfinished_operation(git_directory(repository))
    _, found = repository.call(["rev-parse", "--verify", "--quiet", "HEAD^{commit}"], allowed=(0, 1))
    head = found.strip() or None
    temp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="commit-", dir=temp_dir) as work:
        index = Path(work) / "index"
        if head is not None:
            repository.call(["read-tree", head], index)
        paths = [*_not_ignored(repository, index, written), *removed]
        repository.call(UPDATE_INDEX, index, [path for path in paths if path not in no_reason_alone])
        if _written_tree(repository, index) == _tree_without_the_run(repository, head):
            return None
        repository.call(UPDATE_INDEX, index, paths)
        tree = _written_tree(repository, index)
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
        raise CommitError(
            f"the run is committed as {new[:SHOWN_ID_LENGTH]}, but the repository's index was not brought "
            f"up to date, so git status shows the files of the run as changed: {error}"
        ) from error
    return new


def git_directory(repository: Repository) -> Path:
    """The repository's git directory, for a store folder that is the top of its work tree; a
    ``CommitError`` says why there is none to commit into."""
    if repository.store.is_evicted(GIT_FOLDER):
        raise CommitError(f"{GIT_FOLDER} is not downloaded to this machine; run: {fetch_command(GIT_FOLDER)}")
    answer = repository.call(["rev-parse", "--absolute-git-dir", "--show-toplevel"])[1].splitlines()
    if len(answer) != 2 or Path(answer[1]).resolve() != repository.store.root.resolve():
        raise CommitError("the store folder is not the top of the repository's work tree")
    return Path(answer[0])


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


def _written_tree(repository: Repository, index: Path) -> str:
    return repository.call(["write-tree"], index)[1].strip()


def _tree_without_the_run(repository: Repository, head: str | None) -> str:
    """The tree a commit would repeat: HEAD's, or the empty tree on a branch without a commit."""
    if head is None:
        return repository.call(["mktree"])[1].strip()
    return repository.call(["rev-parse", f"{head}^{{tree}}"])[1].strip()
