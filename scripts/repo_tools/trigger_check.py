"""Checks that the client skills trigger on everyday phrases, the way people ask, in English and German.

Every phrase in ``tests/triggers/phrases.json`` runs as the prompt of a fenced ``claude -p``
(``fenced_claude``) against a test store with a small distillate; the run stops at its first
``Skill`` call, which must name the phrase's skill. It needs the user's own Claude login and the
real model, so it is not part of ``scripts/check``: run it with ``scripts/trigger-check``.

All runs share one empty working folder, so Claude Code keeps one project folder for them and
not one per phrase. The run is refused when that folder, which it wipes first, touches the store
of the real config.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from m2b.paths import HOME_VARIABLE, MachinePaths, machine_paths

from repo_tools import REPO_ROOT, fenced_claude
from repo_tools.e2e import CORE_PLUGIN, TEST_RESOURCE_PREFIX, RealStoreError, isolated_machine_config, refuse_real_store

PHRASES = REPO_ROOT / "tests" / "triggers" / "phrases.json"
DEFAULT_WORK_ROOT = Path(tempfile.gettempdir()) / f"{TEST_RESOURCE_PREFIX}m2b-trigger-check"
DEFAULT_JOBS = 4
RUN_TIMEOUT_SECONDS = 120
LANGUAGES = ("en", "de")

EXIT_PASSED = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_REFUSED = 2

STORE_SETTINGS = {
    "format": 1,
    "tasks": {"backend": "markdown"},
    "curating_machine": f"{TEST_RESOURCE_PREFIX}e2e",
    "journal_since": "2026-11-01",
}
# Facts no phrase asks about: a phrase whose answer stands in the distillate is answered from it,
# rightly, without a skill ("Dana's birthday?" needs no search).
DISTILLATE = (
    "# Memory\n\n## Facts\n\n- Sam repairs boats at the harbour (sam.md)\n\n"
    "## Current\n\n- Planning the trip to Porto\n"
)


@dataclass(frozen=True)
class Phrase:
    skill: str
    language: str
    text: str


@dataclass(frozen=True)
class Outcome:
    phrase: Phrase
    run: fenced_claude.SkillRun

    @property
    def hit(self) -> bool:
        return self.run.error is None and self.run.skill == self.phrase.skill


def load_phrases(path: Path, skill: str | None, language: str | None) -> list[Phrase]:
    skills = json.loads(path.read_text(encoding="utf-8"))["skills"]
    return [
        Phrase(name, lang, text)
        for name, languages in skills.items()
        if skill in (None, name)
        for lang in LANGUAGES
        if language in (None, lang)
        for text in languages.get(lang, [])
    ]


def prepare_sandbox(work_root: Path, environ: Mapping[str, str]) -> tuple[Path, dict[str, str]]:
    """A fresh empty working folder, machine home and test store; returns the folder and the environment."""
    store = work_root / f"{TEST_RESOURCE_PREFIX}triggers-store"
    # The whole folder is wiped, so the guard covers the whole folder, not only the store in it.
    refuse_real_store(work_root, machine_paths(environ))
    shutil.rmtree(work_root, ignore_errors=True)
    work, home = work_root / "work", work_root / "home"
    work.mkdir(parents=True)
    (store / "memory").mkdir(parents=True)
    (store / "store.json").write_text(json.dumps(STORE_SETTINGS, indent=2) + "\n", encoding="utf-8")
    (store / "memory" / "MEMORY.md").write_text(DISTILLATE, encoding="utf-8")
    config = MachinePaths(home).config_file
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps(isolated_machine_config(store), indent=2) + "\n", encoding="utf-8")
    environment = dict(environ)
    environment[HOME_VARIABLE] = str(home)
    environment["M2B_CORE_ROOT"] = str(CORE_PLUGIN)
    return work, environment


def check(
    phrases: Sequence[Phrase], work: Path, environment: Mapping[str, str], claude: str, jobs: int
) -> list[Outcome]:
    def run(phrase: Phrase) -> Outcome:
        command = fenced_claude.fenced_command(phrase.text, CORE_PLUGIN, claude=claude)
        return Outcome(phrase, fenced_claude.run_until_skill(command, work, environment, RUN_TIMEOUT_SECONDS))

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        return list(pool.map(run, phrases))


def report(outcomes: Sequence[Outcome]) -> None:
    for outcome in outcomes:
        phrase, run = outcome.phrase, outcome.run
        where = f"{phrase.skill} {phrase.language}: {phrase.text!r}"
        if run.error is not None:
            print(f"error {where}: {run.error}")
        elif not outcome.hit:
            print(f"miss {where} -> {run.skill or 'no skill'}")
    loaded = next((o.run.loaded_skills for o in outcomes if o.run.loaded_skills is not None), None)
    if loaded is not None and not any(skill.startswith("m2b:") for skill in loaded):
        print("trigger-check: the sessions did not load the m2b skills; check --plugin-dir")
    hits = sum(outcome.hit for outcome in outcomes)
    print(f"trigger-check: {hits} of {len(outcomes)} phrases triggered their skill")


def _parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="trigger-check", description=__doc__.split("\n", 1)[0])
    parser.add_argument("--skill", help="only the phrases of this skill, such as m2b:capture")
    parser.add_argument("--language", choices=LANGUAGES, help="only the phrases in this language")
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS, help="runs at the same time")
    parser.add_argument("--claude", default="claude", help="the claude command")
    parser.add_argument("--phrases", type=Path, default=PHRASES, help=argparse.SUPPRESS)
    parser.add_argument("--work-root", type=Path, default=DEFAULT_WORK_ROOT, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    arguments = _parse_arguments(sys.argv[1:] if argv is None else argv)
    environ = os.environ if environ is None else environ
    phrases = load_phrases(arguments.phrases, arguments.skill, arguments.language)
    if not phrases:
        filters = (("skill", arguments.skill), ("language", arguments.language))
        given = " and ".join(f"{name} {value}" for name, value in filters if value)
        print(f"trigger-check: no phrases for {given}", file=sys.stderr)
        return EXIT_USAGE
    try:
        work, environment = prepare_sandbox(arguments.work_root, environ)
    except RealStoreError as error:
        print(f"trigger-check: {error}", file=sys.stderr)
        return EXIT_REFUSED
    outcomes = check(phrases, work, environment, arguments.claude, arguments.jobs)
    report(outcomes)
    return EXIT_PASSED if all(outcome.hit for outcome in outcomes) else EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
