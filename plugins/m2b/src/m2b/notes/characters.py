"""Characters that change what a reader sees without being seen themselves.

The distillate enters every session, and its lines come from captures that may hold someone else's
text, so a line must read the same to the owner in the review as to the model. These characters
break that:

- the bidirectional embeddings, overrides and isolates (U+202A to U+202E, U+2066 to U+2069) put
  text on screen in another order than the model reads it;
- the zero-width space, the Mongolian vowel separator, the word joiner, the invisible operators and
  the byte order mark (U+200B, U+180E, U+2060 to U+2064, U+FEFF) hide inside a word;
- the tag characters (U+E0000 to U+E007F) spell ASCII that no font draws, a whole instruction
  nobody sees.

The joiners U+200C and U+200D and the direction marks U+200E and U+200F stay: emoji, Persian and
several Indic scripts need them, and none of them carries text or reorders more than a neighbour.
"""

from __future__ import annotations

import re

_UNSAFE = re.compile("[᠎​‪-‮⁠-⁤⁦-⁩﻿\U000e0000-\U000e007f]")


def unsafe_characters(text: str) -> list[str]:
    """The unsafe characters in ``text`` as ``U+XXXX``, each once, in the order they first come."""
    names: dict[str, None] = {}
    for match in _UNSAFE.finditer(text):
        names[f"U+{ord(match.group()):04X}"] = None
    return list(names)


def strip_unsafe(text: str) -> str:
    return _UNSAFE.sub("", text)
