"""Which topics a session has been shown, so a topic comes in once per session."""

from __future__ import annotations

import datetime
import os
import tempfile
import unittest
from pathlib import Path

from m2b import topic_state
from m2b.paths import MachinePaths

NOW = datetime.datetime(2026, 11, 8, 9, 0).astimezone()
SESSION = "ea4af7eb-7f1d-4eab-aac2-987397455c4b"


class TopicStateTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.machine = MachinePaths(Path(temp.name))

    def test_a_new_session_starts_with_what_its_start_showed(self) -> None:
        """Covers: B47"""
        topic_state.start_session(self.machine, SESSION, "startup", ["Acme Ltd"], NOW)

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
                topic_state.start_session(self.machine, SESSION, "startup", ["Acme Ltd"], NOW)
                topic_state.start_session(self.machine, SESSION, source, ["Globex"], NOW)
                self.assertEqual(topic_state.shown_topics(self.machine, SESSION), expected)

    def test_topics_shown_later_are_added(self) -> None:
        topic_state.start_session(self.machine, SESSION, "startup", [], NOW)
        topic_state.add_shown(self.machine, SESSION, ["Acme Ltd"])
        topic_state.add_shown(self.machine, SESSION, ["Globex", "Acme Ltd"])

        self.assertEqual(topic_state.shown_topics(self.machine, SESSION), {"Acme Ltd", "Globex"})

    def test_a_session_id_that_is_no_plain_name_is_never_a_file(self) -> None:
        for session_id in ("../escape", "a/b", "", "x" * 200, None, "ä"):
            with self.subTest(session_id=session_id):
                topic_state.start_session(self.machine, session_id, "startup", ["Acme Ltd"], NOW)
                topic_state.add_shown(self.machine, session_id, ["Acme Ltd"])
                self.assertEqual(topic_state.shown_topics(self.machine, session_id), set())
        folder = self.machine.state_dir / topic_state.TOPICS_FOLDER
        self.assertEqual(list(folder.iterdir()) if folder.exists() else [], [])

    def test_lists_older_than_seven_days_are_removed_when_a_session_starts(self) -> None:
        topic_state.start_session(self.machine, "old-session", "startup", ["Acme Ltd"], NOW)
        topic_state.start_session(self.machine, "recent-session", "startup", ["Acme Ltd"], NOW)
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


if __name__ == "__main__":
    unittest.main()
