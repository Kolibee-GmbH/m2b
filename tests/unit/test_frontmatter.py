from __future__ import annotations

import datetime
import unittest
from zoneinfo import ZoneInfo

from m2b.notes import frontmatter
from m2b.notes.frontmatter import Frontmatter, Note, NoteFormatError

ZURICH = ZoneInfo("Europe/Zurich")

PLAIN = "---\ncreated: 2026-03-29T01:30:00+01:00\nsource: claude\n---\nAlex prefers  green tea.\n"


class RoundTripTest(unittest.TestCase):
    def test_files_come_back_byte_for_byte(self) -> None:
        """Covers: X14"""
        cases = {
            "plain": PLAIN,
            "crlf": PLAIN.replace("\n", "\r\n"),
            "block at the very end": "---\r\ncreated: 2026-03-29T01:30:00+01:00\r\nsource: claude\r\n---",
            "block at the end with newline": "---\ncreated: 2026-03-29T01:30:00+01:00\n---\n",
            "no frontmatter": "Just a thought\nwithout a block.\n",
            "unclosed block": "---\ncreated: 2026-03-29T01:30:00+01:00\nno closing line\n",
            "empty block": "---\n---\nbody\n",
            "unknown keys and odd lines": "---\nsource: cli\nmood: sunny\n# a comment\n\nweird line\n---\nbody",
            "mixed endings": "---\r\ncreated: 2026-03-29T01:30:00+01:00\nsource: cli\r\n---\nbody\r\nmore\n",
            "carriage return inside a line": "---\nsource: cli\n---\nprogress\rdone\n",
        }
        for label, text in cases.items():
            with self.subTest(label):
                self.assertEqual(Note.parse(text).render(), text)

    def test_crlf_and_a_block_at_the_end_are_read(self) -> None:
        """Covers: X14"""
        note = Note.parse("---\r\ncreated: 2026-03-29T01:30:00+01:00\r\nsource: claude\r\n---")

        assert note.frontmatter is not None
        self.assertEqual(note.frontmatter.get("source"), "claude")
        self.assertEqual(note.body, "")

    def test_a_file_without_a_closing_line_has_no_frontmatter(self) -> None:
        note = Note.parse("---\nsource: cli\nstill the body\n")

        self.assertIsNone(note.frontmatter)
        self.assertEqual(note.body, "---\nsource: cli\nstill the body\n")

    def test_a_changed_key_rewrites_only_its_line_in_the_files_line_ending(self) -> None:
        note = Note.parse(PLAIN.replace("\n", "\r\n").replace("source: claude", "source:   claude  "))
        assert note.frontmatter is not None

        note.frontmatter.set("kind", "worklog")
        note.frontmatter.set("created", "2026-03-29T01:31:00+01:00")

        self.assertEqual(
            note.render(),
            "---\r\ncreated: 2026-03-29T01:31:00+01:00\r\nsource:   claude  \r\nkind: worklog\r\n---\r\n"
            "Alex prefers  green tea.\r\n",
        )

    def test_a_key_added_to_a_block_at_the_very_end_keeps_the_file_ending_bare(self) -> None:
        note = Note.parse("---\nsource: cli\n---")
        assert note.frontmatter is not None

        note.frontmatter.set("quiet", True)

        self.assertEqual(note.render(), "---\nsource: cli\nquiet: true\n---")


class ValuesTest(unittest.TestCase):
    def _frontmatter(self, *lines: str) -> Frontmatter:
        note = Note.parse("---\n" + "".join(f"{line}\n" for line in lines) + "---\n")
        assert note.frontmatter is not None
        return note.frontmatter

    def test_scalars_lists_and_flags(self) -> None:
        fields = self._frontmatter("source: cli", "tasks: [a1b2, c3d4]", "refs: []", "curated: true", "quiet: yes")

        self.assertEqual(fields.get("source"), "cli")
        self.assertEqual(fields.get_list("tasks"), ["a1b2", "c3d4"])
        self.assertEqual(fields.get_list("refs"), [])
        self.assertEqual(fields.get_list("missing"), [])
        self.assertTrue(fields.get_flag("curated"))
        self.assertFalse(fields.get_flag("quiet"))
        self.assertIsNone(fields.get("missing"))

    def test_keys_keep_their_order_and_unknown_keys_are_kept(self) -> None:
        fields = self._frontmatter("source: cli", "mood: sunny", "created: 2026-03-29T01:30:00+01:00")

        self.assertEqual(fields.keys(), ["source", "mood", "created"])

    def test_a_list_key_holding_a_scalar_is_a_format_error(self) -> None:
        with self.assertRaises(NoteFormatError):
            self._frontmatter("refs: a.md").get_list("refs")

    def test_adding_refs_merges_in_order_and_drops_duplicates(self) -> None:
        """Covers: X10"""
        fields = self._frontmatter("refs: [a]")

        fields.add_to_list("refs", ["b"])
        self.assertEqual(fields.get_list("refs"), ["a", "b"])
        fields.add_to_list("refs", ["a"])
        self.assertEqual(fields.get_list("refs"), ["a", "b"])
        fields.add_to_list("refs", ["c", "c", "b"])
        self.assertEqual(fields.get_list("refs"), ["a", "b", "c"])

    def test_a_trailing_comma_in_a_hand_edited_list_is_no_item(self) -> None:
        """Covers: X10"""
        fields = self._frontmatter("refs: [a.md,  ]")

        self.assertEqual(fields.get_list("refs"), ["a.md"])
        fields.add_to_list("refs", ["b.md"])
        self.assertEqual(fields.get_list("refs"), ["a.md", "b.md"])

    def test_adding_to_a_missing_list_creates_it(self) -> None:
        """Covers: X10"""
        fields = self._frontmatter("source: cli")

        fields.add_to_list("refs", ["https://example.com/a"])

        self.assertEqual(fields.get_list("refs"), ["https://example.com/a"])

    def test_values_the_format_cannot_hold_are_refused(self) -> None:
        fields = self._frontmatter("source: cli")
        for key, value in (("refs", ["a, b"]), ("refs", ["[x]"]), ("refs", [""]), ("kind", "two\nlines")):
            with self.subTest(key=key, value=value), self.assertRaises(NoteFormatError):
                fields.set(key, value)

    def test_keys_that_are_not_lowercase_names_are_refused(self) -> None:
        with self.assertRaises(NoteFormatError):
            self._frontmatter("source: cli").set("Follow Up", "2026-04-01")

    def test_removing_a_key_drops_its_line(self) -> None:
        fields = self._frontmatter("source: cli", "follow_up: 2026-04-01")

        fields.remove("follow_up")

        self.assertEqual(fields.keys(), ["source"])


class CreatedTest(unittest.TestCase):
    def test_created_keeps_the_local_offset(self) -> None:
        """Covers: X5"""
        note = Note.new({}, "Alex prefers green tea.\n")
        assert note.frontmatter is not None

        frontmatter.set_created(note.frontmatter, datetime.datetime(2026, 3, 29, 1, 30, tzinfo=ZURICH))

        self.assertEqual(note.frontmatter.get("created"), "2026-03-29T01:30:00+01:00")

    def test_writing_created_without_offset_is_refused(self) -> None:
        """Covers: X5"""
        note = Note.new({}, "")
        assert note.frontmatter is not None

        with self.assertRaises(NoteFormatError):
            frontmatter.set_created(note.frontmatter, datetime.datetime(2026, 3, 29, 1, 30))

    def test_reading_created_without_offset_is_tolerated_and_flagged(self) -> None:
        """Covers: X5"""
        fields = Note.parse("---\ncreated: 2026-03-29T01:30:00\n---\n").frontmatter
        assert fields is not None

        created = frontmatter.read_created(fields)

        assert created is not None
        self.assertFalse(created.has_offset)
        self.assertEqual(created.value, datetime.datetime(2026, 3, 29, 1, 30))

    def test_reading_created_accepts_a_z_for_utc(self) -> None:
        fields = Note.parse("---\ncreated: 2026-03-29T00:30:00Z\n---\n").frontmatter
        assert fields is not None

        created = frontmatter.read_created(fields)

        assert created is not None
        self.assertTrue(created.has_offset)
        self.assertEqual(created.value.utcoffset(), datetime.timedelta(0))

    def test_only_the_documented_time_syntax_is_read_on_every_python(self) -> None:
        """Covers: X5"""
        for text in ("2026-03-29T01:30:00+0100", "2026-03-29T01:30:00.5+01:00", "20260329T013000+01:00", "2026-03-29"):
            fields = Note.parse(f"---\ncreated: {text}\n---\n").frontmatter
            assert fields is not None
            with self.subTest(text=text), self.assertRaises(NoteFormatError):
                frontmatter.read_created(fields)

    def test_every_write_of_created_needs_an_offset(self) -> None:
        """Covers: X5"""
        for text in ("2026-03-29T01:30:00", "soon"):
            with self.subTest(text=text), self.assertRaises(NoteFormatError):
                Note.new({frontmatter.CREATED: text}, "")

    def test_a_created_that_is_not_a_time_is_a_format_error(self) -> None:
        fields = Note.parse("---\ncreated: yesterday\n---\n").frontmatter
        assert fields is not None

        with self.assertRaises(NoteFormatError):
            frontmatter.read_created(fields)


class QuietTest(unittest.TestCase):
    def test_the_rest_marker_is_the_exact_frontmatter_line(self) -> None:
        """Covers: B4"""
        quiet = Note.parse("---\nsource: cli\nquiet: true\n---\nbody\n")
        loud_variants = [
            "---\nsource: cli\nquiet: True\n---\nbody\n",
            "---\nsource: cli\nquiet:true\n---\nbody\n",
            "---\nsource: cli\nquiet: true # please\n---\nbody\n",
            "---\nsource: cli\n---\nquiet: true\n",
            "quiet: true\n",
        ]

        self.assertTrue(quiet.is_quiet)
        for text in loud_variants:
            with self.subTest(text=text):
                self.assertFalse(Note.parse(text).is_quiet)

    def test_the_rest_marker_counts_with_crlf_line_endings(self) -> None:
        """Covers: B4"""
        self.assertTrue(Note.parse("---\r\nquiet: true\r\n---\r\n").is_quiet)

    def test_setting_quiet_writes_the_exact_marker_line(self) -> None:
        """Covers: B4"""
        note = Note.new({"source": "cli"}, "body\n")
        assert note.frontmatter is not None

        note.frontmatter.set(frontmatter.QUIET, True)

        self.assertIn("\nquiet: true\n", note.render())
        self.assertTrue(Note.parse(note.render()).is_quiet)


class NewNoteTest(unittest.TestCase):
    def test_a_new_note_renders_its_keys_in_order_and_the_body_as_given(self) -> None:
        note = Note.new({"created": "2026-03-29T01:30:00+01:00", "source": "claude", "tasks": []}, "Alex  likes tea")

        self.assertEqual(
            note.render(), "---\ncreated: 2026-03-29T01:30:00+01:00\nsource: claude\ntasks: []\n---\nAlex  likes tea"
        )


if __name__ == "__main__":
    unittest.main()
