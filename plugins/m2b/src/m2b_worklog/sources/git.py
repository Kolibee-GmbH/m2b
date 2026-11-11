"""Commits per working folder: only the owner's (the repository's ``user.email``), all branches, in the period.

The period is matched against each commit's author time here, not with ``git log --since``: git stops
walking at the first commit older than ``--since``, and a rebased or cherry-picked commit with an
older date on top would hide every commit below it.

A folder that is not a repository, a git that fails or does not answer, is "could not read" for
that session, never "no commits".
"""

from __future__ import annotations

import datetime
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from m2b.redaction import redact

from m2b_worklog.sources import SourceState

GIT_TIMEOUT_SECONDS = 10.0
_FIELD = "\x1f"

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


@dataclass(frozen=True)
class Commit:
    commit_hash: str
    time: datetime.datetime
    subject: str
    # On the branch this folder has checked out: which of two worktrees made it.
    on_head: bool = False


@dataclass(frozen=True)
class GitFacts:
    commits: list[Commit]
    remote: str | None
    state: SourceState


class _GitError(Exception):
    pass


def read_git(
    folder: Path, start: datetime.datetime, end: datetime.datetime, git: str = "git", run: Runner = subprocess.run
) -> GitFacts:
    try:
        email = _git(run, git, folder, ["config", "user.email"]).strip()
        if not email:
            return GitFacts([], None, SourceState.failed(f"git config user.email is empty in {folder}"))
        log = _git(
            run,
            git,
            folder,
            [
                "log",
                # Before --all, or it does not apply: a stash is no work.
                "--exclude=refs/stash",
                "--all",
                "--fixed-strings",
                f"--author=<{email}>",
                f"--format=%H{_FIELD}%aI{_FIELD}%s",
            ],
        )
        head = _git(run, git, folder, ["log", "HEAD", "--fixed-strings", f"--author=<{email}>", "--format=%H"])
        remote = _git(run, git, folder, ["config", "--get", "remote.origin.url"], allow_missing=True).strip() or None
    except _GitError as error:
        return GitFacts([], None, SourceState.failed(str(error)))
    commits = []
    on_head = set(head.split())
    # Not splitlines(): it also breaks at the field separator \x1f.
    for line in log.split("\n"):
        commit_hash, _, rest = line.partition(_FIELD)
        moment_text, _, subject = rest.partition(_FIELD)
        try:
            moment = datetime.datetime.fromisoformat(moment_text)
        except ValueError:
            continue
        if start <= moment < end:
            commits.append(Commit(commit_hash, moment, redact(subject.strip()), commit_hash in on_head))
    return GitFacts(sorted(commits, key=lambda commit: commit.time), remote, SourceState.read())


def _git(run: Runner, git: str, folder: Path, arguments: list[str], allow_missing: bool = False) -> str:
    try:
        result = run(
            [git, "-C", str(folder), *arguments],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError as error:
        raise _GitError(f"{git} was not found") from error
    except subprocess.TimeoutExpired as error:
        raise _GitError(f"git did not answer within {GIT_TIMEOUT_SECONDS:g} seconds in {folder}") from error
    except OSError as error:
        raise _GitError(f"git could not be run in {folder}: {error}") from error
    if result.returncode != 0 and not (allow_missing and result.returncode == 1):
        reason = result.stderr.strip().splitlines()[:1]
        raise _GitError(f"git {arguments[0]} failed in {folder}" + (f": {reason[0]}" if reason else ""))
    return result.stdout if result.returncode == 0 else ""
