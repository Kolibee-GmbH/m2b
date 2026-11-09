"""Migrations: a curation run brings a store's content up to the rules of this m2b, one format at a time."""

from __future__ import annotations

import json
from unittest import mock

import test_runner
from m2b import expiry
from m2b.config import store_settings
from m2b.config.errors import FormatTooNewError
from m2b.curate import migrations
from m2b.notes.layout import MEMORY, MEMORY_INDEX
from m2b.run_record import FAILED, SUCCEEDED, load_run_record
from m2b.store.base import Store

MARK = "- Format two marks every distillate (migrated.md)\n"


def _mark_the_distillate(store: Store) -> None:
    path = f"{MEMORY}/{MEMORY_INDEX}"
    text = store.read_bytes(path).decode("utf-8")
    if MARK not in text:
        store.replace(path, text.replace("## Facts\n\n", f"## Facts\n\n{MARK}").encode("utf-8"))


def _only_the_mark(before: migrations.Snapshot, after: migrations.Snapshot) -> str | None:
    path = f"{MEMORY}/{MEMORY_INDEX}"
    old, new = before.text(path) or "", after.text(path) or ""
    if set(before.files) != set(after.files) or new.replace(MARK, "") != old.replace(MARK, ""):
        return "migration 2 changed more than the mark"
    return None


DANA = "- Dana likes old maps (dana.md)\n"
DANA_NOW = "- Dana collects old maps (dana.md)\n"


def _rewrite_dana(store: Store) -> None:
    path = f"{MEMORY}/{MEMORY_INDEX}"
    store.replace(path, store.read_bytes(path).decode("utf-8").replace(DANA, DANA_NOW).encode("utf-8"))


def _write_a_stray_file(store: Store) -> None:
    store.replace(f"{MEMORY}/stray.md", b"# Stray\n")


def _fail_halfway(store: Store) -> None:
    _mark_the_distillate(store)
    raise OSError("the disk went away")


MARK_IT = migrations.Migration(2, "every distillate gets a mark", _mark_the_distillate, _only_the_mark)
STRAY = migrations.Migration(2, "writes a file it may not", _write_a_stray_file, _only_the_mark)
FAILS = migrations.Migration(2, "fails halfway", _fail_halfway, _only_the_mark)
THREE = migrations.Migration(3, "changes nothing", lambda store: None, lambda before, after: None)
REWRITE = migrations.Migration(2, "rewrites a facts line", _rewrite_dana, lambda before, after: None)
THREE_FAILS = migrations.Migration(3, "fails at once", lambda store: _fail_halfway(store), lambda before, after: None)


class RegistryTest(test_runner.RunnerTest):
    def test_this_m2b_knows_one_format_more_than_it_has_migrations_and_they_count_up_from_two(self) -> None:
        """Covers: B69"""
        self.assertEqual(store_settings.KNOWN_STORE_FORMAT, 1 + len(migrations.MIGRATIONS))
        self.assertEqual(
            [m.target for m in migrations.MIGRATIONS], list(range(2, store_settings.KNOWN_STORE_FORMAT + 1))
        )

    def test_only_the_migrations_above_the_store_format_are_due(self) -> None:
        """Covers: B69"""
        self.assertEqual(migrations.due(1, (MARK_IT, THREE)), [MARK_IT, THREE])
        self.assertEqual(migrations.due(2, (MARK_IT, THREE)), [THREE])
        self.assertEqual(migrations.due(3, (MARK_IT, THREE)), [])


class MigrationFixture(test_runner.RunnerTest):
    def knowing(self, *known: migrations.Migration) -> None:
        for patcher in (
            mock.patch.object(migrations, "MIGRATIONS", known),
            mock.patch.object(store_settings, "KNOWN_STORE_FORMAT", 1 + len(known)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        # The test migrations count up from format 1, whatever format this m2b really knows.
        settings = json.loads((self.store_root / "store.json").read_text(encoding="utf-8"))
        (self.store_root / "store.json").write_text(json.dumps({**settings, "format": 1}), encoding="utf-8")

    def store_format(self) -> int:
        return int(json.loads((self.store_root / "store.json").read_text(encoding="utf-8"))["format"])

    def distillate(self) -> str:
        return (self.store_root / "memory/MEMORY.md").read_text(encoding="utf-8")


class MigrationRunTest(MigrationFixture):
    def test_a_due_migration_runs_before_every_other_step_and_raises_the_format(self) -> None:
        """Covers: B69"""
        self.curating()
        self.write("STORE.md", "# m2b store\n\nThis folder is an m2b store, format 1.\n")
        self.knowing(MARK_IT, THREE)

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.store_format(), 3)
        self.assertIn(MARK, self.distillate())
        record = load_run_record(self.store)
        assert record is not None
        names = [(step.name, step.result) for step in record.steps]
        self.assertEqual(names[:3], [("migrate-2", SUCCEEDED), ("migrate-3", SUCCEEDED), ("harvest", SUCCEEDED)])
        self.assertIn("format 3", (self.store_root / "STORE.md").read_text(encoding="utf-8"))

    def test_a_store_md_that_is_not_downloaded_is_named_in_the_review_and_stops_nothing(self) -> None:
        """Covers: B69"""
        self.curating()
        self.write("STORE.md", "# m2b store\n\nThis folder is an m2b store, format 1.\n")
        self.eviction.evicted.add(self.store_root / "STORE.md")
        self.knowing(MARK_IT)

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.store_format(), 2)
        (review,) = self.review_tasks()
        self.assertIn("STORE.md is not downloaded", review.notes)

    def test_the_format_is_written_after_each_migration_so_a_later_failure_keeps_the_earlier_one(self) -> None:
        """Covers: B69"""
        self.curating()
        self.knowing(MARK_IT, THREE_FAILS)

        outcome = self.run_curate()

        self.assertEqual(outcome.state, FAILED)
        self.assertEqual(self.store_format(), 2)
        self.assertIn(MARK, self.distillate())

    def test_the_facts_lines_a_migration_changed_are_listed_in_the_review(self) -> None:
        """Covers: B69"""
        self.curating()
        self.write("memory/MEMORY.md", f"# Memory\n\n## Facts\n\n{DANA}\n## Current\n")
        self.write("memory/dana.md", "# Dana\n\n- Likes old maps.\n")
        self.knowing(REWRITE)

        self.run_curate()

        (review,) = self.review_tasks()
        self.assertIn("migrate-2", review.notes)
        self.assertIn("Dana likes old maps", review.notes)

    def test_a_refresh_all_run_reads_the_undated_lines_again_after_a_migration(self) -> None:
        """Covers: B69"""
        self.curating()
        self.write("memory/MEMORY.md", f"# Memory\n\n## Facts\n\n{DANA}\n## Current\n")
        self.write("memory/dana.md", "# Dana\n\n- Likes old maps.\n")
        self.knowing(REWRITE)
        seen: list[str] = []
        real = expiry.undated

        def undated(store: Store) -> expiry.Undated:
            seen.append((self.store_root / "memory/MEMORY.md").read_text(encoding="utf-8"))
            return real(store)

        with mock.patch.object(expiry, "undated", undated):
            self.run_curate(refresh_all=True)

        self.assertIn(DANA_NOW, seen[-1])

    def test_a_store_at_the_known_format_gets_no_migration_step(self) -> None:
        """Covers: B69"""
        self.curating()

        self.run_curate()

        record = load_run_record(self.store)
        assert record is not None
        self.assertNotIn("migrate", " ".join(step.name for step in record.steps))
        self.assertEqual(self.store_format(), store_settings.KNOWN_STORE_FORMAT)

    def test_a_migration_that_fails_puts_memory_back_keeps_the_format_and_stops_the_run(self) -> None:
        """Covers: B70"""
        for broken in (FAILS, STRAY):
            with self.subTest(migration=broken.summary):
                self.curating()
                self.capture()
                self.knowing(broken, THREE)

                outcome = self.run_curate()

                self.assertEqual(outcome.state, FAILED)
                self.assertEqual(self.distillate(), test_runner.MEMORY)
                self.assertFalse((self.store_root / "memory/stray.md").exists())
                self.assertEqual(self.store_format(), 1)
                record = load_run_record(self.store)
                assert record is not None
                self.assertEqual([step.name for step in record.steps], ["migrate-2", "review"])
                self.assertEqual(record.steps[0].result, FAILED)
                self.assertEqual(len(list((self.store_root / "inbox").iterdir())), 1)
                (review,) = self.review_tasks()
                self.assertIn("migrate-2", review.notes)

    def test_an_older_m2b_does_not_curate_a_store_of_a_newer_format(self) -> None:
        """Covers: B70"""
        self.curating()
        self.capture()
        settings = json.loads((self.store_root / "store.json").read_text(encoding="utf-8"))
        newer = store_settings.KNOWN_STORE_FORMAT + 1
        (self.store_root / "store.json").write_text(json.dumps({**settings, "format": newer}), encoding="utf-8")

        with self.assertRaisesRegex(FormatTooNewError, "update"):
            self.run_curate()

        self.assertEqual(self.distillate(), test_runner.MEMORY)
        self.assertEqual(len(list((self.store_root / "inbox").iterdir())), 1)
        self.assertIsNone(load_run_record(self.store))


class FormatReportTest(MigrationFixture):
    def with_format(self, store_format: int) -> None:
        settings = json.loads((self.store_root / "store.json").read_text(encoding="utf-8"))
        (self.store_root / "store.json").write_text(json.dumps({**settings, "format": store_format}), encoding="utf-8")

    def doctor_line(self) -> tuple[int, str]:
        code, out, _ = self.run_command("doctor")
        (line,) = [line for line in out.splitlines() if line.startswith("store-format: ")]
        return code, line

    def test_doctor_and_status_name_a_store_newer_than_this_m2b_as_a_problem(self) -> None:
        """Covers: B72"""
        self.curating()
        known = store_settings.KNOWN_STORE_FORMAT
        self.with_format(known + 1)

        code, line = self.doctor_line()

        self.assertEqual(code, 1)
        self.assertEqual(
            line,
            f"store-format: newer (the store has format {known + 1}, this m2b knows {known}: "
            "update m2b on this machine)",
        )
        status = self.run_json("status")["store_format"]
        self.assertEqual((status["store"], status["known"], status["state"]), (known + 1, known, "newer"))

    def test_doctor_and_status_say_when_the_next_curation_run_migrates(self) -> None:
        """Covers: B72"""
        self.curating()
        self.knowing(MARK_IT)

        _, line = self.doctor_line()

        self.assertEqual(
            line,
            "store-format: migrates (the store has format 1, this m2b knows 2: "
            "once sb-test-m1 runs this m2b, its next curation run migrates it)",
        )
        status = self.run_json("status")["store_format"]
        self.assertEqual((status["store"], status["known"], status["state"]), (1, 2, "migrates"))

    def test_a_store_at_the_known_format_is_current(self) -> None:
        """Covers: B72"""
        self.curating()

        _, line = self.doctor_line()

        known = store_settings.KNOWN_STORE_FORMAT
        self.assertEqual(line, f"store-format: current (format {known})")
        self.assertIn(f"store format: current (format {known})", self.run_command("status")[1])


class EarlierValuesMigrationTest(MigrationFixture):
    def test_format_two_is_the_first_migration_and_changes_nothing_in_memory(self) -> None:
        """Covers: B73"""
        self.curating()
        self.write("memory/dana.md", "# Dana\n\n- Likes old maps.\n")
        settings = json.loads((self.store_root / "store.json").read_text(encoding="utf-8"))
        (self.store_root / "store.json").write_text(json.dumps({**settings, "format": 1}), encoding="utf-8")
        before = {path.name: path.read_bytes() for path in (self.store_root / "memory").iterdir()}

        outcome = self.run_curate()

        self.assertEqual(outcome.state, SUCCEEDED, outcome.message)
        self.assertEqual(self.store_format(), 2)
        self.assertEqual({path.name: path.read_bytes() for path in (self.store_root / "memory").iterdir()}, before)
        record = load_run_record(self.store)
        assert record is not None
        self.assertEqual((record.steps[0].name, record.steps[0].result), ("migrate-2", SUCCEEDED))

    def test_the_earlier_values_migration_refuses_any_change(self) -> None:
        """Covers: B73"""
        (migration,) = [m for m in migrations.MIGRATIONS if m.target == 2]
        empty = migrations.Snapshot({})
        changed = migrations.Snapshot({"memory/dana.md": b"# Dana\n"})

        self.assertIsNone(migration.problem(empty, empty))
        self.assertIsNotNone(migration.problem(empty, changed))
