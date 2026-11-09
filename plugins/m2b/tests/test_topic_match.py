"""When a topic counts as named: its words in a prompt or a project path."""

from __future__ import annotations

import unicodedata
import unittest

from m2b.notes.memory_index import Topic
from m2b.topic_match import named_topics, names_topic, names_topic_in_path, path_text

ACME = Topic("Acme Ltd", ("Acme", "Kim Lee"))
ZURICH = Topic("Zürich office", ("Zürich Office",))
NODE = Topic("Node tooling", ("node.js", "C++"))


class NamesTopicTest(unittest.TestCase):
    def test_a_word_counts_whole_and_regardless_of_case(self) -> None:
        """Covers: B45"""
        for text, expected in (
            ("Mail an Kim wegen ACME-Export", True),
            ("acme", True),
            ("(acme)", True),
            ("Acmes Export", False),
            ("subacme", False),
            ("Kim and Lee", False),
            ("kim   lee called", True),
        ):
            with self.subTest(text=text):
                self.assertEqual(names_topic(ACME, text), expected)

    def test_decomposed_umlauts_match_composed_ones(self) -> None:
        """Covers: B45"""
        decomposed = unicodedata.normalize("NFD", "Notes from the zürich office")

        self.assertTrue(names_topic(ZURICH, decomposed))

    def test_words_with_punctuation_match_as_they_are(self) -> None:
        """Covers: B45"""
        self.assertTrue(names_topic(NODE, "upgrade node.js today"))
        self.assertTrue(names_topic(NODE, "a C++ build"))
        self.assertFalse(names_topic(NODE, "node js"))

    def test_an_inflected_form_does_not_match(self) -> None:
        self.assertFalse(names_topic(Topic("Müller", ("Müller AG", "Müller")), "Müllers Angebot"))

    def test_a_word_under_three_characters_never_matches(self) -> None:
        self.assertFalse(names_topic(Topic("X", ("ab", "x")), "ab x"))


class PathTextTest(unittest.TestCase):
    def test_separators_in_a_path_count_as_spaces(self) -> None:
        """Covers: B45"""
        text = path_text("/home/alex/.herdr/tasks/kim-lee_export.v2")

        self.assertTrue(names_topic(ACME, text))

    def test_a_word_with_separators_matches_a_path_written_with_others(self) -> None:
        """Covers: B45"""
        hans = Topic("Müller AG", ("Hans-Peter Müller",))

        self.assertTrue(names_topic_in_path(hans, "/home/alex/tasks/offer_hans_peter_müller"))
        self.assertTrue(names_topic_in_path(NODE, "/home/alex/code/node-js-upgrade"))
        self.assertFalse(names_topic(NODE, "node js upgrade"))

    def test_camel_case_in_a_path_does_not_match(self) -> None:
        self.assertFalse(names_topic(ACME, path_text("/home/alex/code/KimLeeExport")))


class NamedTopicsTest(unittest.TestCase):
    def test_every_topic_a_text_names_comes_in_file_order(self) -> None:
        """Covers: B45"""
        shared = Topic("Kim's club", ("Kim Lee", "Chess Club"))

        self.assertEqual(named_topics([ACME, ZURICH, shared], "call Kim Lee"), [ACME, shared])

    def test_nothing_named_gives_nothing(self) -> None:
        self.assertEqual(named_topics([ACME], "write the release notes"), [])


if __name__ == "__main__":
    unittest.main()
