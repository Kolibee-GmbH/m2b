from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from m2b import locale


class ShippedLocalesTest(unittest.TestCase):
    def test_english_and_german_ship(self) -> None:
        self.assertEqual(locale.available_languages(), ("de", "en"))

    def test_every_language_has_exactly_the_keys_of_english(self) -> None:
        english = set(_keys("en"))
        for language in locale.available_languages():
            with self.subTest(language=language):
                self.assertEqual(set(_keys(language)), english)

    def test_german_text_comes_from_the_german_file(self) -> None:
        german = locale.load_locale("de").text("review.title")

        self.assertEqual(german, _keys("de")["review.title"])
        self.assertNotEqual(german, locale.load_locale("en").text("review.title"))


class LookupTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.directory = Path(self._temp.name)
        _write(self.directory / "en.json", {"greeting": "Hello {name}", "only.english": "fallback"})
        _write(self.directory / "de.json", {"greeting": "Hallo {name}"})

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_a_key_missing_in_the_language_falls_back_to_english(self) -> None:
        self.assertEqual(locale.load_locale("de", self.directory).text("only.english"), "fallback")

    def test_fields_are_filled_in(self) -> None:
        self.assertEqual(locale.load_locale("de", self.directory).text("greeting", name="Dana"), "Hallo Dana")

    def test_a_key_missing_everywhere_is_an_error(self) -> None:
        with self.assertRaises(locale.UnknownTextError):
            locale.load_locale("en", self.directory).text("nowhere")

    def test_an_unknown_language_is_an_error(self) -> None:
        with self.assertRaises(locale.UnknownLanguageError):
            locale.load_locale("fr", self.directory)


def _keys(language: str) -> dict[str, str]:
    data: dict[str, str] = json.loads((locale.LOCALE_DIR / f"{language}.json").read_text(encoding="utf-8"))
    return data


def _write(path: Path, data: dict[str, str]) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
