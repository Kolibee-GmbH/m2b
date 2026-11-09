"""The ``m2b-herdr`` command.

``neighbours`` is the session-start hook: it always exits 0, so it never blocks a session (B7), and
prints nothing while the herdr part is off.
``check`` is for the setup skill: it says whether herdr answers and installs nothing into herdr.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

from m2b_herdr import neighbours

EXIT_OK = 0
EXIT_PROBLEM = 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="m2b-herdr", description="The herdr part of m2b.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("neighbours", help="the session-start hook: the other agent sessions in herdr")
    commands.add_parser("check", help="whether herdr answers; changes nothing")
    arguments = parser.parse_args(argv)
    if arguments.command == "neighbours":
        return _neighbours()
    return _check()


def _neighbours() -> int:
    if not os.environ.get(neighbours.PANE_VARIABLE) or not neighbours.part_on(os.environ):
        return EXIT_OK
    try:
        print(neighbours.hook_output(os.environ), end="")
    except Exception as error:  # A hook must never fail a session, whatever went wrong.
        print(f"m2b neighbours: herdr could not be read ({type(error).__name__}).")
    return EXIT_OK


def _check() -> int:
    try:
        snapshot = neighbours.read_snapshot(neighbours.herdr_command(os.environ))
    except neighbours.HerdrError as error:
        print(f"herdr could not be read: {error}")
        return EXIT_PROBLEM
    agents = len(snapshot["agents"])
    print(f"herdr answers: {agents} agent session{'' if agents == 1 else 's'} open")
    inside = os.environ.get(neighbours.PANE_VARIABLE)
    if inside:
        print("this session runs inside herdr")
    else:
        print("this session runs outside herdr: the hook prints nothing here")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
