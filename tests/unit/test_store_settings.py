from __future__ import annotations

import copy
import datetime
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from m2b.config import store_settings
from m2b.config.errors import FormatTooNewError, InvalidConfigError, NotSetUpError
from m2b.store.base import EvictedFileError
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard
from store_contract import FakeEviction

INVENTED_SETTINGS: dict[str, Any] = {
    "format": 1,
    "tasks": {"backend": "apple-reminders", "list": "Inbox", "timeout_seconds": 20},
    "curating_machine": "b41c-tower",
    "journal_since": "2026-11-06",
}


# The keys of store.json and of its tasks section, per format as released. An entry never changes:
# a new key comes with a new format, its own entry here and an additive migration.
KEYS_BY_FORMAT: dict[int, tuple[set[str], set[str]]] = {
    1: ({"format", "tasks", "curating_machine", "journal_since"}, {"backend", "list", "timeout_seconds"}),
    2: ({"format", "tasks", "curating_machine", "journal_since"}, {"backend", "list", "timeout_seconds"}),
    3: ({"format", "tasks", "curating_machine", "journal_since"}, {"backend", "list", "timeout_seconds"}),
}


def _settings(**changes: Any) -> dict[str, Any]:
    raw = copy.deepcopy(INVENTED_SETTINGS)
    raw.update(changes)
    return raw


class ParseTest(unittest.TestCase):
    def test_the_documented_example_parses(self) -> None:
        settings = store_settings.parse_store_settings(INVENTED_SETTINGS)

        self.assertEqual(settings.format, 1)
        self.assertEqual(settings.tasks.backend, "apple-reminders")
        self.assertEqual(settings.tasks.list_name, "Inbox")
        self.assertEqual(settings.tasks.timeout_seconds, 20)
        self.assertEqual(settings.curating_machine, "b41c-tower")
        self.assertEqual(settings.journal_since, datetime.date(2026, 11, 6))

    def test_the_markdown_backend_needs_no_list(self) -> None:
        settings = store_settings.parse_store_settings(_settings(tasks={"backend": "markdown"}))

        self.assertIsNone(settings.tasks.list_name)

    def test_apple_reminders_without_a_list_names_the_key(self) -> None:
        with self.assertRaises(InvalidConfigError) as caught:
            store_settings.parse_store_settings(_settings(tasks={"backend": "apple-reminders"}))

        self.assertIn("tasks.list", str(caught.exception))

    def test_an_unknown_tasks_backend_names_the_allowed_values(self) -> None:
        with self.assertRaises(InvalidConfigError) as caught:
            store_settings.parse_store_settings(_settings(tasks={"backend": "todoist"}))

        self.assertIn("apple-reminders, markdown", str(caught.exception))

    def test_a_journal_start_that_is_not_a_date_is_refused(self) -> None:
        with self.assertRaises(InvalidConfigError) as caught:
            store_settings.parse_store_settings(_settings(journal_since="06.11.2026"))

        self.assertIn("journal_since", str(caught.exception))

    def test_a_newer_format_can_be_read_but_not_written(self) -> None:
        raw = _settings(format=99, added_in_format_two={"x": 1})

        settings = store_settings.parse_store_settings(raw)

        self.assertEqual(settings.curating_machine, "b41c-tower")
        with self.assertRaises(FormatTooNewError) as caught:
            store_settings.require_writable(settings)
        self.assertIn("update", str(caught.exception))

    def test_a_newer_format_with_values_this_version_does_not_know_says_to_update(self) -> None:
        with self.assertRaises(FormatTooNewError):
            store_settings.parse_store_settings(_settings(format=99, tasks={"backend": "things"}))

    def test_an_unknown_key_in_the_known_format_is_refused(self) -> None:
        """Covers: B77"""
        with self.assertRaises(InvalidConfigError):
            store_settings.parse_store_settings(_settings(curating_machin="typo"))
        with self.assertRaises(InvalidConfigError):
            store_settings.parse_store_settings(_settings(tasks={"backend": "markdown", "timeout": 5}))

    def test_a_new_key_comes_with_a_new_format(self) -> None:
        """Covers: B77

        Fails when a key is added without raising the format: every machine on the m2b before it
        would refuse the store, capture included.
        """
        known = store_settings.KNOWN_STORE_FORMAT

        self.assertIn(known, KEYS_BY_FORMAT, "a new format needs its entry in KEYS_BY_FORMAT")
        self.assertEqual(
            {number: (set(keys), set(tasks)) for number, (keys, tasks) in store_settings.KEYS_BY_FORMAT.items()},
            {number: keys for number, keys in KEYS_BY_FORMAT.items() if number <= known},
            "a new key raises KNOWN_STORE_FORMAT and gets a new KEYS_BY_FORMAT entry; a released entry never changes",
        )

    def test_a_key_of_a_later_format_is_refused_in_a_store_of_an_earlier_one(self) -> None:
        """Covers: B77

        A newer m2b must not write its new key into a store the curating machine has not migrated
        yet: every machine on the m2b before would refuse that store.
        """
        keys, tasks = store_settings.KEYS_BY_FORMAT[store_settings.KNOWN_STORE_FORMAT]
        later = store_settings.KNOWN_STORE_FORMAT + 1
        with (
            mock.patch.object(store_settings, "KNOWN_STORE_FORMAT", later),
            mock.patch.dict(store_settings.KEYS_BY_FORMAT, {later: (keys | {"sb_test_new_key"}, tasks)}),
        ):
            self.assertEqual(
                store_settings.parse_store_settings(_settings(format=later, sb_test_new_key=1)).format, later
            )
            with self.assertRaises(InvalidConfigError):
                store_settings.parse_store_settings(_settings(format=later - 1, sb_test_new_key=1))

    def test_a_format_below_the_first_is_refused(self) -> None:
        with self.assertRaises(InvalidConfigError):
            store_settings.parse_store_settings(_settings(format=0))


class FileTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.store = Path(self._temp.name) / "store"
        self.store.mkdir()
        self.temp_dir = Path(self._temp.name) / "machine-temp"
        self.eviction = FakeEviction()
        self.files = FolderStore(self.store, self.temp_dir, DatalessGuard(True, lstat=self.eviction.lstat))

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _write(self, raw: dict[str, Any]) -> None:
        (self.store / "store.json").write_text(json.dumps(raw), encoding="utf-8")

    def test_evicted_settings_are_not_read_and_not_taken_for_missing_ones(self) -> None:
        """Covers: B6"""
        self._write(INVENTED_SETTINGS)
        self.eviction.evicted.add(self.store / "store.json")

        with self.assertRaises(EvictedFileError):
            store_settings.load_store_settings(self.files)

    def test_a_store_without_settings_names_setup(self) -> None:
        with self.assertRaises(NotSetUpError) as caught:
            store_settings.load_store_settings(self.files)

        self.assertIn("/m2b:m2b setup", str(caught.exception))

    def test_loading_a_newer_format_for_writing_says_to_update(self) -> None:
        self._write(_settings(format=99))

        self.assertEqual(store_settings.load_store_settings(self.files).format, 99)
        with self.assertRaises(FormatTooNewError):
            store_settings.load_store_settings(self.files, for_writing=True)

    def test_save_writes_the_settings_into_the_store(self) -> None:
        store_settings.save_store_settings(self.files, INVENTED_SETTINGS)

        self.assertEqual(json.loads((self.store / "store.json").read_text(encoding="utf-8")), INVENTED_SETTINGS)
        self.assertEqual([p.name for p in self.store.iterdir()], ["store.json"])

    def test_save_refuses_to_replace_settings_of_a_newer_format(self) -> None:
        self._write(_settings(format=99))

        with self.assertRaises(FormatTooNewError):
            store_settings.save_store_settings(self.files, INVENTED_SETTINGS)

        self.assertEqual(json.loads((self.store / "store.json").read_text(encoding="utf-8"))["format"], 99)


if __name__ == "__main__":
    unittest.main()
