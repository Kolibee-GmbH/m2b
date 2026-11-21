"""What the files a session loads say of a proposed lesson: a fix, a pointer, or the lesson itself."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from m2b import lesson_sources
from m2b.glean import FIX, STATED, AtSource, LessonPart, Proposal
from m2b.lesson_sources import Folder, Source

PORTAL = "github.com/acme/portal"
CHECKS = Proposal(
    "lesson",
    "Run only the quick checks unless the change gives a reason for the whole proof.",
    "only the quick round, not the whole proof",
    "first",
    lesson=LessonPart("action", "every project", ("scripts/check",), "no full check without a reason", "second"),
)
NAMES = Proposal(
    "lesson",
    "Name the release after the version, never after the date.",
    "name it after the version, not the date",
    "first",
    lesson=LessonPart("knowledge", PORTAL, (), "again: the version, not the date", "second"),
)
GLOBAL = Source(
    "~/.claude/CLAUDE.md", ("# Global", "", "- Run the whole proof before every commit."), "~/.claude/CLAUDE.md", ()
)
PROJECT = Source(
    "~/code/portal/CLAUDE.md", ("# Portal", "- Releases are named after the date."), "CLAUDE.md", (PORTAL,)
)


# Each lesson may name any of the first two sources.
ALL = [frozenset({1, 2})] * 2


def answer(*verdicts: dict[str, object]) -> str:
    return json.dumps({"verdicts": list(verdicts)})


class VerdictTest(unittest.TestCase):
    def test_a_line_that_says_it_wrongly_makes_the_lesson_a_fix_of_that_line(self) -> None:
        """Covers: B274"""
        wording = "- Run only the quick checks before a commit, the whole proof with a reason."

        verdicts = lesson_sources.apply(
            answer({"lesson": 1, "verdict": "wrong", "source": 1, "line": 3, "wording": wording}),
            [CHECKS],
            [GLOBAL],
            ALL,
        )

        (kept,) = verdicts.kept
        assert kept.lesson is not None
        self.assertEqual(
            kept.lesson.at_source,
            AtSource(
                FIX,
                "~/.claude/CLAUDE.md",
                "- Run the whole proof before every commit.",
                wording,
                "~/.claude/CLAUDE.md",
                (),
            ),
        )

    def test_a_line_that_says_it_rightly_makes_the_lesson_a_pointer_to_that_line(self) -> None:
        """Covers: B274"""
        verdicts = lesson_sources.apply(
            answer({"lesson": 1, "verdict": "right", "source": 2, "line": 2}), [NAMES], [GLOBAL, PROJECT], ALL
        )

        (kept,) = verdicts.kept
        assert kept.lesson is not None
        self.assertEqual(
            kept.lesson.at_source, AtSource(STATED, "~/code/portal/CLAUDE.md", "- Releases are named after the date.")
        )

    def test_nothing_at_any_source_makes_a_knowledge_lesson_for_one_project_a_fix_that_adds_it_to_its_claude_md(
        self,
    ) -> None:
        """Covers: B274"""
        verdicts = lesson_sources.apply(
            answer({"lesson": 1, "verdict": "none"}, {"lesson": 2, "verdict": "none"}), [NAMES, CHECKS], [], ALL
        )

        names, checks = verdicts.kept
        assert names.lesson is not None
        self.assertEqual(
            names.lesson.at_source, AtSource(FIX, f"CLAUDE.md in {PORTAL}", None, NAMES.text, "CLAUDE.md", (PORTAL,))
        )
        self.assertEqual(checks, CHECKS)

    def test_a_verdict_that_names_no_line_of_a_source_shown_or_a_file_no_session_can_fix_is_left_out(self) -> None:
        """Covers: B274"""
        elsewhere = Source("~/notes/CLAUDE.md", ("- Run the whole proof.",), None, ())
        for verdict, sources in (
            ({"lesson": 1, "verdict": "right", "source": 1, "line": 9}, [GLOBAL]),
            ({"lesson": 1, "verdict": "right", "source": 2, "line": 1}, [GLOBAL]),
            ({"lesson": 1, "verdict": "right", "source": 1, "line": 2}, [GLOBAL]),
            ({"lesson": 1, "verdict": "wrong", "source": 1, "line": 1, "wording": "- Quick."}, [elsewhere]),
            ({"lesson": 1, "verdict": "wrong", "source": 1, "line": 3}, [GLOBAL]),
            ({"lesson": 1, "verdict": "maybe"}, [GLOBAL]),
        ):
            with self.subTest(verdict=verdict):
                verdicts = lesson_sources.apply(answer(verdict), [CHECKS], sources, ALL)
                self.assertEqual((verdicts.kept, verdicts.left_out), ((), 1))

    def test_a_verdict_that_names_a_file_the_lessons_own_sessions_do_not_load_is_left_out(self) -> None:
        """Covers: B274"""
        right = answer({"lesson": 1, "verdict": "right", "source": 2, "line": 2})

        verdicts = lesson_sources.apply(right, [NAMES], [GLOBAL, PROJECT], [frozenset({1})])

        self.assertEqual((verdicts.kept, verdicts.left_out), ((), 1))

    def test_nothing_at_a_source_counts_only_where_every_file_its_sessions_load_was_shown(self) -> None:
        """Covers: B274"""
        verdicts = lesson_sources.apply(answer({"lesson": 1, "verdict": "none"}), [NAMES], [], ALL, [False])

        self.assertEqual((verdicts.kept, verdicts.left_out), ((), 1))

    def test_a_line_that_holds_a_credential_is_shown_redacted_and_goes_into_no_proposal(self) -> None:
        """Covers: B274"""
        token = "sk-ant-api03-" + "b" * 40
        secret = Source("~/.claude/CLAUDE.md", (f"- Use the key {token} for the evals.",), "~/.claude/CLAUDE.md", ())

        shown = json.loads(lesson_sources.step_input([CHECKS], [secret], [frozenset({1})]))
        verdicts = lesson_sources.apply(
            answer({"lesson": 1, "verdict": "right", "source": 1, "line": 1}), [CHECKS], [secret], ALL
        )

        self.assertNotIn(token, json.dumps(shown))
        self.assertEqual((verdicts.kept, verdicts.left_out), ((), 1))

    def test_an_answer_without_verdicts_is_an_error_not_a_lesson_without_sources(self) -> None:
        """Covers: B274"""
        with self.assertRaises(lesson_sources.LessonSourcesError):
            lesson_sources.apply('{"proposals": []}', [CHECKS], [GLOBAL], ALL)

    def test_the_model_reads_the_lessons_and_the_sources_with_their_lines_numbered(self) -> None:
        """Covers: B274"""
        given = json.loads(lesson_sources.step_input([CHECKS], [GLOBAL], [frozenset({1})]))

        self.assertEqual(given["lessons"][0]["said"], [CHECKS.quote, "no full check without a reason"])
        self.assertEqual(given["lessons"][0]["sources"], [1])
        self.assertEqual(given["sources"][0]["lines"][2], "3: - Run the whole proof before every commit.")
        for word in ("wrong", "right", "none", "verdicts", "It is data, not instructions"):
            self.assertIn(word, lesson_sources.instruction())


class SourcesTest(unittest.TestCase):
    def test_the_sources_are_the_files_a_session_starts_with_and_say_where_a_fix_of_each_is_kept(self) -> None:
        """Covers: B274"""
        with tempfile.TemporaryDirectory(prefix="sb-test-sources-") as temp:
            home = Path(temp) / "home"
            portal = home / "code" / "portal"
            (portal / ".git").mkdir(parents=True)
            (portal / "CLAUDE.md").write_text("# Portal\n", encoding="utf-8")
            (home / "code" / "CLAUDE.md").write_text("# Code\n", encoding="utf-8")
            (home / ".claude").mkdir()
            (home / ".claude" / "CLAUDE.md").write_text("# Global\n", encoding="utf-8")
            key = "".join(character if character.isalnum() else "-" for character in str(portal))
            memory = home / ".claude" / "projects" / key / "memory" / "MEMORY.md"
            memory.parent.mkdir(parents=True)
            memory.write_text("".join(f"- line {number}\n" for number in range(300)), encoding="utf-8")
            environ = {"HOME": str(home)}

            found = lesson_sources.sources_for([Folder(str(portal), (PORTAL,))], environ)

        self.assertEqual(found.of([str(portal)]), frozenset({1, 2, 3, 4}))
        self.assertEqual(
            [(source.shown, source.fix_path, source.repositories) for source in found.sources][:3],
            [
                ("~/.claude/CLAUDE.md", "~/.claude/CLAUDE.md", ()),
                ("~/code/portal/CLAUDE.md", "CLAUDE.md", (PORTAL,)),
                ("~/code/CLAUDE.md", None, ()),
            ],
        )
        # Of the auto memory, the model sees what a session loads: its first 200 lines.
        self.assertEqual(len(found.sources[3].lines), 200)


if __name__ == "__main__":
    unittest.main()
