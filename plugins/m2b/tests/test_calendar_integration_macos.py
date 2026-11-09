"""The calendar contract against the real Apple Calendar; it runs only when asked to.

    M2B_IT=1 scripts/check --quick m2b

Each test creates its own calendar ``sb-test-calendar-<random>`` in the account named by
``M2B_IT_CALENDAR_ACCOUNT`` (default ``iCloud``) and removes it, with its events,
afterwards. The helper script refuses any name not starting with ``sb-test-``, so the owner's
own calendars are never written; reading them is part of the contract, comparing them is not.
Access is asked for through the product's own script before the test calendar is created, so
on a machine without the grant the first test shows the access prompt.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from calendar_contract import Contracts
from m2b.calendar.apple import OSASCRIPT, AppleCalendarBackend
from m2b.calendar.base import Calendar

TEST_CALENDAR_PREFIX = "sb-test-"
ACCOUNT_VARIABLE = "M2B_IT_CALENDAR_ACCOUNT"
FIXTURE = Path(__file__).resolve().parent / "helpers" / "sb_test_calendar.js"


def integration_requested(environ: Mapping[str, str]) -> bool:
    return environ.get("M2B_IT") == "1" and sys.platform == "darwin"


def run_fixture(*arguments: str) -> Any:
    """Runs the helper script and returns its answer; an error answer raises ``RuntimeError``."""
    if len(arguments) < 2 or not arguments[1].startswith(TEST_CALENDAR_PREFIX):
        raise RuntimeError(f"a test calendar name starts with {TEST_CALENDAR_PREFIX}, got {arguments[1:2]}")
    result = subprocess.run(
        [OSASCRIPT, "-l", "JavaScript", str(FIXTURE), *arguments], capture_output=True, text=True, timeout=60
    )
    reply = json.loads(result.stdout or "{}")
    if result.returncode != 0 or "ok" not in reply:
        raise RuntimeError(f"sb_test_calendar.js {arguments[0]}: {reply.get('error') or result.stderr.strip()}")
    return reply["ok"]


class FixtureGuardTest(unittest.TestCase):
    def test_a_calendar_not_named_for_tests_is_refused(self) -> None:
        for name in ("Home", "Calendar", "test-calendar"):
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                run_fixture("remove", name)

    @unittest.skipUnless(sys.platform == "darwin", "osascript exists on macOS only")
    def test_the_script_itself_refuses_before_opening_the_store(self) -> None:
        result = subprocess.run(
            [OSASCRIPT, "-l", "JavaScript", str(FIXTURE), "remove", "Home"], capture_output=True, text=True, timeout=60
        )

        self.assertIn("refused", json.loads(result.stdout)["error"])

    def test_without_the_switch_nothing_runs(self) -> None:
        self.assertFalse(integration_requested({}))


@unittest.skipUnless(sys.platform == "darwin", "Apple Calendar exists on macOS only")
class AppleCalendarIntegrationTest(Contracts.CalendarContract):
    def make_calendar(self, folder: Path) -> Calendar:
        if not integration_requested(os.environ):
            self.skipTest("set M2B_IT=1 on macOS")
        # Long enough for someone to answer the access prompt, which only the first call can show.
        Calendar(AppleCalendarBackend(timeout_seconds=150)).check_access()
        self.calendar_name = f"{TEST_CALENDAR_PREFIX}calendar-{secrets.token_hex(3)}"
        run_fixture("create", self.calendar_name, os.environ.get(ACCOUNT_VARIABLE, "iCloud"))
        self.addCleanup(run_fixture, "remove", self.calendar_name)
        return Calendar(AppleCalendarBackend(timeout_seconds=30))


if __name__ == "__main__":
    unittest.main()
