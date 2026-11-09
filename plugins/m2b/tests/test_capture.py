"""Capture: one new inbox file per capture, text verbatim, and an optional follow-up task."""

from __future__ import annotations

import contextlib
import datetime
import errno
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from m2b import cli, paths
from m2b.capture import FOLLOW_UP_KEY, NOT_SAVED, NotSavedError, capture
from m2b.commands import capture as capture_commands
from m2b.config import machine
from m2b.config.store_settings import save_store_settings
from m2b.notes.frontmatter import Note
from m2b.notes.names import NoteName
from m2b.store import base as store_base
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard
from m2b.tasks import markers
from m2b.tasks.base import Due, TasksUnreachableError, UnconfirmedTaskError
from m2b.tasks.markdown import MarkdownTasks
from store_contract import FakeEviction
from tasks_contract import local_date

FAKES = Path(__file__).resolve().parent / "fakes"
NOW = datetime.datetime(2026, 11, 7, 10, 15, 0).astimezone()
# What the file system answers when a capture cannot be written: a folder without write
# permission, a full disk, a volume mounted read-only.
WRITE_ERRORS = (
    PermissionError(errno.EACCES, os.strerror(errno.EACCES)),
    OSError(errno.ENOSPC, os.strerror(errno.ENOSPC)),
    OSError(errno.EROFS, os.strerror(errno.EROFS)),
)


class StoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        self.store_root = self.root / "store"
        self.store_root.mkdir()
        self.store = FolderStore(self.store_root, self.root / "machine-tmp", DatalessGuard(False))

    def inbox(self) -> dict[str, str]:
        folder = self.store_root / "inbox"
        return {p.name: p.read_text(encoding="utf-8") for p in sorted(folder.iterdir())} if folder.is_dir() else {}


class UnreachableTasks(MarkdownTasks):
    def add(self, title: str, notes: str = "", due: Due | None = None) -> str:
        raise TasksUnreachableError("Reminders answered with no lists at all")


class NotesFailTasks(MarkdownTasks):
    def set_notes(self, task_id: str, notes: str) -> None:
        raise TasksUnreachableError("Reminders did not answer within 20 seconds")


class StuckTasks(NotesFailTasks):
    def delete(self, task_id: str) -> None:
        raise TasksUnreachableError("Reminders did not answer within 20 seconds")


class UnconfirmedTasks(MarkdownTasks):
    def add(self, title: str, notes: str = "", due: Due | None = None) -> str:
        raise UnconfirmedTaskError("the reminder was added but could not be found again")


class CaptureTest(StoreTestCase):
    def test_the_text_is_kept_byte_for_byte_with_one_newline_added(self) -> None:
        """Covers: B1"""
        text = "Dana  prefers tea,, not coffe\n\n  (ask again)"

        result = capture(self.store, text, source="cli", now=NOW)

        (name, content) = self.inbox().popitem()
        self.assertEqual(f"inbox/{name}", result.path)
        note = Note.parse(content)
        self.assertEqual(note.body, text + "\n")
        assert note.frontmatter is not None
        self.assertEqual(note.frontmatter.get("source"), "cli")
        self.assertEqual(note.frontmatter.get("created"), NOW.isoformat(timespec="seconds"))
        self.assertEqual(NoteName.parse(name), NoteName.for_capture(NOW, "cli", suffix=name[-7:-3]))

    def test_a_text_ending_in_a_newline_gets_none_added(self) -> None:
        """Covers: B1"""
        capture(self.store, "Buy milk\n", source="cli", now=NOW)

        (content,) = self.inbox().values()
        self.assertTrue(content.endswith("\nBuy milk\n"))

    def test_two_captures_in_the_same_second_get_different_names(self) -> None:
        """Covers: B2"""
        with mock.patch("m2b.notes.names.secrets") as names_secrets:
            names_secrets.token_hex.side_effect = ["3f9a", "3f9a", "0b1c"]
            first = capture(self.store, "first", source="cli", now=NOW)
            second = capture(self.store, "second", source="cli", now=NOW)

        self.assertNotEqual(first.path, second.path)
        self.assertEqual(sorted(Note.parse(c).body for c in self.inbox().values()), ["first\n", "second\n"])

    def test_empty_text_writes_nothing_not_even_the_inbox_folder(self) -> None:
        """Covers: B3"""
        for text in ("", "  \n\t\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                capture(self.store, text, source="cli", now=NOW)

        self.assertFalse((self.store_root / "inbox").exists())

    def test_quiet_sets_the_rest_marker_line(self) -> None:
        """Covers: B4"""
        capture(self.store, "Not for replay", source="cli", quiet=True, now=NOW)

        (content,) = self.inbox().values()
        self.assertTrue(Note.parse(content).is_quiet)
        self.assertIn("\nquiet: true\n", content)

    def test_a_quiet_word_in_the_text_is_no_rest_marker(self) -> None:
        """Covers: B4"""
        capture(self.store, "quiet: true", source="cli", now=NOW)

        (content,) = self.inbox().values()
        self.assertFalse(Note.parse(content).is_quiet)

    def test_a_source_that_is_no_lowercase_token_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            capture(self.store, "text", source="Claude Code", now=NOW)
        self.assertFalse((self.store_root / "inbox").exists())


class FollowUpTest(StoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tasks = MarkdownTasks(self.store)

    def test_the_task_names_the_capture_and_the_capture_records_the_task(self) -> None:
        """Covers: B32"""
        result = capture(
            self.store,
            "Call Dana about the shed",
            source="cli",
            follow_up=datetime.date(2026, 11, 20),
            tasks=self.tasks,
            now=NOW,
        )

        (task,) = self.tasks.items()
        (content,) = self.inbox().values()
        name = result.path.rsplit("/", 1)[1]
        self.assertEqual((task.title, local_date(task.due)), ("Call Dana about the shed", datetime.date(2026, 11, 20)))
        self.assertEqual(task.marker, markers.CAPTURE)
        self.assertEqual(markers.marker_of(task.notes), (markers.CAPTURE, (name, FOLLOW_UP_KEY)))
        note = Note.parse(content)
        assert note.frontmatter is not None
        self.assertEqual(note.frontmatter.get_list("tasks"), [task.id])
        self.assertIsNone(note.frontmatter.get("follow_up"))
        self.assertEqual(result.task_id, task.id)

    def test_a_long_text_gives_the_task_its_first_line_shortened(self) -> None:
        capture(
            self.store,
            "\n  " + "x" * 300 + "\nsecond line",
            source="cli",
            follow_up=datetime.date(2026, 11, 20),
            tasks=self.tasks,
            now=NOW,
        )

        (task,) = self.tasks.items()
        self.assertEqual(len(task.title), 120)
        self.assertTrue(task.title.endswith("…"))

    def test_a_name_collision_corrects_the_task_before_the_file_is_written(self) -> None:
        """Covers: B2, B32"""
        self.store.create_exclusive("inbox/" + str(NoteName.for_capture(NOW, "cli", suffix="3f9a")), b"taken\n")

        with mock.patch("m2b.notes.names.secrets") as names_secrets:
            names_secrets.token_hex.side_effect = ["3f9a", "0b1c"]
            result = capture(
                self.store, "Call Dana", source="cli", follow_up=datetime.date(2026, 11, 20), tasks=self.tasks, now=NOW
            )

        (task,) = self.tasks.items()
        self.assertTrue(result.path.endswith("-cli-0b1c.md"))
        self.assertIn("-cli-0b1c.md", task.notes)
        self.assertEqual(self.inbox()[result.path.rsplit("/", 1)[1]].count("tasks: ["), 1)

    def test_a_collision_whose_task_cannot_be_corrected_still_writes_the_capture(self) -> None:
        """Covers: B32"""
        self.store.create_exclusive("inbox/" + str(NoteName.for_capture(NOW, "cli", suffix="3f9a")), b"taken\n")
        tasks = NotesFailTasks(self.store)

        with mock.patch("m2b.notes.names.secrets") as names_secrets:
            names_secrets.token_hex.side_effect = ["3f9a", "0b1c"]
            result = capture(
                self.store, "Call Dana", source="cli", follow_up=datetime.date(2026, 11, 20), tasks=tasks, now=NOW
            )

        note = Note.parse(self.inbox()[result.path.rsplit("/", 1)[1]])
        assert note.frontmatter is not None
        self.assertEqual(note.frontmatter.get("follow_up"), "2026-11-20")
        self.assertEqual(note.frontmatter.get_list("tasks"), [])
        self.assertEqual(tasks.items(), [], "the task naming the other capture is removed")
        self.assertIsNone(result.task_id)

    def test_a_collision_whose_task_can_neither_be_corrected_nor_removed_is_reported(self) -> None:
        """The task stays, so ingest must not create a second one: no follow_up, and exit 1."""
        self.store.create_exclusive("inbox/" + str(NoteName.for_capture(NOW, "cli", suffix="3f9a")), b"taken\n")

        with mock.patch("m2b.notes.names.secrets") as names_secrets:
            names_secrets.token_hex.side_effect = ["3f9a", "0b1c"]
            with self.assertRaises(UnconfirmedTaskError):
                capture(
                    self.store,
                    "Call Dana",
                    source="cli",
                    follow_up=datetime.date(2026, 11, 20),
                    tasks=StuckTasks(self.store),
                    now=NOW,
                )

        note = Note.parse(self.inbox()[str(NoteName.for_capture(NOW, "cli", suffix="0b1c"))])
        assert note.frontmatter is not None
        self.assertIsNone(note.frontmatter.get("follow_up"))
        self.assertEqual(note.frontmatter.get_list("tasks"), [])

    def test_with_tasks_unreachable_the_capture_waits_with_its_follow_up_date(self) -> None:
        """Covers: B32"""
        result = capture(
            self.store,
            "Call Dana",
            source="cli",
            follow_up=datetime.date(2026, 11, 20),
            tasks=UnreachableTasks(self.store),
            now=NOW,
        )

        (content,) = self.inbox().values()
        note = Note.parse(content)
        assert note.frontmatter is not None
        self.assertEqual(note.frontmatter.get("follow_up"), "2026-11-20")
        self.assertEqual(note.frontmatter.get_list("tasks"), [])
        self.assertIsNone(result.task_id)
        self.assertIn("Reminders", result.notice or "")

    def test_a_task_added_but_not_confirmed_keeps_the_capture_and_reports_it(self) -> None:
        with self.assertRaises(UnconfirmedTaskError):
            capture(
                self.store,
                "Call Dana",
                source="cli",
                follow_up=datetime.date(2026, 11, 20),
                tasks=UnconfirmedTasks(self.store),
                now=NOW,
            )

        (content,) = self.inbox().values()
        note = Note.parse(content)
        assert note.frontmatter is not None
        self.assertIsNone(note.frontmatter.get("follow_up"), "ingest must not create a second task")
        self.assertEqual(note.body, "Call Dana\n")


class NotSavedTest(StoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tasks = MarkdownTasks(self.store)

    def capture_failing_with(self, error: OSError, tasks: MarkdownTasks | None = None) -> NotSavedError:
        tasks = tasks or self.tasks
        create_exclusive = self.store.create_exclusive

        def refuse_the_inbox(relative: str, data: bytes) -> None:
            if relative.startswith("inbox/"):
                raise error
            create_exclusive(relative, data)

        with (
            mock.patch.object(self.store, "create_exclusive", side_effect=refuse_the_inbox),
            self.assertRaises(NotSavedError) as raised,
        ):
            capture(self.store, "Call Dana", source="cli", follow_up=datetime.date(2026, 11, 20), tasks=tasks, now=NOW)
        return raised.exception

    def test_a_write_error_keeps_no_note_and_removes_the_follow_up_task(self) -> None:
        """Covers: B75"""
        for error in WRITE_ERRORS:
            with self.subTest(errno=errno.errorcode[error.errno]):
                raised = self.capture_failing_with(error)

                self.assertEqual(self.inbox(), {})
                self.assertEqual(self.tasks.items(), [], "a task pointing to no capture is removed")
                self.assertIn(NOT_SAVED, str(raised))
                self.assertIn(error.strerror, str(raised))
                self.assertNotIn("\n", str(raised))

    def test_a_write_error_without_a_file_name_names_the_inbox_folder(self) -> None:
        """Covers: B75"""
        raised = self.capture_failing_with(OSError(errno.ENOSPC, os.strerror(errno.ENOSPC)))

        self.assertIn(f"in {self.store.path('inbox')}", str(raised))

    def test_a_follow_up_task_that_cannot_be_removed_is_named(self) -> None:
        """Covers: B75"""
        tasks = StuckTasks(self.store)

        raised = self.capture_failing_with(WRITE_ERRORS[1], tasks)

        (task,) = tasks.items()
        self.assertEqual(self.inbox(), {})
        self.assertIn(NOT_SAVED, str(raised))
        self.assertIn(task.id, str(raised))

    def test_a_follow_up_task_that_was_not_confirmed_is_mentioned(self) -> None:
        """The task may exist; the owner is told to look, since nothing here can find it."""
        raised = self.capture_failing_with(WRITE_ERRORS[1], UnconfirmedTasks(self.store))

        self.assertIn(NOT_SAVED, str(raised))
        self.assertIn("task list", str(raised))

    @unittest.skipIf(os.geteuid() == 0, "root writes into a folder without write permission")
    def test_a_task_folder_that_cannot_be_written_still_saves_the_capture_with_its_follow_up_date(self) -> None:
        """Covers: B32"""
        folder = self.store_root / "tasks"
        folder.mkdir()
        folder.chmod(0o555)
        self.addCleanup(folder.chmod, 0o755)

        result = capture(
            self.store, "Call Dana", source="cli", follow_up=datetime.date(2026, 11, 20), tasks=self.tasks, now=NOW
        )

        (content,) = self.inbox().values()
        self.assertIn("\nfollow_up: 2026-11-20\n", content)
        self.assertIsNone(result.task_id)
        self.assertIn("next curation run", result.notice or "")

    def test_running_out_of_free_names_is_not_saved_either(self) -> None:
        with (
            mock.patch.object(self.store, "create_exclusive", side_effect=FileExistsError("taken")),
            self.assertRaises(NotSavedError),
        ):
            capture(self.store, "Call Dana", source="cli", now=NOW)


class CaptureCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        root = Path(self._temp.name)
        self.home = root / "home"
        self.store_root = root / "store"
        self.store_root.mkdir()
        self.environ = {"HOME": str(root / "user-home"), "M2B_HOME": str(self.home)}

    def set_up(self, tasks: dict[str, Any] | None = None, executables: dict[str, str] | None = None) -> None:
        machine.save_machine_config(
            paths.MachinePaths(self.home),
            {
                "version": 1,
                "machine_id": "sb-test-m1",
                "store": {"backend": "folder", "path": str(self.store_root)},
                **({"executables": executables} if executables else {}),
            },
        )
        store = FolderStore(self.store_root, paths.MachinePaths(self.home).temp_dir, DatalessGuard(False))
        save_store_settings(
            store,
            {
                "format": 1,
                "tasks": tasks or {"backend": "markdown"},
                "curating_machine": "sb-test-m1",
                "journal_since": "2026-11-01",
            },
        )

    def run_command(self, *arguments: str, stdin: str = "") -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with (
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
            mock.patch("sys.stdin", io.StringIO(stdin)),
        ):
            code = cli.main(list(arguments), self.environ)
        return code, out.getvalue(), err.getvalue()

    def inbox_files(self) -> list[Path]:
        folder = self.store_root / "inbox"
        return sorted(folder.iterdir()) if folder.is_dir() else []

    def test_the_command_line_capture_has_the_source_cli_and_prints_its_path(self) -> None:
        """Covers: B1"""
        self.set_up()

        code, out, _ = self.run_command("capture", "Alex prefers green tea")

        (path,) = self.inbox_files()
        self.assertEqual((code, out.strip()), (cli.EXIT_OK, f"inbox/{path.name}"))
        self.assertIn("\nsource: cli\n", path.read_text(encoding="utf-8"))

    def test_the_skill_passes_its_text_on_standard_input_with_the_source_claude(self) -> None:
        self.set_up()
        text = 'Dana\'s birthday is on 3 March.\nShe likes "maps" and $HOME stays literal.'

        code, out, _ = self.run_command("capture", "--source", "claude", "--json", "-", stdin=text)

        (path,) = self.inbox_files()
        answer = json.loads(out)
        self.assertEqual((code, answer["path"]), (cli.EXIT_OK, f"inbox/{path.name}"))
        self.assertEqual(Note.parse(path.read_text(encoding="utf-8")).body, text + "\n")
        self.assertIn("-claude-", path.name)

    def test_empty_text_exits_2_and_writes_nothing(self) -> None:
        """Covers: B3"""
        self.set_up()
        for arguments, stdin in ((("capture", ""), ""), (("capture", "-"), "\n \n")):
            with self.subTest(arguments=arguments):
                code, _, err = self.run_command(*arguments, stdin=stdin)
                self.assertEqual(code, cli.EXIT_USAGE, err)
        self.assertFalse((self.store_root / "inbox").exists())

    def test_without_a_store_set_up_it_exits_2_and_a_missing_store_folder_3_writing_nothing(self) -> None:
        """Covers: B3"""
        code, _, err = self.run_command("capture", "Alex prefers green tea")
        self.assertEqual(code, cli.EXIT_USAGE, err)

        self.set_up()
        self.store_root.rename(self.store_root.with_name("moved"))
        code, _, err = self.run_command("capture", "Alex prefers green tea")
        self.assertEqual(code, cli.EXIT_UNREACHABLE, err)
        self.assertFalse(self.store_root.exists())

    def test_follow_up_through_the_command_creates_the_task(self) -> None:
        """Covers: B32"""
        self.set_up()

        answer = json.loads(self.run_command("capture", "Call Dana", "--follow-up", "2026-11-20", "--json")[1])

        (task_file,) = sorted((self.store_root / "tasks").iterdir())
        self.assertEqual(task_file.stem, answer["task_id"])
        self.assertIn(answer["path"].rsplit("/", 1)[1], task_file.read_text(encoding="utf-8"))
        self.assertIsNone(answer["follow_up"])

    def test_follow_up_with_unreachable_reminders_still_captures_and_says_so(self) -> None:
        """Covers: B32"""
        missing = str(Path(self._temp.name) / "missing-reminders")
        self.set_up(tasks={"backend": "apple-reminders", "list": "sb-test-inbox"}, executables={"reminders": missing})

        code, out, err = self.run_command("capture", "Call Dana", "--follow-up", "2026-11-20", "--json")

        (path,) = self.inbox_files()
        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(json.loads(out)["follow_up"], "2026-11-20")
        self.assertIn("\nfollow_up: 2026-11-20\n", path.read_text(encoding="utf-8"))
        self.assertIn("follow-up", err)

    def test_a_capture_goes_into_a_store_of_a_newer_format(self) -> None:
        """Covers: B71"""
        self.set_up()
        (self.store_root / "store.json").write_text(
            json.dumps(
                {
                    "format": 99,
                    "tasks": {"backend": "markdown", "added_in_format_two": True},
                    "curating_machine": "sb-test-m1",
                    "journal_since": "2026-11-01",
                }
            ),
            encoding="utf-8",
        )

        code, _, err = self.run_command("capture", "Alex prefers green tea", "--follow-up", "2026-11-20")

        self.assertEqual(code, cli.EXIT_OK, err)
        (path,) = self.inbox_files()
        self.assertIn("Alex prefers green tea", path.read_text(encoding="utf-8"))
        self.assertRegex(path.read_text(encoding="utf-8"), r"\ntasks: \[[0-9a-f]+\]\n")

    def test_a_broken_store_json_is_still_refused_before_anything_is_written(self) -> None:
        self.set_up()
        (self.store_root / "store.json").write_text(json.dumps({"format": "two"}), encoding="utf-8")

        code, _, err = self.run_command("capture", "Alex prefers green tea")

        self.assertEqual(code, cli.EXIT_USAGE, err)
        self.assertFalse((self.store_root / "inbox").exists())

    def assert_not_saved(self, code: int, out: str, err: str) -> None:
        self.assertEqual(code, cli.EXIT_NOT_SAVED, err)
        self.assertEqual(out, "")
        self.assertEqual(len(err.splitlines()), 1, err)
        self.assertTrue(err.startswith(f"m2b: {NOT_SAVED}"), err)
        self.assertEqual(self.inbox_files(), [])
        tasks = self.store_root / "tasks"
        self.assertEqual(sorted(tasks.iterdir()) if tasks.is_dir() else [], [], "no task pointing to no capture")

    @unittest.skipIf(os.geteuid() == 0, "root writes into a folder without write permission")
    def test_a_read_only_inbox_exits_4_with_one_line_and_leaves_no_task(self) -> None:
        """Covers: B75"""
        self.set_up()
        inbox = self.store_root / "inbox"
        inbox.mkdir()
        inbox.chmod(0o555)
        self.addCleanup(inbox.chmod, 0o755)

        self.assert_not_saved(*self.run_command("capture", "Call Dana", "--follow-up", "2026-11-20"))

    def test_a_full_or_read_only_disk_exits_4_with_one_line_and_leaves_no_task(self) -> None:
        """Covers: B75"""
        self.set_up()
        create_exclusively = store_base.create_exclusively
        for error in WRITE_ERRORS[1:]:

            def refuse_the_inbox(target: Path, data: bytes, temp_dir: Path, error: OSError = error) -> None:
                if target.parent.name == "inbox":
                    raise error
                create_exclusively(target, data, temp_dir)

            with self.subTest(errno=errno.errorcode[error.errno]):
                with mock.patch.object(store_base, "create_exclusively", side_effect=refuse_the_inbox):
                    result = self.run_command("capture", "Call Dana", "--follow-up", "2026-11-20", "--json")

                self.assert_not_saved(*result)
                self.assertIn(error.strerror, result[2])

    def evicted_store_json(self, downloads: bool) -> tuple[FakeEviction, list[str]]:
        eviction = FakeEviction()
        eviction.evicted.add(self.store_root / "store.json")
        requested: list[str] = []

        def start_download(store: FolderStore, relative: str, timeout_seconds: float) -> None:
            requested.append(relative)
            if downloads:
                eviction.evicted.clear()

        for patcher in (
            mock.patch("m2b.store.factory.guard_for_platform", return_value=DatalessGuard(True, lstat=eviction.lstat)),
            mock.patch.object(FolderStore, "_start_download", autospec=True, side_effect=start_download),
            mock.patch.object(capture_commands, "STORE_SETTINGS_FETCH_SECONDS", 0.3),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        return eviction, requested

    def test_an_evicted_store_json_is_fetched_before_the_capture(self) -> None:
        """Covers: B79"""
        self.set_up()
        _, requested = self.evicted_store_json(downloads=True)

        code, _, err = self.run_command("capture", "Alex prefers green tea")

        self.assertEqual(code, cli.EXIT_OK, err)
        self.assertEqual(requested, ["store.json"])
        self.assertEqual(len(self.inbox_files()), 1)

    def test_a_store_json_that_stays_evicted_refuses_the_capture_saying_what_to_do(self) -> None:
        """Covers: B79"""
        self.set_up()
        _, requested = self.evicted_store_json(downloads=False)

        code, _, err = self.run_command("capture", "Alex prefers green tea")

        self.assertEqual(code, cli.EXIT_UNREACHABLE, err)
        self.assertEqual(requested, ["store.json"])
        self.assertIn("m2b store fetch store.json", err)
        self.assertEqual(len(err.splitlines()), 1, err)
        self.assertEqual(self.inbox_files(), [])

    def test_a_loose_follow_up_date_is_a_usage_error(self) -> None:
        self.set_up()

        code, _, _ = self.run_command("capture", "Call Dana", "--follow-up", "20.11.2026")

        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertFalse((self.store_root / "inbox").exists())


class CaptureSkillTest(unittest.TestCase):
    """Structure only: the policy prose lives once, in the skill (X15)."""

    skill = Path(__file__).resolve().parents[1] / "skills" / "capture" / "SKILL.md"

    def frontmatter(self) -> dict[str, str]:
        text = self.skill.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        block = text.split("\n---\n", 1)[0].split("\n")[1:]
        return dict(line.split(": ", 1) for line in block if ": " in line)

    def test_the_skill_may_only_run_capture_and_calendar_commands(self) -> None:
        """Checks the skill's structure, not its prose."""
        fields = self.frontmatter()

        self.assertEqual(fields["name"], "capture")
        self.assertEqual(fields["allowed-tools"], "Bash(m2b capture *), Bash(m2b calendar *)")
        self.assertTrue(fields["description"])

    def test_the_skill_captures_with_the_source_claude_on_standard_input(self) -> None:
        body = self.skill.read_text(encoding="utf-8")

        self.assertIn("m2b capture --source claude", body)
        self.assertIn("<<'CAPTURE'\nI prefer window seats on long train rides.\nCAPTURE", body)
        self.assertIn("m2b calendar add --calendar", body)
        self.assertIn("m2b calendar list --writable", body)

    def test_the_skill_knows_the_words_the_command_uses_when_nothing_was_saved(self) -> None:
        """The skill keys a failed capture on this message, not on an exit code."""
        self.assertIn(NOT_SAVED, self.skill.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
