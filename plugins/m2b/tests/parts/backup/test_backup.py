"""The backup part: mirror, attic, task dump, pruning, and the checks before any of it."""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from m2b_backup import backup, snapshot
from m2b_backup.backup import BackupError, NotSetUpError
from m2b_backup.core import TasksUnreachableError

TODAY = datetime.date(2026, 3, 14)
COMMAND = Path(__file__).resolve().parents[3] / "bin" / "m2b-backup"
TASKS = [{"id": "aaaa00000001", "title": "Call the plumber", "completed": False}]


class FakeCore:
    def __init__(self, store: Path, settings: Any) -> None:
        self._store, self._settings = store, settings
        self.listed: str | Exception = json.dumps(TASKS)
        self.reported: list[tuple[str, str]] = []

    def store(self) -> Path:
        return self._store

    def settings(self) -> Any:
        """``parts.backup`` as the core gives it: the part is on, the settings beside ``on``."""
        return {"on": True, **self._settings} if isinstance(self._settings, dict) else self._settings

    def tasks(self) -> str:
        if isinstance(self.listed, Exception):
            raise self.listed
        return self.listed

    def report(self, kind: str, text: str) -> bool:
        self.reported.append((kind, text))
        return True


class BackupFixture(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.home = self.base / "home"
        self.store = self.base / "sb-test-store"
        self.target = self.home / "backup"
        self.target.mkdir(parents=True)
        self.core = FakeCore(self.store, {"target": "~/backup", "attic_days": 30})
        self.evicted: set[str] = set()
        self.write("store.json", '{"format": 1}\n')
        self.write("inbox/20260314T090000Z-cli-a1b2.md", "---\ncreated: 2026-03-14T10:00:00+01:00\n---\nA note\n")
        self.write("memory/MEMORY.md", "# Memory\n")

    def write(self, relative: str, text: str) -> None:
        path = self.store / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def backup(self, today: datetime.date = TODAY) -> backup.Outcome:
        evicted = {str(self.store / relative) for relative in self.evicted}
        with mock.patch.object(snapshot, "is_evicted", side_effect=lambda path: str(path) in evicted):
            return backup.run(self.core, self.home, today)

    def files(self, folder: Path) -> dict[str, str]:
        return {
            p.relative_to(folder).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted(folder.rglob("*"))
            if p.is_file()
        }


class MirrorTest(BackupFixture):
    def test_a_backup_has_a_mirror_without_hidden_files_an_attic_and_a_task_dump(self) -> None:
        """Covers: B27"""
        self.write(".sb-tmp-memory.md.x1", "half a write")
        self.write("state/parts/worklog/ledger.xlsx", "xlsx")
        self.write("state/parts/worklog/~$ledger.xlsx", "lock")
        self.write("corpus/.hidden/note.md", "hidden folder")
        self.backup()
        self.write("memory/MEMORY.md", "# Memory\n\n## Facts\n")

        outcome = self.backup()

        self.assertEqual(
            sorted(self.files(self.target / "mirror")),
            [
                "inbox/20260314T090000Z-cli-a1b2.md",
                "memory/MEMORY.md",
                "state/parts/worklog/ledger.xlsx",
                "store.json",
            ],
        )
        self.assertEqual(self.files(self.target / "mirror")["memory/MEMORY.md"], "# Memory\n\n## Facts\n")
        self.assertEqual(self.files(self.target / "attic"), {"2026-03-14/memory/MEMORY.md": "# Memory\n"})
        self.assertEqual(json.loads((self.target / "tasks.json").read_text(encoding="utf-8")), TASKS)
        self.assertEqual((outcome.result.copied, outcome.result.unchanged, outcome.result.to_attic), (1, 3, 1))

    def test_a_file_gone_from_the_store_moves_into_the_attic_and_its_folder_goes(self) -> None:
        """Covers: B27"""
        self.backup()
        (self.store / "inbox" / "20260314T090000Z-cli-a1b2.md").rename(self.base / "filed.md")

        self.backup()

        self.assertNotIn("inbox/20260314T090000Z-cli-a1b2.md", self.files(self.target / "mirror"))
        self.assertFalse((self.target / "mirror" / "inbox").exists())
        self.assertIn("2026-03-14/inbox/20260314T090000Z-cli-a1b2.md", self.files(self.target / "attic"))

    def test_a_file_replaced_twice_on_one_day_keeps_both_old_versions(self) -> None:
        self.backup()
        self.write("memory/MEMORY.md", "second\n")
        self.backup()
        self.write("memory/MEMORY.md", "third\n")

        self.backup()

        self.assertEqual(
            self.files(self.target / "attic"),
            {"2026-03-14/memory/MEMORY (2).md": "second\n", "2026-03-14/memory/MEMORY.md": "# Memory\n"},
        )

    def test_a_second_backup_without_changes_copies_nothing(self) -> None:
        self.backup()

        outcome = self.backup()

        self.assertEqual((outcome.result.copied, outcome.result.to_attic), (0, 0))
        self.assertFalse((self.target / "attic").exists())

    def test_an_evicted_file_keeps_its_previous_copy_and_is_counted(self) -> None:
        """Covers: B27"""
        self.backup()
        self.write("memory/MEMORY.md", "changed in the cloud\n")
        self.evicted.add("memory/MEMORY.md")

        outcome = self.backup()

        self.assertEqual(self.files(self.target / "mirror")["memory/MEMORY.md"], "# Memory\n")
        self.assertFalse((self.target / "attic").exists())
        self.assertEqual(outcome.result.evicted, ["memory/MEMORY.md"])
        [(kind, text)] = self.core.reported
        self.assertEqual(kind, "info")
        self.assertIn("1 files not downloaded were not backed up", text)

    def test_an_evicted_folder_keeps_the_mirror_copies_of_its_files(self) -> None:
        """Covers: B27"""
        self.write("corpus/2025/03/20250301T090000Z-cli-0001.md", "an old note\n")
        self.backup()
        self.evicted.add("corpus/2025/03")

        outcome = self.backup()

        self.assertIn("corpus/2025/03/20250301T090000Z-cli-0001.md", self.files(self.target / "mirror"))
        self.assertFalse((self.target / "attic").exists())
        self.assertEqual(outcome.result.unread, ["corpus/2025/03"])
        self.assertIn("1 folders could not be read", self.core.reported[0][1])

    def test_a_folder_that_cannot_be_listed_keeps_the_mirror_copies_of_its_files(self) -> None:
        self.write("tasks/aaaa00000001.md", "Call the plumber\n")
        self.backup()
        (self.store / "tasks").chmod(0)
        self.addCleanup((self.store / "tasks").chmod, 0o755)

        outcome = self.backup()

        self.assertIn("tasks/aaaa00000001.md", self.files(self.target / "mirror"))
        self.assertFalse((self.target / "attic").exists())
        self.assertEqual(outcome.result.unread, ["tasks"])

    def test_a_store_that_cannot_be_listed_stops_the_backup(self) -> None:
        self.backup()
        # Without read but with search permission: store.json can be seen, the folder not listed.
        self.store.chmod(0o311)
        self.addCleanup(self.store.chmod, 0o755)

        with self.assertRaisesRegex(BackupError, "cannot be listed"):
            self.backup()

        self.assertFalse((self.target / "attic").exists())

    def test_a_crash_left_temporary_file_in_the_mirror_is_removed(self) -> None:
        self.backup()
        leftover = self.target / "mirror" / "memory" / ".sb-tmp-MEMORY.md.x1"
        leftover.write_text("half", encoding="utf-8")

        self.backup()

        self.assertFalse(leftover.exists())
        self.assertFalse((self.target / "attic").exists())


class TaskDumpTest(BackupFixture):
    def test_unreachable_tasks_keep_the_previous_dump(self) -> None:
        """Covers: X3"""
        self.backup()
        self.core.listed = TasksUnreachableError("Reminders access was not granted")

        outcome = self.backup()

        self.assertEqual(json.loads((self.target / "tasks.json").read_text(encoding="utf-8")), TASKS)
        self.assertEqual(outcome.dump, "previous dump kept")
        [(kind, text)] = self.core.reported
        self.assertEqual(kind, "action")
        self.assertIn("could not be reached (Reminders access was not granted)", text)

    def test_an_empty_answer_never_replaces_a_dump_with_tasks(self) -> None:
        """Covers: B27"""
        self.backup()
        self.core.listed = "[]\n"

        self.backup()

        self.assertEqual(json.loads((self.target / "tasks.json").read_text(encoding="utf-8")), TASKS)
        self.assertIn("answered with no tasks at all", self.core.reported[0][1])

    def test_an_empty_list_is_dumped_when_there_was_none_before(self) -> None:
        self.core.listed = "[]\n"

        self.backup()

        self.assertEqual((self.target / "tasks.json").read_text(encoding="utf-8"), "[]\n")
        self.assertEqual(self.core.reported, [])


class PruneTest(BackupFixture):
    def test_an_attic_day_older_than_attic_days_is_removed(self) -> None:
        for day in ("2026-02-11", "2026-02-12", "notes"):
            (self.target / "attic" / day).mkdir(parents=True)
            (self.target / "attic" / day / "MEMORY.md").write_text("old\n", encoding="utf-8")

        outcome = self.backup()

        self.assertEqual(outcome.result.pruned, ["2026-02-11"])
        self.assertEqual(sorted(p.name for p in (self.target / "attic").iterdir()), ["2026-02-12", "notes"])


class SettingsTest(BackupFixture):
    def test_a_missing_target_folder_stops_the_backup_and_creates_nothing(self) -> None:
        self.core = FakeCore(self.store, {"target": str(self.base / "Volumes" / "sb-test-disk" / "m2b")})

        with self.assertRaisesRegex(BackupError, "does not exist; connect its disk"):
            self.backup()

        self.assertFalse((self.base / "Volumes").exists())

    def test_a_target_inside_the_store_or_around_it_is_refused(self) -> None:
        (self.store / "backup").mkdir()
        for target in (str(self.store / "backup"), str(self.base), str(self.store)):
            with self.subTest(target=target):
                self.core = FakeCore(self.store, {"target": target})

                with self.assertRaisesRegex(BackupError, "must not lie inside each other"):
                    self.backup()

    def test_a_store_that_is_not_there_stops_the_backup_before_the_mirror_is_touched(self) -> None:
        self.backup()
        self.core = FakeCore(self.base / "Volumes" / "sb-test-disk" / "store", {"target": "~/backup"})

        with self.assertRaisesRegex(BackupError, "is not reachable; nothing was backed up"):
            self.backup()

        self.assertIn("store.json", self.files(self.target / "mirror"))
        self.assertFalse((self.target / "attic").exists())

    def test_settings_are_checked(self) -> None:
        for off in (None, {"target": "~/b"}, {"on": False, "target": "~/b"}):
            with self.subTest(off=off), self.assertRaises(NotSetUpError):
                backup.settings_of(off, self.home)
        for raw in (
            {"on": True},
            {"on": True, "target": "backup"},
            {"on": True, "target": "~/b", "attic_days": 0},
            {"on": True, "target": "~/b", "attic_days": True},
        ):
            with self.subTest(raw=raw), self.assertRaises(BackupError):
                backup.settings_of(raw, self.home)
        self.assertEqual(
            backup.settings_of({"on": True, "target": "~/b"}, self.home), backup.Settings(self.home / "b", 30)
        )


class CommandTest(BackupFixture):
    """``m2b-backup run`` through a fake launcher: the core's commands as the backup calls them."""

    def launcher(self, settings: Any, tasks_exit: int = 0) -> Path:
        launcher = self.home / ".local" / "bin" / "m2b"
        launcher.parent.mkdir(parents=True)
        calls = self.base / "launcher-calls.txt"
        parts = {"backup": {"on": True, **settings}} if settings is not None else {}
        script = f"""#!{sys.executable}
import json, sys
arguments = sys.argv[1:]
with open({str(calls)!r}, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(arguments) + "\\n")
if arguments == ["config", "get", "store.path", "--json"]:
    print(json.dumps({str(self.store)!r}))
elif arguments == ["config", "get", "parts", "--json"]:
    print({json.dumps(parts)!r})
elif arguments == ["tasks", "list", "--include-completed", "--json"]:
    if {tasks_exit}:
        sys.exit(print("m2b: the task list could not be reached", file=sys.stderr) or {tasks_exit})
    print({json.dumps(TASKS)!r})
elif arguments[:2] == ["curate", "report"]:
    pass
else:
    sys.exit(f"unexpected: {{arguments}}")
"""
        launcher.write_text(script, encoding="utf-8")
        launcher.chmod(0o755)
        return calls

    def command(self, *arguments: str, token: str | None = None) -> subprocess.CompletedProcess[str]:
        environ = {"PATH": os.environ.get("PATH", ""), "M2B_HOME": str(self.home), "M2B_PYTHON": sys.executable}
        if token:
            environ["M2B_RUN_TOKEN"] = token
        return subprocess.run([str(COMMAND), *arguments], capture_output=True, text=True, env=environ, timeout=60)

    def test_run_backs_up_and_says_what_it_did(self) -> None:
        self.launcher({"target": "~/backup"})

        result = self.command("run", "--today", TODAY.isoformat())

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "backup: 3 copied, 0 unchanged, 0 into the attic\ntasks: 1 written\n")

    def test_not_set_up_exits_2(self) -> None:
        self.launcher(None)

        result = self.command("run")

        self.assertEqual(result.returncode, 2)
        self.assertIn("/m2b:backup-setup", result.stderr)

    def test_inside_a_run_unreachable_tasks_are_reported_to_it(self) -> None:
        """Covers: X3"""
        calls = self.launcher({"target": "~/backup"}, tasks_exit=3)

        result = self.command("run", "--today", TODAY.isoformat(), token="sb-test-token")

        self.assertEqual(result.returncode, 0, result.stderr)
        made = [json.loads(line) for line in calls.read_text(encoding="utf-8").splitlines()]
        [report] = [call for call in made if call[:2] == ["curate", "report"]]
        self.assertEqual(report[:6], ["curate", "report", "--step", "backup", "--kind", "action"])
        self.assertIn("the task list could not be reached", report[-1])

    def test_outside_a_run_nothing_is_reported_to_the_core(self) -> None:
        calls = self.launcher({"target": "~/backup"}, tasks_exit=3)

        result = self.command("run", "--today", TODAY.isoformat())

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("action: the task list could not be reached", result.stdout)
        made = [json.loads(line) for line in calls.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([call for call in made if call[:2] == ["curate", "report"]], [])


if __name__ == "__main__":
    unittest.main()
