"""The characters that draw nothing, and the few of them that undo a model step."""

from __future__ import annotations

import re
import unittest

from locations import PLUGIN_ROOT
from m2b.notes.characters import HIDDEN_RANGES, unsafe_characters, with_hidden_written_out, without_hidden

MOD_TABLE = PLUGIN_ROOT / "hooks" / "plain-text.ts"
JOINERS = ("‌", "‍")


def every_character() -> str:
    surrogates = range(0xD800, 0xE000)
    return "".join(chr(code) for code in range(0x110000) if code not in surrogates)


class UnsafeCharactersTest(unittest.TestCase):
    def test_bidi_controls_zero_width_space_word_joiner_bom_and_tags_are_unsafe(self) -> None:
        """Covers: B56"""
        for character in ("‮", "⁦", "​", "⁠", "﻿", "\U000e0041", "᠎"):
            with self.subTest(code=f"U+{ord(character):04X}"):
                self.assertEqual(unsafe_characters(f"Dana{character} likes maps"), [f"U+{ord(character):04X}"])
                self.assertEqual(without_hidden(f"Dana{character} likes maps"), "Dana likes maps")

    def test_what_real_text_carries_is_not_unsafe(self) -> None:
        """Covers: B56"""
        carried = (
            "Dana \U0001f469‍\U0001f4bb codes",
            "می‌خواهم",
            "a‎b",
            "Dana ❤️ maps",
            "Zusammen­arbeit",
            "葛\U000e0100",
        )
        for text in carried:
            with self.subTest(text=text):
                self.assertEqual(unsafe_characters(text), [])

    def test_each_unsafe_character_is_named_once_in_the_order_it_comes(self) -> None:
        self.assertEqual(unsafe_characters("‮x​y‮"), ["U+202E", "U+200B"])


class HiddenCharactersTest(unittest.TestCase):
    def test_what_draws_nothing_is_taken_out_and_the_text_around_it_stays(self) -> None:
        """Covers: B143"""
        hidden = {
            "a‎b": "ab",
            "Dana ❤️ maps": "Dana ❤ maps",
            "Zusammen­arbeit": "Zusammenarbeit",
            "葛\U000e0100": "葛",
            "Ply᠏wood⁥ ￰off\U0001bca0cuts\U0001d173\U000e0fff": "Plywood offcuts",
        }
        for text, shown in hidden.items():
            with self.subTest(text=text):
                self.assertEqual(without_hidden(text), shown)

    def test_a_name_someone_has_to_find_gets_them_written_out(self) -> None:
        self.assertEqual(
            with_hidden_written_out("memory/dana\u00ad\U000e0049.md, line 3"),
            "memory/dana<U+00AD><U+E0049>.md, line 3",
        )
        self.assertEqual(with_hidden_written_out("memory/dana\u200c\u200d.md"), "memory/dana<U+200C><U+200D>.md")
        self.assertEqual(with_hidden_written_out("memory/dana.md"), "memory/dana.md")

    def test_the_joiners_stay_because_emoji_and_scripts_need_them(self) -> None:
        """Covers: B143"""
        for text in ("Dana \U0001f469‍\U0001f4bb codes", "می‌خواهم"):
            with self.subTest(text=text):
                self.assertEqual(without_hidden(text), text)
        for first, last in HIDDEN_RANGES:
            for joiner in JOINERS:
                self.assertFalse(first <= ord(joiner) <= last)

    def test_each_range_goes_from_its_first_to_its_last_character_and_no_further(self) -> None:
        for first, last in HIDDEN_RANGES:
            with self.subTest(range=f"U+{first:04X} to U+{last:04X}"):
                self.assertLessEqual(first, last)
                before, after = chr(first - 1), chr(last + 1)
                self.assertEqual(without_hidden(f"{before}{chr(first)}{chr(last)}{after}"), f"{before}{after}")

    def test_every_unsafe_character_is_one_of_those_that_draw_nothing(self) -> None:
        """Covers: B143"""
        unsafe = [chr(int(name[2:], 16)) for name in unsafe_characters(every_character())]

        self.assertGreater(len(unsafe), 100)
        self.assertEqual(without_hidden("".join(unsafe)), "")

    def test_the_mod_keeps_the_same_table(self) -> None:
        """Covers: B143"""
        source = MOD_TABLE.read_text(encoding="utf-8")
        table = re.search(r"const HIDDEN_RANGES\b[^=]*= \[\n(.*?)\n\]", source, re.DOTALL)
        assert table is not None, "hooks/plain-text.ts holds no HIDDEN_RANGES table"
        rows = [row.strip() for row in table.group(1).splitlines()]
        pairs = [re.fullmatch(r"\[0x([0-9a-f]+), 0x([0-9a-f]+)\],(?: //.*)?", row) for row in rows]

        self.assertNotIn(None, pairs, "a row of the mod's table is no [0x..., 0x...] pair")
        self.assertEqual(
            [(int(pair.group(1), 16), int(pair.group(2), 16)) for pair in pairs if pair is not None],
            list(HIDDEN_RANGES),
        )


if __name__ == "__main__":
    unittest.main()
