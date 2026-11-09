"""The text the curator writes for the owner, in the profile's language.

One JSON file per language in the plugin's ``locale/`` folder maps keys to text with
``{field}`` placeholders. English is complete; another language may lack a key, which then
falls back to English.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

LOCALE_DIR = Path(__file__).resolve().parents[2] / "locale"
DEFAULT_LANGUAGE = "en"


class UnknownLanguageError(ValueError):
    """No locale file exists for the language."""


class UnknownTextError(LookupError):
    """Neither the language nor English has the key."""


@dataclass(frozen=True)
class Locale:
    language: str
    texts: Mapping[str, str]
    fallback: Mapping[str, str]

    def text(self, key: str, **fields: object) -> str:
        template = self.texts.get(key, self.fallback.get(key))
        if template is None:
            raise UnknownTextError(f"no text for {key!r} in {self.language} or {DEFAULT_LANGUAGE}")
        return template.format(**fields)


def available_languages(directory: Path = LOCALE_DIR) -> tuple[str, ...]:
    return tuple(sorted(path.stem for path in directory.glob("*.json")))


def load_locale(language: str, directory: Path = LOCALE_DIR) -> Locale:
    if language not in available_languages(directory):
        raise UnknownLanguageError(
            f"no locale for {language!r}; available: {', '.join(available_languages(directory))}"
        )
    return Locale(
        language=language,
        texts=_read(directory / f"{language}.json"),
        fallback=_read(directory / f"{DEFAULT_LANGUAGE}.json"),
    )


def _read(path: Path) -> Mapping[str, str]:
    texts: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
    return texts
