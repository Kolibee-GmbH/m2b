"""The ``m2b-worklog`` command.

``recorder check`` says whether herdr is there, new enough and running, which setup asks first.
``recorder install`` and ``recorder remove`` copy the recorder and link it in herdr, or unlink it;
both run twice without harm. ``recordings delete`` deletes what the recorder wrote. ``collect``
prints the facts of the period since the watermark. ``run`` is the daily worklog, the module's
curation step; ``facts`` and ``verdict`` are the two commands its model step may call. ``machine``
says whether this machine curates, which setup needs. ``hook session-start`` is the session-start
hook and always exits 0.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from m2b_worklog import core, daily, facts, ledger, recorder, session_start
from m2b_worklog.paths import WorklogPaths, worklog_paths
from m2b_worklog.sources.git import git_to_start
from m2b_worklog.sources.transcripts import projects_folder

EXIT_OK = 0
EXIT_PROBLEM = 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="m2b-worklog", description="The worklog add-on of m2b.")
    commands = parser.add_subparsers(dest="group", required=True)
    recorder_group = commands.add_parser("recorder", help="the activity recorder in herdr")
    recorder_commands = recorder_group.add_subparsers(dest="command", required=True)
    check_command = recorder_commands.add_parser("check", help="whether herdr is installed, new enough and running")
    check_command.add_argument("--json", action="store_true", help="answer as JSON")
    recorder_commands.add_parser("install", help="copy the recorder and link it in herdr")
    recorder_commands.add_parser("remove", help="unlink the recorder and delete its copy; recordings stay")
    recordings = commands.add_parser("recordings", help="what the recorder wrote on this machine")
    recordings_commands = recordings.add_subparsers(dest="command", required=True)
    recordings_commands.add_parser("delete", help="delete every recorded event and the workspace cache")
    run = commands.add_parser("run", help="the daily worklog: the curation step before ingest")
    run.add_argument("--now", help="the period's end, ISO 8601 with an offset (default: now)")
    facts_command = commands.add_parser("facts", help="the facts being judged, for the verdict's model step")
    facts_command.add_argument("--json", action="store_true", help="accepted for symmetry; the output is JSON")
    commands.add_parser("verdict", help="hand in the verdict written to the file `facts` names: checked, then stored")
    state_command = commands.add_parser(
        "state", help="the watermark, an unfinished worklog and the last period in the ledger"
    )
    state_command.add_argument("--json", action="store_true", help="answer as JSON")
    machine = commands.add_parser("machine", help="whether this machine curates, so it may record")
    machine.add_argument("--json", action="store_true", help="answer as JSON")
    collect = commands.add_parser("collect", help="the facts of the period since the watermark, as JSON")
    collect.add_argument("--now", help="the period's end, ISO 8601 with an offset (default: now)")
    collect.add_argument("--out", help="write the facts to this file instead of printing them")
    hook_group = commands.add_parser("hook", help="the plugin's hooks")
    hook_commands = hook_group.add_subparsers(dest="command", required=True)
    hook_commands.add_parser("session-start", help="the recording switch and the recorder copy")
    arguments = parser.parse_args(argv)

    paths = worklog_paths(os.environ)
    if arguments.group == "hook":
        try:
            print(session_start.session_start(paths, os.environ), end="")
        except Exception as error:  # A hook must never fail a session, whatever went wrong.
            print(f"m2b worklog: the session-start check failed ({type(error).__name__}).")
        return EXIT_OK
    if arguments.group == "collect":
        return _collect(paths, arguments.now, arguments.out)
    if arguments.group == "run":
        return _run(paths, arguments.now)
    if arguments.group == "facts":
        return _facts(paths)
    if arguments.group == "verdict":
        return _verdict(paths)
    if arguments.group == "machine":
        return _machine(paths, arguments.json)
    if arguments.group == "state":
        return _state(paths, arguments.json)
    if arguments.group == "recordings":
        shutil.rmtree(paths.state_dir, ignore_errors=True)
        shutil.rmtree(paths.run_dir, ignore_errors=True)
        print(f"recordings deleted: {paths.state_dir}, {paths.run_dir}")
        return EXIT_OK
    if arguments.command == "check":
        return _check(arguments.json)
    action = recorder.install if arguments.command == "install" else recorder.remove
    try:
        print(action(paths, os.environ))
    except (recorder.HerdrError, OSError) as error:
        print(f"m2b-worklog: {error}", file=sys.stderr)
        return EXIT_PROBLEM
    return EXIT_OK


def _check(as_json: bool) -> int:
    answer = recorder.check(os.environ)
    if as_json:
        print(json.dumps(answer))
    elif answer["ready"]:
        print(f"herdr {answer['herdr']} is running")
    else:
        print(answer["problem"])
    return EXIT_OK


def _collect(paths: WorklogPaths, now_text: str | None, out: str | None) -> int:
    try:
        now = _now(now_text)
        store = Path(core.ask(paths, ["config", "get", "store.path"]))
        profile = core.ask(paths, ["profile", "get"])
        inputs = facts.Inputs(
            store=store,
            recordings=paths.state_dir,
            transcripts=projects_folder(os.environ, paths.home),
            home=paths.home,
            profile=profile if isinstance(profile, dict) else {},
            now=now,
            remote_notes=paths.session_remotes,
            git=git_to_start(os.environ),
            herdr=recorder.herdr_state(os.environ),
        )
        text = json.dumps(facts.collect(inputs), ensure_ascii=False, indent=1) + "\n"
    except (ValueError, core.CoreError, facts.FactsError) as error:
        print(f"m2b-worklog: {error}", file=sys.stderr)
        return EXIT_PROBLEM
    if out:
        Path(out).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return EXIT_OK


def _run(paths: WorklogPaths, now_text: str | None) -> int:
    try:
        now = _now(now_text)
        sources = daily.Sources(
            projects_folder(os.environ, paths.home), recorder.herdr_state(os.environ), git_to_start(os.environ)
        )
        print(daily.run(paths, core.LauncherCore(paths, os.environ), now, sources))
    except (ValueError, OSError, core.CoreError, facts.FactsError, daily.DailyError, ledger.LedgerError) as error:
        print(f"m2b-worklog: {error}", file=sys.stderr)
        return EXIT_PROBLEM
    return EXIT_OK


def _facts(paths: WorklogPaths) -> int:
    try:
        print(json.dumps(daily.facts_for_model(paths), ensure_ascii=False, indent=1))
    except daily.DailyError as error:
        print(f"m2b-worklog: {error}", file=sys.stderr)
        return EXIT_PROBLEM
    return EXIT_OK


def _verdict(paths: WorklogPaths) -> int:
    try:
        problems = daily.accept_verdict(paths)
    except (OSError, daily.DailyError) as error:
        print(f"m2b-worklog: {error}", file=sys.stderr)
        return EXIT_PROBLEM
    if problems:
        print("the verdict was not accepted; fix these and hand it in again:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return EXIT_PROBLEM
    print("verdict accepted")
    return EXIT_OK


def _state(paths: WorklogPaths, as_json: bool) -> int:
    try:
        store = Path(core.ask(paths, ["config", "get", "store.path"]))
    except core.CoreError as error:
        print(f"m2b-worklog: {error}", file=sys.stderr)
        return EXIT_PROBLEM
    shown = daily.state(store)
    if as_json:
        print(json.dumps(shown, indent=1))
        return EXIT_OK
    last = shown["ledger"]["last"] if isinstance(shown["ledger"], dict) else None
    unfinished = shown["unfinished"]
    if shown["watermark"]:
        print(f"watermark: {shown['watermark']}")
    elif last:
        print(f"watermark: missing; it belongs at {last['end']}, the end of the last period in the ledger")
    else:
        print("watermark: none yet, the first worklog reaches three days back")
    if isinstance(unfinished, dict):
        print(f"unfinished worklog: {unfinished['start']} to {unfinished['end']}; the next run finishes it")
    else:
        print(f"unfinished worklog: {unfinished or 'none'}")
    if isinstance(shown["ledger"], dict):
        count = shown["ledger"]["periods"]
        held = f"{count} period{'' if count == 1 else 's'}"
        print(f"ledger: {held}" + (f", the last from {last['start']} to {last['end']}" if last else ""))
    else:
        print(f"ledger: {shown['ledger']}")
    return EXIT_OK


def _machine(paths: WorklogPaths, as_json: bool) -> int:
    try:
        curates = session_start.this_machine_curates(paths)
    except session_start.StatusError as error:
        print(f"m2b-worklog: {error}", file=sys.stderr)
        return EXIT_PROBLEM
    answer = {"set_up": curates is not None, "this_machine_curates": curates is True}
    if as_json:
        print(json.dumps(answer))
    elif curates is None:
        print("m2b is not set up on this machine; /m2b:m2b setup sets it up")
    else:
        print("this machine curates" if curates else "another machine curates")
    return EXIT_OK


def _now(text: str | None) -> datetime.datetime:
    now = datetime.datetime.fromisoformat(text) if text else datetime.datetime.now().astimezone()
    if now.tzinfo is None:
        raise ValueError("--now needs an offset, like 2026-03-14T18:00:00+01:00")
    return now


if __name__ == "__main__":
    sys.exit(main())
