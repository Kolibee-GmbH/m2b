"""Which checks a change needs: ``scripts/ci-scope BASE HEAD`` prints ``release`` or ``full``.

A release pull request changes the version, the changelog and the eval page, and a pin pull request
the marketplace; the code they release was proved by the pull requests before them and by the run
on ``main`` after each merge. For such a change CI runs ``scripts/check --release``, which checks
what these files can break, instead of the whole proof a third and fourth time. Anything else, and
anything this cannot tell for sure (an unknown base, a file added or removed, a manifest change
beyond its version, a git error), is ``full``.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from repo_tools import REPO_ROOT

RELEASE, FULL = "release", "full"
MANIFEST = "plugins/m2b/.claude-plugin/plugin.json"
# The files a release or a pin changes, besides the manifest's version.
RELEASE_FILES = frozenset({"CHANGELOG.md", "docs/evals.md", ".claude-plugin/marketplace.json"})
VERSION_LINE = re.compile(r'^[+-]\s*"version": "[^"]*",?$')
NO_COMMIT = re.compile(r"\A0*\Z")


class ScopeError(Exception):
    """Git could not say what changed."""


def scope(base: str, head: str, repository: Path = REPO_ROOT) -> str:
    return _scope_and_reason(base, head, repository)[0]


def _scope_and_reason(base: str, head: str, repository: Path) -> tuple[str, str]:
    if NO_COMMIT.match(base):
        return FULL, "no base commit to compare with"
    try:
        changes = _git(repository, "diff", "--name-status", "--no-renames", base, head).splitlines()
    except ScopeError as error:
        return FULL, str(error)
    if not changes:
        return FULL, "nothing changed"
    for change in changes:
        status, _, path = change.partition("\t")
        if status != "M":
            return FULL, f"{path} is added or removed"
        if path == MANIFEST:
            if not _only_the_version_changed(repository, base, head):
                return FULL, f"{MANIFEST} changes more than its version"
        elif path not in RELEASE_FILES:
            return FULL, f"{path} is not a file of a release or a pin"
    return RELEASE, "only " + ", ".join(sorted(change.partition("\t")[2] for change in changes))


def _only_the_version_changed(repository: Path, base: str, head: str) -> bool:
    try:
        diff = _git(repository, "diff", "--unified=0", base, head, "--", MANIFEST)
    except ScopeError:
        return False
    changed = [line for line in diff.splitlines() if line[:1] in "+-" and not line.startswith(("+++", "---"))]
    return bool(changed) and all(VERSION_LINE.match(line) for line in changed)


def _git(repository: Path, *arguments: str) -> str:
    try:
        done = subprocess.run(["git", *arguments], cwd=repository, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ScopeError(f"git could not run: {error}") from error
    if done.returncode != 0:
        raise ScopeError(f"git {arguments[0]} failed: {done.stderr.strip()[:200]}")
    return done.stdout


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ci-scope", description=__doc__.split("\n", 1)[0])
    parser.add_argument("base", help="the commit the change starts from")
    parser.add_argument("head", help="the commit the change ends at")
    parser.add_argument("--repository", type=Path, default=REPO_ROOT, help=argparse.SUPPRESS)
    arguments = parser.parse_args(sys.argv[1:] if argv is None else argv)
    found, reason = _scope_and_reason(arguments.base, arguments.head, arguments.repository)
    print(f"ci-scope: {found}: {reason}", file=sys.stderr)
    print(found)
    return 0


if __name__ == "__main__":
    sys.exit(main())
