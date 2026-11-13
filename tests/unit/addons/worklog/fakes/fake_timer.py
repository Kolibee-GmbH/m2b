#!/usr/bin/env python3
"""Stands in for ``launchctl`` and ``systemctl`` in the worklog's tests; never touches a real timer.

Every call is appended to ``FAKE_TIMER_CALLS`` as one line: the name its wrapper sets in
``FAKE_COMMAND_NAME``, then its arguments.
It exits with ``FAKE_TIMER_EXIT`` (default 0), and with 1 for a subcommand named in the comma list
``FAKE_TIMER_FAIL``, such as ``print``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    calls = os.environ.get("FAKE_TIMER_CALLS")
    if calls:
        with Path(calls).open("a", encoding="utf-8") as log:
            log.write(" ".join([os.environ.get("FAKE_COMMAND_NAME", "timer"), *sys.argv[1:]]) + "\n")
    if len(sys.argv) > 1 and sys.argv[1] in os.environ.get("FAKE_TIMER_FAIL", "").split(","):
        return 1
    return int(os.environ.get("FAKE_TIMER_EXIT", "0"))


if __name__ == "__main__":
    sys.exit(main())
