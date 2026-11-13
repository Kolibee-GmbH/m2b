"""Characters a reader does not see: all that draw nothing, and the few of them that mislead.

``HIDDEN_RANGES`` is what draws nothing: the code points Unicode calls default ignorable, without
the joiners U+200C and U+200D, which emoji, Persian and several Indic scripts need. Text from the
store goes to a model without them (``without_hidden``): the distillate at session start, a
topic's facts before a prompt, the hits ``m2b search`` prints, and what the mod's tools answer;
the mod keeps the same table in ``hooks/plain-text.ts``. A model does not draw, so it loses
nothing, and nothing rides along unseen.

``unsafe_characters`` names the few of them that make a line read one way to the owner and another
to the model. A line a model step writes with one of them undoes the step:

- the bidirectional embeddings, overrides and isolates (U+202A to U+202E, U+2066 to U+2069) put
  text on screen in another order than the model reads it;
- the zero-width space, the Mongolian vowel separator, the word joiner, the invisible operators and
  the byte order mark (U+200B, U+180E, U+2060 to U+2064, U+FEFF) hide inside a word;
- the tag characters (U+E0000 to U+E007F) spell ASCII that no font draws, a whole instruction
  nobody sees.

The others undo nothing, because text people write carries them: the selector after an emoji
(U+FE0F), the soft hyphen of a pasted web page, the selectors of Mongolian and of Japanese name
variants, the direction marks U+200E and U+200F.
"""

from __future__ import annotations

import re

HIDDEN_RANGES: tuple[tuple[int, int], ...] = (
    (0x00AD, 0x00AD),  # soft hyphen
    (0x034F, 0x034F),  # combining grapheme joiner
    (0x061C, 0x061C),  # Arabic letter mark
    (0x115F, 0x1160),  # Hangul fillers
    (0x17B4, 0x17B5),  # Khmer inherent vowels
    (0x180B, 0x180F),  # Mongolian variation selectors and vowel separator
    (0x200B, 0x200B),  # zero-width space
    (0x200E, 0x200F),  # direction marks
    (0x202A, 0x202E),  # bidirectional embeddings and overrides
    (0x2060, 0x206F),  # word joiner, invisible operators, isolates, deprecated format controls
    (0x3164, 0x3164),  # Hangul filler
    (0xFE00, 0xFE0F),  # variation selectors
    (0xFEFF, 0xFEFF),  # byte order mark
    (0xFFA0, 0xFFA0),  # halfwidth Hangul filler
    (0xFFF0, 0xFFF8),  # reserved
    (0x1BCA0, 0x1BCA3),  # shorthand format controls
    (0x1D173, 0x1D17A),  # musical format controls
    (0xE0000, 0xE0FFF),  # tag characters, variation selectors supplement
)
_HIDDEN_CLASS = "".join(f"{chr(first)}-{chr(last)}" for first, last in HIDDEN_RANGES)
_HIDDEN = re.compile(f"[{_HIDDEN_CLASS}]")
# In a name the joiners mislead like the rest: two names that look the same are two files.
_UNSEEN_IN_A_NAME = re.compile(f"[{_HIDDEN_CLASS}\u200c\u200d]")
_UNSAFE = re.compile("[\u180e\u200b\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff\U000e0000-\U000e007f]")


def unsafe_characters(text: str) -> list[str]:
    """The unsafe characters in ``text`` as ``U+XXXX``, each once, in the order they first come."""
    names: dict[str, None] = {}
    for match in _UNSAFE.finditer(text):
        names[f"U+{ord(match.group()):04X}"] = None
    return list(names)


def without_hidden(text: str) -> str:
    """The text as it goes to a model: without any character that draws nothing."""
    return _HIDDEN.sub("", text)


def with_hidden_written_out(text: str) -> str:
    """The text with each character that draws nothing, the joiners too, as ``<U+XXXX>``.

    For a name the owner has to find: without its hidden characters it could be another file's.
    """
    return _UNSEEN_IN_A_NAME.sub(lambda match: f"<U+{ord(match.group()):04X}>", text)
