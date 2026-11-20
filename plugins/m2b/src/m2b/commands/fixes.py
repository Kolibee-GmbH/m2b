"""``fix``: keep a fix for a file Claude reads, show it, list the kept ones, settle one.

``m2b fix add`` reads one JSON object from standard input: ``file`` (its path, absolute or from the
working folder), ``wording`` (the new text), ``why`` (what is wrong, one line) and, for a fix that
replaces a line, ``line``. A session runs it on the owner's word ("merk dir als Fix: ..."); what the
owner says is kept, so it needs no answer to a proposal. The file is named by where it lies: under
``~/.claude/`` by its path from ``~`` and this machine, in a repository by the addresses of its
remotes and its path in the repository. A file in neither, or in a repository without a remote, is
refused: a fix must be found again in a clone on another machine.

``m2b fix show <name>`` prints a fix whole: the session start names a waiting fix by its name only.
``done`` and ``drop`` settle it. A name that is no fix's ends with exit 2, one nobody kept with
exit 1.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

from m2b import fixes, session_remotes
from m2b.commands import Context, ProblemError, UsageError
from m2b.commands.backends import configured_store
from m2b.commands.output import print_json
from m2b.config.machine import load_machine_config
from m2b.config.store_settings import require_store_writable
from m2b.fixes import DONE, DROPPED, Fix, FixRefusedError, UnknownFixError
from m2b.notes.characters import with_hidden_written_out, without_hidden
from m2b.store.base import Store

ADD = "add"
SHOW = "show"
LIST = "list"
# The two actions that settle a fix, with the state each gives it.
SETTLE = {"done": DONE, "drop": DROPPED}
INPUT_LENGTH = 16 * 1024
GIT_TIMEOUT_SECONDS = 5.0


def fix_command(arguments: argparse.Namespace, context: Context) -> int:
    config = load_machine_config(context.machine)
    store = configured_store(config, context.machine)
    action = arguments.action
    try:
        if action == ADD:
            fix = _fix_from_input(_read_input(), context, config.machine_id)
            require_store_writable(store)
            is_new = fixes.keep(store, fix)
            print(("Kept" if is_new else "Kept before") + f" as {fix.name}: a fix for {_name(fix.place)}.")
            print(_where_it_waits(fix))
            return 0
        if action == SHOW:
            kept = fixes.find(store, arguments.name)
            print("\n".join(_shown(kept)))
            return 0
        if action in SETTLE:
            require_store_writable(store)
            settled = fixes.settle(store, arguments.name, SETTLE[action])
            state = SETTLE[action] if settled else fixes.find(store, arguments.name).state
            print(f"{arguments.name} is {state}" + ("." if settled else ", as it was before."))
            return 0
        return _list(store, arguments.json)
    except FixRefusedError as error:
        raise UsageError(with_hidden_written_out(str(error))) from error
    except UnknownFixError as error:
        raise ProblemError(with_hidden_written_out(str(error))) from error


def _read_input() -> dict[str, object]:
    written = sys.stdin.buffer.read(INPUT_LENGTH + 1)
    try:
        if len(written) > INPUT_LENGTH:
            raise ValueError("longer than a fix")
        given = json.loads(written.decode("utf-8"))
    except (ValueError, RecursionError) as error:
        raise UsageError("m2b fix add reads one JSON object from standard input") from error
    if not isinstance(given, dict):
        raise UsageError("m2b fix add reads one JSON object from standard input")
    return given


def _fix_from_input(given: dict[str, object], context: Context, machine_id: str) -> Fix:
    file, line, wording, why = (given.get(key) for key in ("file", "line", "wording", "why"))
    if not isinstance(file, str) or not file.strip():
        raise UsageError("a fix names its file: file, its path")
    if not isinstance(wording, str) or not isinstance(why, str) or not (line is None or isinstance(line, str)):
        raise UsageError("a fix gives wording and why as text, and line as text or not at all")
    home = context.environ.get("HOME")
    target = Path(os.path.abspath(Path(file).expanduser() if home is None else _expanded(file, home)))
    today = datetime.date.today().isoformat()
    claude_folder = None if home is None else Path(os.path.abspath(home)) / ".claude"
    if claude_folder is not None and _is_below(target, claude_folder):
        path = fixes.HOME_PREFIX + target.relative_to(claude_folder).as_posix()
        fix = fixes.new_fix(path, (), machine_id, line, wording, why, today)
    else:
        top, addresses = _repository_of(target, context)
        fix = fixes.new_fix(target.relative_to(top).as_posix(), addresses, None, line, wording, why, today)
    if fix.line is not None and fixes.look(fix, target) == fixes.GONE:
        raise FixRefusedError(f"{target} does not hold the line the fix replaces; give it as the file has it")
    return fix


def _expanded(file: str, home: str) -> Path:
    return Path(home) / file[2:] if file == "~" or file.startswith("~/") else Path(file)


def _is_below(path: Path, folder: Path) -> bool:
    try:
        path.relative_to(folder)
    except ValueError:
        return False
    return True


def _repository_of(target: Path, context: Context) -> tuple[Path, tuple[str, ...]]:
    try:
        repository = session_remotes.repository_of(target.parent, context.environ, GIT_TIMEOUT_SECONDS)
    except session_remotes.RepositoryNotKnownError as error:
        if error.reason == session_remotes.NOT_IN_A_REPOSITORY:
            raise UsageError(
                f"{target} lies in no repository and not under ~/.claude/; m2b keeps fixes for those only"
            ) from error
        if error.reason == session_remotes.NO_REMOTE:
            raise UsageError(
                f"the repository at {error.top} has no remote; m2b names a repository by its remote, "
                "to find it again in a clone on another machine, so nothing was kept"
            ) from error
        raise UsageError(f"git could not say the remotes of the repository at {error.top}; nothing was kept") from error
    return repository.top, repository.addresses


def _where_it_waits(fix: Fix) -> str:
    if fix.for_home:
        return "Every session on this machine says that it waits, until it is done."
    return "A session that starts in a clone of that repository says that it waits, until it is done."


def _shown(kept: fixes.Kept) -> list[str]:
    fix = kept.fix
    lines = [f"Fix {fix.name}, kept {fix.kept}, for {_name(fix.place)}: {kept.state}"]
    lines.extend(["", f"What is wrong: {_text(fix.why)}", ""])
    if fix.line is not None:
        lines.extend(["The line it replaces:", f"  {_text(fix.line)}", "", "With:"])
    else:
        lines.append("What it adds:")
    lines.extend(f"  {_text(line)}" for line in fix.wording.splitlines())
    return lines


def _list(store: Store, as_json: bool) -> int:
    kept = fixes.read_all(store)
    if as_json:
        print_json(
            {
                "fixes": [
                    {
                        "name": item.fix.name,
                        "state": item.state,
                        "file": _name(item.fix.place),
                        "why": _text(item.fix.why),
                        "kept": item.fix.kept,
                    }
                    for item in kept
                ]
            }
        )
        return 0
    if not kept:
        print("No fix is kept.")
    for item in kept:
        print(f"{item.fix.name}  {item.state}  {_name(item.fix.place)}: {_text(item.fix.why)}")
    return 0


def _text(text: str) -> str:
    return without_hidden(text)


def _name(name: str) -> str:
    return with_hidden_written_out(name)
