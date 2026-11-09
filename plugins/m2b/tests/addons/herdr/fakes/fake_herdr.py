#!/usr/bin/env python3
"""Stands in for ``herdr`` in tests: answers ``api snapshot`` from files, never from a real herdr.

``FAKE_HERDR_REPLY`` names a file whose text is printed as the answer; ``FAKE_HERDR_EXIT`` sets the
exit code; ``FAKE_HERDR_SLEEP`` waits that many seconds first. Each call is appended to the file
``FAKE_HERDR_CALLS`` names, one line of arguments.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def main() -> int:
    calls = os.environ.get("FAKE_HERDR_CALLS")
    if calls:
        with Path(calls).open("a", encoding="utf-8") as log:
            log.write(" ".join(sys.argv[1:]) + "\n")
    if sys.argv[1:] != ["api", "snapshot"]:
        print(f"fake herdr: unexpected arguments {sys.argv[1:]}", file=sys.stderr)
        return 2
    time.sleep(float(os.environ.get("FAKE_HERDR_SLEEP", "0")))
    reply = os.environ.get("FAKE_HERDR_REPLY")
    if reply:
        print(Path(reply).read_text(encoding="utf-8"), end="")
    code = int(os.environ.get("FAKE_HERDR_EXIT", "0"))
    if code:
        print("fake herdr: no server is running", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
