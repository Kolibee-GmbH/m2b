"""How m2b starts git: a repository's configuration starts no program of its own, and nothing reaches a remote.

Each repository here names a command that writes a marker file, and is first shown to run it under
a git started plainly: a test that only saw no marker would pass with a fixture that never fetches
or never checks a signature.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
from collections.abc import Mapping, Sequence
from pathlib import Path

from m2b import git_program

GIT = shutil.which("git")
OWNER_EMAIL = "alex@example.com"
OWNER = ("-c", "user.name=Alex", "-c", f"user.email={OWNER_EMAIL}")
SIGNED_AT = 1_700_000_000
SIGNED_SUBJECT = "a commit that carries a signature"
# The first git that knows the switch against fetching what a partial clone lacks.
KNOWS_NO_LAZY_FETCH = (2, 45)


def without_the_machines_configuration(environ: Mapping[str, str]) -> dict[str, str]:
    """Neither the developer's nor the machine's git configuration reaches a test."""
    return {**environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


def git(environ: Mapping[str, str], folder: Path, *arguments: str, stdin: str | None = None) -> str:
    result = subprocess.run(
        ["git", *OWNER, *arguments], cwd=folder, env=dict(environ), input=stdin, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(arguments)} failed: {result.stderr}")
    return result.stdout


def git_version(environ: Mapping[str, str]) -> tuple[int, ...]:
    found = re.search(r"(\d+)\.(\d+)", git(environ, Path.cwd(), "--version"))
    assert found is not None
    return tuple(int(part) for part in found.groups())


def make_partial_clone(
    environ: Mapping[str, str], work: Path, clone: Path, marker: Path, allows_its_transport: bool = True
) -> str:
    """Makes ``clone`` a clone without its trees whose remote names a command for fetching; HEAD's commit.

    ``work`` holds what the clone is made from. With ``allows_its_transport`` the clone's own
    configuration allows the transport to its remote by name.
    """
    source = work / "source"
    source.mkdir(parents=True)
    git(environ, source, "init", "-q", "-b", "main")
    (source / "note.md").write_text("Dana likes old maps\n", encoding="utf-8")
    git(environ, source, "add", "note.md")
    git(environ, source, "commit", "-q", "-m", "the first note")
    origin = work / "origin.git"
    git(environ, work, "init", "-q", "--bare", str(origin))
    git(environ, source, "push", "-q", str(origin), "main")
    git(environ, origin, "config", "uploadpack.allowFilter", "true")
    git(environ, work, "clone", "-q", "--no-checkout", "--filter=tree:0", origin.as_uri(), str(clone))
    git(environ, clone, "config", "remote.origin.uploadpack", f"touch {shlex.quote(str(marker))}; git-upload-pack")
    if allows_its_transport:
        git(environ, clone, "config", "protocol.file.allow", "always")
    return git(environ, clone, "rev-parse", "HEAD").strip()


def make_repository_that_checks_signatures(environ: Mapping[str, str], folder: Path, marker: Path) -> None:
    """Makes ``folder`` a repository with one commit of the owner that carries a signature, whose
    configuration has ``git log`` check signatures with a program that writes ``marker``."""
    folder.mkdir(parents=True, exist_ok=True)
    git(environ, folder, "init", "-q", "-b", "main")
    git(environ, folder, "config", "user.email", OWNER_EMAIL)
    tree = git(environ, folder, "write-tree").strip()
    person = f"Alex <{OWNER_EMAIL}> {SIGNED_AT} +0000"
    signature = "gpgsig -----BEGIN PGP SIGNATURE-----\n \n iQEzBAABCAAdFiEE\n -----END PGP SIGNATURE-----"
    text = f"tree {tree}\nauthor {person}\ncommitter {person}\n{signature}\n\n{SIGNED_SUBJECT}\n"
    commit = git(environ, folder, "hash-object", "-t", "commit", "-w", "--stdin", stdin=text).strip()
    git(environ, folder, "update-ref", "refs/heads/main", commit)
    program = folder / "checks-signatures.sh"
    program.write_text(f"#!/bin/sh\ntouch {shlex.quote(str(marker))}\nexit 1\n", encoding="utf-8")
    program.chmod(0o755)
    git(environ, folder, "config", "log.showSignature", "true")
    git(environ, folder, "config", "gpg.program", str(program))


class CommandLineTest(unittest.TestCase):
    def test_the_settings_come_after_the_callers_own_and_before_the_subcommand(self) -> None:
        """Covers: B169"""
        command = git_program.git_command("/usr/bin/git", Path("/work/acme"), ["log", "-1"], ["safe.directory=*"])

        settings = [option for setting in git_program.SETTINGS for option in ("-c", setting)]
        self.assertEqual(
            command, ["/usr/bin/git", "-C", "/work/acme", "-c", "safe.directory=*", *settings, "log", "-1"]
        )
        self.assertEqual(
            set(git_program.SETTINGS),
            {
                f"core.hooksPath={os.devnull}",
                "core.fsmonitor=false",
                "log.showSignature=false",
                "protocol.allow=never",
            },
        )

    def test_a_named_git_directory_is_given_before_the_settings(self) -> None:
        command = git_program.git_command("git", Path("/store"), ["status"], git_directory=Path("/history"))

        self.assertEqual(command[:5], ["git", "-C", "/store", "--git-dir", "/history"])

    def test_variables_that_point_git_elsewhere_are_taken_out_and_no_remote_is_reached(self) -> None:
        """Covers: B169"""
        given = {"PATH": "/usr/bin", "HOME": "/home/alex", "GIT_ALLOW_PROTOCOL": "file:ssh"}
        pointing = dict.fromkeys(git_program.REDIRECTING_VARIABLES, "/elsewhere")

        environ = git_program.git_environment({**given, **pointing})

        self.assertEqual(
            environ,
            {
                "PATH": "/usr/bin",
                "HOME": "/home/alex",
                "GIT_ALLOW_PROTOCOL": "",
                "GIT_NO_LAZY_FETCH": "1",
                "GIT_TERMINAL_PROMPT": "0",
            },
        )
        self.assertLessEqual({"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_CONFIG"}, set(pointing))


@unittest.skipIf(GIT is None, "git is not installed")
class HostileRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.base = Path(self._temp.name).resolve()
        self.marker = self.base / "a-command-ran"
        self.environ = without_the_machines_configuration(
            {"PATH": os.environ.get("PATH", ""), "HOME": str(self.base / "user-home")}
        )

    def started(self, command: Sequence[str], environ: Mapping[str, str]) -> subprocess.CompletedProcess[str]:
        index = {"GIT_INDEX_FILE": str(self.base / "index")}
        return subprocess.run(list(command), env={**environ, **index}, capture_output=True, text=True)

    def partial_clone(self, allows_its_transport: bool = True) -> tuple[Path, str]:
        clone = self.base / "clone"
        head = make_partial_clone(self.environ, self.base / "made-from", clone, self.marker, allows_its_transport)
        return clone, head


class NoFetchTest(HostileRepositoryTest):
    def test_a_git_started_plainly_fetches_what_the_partial_clone_lacks(self) -> None:
        clone, head = self.partial_clone()

        result = self.started(["git", "-C", str(clone), "read-tree", head], self.environ)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.marker.exists())

    def test_a_git_m2b_starts_fetches_nothing_and_runs_no_command_of_the_remote(self) -> None:
        """Covers: B169"""
        clone, head = self.partial_clone()

        command = git_program.git_command("git", clone, ["read-tree", head])
        result = self.started(command, git_program.git_environment(self.environ))

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.marker.exists())

    def test_the_closed_transports_hold_alone_against_a_repository_that_allows_its_own(self) -> None:
        """Covers: B169"""
        clone, head = self.partial_clone()
        environ = git_program.git_environment(self.environ)
        del environ["GIT_NO_LAZY_FETCH"]

        result = self.started(git_program.git_command("git", clone, ["read-tree", head]), environ)

        self.assertIn("transport 'file' not allowed", result.stderr)
        self.assertFalse(self.marker.exists())

    def test_the_switch_against_lazy_fetches_holds_alone(self) -> None:
        """Covers: B169"""
        if git_version(self.environ) < KNOWS_NO_LAZY_FETCH:
            self.skipTest("this git does not know GIT_NO_LAZY_FETCH; the closed transports hold there")
        clone, head = self.partial_clone()
        environ = git_program.git_environment(self.environ)
        del environ["GIT_ALLOW_PROTOCOL"]

        result = self.started(git_program.git_command("git", clone, ["read-tree", head]), environ)

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.marker.exists())

    def test_the_setting_alone_closes_the_transport_of_a_repository_that_names_no_policy(self) -> None:
        clone, head = self.partial_clone(allows_its_transport=False)

        result = self.started(git_program.git_command("git", clone, ["read-tree", head]), self.environ)

        self.assertIn("transport 'file' not allowed", result.stderr)
        self.assertFalse(self.marker.exists())


class NoSignatureCheckTest(HostileRepositoryTest):
    LOG = ("log", "--all", "--format=%s")

    def test_a_git_started_plainly_starts_the_program_the_repository_names(self) -> None:
        folder = self.base / "work"
        make_repository_that_checks_signatures(self.environ, folder, self.marker)

        self.started(["git", "-C", str(folder), *self.LOG], self.environ)

        self.assertTrue(self.marker.exists())

    def test_a_git_m2b_starts_reads_the_log_and_checks_no_signature(self) -> None:
        """Covers: B169"""
        folder = self.base / "work"
        make_repository_that_checks_signatures(self.environ, folder, self.marker)

        command = git_program.git_command("git", folder, self.LOG)
        result = self.started(command, git_program.git_environment(self.environ))

        self.assertEqual(result.stdout.strip(), SIGNED_SUBJECT)
        self.assertFalse(self.marker.exists())


if __name__ == "__main__":
    unittest.main()
