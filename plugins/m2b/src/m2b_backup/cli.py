"""The ``m2b-backup`` command.

``run`` makes one backup: the part's ``after_journal`` curation step, or a backup on demand.
Exit 0 when the backup was made, also with findings such as files not downloaded; 1 when it could
not be made (target missing, core not answering); 2 when the backup is not set up on this machine.
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from m2b_backup import backup, core

EXIT_OK = 0
EXIT_PROBLEM = 1
EXIT_NOT_SET_UP = 2


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="m2b-backup", description="The backup part of m2b.")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="mirror the store, prune the attic, dump the task list")
    run.add_argument("--today", help="the attic's day, YYYY-MM-DD (default: today)")
    arguments = parser.parse_args(argv)

    home = Path(os.environ.get("M2B_HOME") or os.environ.get("HOME") or str(Path.home()))
    launcher = home / ".local" / "bin" / "m2b"
    try:
        today = datetime.date.fromisoformat(arguments.today) if arguments.today else datetime.date.today()
        outcome = backup.run(core.Core(launcher, os.environ), home, today)
    except backup.NotSetUpError as error:
        print(f"m2b-backup: {error}", file=sys.stderr)
        return EXIT_NOT_SET_UP
    except (ValueError, OSError, backup.BackupError, core.CoreError) as error:
        print(f"m2b-backup: {error}", file=sys.stderr)
        return EXIT_PROBLEM
    print("\n".join(outcome.lines()))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
