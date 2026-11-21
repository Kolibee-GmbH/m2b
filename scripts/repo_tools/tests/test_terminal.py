"""The hidden terminal that types keys into a command and records what it draws."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from repo_tools import terminal

SHELL = {"PATH": "/usr/bin:/bin"}


class RecordTimedTest(unittest.TestCase):
    def test_a_wait_ends_as_soon_as_what_it_waits_for_is_drawn_and_every_chunk_has_its_time(self) -> None:
        command = ["sh", "-c", "printf 'one\\n'; read answer; printf 'two\\n'; sleep 5"]
        waits = [terminal.Wait(30, "go\r", until=b"one"), terminal.Wait(30, until=b"two")]

        recording = terminal.record_timed(command, Path("/"), {"PATH": "/usr/bin:/bin"}, 10, 40, waits)

        self.assertIn(b"two", b"".join(drawn for _, drawn in recording.chunks))
        self.assertEqual(len(recording.typed_at), 2)
        self.assertLess(recording.typed_at[1], 10)
        times = [at for at, _ in recording.chunks]
        self.assertEqual(times, sorted(times))
        self.assertLessEqual(times[-1], recording.typed_at[1])

    def test_a_wait_finds_a_prompt_behind_the_escape_sequence_a_shell_draws_before_it(self) -> None:
        command = ["sh", "-c", "printf 'done\\n\\033[?2004h$ '; sleep 5"]

        recording = terminal.record_timed(
            command, Path("/"), {"PATH": "/usr/bin:/bin"}, 10, 40, [terminal.Wait(3, until=b"\n$ ")]
        )

        self.assertEqual(len(recording.typed_at), 1)

    def test_a_wait_that_never_sees_what_it_waits_for_fails(self) -> None:
        command = ["sh", "-c", "printf 'one\\n'; sleep 5"]

        with self.assertRaisesRegex(terminal.TerminalError, "did not draw b'two' within 0.5 seconds"):
            terminal.record_timed(
                command, Path("/"), {"PATH": "/usr/bin:/bin"}, 10, 40, [terminal.Wait(0.5, until=b"two")]
            )

    def test_a_wait_ends_when_its_sign_outside_the_screen_comes(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            sign = Path(folder) / "ended"
            command = ["sh", "-c", f"read answer; touch {sign}; sleep 5"]
            waits = [terminal.Wait(0.3, "go\r"), terminal.Wait(30, done=sign.exists)]

            recording = terminal.record_timed(command, Path("/"), SHELL, 10, 40, waits)

        self.assertEqual(len(recording.typed_at), 2)
        self.assertLess(recording.typed_at[1], 10)

    def test_a_wait_whose_sign_never_comes_fails_and_names_the_sign(self) -> None:
        command = ["sh", "-c", "sleep 5"]

        with self.assertRaisesRegex(terminal.TerminalError, "no end of turn 1 within 0.5 seconds"):
            terminal.record_timed(
                command, Path("/"), SHELL, 10, 40, [terminal.Wait(0.5, done=lambda: False, waits_for="end of turn 1")]
            )

    def test_the_text_of_a_recording_has_no_escape_sequences(self) -> None:
        recording = terminal.Recording(((0.0, b"\x1b[1mbold\x1b[0m "), (0.1, b"plain")), ())

        self.assertEqual(recording.text(), "bold plain")


if __name__ == "__main__":
    unittest.main()
