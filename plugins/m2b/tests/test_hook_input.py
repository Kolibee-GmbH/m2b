"""Reading Claude Code's hook input from stdin."""

from __future__ import annotations

import io
import unittest

from m2b.hook_input import HookInput, read_hook_input


class _Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


class ReadHookInputTest(unittest.TestCase):
    def test_the_known_fields_are_read(self) -> None:
        stream = io.StringIO('{"session_id": "s-1", "source": "compact", "cwd": "/w", "prompt": "hi", "other": 1}')

        self.assertEqual(read_hook_input(stream), HookInput("s-1", "compact", "/w", "hi"))

    def test_a_field_that_is_no_string_counts_as_missing(self) -> None:
        self.assertEqual(read_hook_input(io.StringIO('{"session_id": 7, "cwd": ["/w"]}')), HookInput())

    def test_no_input_broken_input_and_a_terminal_give_an_empty_input(self) -> None:
        for stream in (None, io.StringIO(""), io.StringIO("{broken"), io.StringIO("[1]"), _Terminal('{"cwd": "/w"}')):
            with self.subTest(stream=stream):
                self.assertEqual(read_hook_input(stream), HookInput())


if __name__ == "__main__":
    unittest.main()
