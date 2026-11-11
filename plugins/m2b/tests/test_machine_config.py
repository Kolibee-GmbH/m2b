from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from m2b import addons, paths
from m2b.config import machine
from m2b.config.errors import FormatTooNewError, InvalidConfigError, NotSetUpError

HOME = Path("/tmp/sb-test-home")

INVENTED_CONFIG: dict[str, Any] = {
    "version": 1,
    "machine_id": "b41c-tower",
    "store": {"backend": "icloud", "path": "~/Library/Mobile Documents/com~apple~CloudDocs/Second Brain"},
    "calendar": {"backend": "apple-calendar", "timeout_seconds": 20},
    "executables": {"python3": "/usr/bin/python3", "claude": "/opt/homebrew/bin/claude"},
    "curation": {"model_timeout_minutes": 15},
    "addons": {"worklog": {"on": True, "default_sphere": "own"}},
}


def _config(**changes: Any) -> dict[str, Any]:
    raw = copy.deepcopy(INVENTED_CONFIG)
    raw.update(changes)
    return raw


class AddonCatalogueTest(unittest.TestCase):
    def test_no_name_is_both_an_addon_and_a_removed_one(self) -> None:
        # A removed name wins in the config loader and in ``m2b addons off``, so an add-on that comes
        # back under its old name must leave the removed list, or its settings are dropped unread.
        self.assertTrue(set(addons.addon_names()).isdisjoint(addons.REMOVED_ADDONS))


class ParseTest(unittest.TestCase):
    def test_the_documented_example_parses(self) -> None:
        config = machine.parse_machine_config(INVENTED_CONFIG, HOME)

        self.assertEqual(config.machine_id, "b41c-tower")
        self.assertEqual(config.store.backend, "icloud")
        self.assertEqual(config.calendar.backend, "apple-calendar")
        self.assertEqual(config.executables["python3"], "/usr/bin/python3")
        self.assertEqual(config.curation.model_timeout_minutes, 15)
        self.assertEqual(config.addons["worklog"], {"on": True, "default_sphere": "own"})

    def test_the_store_path_comes_from_the_config_with_the_tilde_expanded_at_load(self) -> None:
        """Covers: X1"""
        config = machine.parse_machine_config(_config(store={"backend": "folder", "path": "~/notes"}), HOME)

        self.assertEqual(config.store.path, HOME / "notes")

    def test_a_store_path_that_is_not_absolute_is_refused(self) -> None:
        for path in ("Second Brain", "~dana/notes"):
            with self.subTest(path=path), self.assertRaises(InvalidConfigError) as caught:
                machine.parse_machine_config(_config(store={"backend": "folder", "path": path}), HOME)

            self.assertIn("store.path", str(caught.exception))

    def test_optional_sections_get_their_defaults(self) -> None:
        raw = {"version": 1, "machine_id": "m1", "store": {"backend": "folder", "path": "/data/store"}}

        config = machine.parse_machine_config(raw, HOME)

        self.assertEqual(config.calendar.backend, "none")
        self.assertEqual(config.calendar.timeout_seconds, 20)
        self.assertEqual(config.curation.model_timeout_minutes, 15)
        self.assertEqual(config.addons, {})

    def test_an_addon_keeps_its_own_settings_beside_on(self) -> None:
        raw = _config(addons={"worklog": {"on": False, "anything": [1, {"nested": True}]}})

        config = machine.parse_machine_config(raw, HOME)

        self.assertEqual(config.addons["worklog"], {"on": False, "anything": [1, {"nested": True}]})

    def test_an_unknown_addon_names_the_known_ones(self) -> None:
        with self.assertRaises(InvalidConfigError) as caught:
            machine.parse_machine_config(_config(addons={"bakcup": {"on": True}}), HOME)

        self.assertIn("addons.bakcup", str(caught.exception))
        self.assertTrue(str(caught.exception).endswith("known here: worklog"), str(caught.exception))

    def test_an_addon_m2b_no_longer_has_is_ignored_with_its_settings(self) -> None:
        """Covers: B83"""
        raw = _config(
            addons={
                "herdr": {"on": True},
                "backup": {"on": True, "target": "~/Backups/m2b", "attic_days": 30},
                "worklog": {"on": True},
            }
        )

        config = machine.parse_machine_config(raw, HOME)

        self.assertEqual(config.addons, {"worklog": {"on": True}})

    def test_on_must_be_true_or_false(self) -> None:
        for addon in ({"on": "yes"}, {"on": 1}, "on"):
            with self.subTest(addon=addon), self.assertRaises(InvalidConfigError):
                machine.parse_machine_config(_config(addons={"worklog": addon}), HOME)

    def test_reading_the_sessions_is_off_until_the_config_turns_it_on(self) -> None:
        """Covers: B115"""
        self.assertFalse(machine.parse_machine_config(_config(), HOME).curation.read_sessions)
        config = machine.parse_machine_config(_config(curation={"read_sessions": True}), HOME)
        self.assertTrue(config.curation.read_sessions)
        with self.assertRaises(InvalidConfigError):
            machine.parse_machine_config(_config(curation={"read_sessions": "yes"}), HOME)

    def test_the_curation_model_and_turn_limit_default_to_a_small_model_and_100(self) -> None:
        config = machine.parse_machine_config(_config(), HOME)
        self.assertEqual((config.curation.model, config.curation.max_turns), ("haiku", 100))

        config = machine.parse_machine_config(_config(curation={"model": "sonnet", "max_turns": 30}), HOME)
        self.assertEqual((config.curation.model, config.curation.max_turns), ("sonnet", 30))
        for bad in ({"max_turns": 0}, {"model": 4}):
            with self.subTest(bad=bad), self.assertRaises(InvalidConfigError):
                machine.parse_machine_config(_config(curation=bad), HOME)

    def test_the_spending_cap_is_unset_by_default_and_a_positive_number_when_set(self) -> None:
        self.assertIsNone(machine.parse_machine_config(_config(), HOME).curation.max_budget_usd)
        config = machine.parse_machine_config(_config(curation={"max_budget_usd": 1.5}), HOME)
        self.assertEqual(config.curation.max_budget_usd, 1.5)
        for bad in (0, -1, "1", True):
            with self.subTest(bad=bad), self.assertRaises(InvalidConfigError):
                machine.parse_machine_config(_config(curation={"max_budget_usd": bad}), HOME)

    def test_folders_without_the_distillate_are_absolute_after_loading(self) -> None:
        config = machine.parse_machine_config(_config(distillate={"skip_under": ["~/code/acme", "/srv/x"]}), HOME)
        self.assertEqual(config.distillate.skip_under, (HOME / "code" / "acme", Path("/srv/x")))
        with self.assertRaises(InvalidConfigError):
            machine.parse_machine_config(_config(distillate={"skip_under": ["code/acme"]}), HOME)

    def test_the_band_shows_due_tasks_unless_band_due_tasks_is_false(self) -> None:
        """Covers: B102"""
        self.assertTrue(machine.parse_machine_config(_config(), HOME).band.due_tasks)
        self.assertFalse(machine.parse_machine_config(_config(band={"due_tasks": False}), HOME).band.due_tasks)
        with self.assertRaisesRegex(InvalidConfigError, "due_tasks"):
            machine.parse_machine_config(_config(band={"due_tasks": "no"}), HOME)

    def test_the_old_modules_key_and_curation_steps_are_refused(self) -> None:
        for raw in (_config(modules={}), _config(curation={"steps": {}})):
            with self.subTest(raw=raw), self.assertRaises(InvalidConfigError):
                machine.parse_machine_config(raw, HOME)

    def test_an_unknown_backend_names_the_key_and_the_allowed_values(self) -> None:
        with self.assertRaises(InvalidConfigError) as caught:
            machine.parse_machine_config(_config(store={"backend": "dropbox", "path": "/x"}), HOME)

        message = str(caught.exception)
        self.assertIn("store.backend", message)
        self.assertIn("folder, icloud", message)

    def test_a_missing_required_key_is_named(self) -> None:
        for key in ("version", "machine_id", "store"):
            with self.subTest(key=key):
                raw = _config()
                del raw[key]

                with self.assertRaises(InvalidConfigError) as caught:
                    machine.parse_machine_config(raw, HOME)

                self.assertIn(key, str(caught.exception))

    def test_a_missing_nested_key_is_named_with_its_section(self) -> None:
        with self.assertRaises(InvalidConfigError) as caught:
            machine.parse_machine_config(_config(store={"backend": "folder"}), HOME)

        self.assertIn("store.path", str(caught.exception))

    def test_an_unknown_key_outside_addons_is_refused(self) -> None:
        with self.assertRaises(InvalidConfigError) as caught:
            machine.parse_machine_config(_config(calender={"backend": "none"}), HOME)

        self.assertIn("calender", str(caught.exception))

    def test_a_wrong_type_is_named(self) -> None:
        cases = [
            _config(machine_id=7),
            _config(calendar={"backend": "none", "timeout_seconds": "20"}),
            _config(calendar={"backend": "none", "timeout_seconds": True}),
            _config(calendar={"backend": "none", "timeout_seconds": 0}),
            _config(store="~/notes"),
        ]
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(InvalidConfigError):
                machine.parse_machine_config(raw, HOME)

    def test_a_newer_config_version_says_to_update(self) -> None:
        with self.assertRaises(FormatTooNewError) as caught:
            machine.parse_machine_config(_config(version=2), HOME)

        self.assertIn("update", str(caught.exception))

    def test_a_newer_config_with_a_new_key_still_says_to_update(self) -> None:
        with self.assertRaises(FormatTooNewError):
            machine.parse_machine_config(_config(version=2, added_in_version_two=True), HOME)

    def test_a_config_that_is_not_an_object_is_refused(self) -> None:
        with self.assertRaises(InvalidConfigError):
            machine.parse_machine_config([1, 2], HOME)


class FileTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.machine = paths.MachinePaths(Path(self._temp.name))

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_without_a_config_file_loading_names_setup(self) -> None:
        with self.assertRaises(NotSetUpError) as caught:
            machine.load_machine_config(self.machine)

        self.assertIn("/m2b:m2b setup", str(caught.exception))

    def test_a_config_file_that_is_not_json_names_the_file(self) -> None:
        self.machine.config_file.parent.mkdir(parents=True)
        self.machine.config_file.write_text("{oops", encoding="utf-8")

        with self.assertRaises(InvalidConfigError) as caught:
            machine.load_machine_config(self.machine)

        self.assertIn("config.json", str(caught.exception))

    def test_a_config_file_that_cannot_be_read_is_a_config_error(self) -> None:
        self.machine.config_file.parent.mkdir(parents=True)
        self.machine.config_file.write_bytes(b"\xff\xfe not utf-8")

        with self.assertRaises(InvalidConfigError) as caught:
            machine.load_machine_config(self.machine)

        self.assertIn("cannot be read", str(caught.exception))

    def test_a_config_path_that_is_a_folder_is_a_config_error(self) -> None:
        self.machine.config_file.mkdir(parents=True)

        with self.assertRaises(InvalidConfigError):
            machine.load_machine_config(self.machine)

    def test_save_validates_writes_and_load_reads_it_back(self) -> None:
        machine.save_machine_config(self.machine, INVENTED_CONFIG)

        self.assertEqual(json.loads(self.machine.config_file.read_text(encoding="utf-8")), INVENTED_CONFIG)
        self.assertEqual(machine.load_machine_config(self.machine).machine_id, "b41c-tower")
        self.assertEqual(list(self.machine.temp_dir.iterdir()), [])

    def test_an_invalid_config_is_never_written(self) -> None:
        with self.assertRaises(InvalidConfigError):
            machine.save_machine_config(self.machine, _config(store={"backend": "dropbox", "path": "/x"}))

        self.assertFalse(self.machine.config_file.exists())

    def test_set_changes_one_key_and_keeps_the_rest(self) -> None:
        machine.save_machine_config(self.machine, INVENTED_CONFIG)

        machine.set_machine_config_value(self.machine, "calendar.timeout_seconds", 45)

        raw = json.loads(self.machine.config_file.read_text(encoding="utf-8"))
        self.assertEqual(raw["calendar"], {"backend": "apple-calendar", "timeout_seconds": 45})
        self.assertEqual(raw["addons"], INVENTED_CONFIG["addons"])
        self.assertEqual(raw["store"]["path"], INVENTED_CONFIG["store"]["path"])

    def test_set_refuses_a_value_that_makes_the_config_invalid(self) -> None:
        machine.save_machine_config(self.machine, INVENTED_CONFIG)

        with self.assertRaises(InvalidConfigError):
            machine.set_machine_config_value(self.machine, "store.backend", "dropbox")

        self.assertEqual(json.loads(self.machine.config_file.read_text(encoding="utf-8")), INVENTED_CONFIG)

    def test_an_addon_turned_off_keeps_its_settings_and_on_again_changes_nothing_else(self) -> None:
        machine.save_machine_config(self.machine, INVENTED_CONFIG)

        self.assertTrue(machine.set_addon_on(self.machine, "worklog", False))
        self.assertFalse(machine.set_addon_on(self.machine, "worklog", False))
        raw = json.loads(self.machine.config_file.read_text(encoding="utf-8"))
        self.assertEqual(raw["addons"]["worklog"], {"on": False, "default_sphere": "own"})
        self.assertTrue(machine.set_addon_on(self.machine, "worklog", True))
        raw = json.loads(self.machine.config_file.read_text(encoding="utf-8"))
        self.assertEqual(raw["addons"]["worklog"], {"on": True, "default_sphere": "own"})

    def test_the_entry_of_an_addon_m2b_no_longer_has_can_be_removed_and_nothing_else_changes(self) -> None:
        """Covers: B83"""
        raw = copy.deepcopy(INVENTED_CONFIG)
        raw["addons"]["backup"] = {"on": True, "target": "~/Backups/m2b"}
        machine.save_machine_config(self.machine, raw)

        self.assertTrue(machine.remove_addon_entry(self.machine, "backup"))
        self.assertFalse(machine.remove_addon_entry(self.machine, "backup"))
        self.assertEqual(json.loads(self.machine.config_file.read_text(encoding="utf-8")), INVENTED_CONFIG)


if __name__ == "__main__":
    unittest.main()
