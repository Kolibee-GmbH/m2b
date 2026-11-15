"""Which topics a session has been shown, so a topic comes in once per session."""

from __future__ import annotations

import datetime
import json
import os
import tempfile
import unittest
from pathlib import Path

from m2b import topic_state
from m2b.paths import MachinePaths
from m2b.topic_state import Given, Session

NOW = datetime.datetime(2026, 11, 8, 9, 0).astimezone()
SESSION = "ea4af7eb-7f1d-4eab-aac2-987397455c4b"


class TopicStateTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.machine = MachinePaths(Path(temp.name))

    def test_a_new_session_starts_with_what_its_start_showed(self) -> None:
        """Covers: B47"""
        topic_state.start_session(self.machine, SESSION, "startup", [Given("Acme Ltd")], NOW)

        self.assertEqual(topic_state.shown_topics(self.machine, SESSION), {"Acme Ltd"})

    def test_clear_and_compact_forget_what_was_shown_and_resume_keeps_it(self) -> None:
        """Covers: B47"""
        for source, expected in (
            ("clear", {"Globex"}),
            ("compact", {"Globex"}),
            ("startup", {"Globex"}),
            (None, {"Globex"}),
            ("resume", {"Acme Ltd", "Globex"}),
        ):
            with self.subTest(source=source):
                topic_state.start_session(self.machine, SESSION, "startup", [Given("Acme Ltd")], NOW)
                topic_state.start_session(self.machine, SESSION, source, [Given("Globex")], NOW)
                self.assertEqual(topic_state.shown_topics(self.machine, SESSION), expected)

    def test_topics_shown_later_are_added(self) -> None:
        topic_state.start_session(self.machine, SESSION, "startup", [], NOW)
        topic_state.add_shown(self.machine, SESSION, [Given("Acme Ltd")])
        topic_state.add_shown(self.machine, SESSION, [Given("Globex"), Given("Acme Ltd")])

        self.assertEqual(topic_state.shown_topics(self.machine, SESSION), {"Acme Ltd", "Globex"})

    def test_a_session_id_that_is_no_plain_name_is_never_a_file(self) -> None:
        for session_id in ("../escape", "a/b", "", "x" * 200, None, "ä"):
            with self.subTest(session_id=session_id):
                topic_state.start_session(self.machine, session_id, "startup", [Given("Acme Ltd")], NOW)
                topic_state.add_shown(self.machine, session_id, [Given("Acme Ltd")])
                self.assertEqual(topic_state.shown_topics(self.machine, session_id), set())
        folder = self.machine.state_dir / topic_state.TOPICS_FOLDER
        self.assertEqual(list(folder.iterdir()) if folder.exists() else [], [])

    def test_lists_older_than_seven_days_are_removed_when_a_session_starts(self) -> None:
        topic_state.start_session(self.machine, "old-session", "startup", [Given("Acme Ltd")], NOW)
        topic_state.start_session(self.machine, "recent-session", "startup", [Given("Acme Ltd")], NOW)
        folder = self.machine.state_dir / topic_state.TOPICS_FOLDER
        eight_days_ago = (NOW - datetime.timedelta(days=8)).timestamp()
        os.utime(folder / "old-session.json", (eight_days_ago, eight_days_ago))

        topic_state.start_session(self.machine, SESSION, "startup", [], NOW)

        self.assertEqual(
            sorted(path.name for path in folder.iterdir()),
            ["ea4af7eb-7f1d-4eab-aac2-987397455c4b.json", "recent-session.json"],
        )

    def test_a_broken_list_counts_as_empty(self) -> None:
        folder = self.machine.state_dir / topic_state.TOPICS_FOLDER
        folder.mkdir(parents=True)
        (folder / f"{SESSION}.json").write_text("{broken", encoding="utf-8")

        self.assertEqual(topic_state.shown_topics(self.machine, SESSION), set())
        self.assertIsNone(topic_state.session(self.machine, SESSION))


class WhatASessionWasGivenTest(unittest.TestCase):
    """Beside the names: how many lines each topic brought, and how the start printed the distillate."""

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.machine = MachinePaths(Path(temp.name))

    def test_a_session_keeps_the_lines_of_each_topic_and_how_its_start_printed(self) -> None:
        """Covers: B183"""
        topic_state.start_session(self.machine, SESSION, "startup", [Given("Acme Ltd", 3, 1)], NOW, topic_state.WHOLE)
        topic_state.add_shown(self.machine, SESSION, [Given("Globex", 2, 0)])

        self.assertEqual(
            topic_state.session(self.machine, SESSION),
            Session((Given("Acme Ltd", 3, 1), Given("Globex", 2, 0)), topic_state.WHOLE),
        )

    def test_a_resumed_session_keeps_what_it_had_and_takes_the_new_print(self) -> None:
        """Covers: B183"""
        topic_state.start_session(self.machine, SESSION, "startup", [Given("Acme Ltd", 3, 1)], NOW, topic_state.WHOLE)
        topic_state.start_session(self.machine, SESSION, "resume", [Given("Globex", 2, 0)], NOW, topic_state.CUT)

        self.assertEqual(
            topic_state.session(self.machine, SESSION),
            Session((Given("Acme Ltd", 3, 1), Given("Globex", 2, 0)), topic_state.CUT),
        )

    def test_a_compaction_and_a_clear_start_over_so_only_what_came_since_is_kept(self) -> None:
        """Covers: B183"""
        for source in ("compact", "clear"):
            with self.subTest(source=source):
                topic_state.start_session(
                    self.machine, SESSION, "startup", [Given("Acme Ltd", 3, 1)], NOW, topic_state.CUT
                )
                topic_state.start_session(self.machine, SESSION, source, [], NOW, topic_state.WHOLE)
                topic_state.add_shown(self.machine, SESSION, [Given("Globex", 2, 0)])

                self.assertEqual(
                    topic_state.session(self.machine, SESSION), Session((Given("Globex", 2, 0),), topic_state.WHOLE)
                )

    def test_a_topic_given_again_is_counted_as_it_came_last(self) -> None:
        """Covers: B183"""
        topic_state.start_session(self.machine, SESSION, "startup", [Given("Acme Ltd", 3, 1)], NOW, topic_state.WHOLE)
        topic_state.start_session(self.machine, SESSION, "resume", [Given("Acme Ltd", 4, 1)], NOW, topic_state.WHOLE)

        self.assertEqual(
            topic_state.session(self.machine, SESSION), Session((Given("Acme Ltd", 4, 1),), topic_state.WHOLE)
        )

    def test_a_list_from_before_the_counts_reads_with_names_alone(self) -> None:
        """Covers: B183"""
        folder = self.machine.state_dir / topic_state.TOPICS_FOLDER
        folder.mkdir(parents=True)
        (folder / f"{SESSION}.json").write_text('{"shown": ["Globex", "Acme Ltd"]}\n', encoding="utf-8")

        self.assertEqual(
            topic_state.session(self.machine, SESSION), Session((Given("Acme Ltd"), Given("Globex")), None)
        )
        self.assertEqual(topic_state.shown_topics(self.machine, SESSION), {"Acme Ltd", "Globex"})

    def test_counts_and_a_print_that_are_not_in_the_form_count_as_unknown(self) -> None:
        folder = self.machine.state_dir / topic_state.TOPICS_FOLDER
        folder.mkdir(parents=True)
        written = {
            "shown": ["Acme Ltd", "Globex"],
            "given": {"Acme Ltd": {"facts": "3", "current": -1}, "Globex": 7},
            "distillate": "all of it",
        }
        (folder / f"{SESSION}.json").write_text(json.dumps(written), encoding="utf-8")

        self.assertEqual(
            topic_state.session(self.machine, SESSION), Session((Given("Acme Ltd"), Given("Globex")), None)
        )

    def test_a_session_that_never_started_here_is_not_known(self) -> None:
        """Covers: B183"""
        self.assertIsNone(topic_state.session(self.machine, SESSION))

    def test_a_note_without_its_list_of_names_is_not_known_and_the_hooks_start_from_nothing(self) -> None:
        """Covers: B183"""
        folder = self.machine.state_dir / topic_state.TOPICS_FOLDER
        folder.mkdir(parents=True)
        for written in ("{}", '{"shown": "Acme Ltd"}', "[]", "{broken"):
            with self.subTest(written=written):
                (folder / f"{SESSION}.json").write_text(written, encoding="utf-8")

                self.assertIsNone(topic_state.session(self.machine, SESSION))
                self.assertEqual(topic_state.shown_topics(self.machine, SESSION), set())

    def test_a_session_only_a_prompt_noted_has_no_print_of_its_start(self) -> None:
        topic_state.add_shown(self.machine, SESSION, [Given("Globex", 2, 0)])

        self.assertEqual(topic_state.session(self.machine, SESSION), Session((Given("Globex", 2, 0),), None))

    def test_only_letters_digits_and_dashes_are_a_session_id(self) -> None:
        self.assertTrue(topic_state.is_session_id(SESSION))
        for session_id in ("../escape", "a/b", "", "x" * 200, "ä", "a b", "a\n"):
            with self.subTest(session_id=session_id):
                self.assertFalse(topic_state.is_session_id(session_id))
                self.assertIsNone(topic_state.session(self.machine, session_id))


if __name__ == "__main__":
    unittest.main()
