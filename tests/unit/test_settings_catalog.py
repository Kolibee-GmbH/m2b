"""The catalog of the settings is held to the keys the three files take, and to their defaults."""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from locations import PLUGIN_ROOT
from m2b import addons, locale
from m2b.config import catalog, machine, profile, store_settings
from m2b.config.errors import InvalidConfigError

HOME = Path("/home/alex")
MINIMAL_CONFIG: dict[str, Any] = {
    "version": 1,
    "machine_id": "sb-test-m1",
    "store": {"backend": "folder", "path": "/srv/sb-test-store"},
}
MINIMAL_STORE: dict[str, Any] = {
    "format": store_settings.KNOWN_STORE_FORMAT,
    "tasks": {"backend": "markdown"},
    "curating_machine": "sb-test-m1",
    "journal_since": "2026-11-01",
}
MINIMAL_PROFILE: dict[str, Any] = {"version": 1, "owner": "Alex"}
NOT_KNOWN = "is not a known key"


def keys_of(scope: str) -> list[str]:
    return [setting.key for setting in catalog.settings() if setting.scope == scope]


def missing_from_the_catalog() -> dict[str, set[str]]:
    """Per file, the settings its parser takes that the catalog has no entry for."""
    taken = {
        catalog.MACHINE: machine.setting_keys(),
        catalog.STORE: store_settings.setting_keys(),
        catalog.OWNER: profile.setting_keys(),
    }
    return {scope: set(keys) - set(keys_of(scope)) for scope, keys in taken.items()}


NONE_MISSING: dict[str, set[str]] = {catalog.MACHINE: set(), catalog.STORE: set(), catalog.OWNER: set()}


def skills_of_add_ons_not_carried() -> set[str]:
    """The setup skill of each add-on whose code this copy of the plugin does not hold.

    The core names an add-on's setup skill also where the plugin was copied without the add-on,
    as the proof that the core stands alone does; the skill left with the add-on.
    """
    return {f"/m2b:{name}-setup" for name in addons.addon_names() if not (PLUGIN_ROOT / "src" / f"m2b_{name}").is_dir()}


def written_keys(raw: dict[str, Any], prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for key, value in raw.items():
        if isinstance(value, dict):
            keys |= written_keys(value, f"{prefix}{key}.")
        else:
            keys.add(f"{prefix}{key}")
    return keys


class KeyListsTest(unittest.TestCase):
    """The lists the catalog is held to are the ones the parsers refuse an unknown key with."""

    def refusal(self, raw: dict[str, Any]) -> str:
        with self.assertRaises(InvalidConfigError) as caught:
            machine.parse_machine_config(raw, HOME)
        return str(caught.exception)

    def test_the_machine_config_takes_the_listed_keys_of_the_top_level_and_no_other(self) -> None:
        self.assertEqual(set(MINIMAL_CONFIG) - set(machine.KEYS), set())
        for key in machine.KEYS:
            with self.subTest(key=key):
                if key in MINIMAL_CONFIG:
                    continue
                # A value of the wrong type: refused for its type, which only a known key is.
                self.assertNotIn(NOT_KNOWN, self.refusal({**MINIMAL_CONFIG, key: 7}))
        self.assertIn(NOT_KNOWN, self.refusal({**MINIMAL_CONFIG, "colour": 7}))

    def test_each_section_of_the_machine_config_takes_its_listed_keys_and_no_other(self) -> None:
        self.assertEqual(set(machine.SECTION_KEYS) - set(machine.KEYS), set())
        for section, keys in machine.SECTION_KEYS.items():
            written = dict(MINIMAL_CONFIG.get(section, {}))
            for key in keys:
                with self.subTest(section=section, key=key):
                    self.assertNotIn(NOT_KNOWN, self.refusal({**MINIMAL_CONFIG, section: {**written, key: [7]}}))
            with self.subTest(section=section, key="colour"):
                self.assertIn(NOT_KNOWN, self.refusal({**MINIMAL_CONFIG, section: {**written, "colour": 7}}))

    def test_the_profile_takes_its_listed_keys_and_no_other(self) -> None:
        for key in profile.KEYS:
            with self.subTest(key=key):
                if key in MINIMAL_PROFILE:
                    continue
                with self.assertRaises(InvalidConfigError) as caught:
                    profile.parse_profile({**MINIMAL_PROFILE, key: 7})
                self.assertNotIn(NOT_KNOWN, str(caught.exception))
        with self.assertRaises(InvalidConfigError) as caught:
            profile.parse_profile({**MINIMAL_PROFILE, "colour": 7})
        self.assertIn(NOT_KNOWN, str(caught.exception))

    def test_each_object_inside_the_profile_takes_its_listed_keys_and_no_other(self) -> None:
        def profile_with(key: str, value: object) -> dict[str, Any]:
            return {**MINIMAL_PROFILE, key: value}

        objects = (
            (profile.SPHERE_KEYS, lambda held: profile_with("spheres", [{"id": "acme", **held}])),
            (profile.MATCH_KEYS, lambda held: profile_with("spheres", [{"id": "acme", "match": held}])),
            (profile.LEAVE_OUT_KEYS, lambda held: profile_with(profile.ADDED_IN_VERSION_TWO, held)),
        )
        for keys, around in objects:
            for key in keys:
                with self.subTest(key=key):
                    if key == "id":
                        continue
                    with self.assertRaises(InvalidConfigError) as caught:
                        profile.parse_profile(around({key: 7}))
                    self.assertNotIn(NOT_KNOWN, str(caught.exception))
            with self.subTest(keys=keys), self.assertRaises(InvalidConfigError) as caught:
                profile.parse_profile(around({"colour": 7}))
            self.assertIn(NOT_KNOWN, str(caught.exception))

    def test_the_settings_of_the_machine_config_are_its_keys_a_section_by_its_own(self) -> None:
        keys = machine.setting_keys()

        self.assertIn("version", keys)
        self.assertIn("executables", keys)
        self.assertIn("curation.paused", keys)
        self.assertNotIn("curation", keys)
        self.assertNotIn("addons", keys)
        self.assertEqual([key for key in keys if key.startswith("addons.")], ["addons.worklog"])
        for section, section_keys in machine.SECTION_KEYS.items():
            for key in section_keys:
                self.assertIn(f"{section}.{key}", keys)

    def test_the_settings_of_the_store_are_the_keys_of_the_format_this_m2b_writes(self) -> None:
        self.assertEqual(
            store_settings.setting_keys(),
            ("curating_machine", "format", "journal_since", "tasks.backend", "tasks.list", "tasks.timeout_seconds"),
        )
        self.assertEqual(
            profile.setting_keys(), ("version", "owner", "language", "spheres", "customers", "worklog_leave_out")
        )


class CatalogTest(unittest.TestCase):
    def test_the_catalog_names_every_key_of_the_three_files_once(self) -> None:
        """Covers: B194"""
        self.assertEqual(missing_from_the_catalog(), NONE_MISSING)
        self.assertEqual(sorted(keys_of(catalog.MACHINE)), sorted(machine.setting_keys()))
        self.assertEqual(sorted(keys_of(catalog.STORE)), sorted(store_settings.setting_keys()))
        self.assertEqual(sorted(keys_of(catalog.OWNER)), sorted(profile.setting_keys()))
        every = [(setting.scope, setting.key) for setting in catalog.settings()]
        self.assertEqual(len(every), len(set(every)))
        switches = [setting.key for setting in catalog.settings() if setting.kind == catalog.SWITCH]
        self.assertEqual(len(switches), len(set(switches)))
        self.assertEqual(
            {setting.scope for setting in catalog.settings()}, {catalog.MACHINE, catalog.STORE, catalog.OWNER}
        )

    def test_a_key_missing_from_the_catalog_is_what_the_comparison_names(self) -> None:
        """Covers: B194"""
        known = store_settings.KNOWN_STORE_FORMAT
        keys, tasks_keys = store_settings.KEYS_BY_FORMAT[known]
        with mock.patch.object(machine, "SECTION_KEYS", {**machine.SECTION_KEYS, "band": ("due_tasks", "colour")}):
            self.assertEqual(missing_from_the_catalog(), {**NONE_MISSING, catalog.MACHINE: {"band.colour"}})
        with mock.patch.object(machine, "KEYS", (*machine.KEYS, "colour")):
            self.assertEqual(missing_from_the_catalog(), {**NONE_MISSING, catalog.MACHINE: {"colour"}})
        with mock.patch.dict(store_settings.KEYS_BY_FORMAT, {known: (keys | {"colour"}, tasks_keys | {"shade"})}):
            self.assertEqual(missing_from_the_catalog(), {**NONE_MISSING, catalog.STORE: {"colour", "tasks.shade"}})
        with mock.patch.object(profile, "KEYS", (*profile.KEYS, "colour")):
            self.assertEqual(missing_from_the_catalog(), {**NONE_MISSING, catalog.OWNER: {"colour"}})
        self.assertEqual(missing_from_the_catalog(), NONE_MISSING)

    def test_every_setting_says_what_it_is_and_how_it_is_changed(self) -> None:
        """Covers: B194"""
        for setting in catalog.settings():
            with self.subTest(key=setting.key):
                self.assertIn(setting.kind, (catalog.SWITCH, catalog.SHOWN, catalog.NAMED))
                self.assertIn(setting.how, (catalog.COMMAND, catalog.SETUP, catalog.HAND, catalog.NEVER))
                self.assertTrue(setting.title)
                self.assertTrue(setting.does.endswith("."), setting.does)
                self.assertEqual(setting.change is None, setting.how == catalog.NEVER)
                self.assertEqual(setting.file, catalog.FILES[setting.scope])

    def test_a_switch_names_its_few_values_and_is_changed_by_the_one_command(self) -> None:
        """Covers: B195"""
        switches = {setting.key: setting for setting in catalog.settings() if setting.kind == catalog.SWITCH}

        self.assertEqual(
            sorted(switches),
            [
                "band.due_tasks",
                "band.topics",
                "curation.git_commit",
                "curation.model",
                "curation.paused",
                "curation.read_sessions",
                "language",
                "sessions.propose",
            ],
        )
        for key, setting in switches.items():
            with self.subTest(key=key):
                self.assertGreaterEqual(len(setting.choices), 2)
                self.assertEqual(setting.how, catalog.COMMAND)
                self.assertTrue((setting.change or "").startswith(f"m2b settings set {key} "), setting.change)
        self.assertEqual(switches["curation.paused"].choices, (True, False))
        self.assertEqual(switches["curation.paused"].change, "m2b settings set curation.paused true|false")
        self.assertEqual(switches["curation.model"].choices, machine.CURATION_MODELS)
        self.assertEqual(switches["band.due_tasks"].choices, ("off", "count", "list"))
        self.assertEqual(switches["band.due_tasks"].change, "m2b settings set band.due_tasks off|count|list")
        self.assertEqual([key for key, setting in switches.items() if setting.file_takes_more], ["curation.model"])
        self.assertEqual(switches["language"].choices, locale.available_languages())
        for setting in catalog.settings():
            if setting.kind != catalog.SWITCH:
                self.assertEqual(setting.choices, (), setting.key)

    def test_a_default_is_the_value_a_file_without_the_key_reads_as(self) -> None:
        """Covers: B194"""
        read = catalog.values(
            machine.parse_machine_config(MINIMAL_CONFIG, HOME),
            store_settings.parse_store_settings(MINIMAL_STORE),
            profile.parse_profile(MINIMAL_PROFILE),
        )
        written = {
            catalog.MACHINE: written_keys(MINIMAL_CONFIG),
            catalog.STORE: written_keys(MINIMAL_STORE),
            catalog.OWNER: written_keys(MINIMAL_PROFILE),
        }
        for setting in catalog.settings():
            with self.subTest(key=setting.key):
                if setting.kind == catalog.NAMED:
                    continue
                if setting.key in written[setting.scope]:
                    self.assertIsNone(setting.default)
                else:
                    self.assertEqual(read[(setting.scope, setting.key)].value, setting.default)

    def test_every_setting_stands_in_one_group_at_one_place(self) -> None:
        """Covers: B210"""
        held = [setting for group in catalog.groups() for setting in group.holds]

        self.assertEqual(sorted(held), sorted((setting.scope, setting.key) for setting in catalog.settings()))
        self.assertEqual(len(held), len(set(held)))
        for group in catalog.groups():
            with self.subTest(group=group.name):
                self.assertEqual(
                    [catalog.places()[setting] for setting in group.holds],
                    [(group.name, place) for place in range(1, len(group.holds) + 1)],
                )

    def test_the_groups_are_the_four_things_a_person_wants_and_the_few_choices_come_first(self) -> None:
        """Covers: B210"""
        self.assertEqual(
            [(group.name, group.title, group.folded) for group in catalog.groups()],
            [
                ("shows", "What m2b shows", False),
                ("reads", "What m2b reads", False),
                ("curation", "Curation", False),
                ("about", "About this setup", True),
            ],
        )
        by_name = {group.name: group.holds for group in catalog.groups()}
        self.assertEqual(by_name["shows"], ((catalog.MACHINE, "band.due_tasks"), (catalog.MACHINE, "band.topics")))
        self.assertEqual(
            by_name["reads"],
            (
                (catalog.MACHINE, "curation.read_sessions"),
                (catalog.MACHINE, "sessions.propose"),
                (catalog.MACHINE, "distillate.skip_under"),
            ),
        )
        self.assertEqual(
            by_name["curation"][:2], ((catalog.MACHINE, "curation.model"), (catalog.STORE, "curating_machine"))
        )
        self.assertEqual(by_name["about"][0], (catalog.MACHINE, "store.path"))

    def test_a_group_kept_behind_one_row_holds_no_switch(self) -> None:
        """Covers: B210"""
        kinds = {(setting.scope, setting.key): setting.kind for setting in catalog.settings()}
        folded = [setting for group in catalog.groups() if group.folded for setting in group.holds]
        in_sight = [setting for group in catalog.groups() if not group.folded for setting in group.holds]

        self.assertTrue(folded)
        self.assertEqual([setting for setting in folded if kinds[setting] == catalog.SWITCH], [])
        self.assertEqual(
            sorted(key for scope, key in in_sight if kinds[(scope, key)] == catalog.SWITCH),
            sorted(setting.key for setting in catalog.settings() if setting.kind == catalog.SWITCH),
        )

    def test_a_setting_changed_by_a_skill_names_one_the_plugin_has(self) -> None:
        skills = {f"/m2b:{skill.parent.name}" for skill in (PLUGIN_ROOT / "skills").glob("*/SKILL.md")}
        by_setup = [setting for setting in catalog.settings() if setting.how == catalog.SETUP]

        self.assertTrue(by_setup)
        self.assertIn(catalog.SETUP_SKILL, skills)
        for setting in by_setup:
            with self.subTest(key=setting.key):
                if setting.change in skills_of_add_ons_not_carried():
                    continue
                self.assertIn(setting.change, skills)

    def test_an_add_on_is_one_setting_under_its_name(self) -> None:
        for name in addons.addon_names():
            (setting,) = catalog.named(f"addons.{name}")
            self.assertEqual((setting.scope, setting.kind), (catalog.MACHINE, catalog.NAMED))
        self.assertEqual(catalog.named("addons.backup"), ())
        self.assertEqual(catalog.named("curation"), ())
        self.assertEqual([setting.scope for setting in catalog.named("version")], [catalog.MACHINE, catalog.OWNER])


if __name__ == "__main__":
    unittest.main()
