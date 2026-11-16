"""``m2b settings`` lists every setting of the three files; ``m2b settings set`` changes a switch."""

from __future__ import annotations

import json
from typing import Any
from unittest import mock

import test_commands
from m2b import cli
from m2b.commands import settings as settings_commands
from m2b.config import catalog, machine
from m2b.config.machine import load_machine_config
from m2b.config.profile import load_profile, save_profile
from m2b.config.store_settings import STORE_SETTINGS_FILE_NAME

PROFILE: dict[str, Any] = {
    "version": 1,
    "owner": "Alex",
    "language": "en",
    "spheres": [{"id": "acme", "label": "Acme Ltd", "billable": True}, {"id": "private", "default": True}],
    "customers": ["Globex", "Initech"],
}
ENTRY_KEYS = {
    "key",
    "file",
    "scope",
    "group",
    "place",
    "kind",
    "title",
    "does",
    "read",
    "value",
    "shows",
    "default",
    "choices",
    "changed_by",
    "change",
    "curation",
}
OUTSIDE_CLAUDE_CODE = "in a terminal of your own, outside Claude Code"
NO_FORMAT = "{} in the store does not follow its format; {} says where"
ZERO_WIDTH_SPACE = chr(0x200B)
HANGUL_FILLER = chr(0x3164)
LINE_BREAK, ESCAPE, BELL = chr(0x0A), chr(0x1B), chr(0x07)
LINE_SEPARATOR, PARAGRAPH_SEPARATOR = chr(0x2028), chr(0x2029)


class SettingsFixture(test_commands.CommandTest):
    def setUp(self) -> None:
        super().setUp()
        self.set_up(calendar="none")
        save_profile(self.store, PROFILE)

    def listed(self) -> dict[str, Any]:
        answer: dict[str, Any] = self.run_json("settings")
        return answer

    def entry(self, key: str, scope: str = catalog.MACHINE) -> dict[str, Any]:
        found = [entry for entry in self.listed()["settings"] if (entry["scope"], entry["key"]) == (scope, key)]
        self.assertEqual(len(found), 1, key)
        entry: dict[str, Any] = found[0]
        return entry

    def files(self) -> tuple[bytes, bytes, bytes]:
        return (
            self.machine.config_file.read_bytes(),
            (self.store_root / STORE_SETTINGS_FILE_NAME).read_bytes(),
            (self.store_root / "profile.json").read_bytes(),
        )

    def refused(self, *arguments: str) -> str:
        """The one line a refused ``settings set`` says, after checking that it changed no file."""
        before = self.files()
        code, out, err = self.run_command("settings", "set", *arguments)
        self.assertEqual((code, out), (cli.EXIT_USAGE, ""))
        self.assertEqual(self.files(), before)
        self.assertEqual(err.count("\n"), 1, err)
        self.assertTrue(err.startswith("m2b: "), err)
        return err


class SettingsListTest(SettingsFixture):
    def test_every_setting_of_the_three_files_is_listed_with_what_the_catalog_says(self) -> None:
        """Covers: B194"""
        answer = self.listed()

        self.assertEqual(
            [(entry["scope"], entry["key"]) for entry in answer["settings"]],
            [(setting.scope, setting.key) for setting in catalog.settings()],
        )
        for entry, setting in zip(answer["settings"], catalog.settings()):
            with self.subTest(key=setting.key):
                self.assertEqual(set(entry), ENTRY_KEYS)
                self.assertEqual(
                    (entry["file"], entry["kind"], entry["title"], entry["does"], entry["changed_by"], entry["change"]),
                    (setting.file, setting.kind, setting.title, setting.does, setting.how, setting.change),
                )
                self.assertIs(entry["read"], True)
                self.assertIsInstance(entry["shows"], str)
        self.assertEqual(answer["not_read"], {})
        self.assertIs(answer["curates"], True)
        scopes = [entry["scope"] for entry in answer["settings"]]
        self.assertEqual(sorted(scopes, key=["machine", "store", "owner"].index), scopes)
        self.assertEqual(answer["settings"][0]["key"], "version")
        self.assertEqual(len(scopes), 32)

    def test_as_json_every_setting_names_its_group_and_its_place_and_the_groups_come_in_their_order(self) -> None:
        """Covers: B210"""
        answer = self.listed()

        self.assertEqual(
            answer["groups"],
            [
                {"name": "shows", "title": "What m2b shows", "folded": False},
                {"name": "reads", "title": "What m2b reads", "folded": False},
                {"name": "curation", "title": "Curation", "folded": False},
                {"name": "about", "title": "About this setup", "folded": True},
            ],
        )
        placed = {(entry["scope"], entry["key"]): (entry["group"], entry["place"]) for entry in answer["settings"]}
        self.assertEqual(placed, catalog.places())
        self.assertEqual(placed[("machine", "band.due_tasks")], ("shows", 1))
        self.assertEqual(placed[("machine", "sessions.propose")], ("reads", 2))
        self.assertEqual(placed[("owner", "language")], ("curation", 5))
        self.assertEqual(placed[("machine", "store.path")], ("about", 1))
        for group in answer["groups"]:
            with self.subTest(group=group["name"]):
                held = sorted(place for name, place in placed.values() if name == group["name"])
                self.assertEqual(held, list(range(1, len(held) + 1)))

    def test_a_file_that_cannot_be_read_keeps_its_settings_in_their_groups(self) -> None:
        """Covers: B210"""
        (self.store_root / STORE_SETTINGS_FILE_NAME).write_text("{ no json", encoding="utf-8")

        answer = self.listed()

        machine_that_curates = self.entry("curating_machine", catalog.STORE)
        self.assertEqual(
            (machine_that_curates["read"], machine_that_curates["group"], machine_that_curates["place"]),
            (False, "curation", 2),
        )
        self.assertEqual(len(answer["groups"]), 4)

    def test_a_switch_comes_with_its_value_its_default_and_its_few_values(self) -> None:
        """Covers: B194"""
        self.assertEqual(
            self.entry("curation.paused"),
            {
                "key": "curation.paused",
                "file": "config.json",
                "scope": "machine",
                "group": "curation",
                "place": 3,
                "kind": "switch",
                "title": "Curation paused",
                "does": catalog.named("curation.paused")[0].does,
                "read": True,
                "value": False,
                "shows": "off",
                "default": False,
                "choices": [True, False],
                "changed_by": "command",
                "change": "m2b settings set curation.paused true|false",
                "curation": True,
            },
        )
        git_commit = self.entry("curation.git_commit")
        self.assertEqual((git_commit["value"], git_commit["shows"], git_commit["default"]), (True, "on", True))
        language = self.entry("language", catalog.OWNER)
        self.assertEqual(
            (language["file"], language["kind"], language["value"], language["shows"], language["default"]),
            ("profile.json", "switch", "en", "en", "en"),
        )
        self.assertEqual(language["choices"], ["de", "en"])
        self.assertIs(language["curation"], False)

    def test_a_shown_setting_comes_with_its_value_and_how_it_is_changed(self) -> None:
        """Covers: B194"""
        machine_id = self.entry("machine_id")
        self.assertEqual(
            (machine_id["kind"], machine_id["value"], machine_id["shows"], machine_id["changed_by"]),
            ("shown", "sb-test-m1", "sb-test-m1", "never by hand"),
        )
        self.assertIsNone(machine_id["change"])
        self.assertEqual(machine_id["choices"], [])
        path = self.entry("store.path")
        self.assertEqual((path["value"], path["changed_by"]), (str(self.store_root), "command"))
        self.assertEqual(path["change"], "m2b config set store.path <folder>")
        budget = self.entry("curation.max_budget_usd")
        self.assertEqual((budget["value"], budget["shows"], budget["default"]), (None, "not set", None))
        backend = self.entry("tasks.backend", catalog.STORE)
        self.assertEqual(
            (backend["file"], backend["value"], backend["changed_by"], backend["change"]),
            ("store.json", "markdown", "setup", "/m2b:setup"),
        )
        since = self.entry("journal_since", catalog.STORE)
        self.assertEqual((since["value"], since["shows"]), ("2026-11-01", "2026-11-01"))
        self.assertEqual(self.entry("tasks.list", catalog.STORE)["shows"], "not set")
        taken_over = self.entry("curating_machine", catalog.STORE)
        self.assertEqual((taken_over["value"], taken_over["change"]), ("sb-test-m1", "m2b curate take-over"))
        self.assertEqual(self.entry("owner", catalog.OWNER)["value"], "Alex")

    def test_a_named_setting_comes_as_a_count_and_never_with_what_it_holds(self) -> None:
        """Covers: B194"""
        self.run_command("config", "set", "distillate.skip_under", json.dumps(["~/code/globex-secret"]))
        save_profile(
            self.store,
            {**PROFILE, "worklog_leave_out": {"path_under": ["~/code/hidden"], "git_remote_contains": ["a/", "b/"]}},
        )

        shown = {
            (scope, key): self.entry(key, scope)
            for scope, key in (
                (catalog.MACHINE, "executables"),
                (catalog.MACHINE, "distillate.skip_under"),
                (catalog.MACHINE, "addons.worklog"),
                (catalog.OWNER, "spheres"),
                (catalog.OWNER, "customers"),
                (catalog.OWNER, "worklog_leave_out"),
            )
        }

        self.assertEqual(
            {key: entry["shows"] for (_, key), entry in shown.items()},
            {
                "executables": "3 named",
                "distillate.skip_under": "1 folder",
                "addons.worklog": "off",
                "spheres": "2 spheres",
                "customers": "2 customers",
                "worklog_leave_out": "1 folder, 2 remotes",
            },
        )
        for entry in shown.values():
            self.assertEqual((entry["kind"], entry["value"]), ("named", None))
        for mode in ((), ("--json",)):
            out = self.run_command("settings", *mode)[1]
            for held in ("Globex", "Initech", "Acme", "globex-secret", "hidden", "fake_osascript", str(self.bin)):
                self.assertNotIn(held, out, mode)

    def test_nothing_held_reads_as_none_and_an_add_on_turned_on_as_on(self) -> None:
        """Covers: B194"""
        save_profile(self.store, {"version": 1, "owner": "Alex"})
        self.run_command("config", "set", "executables", "{}")
        self.run_command("addons", "on", "worklog")

        self.assertEqual(self.entry("executables")["shows"], "none named")
        self.assertEqual(self.entry("distillate.skip_under")["shows"], "no folders")
        self.assertEqual(self.entry("addons.worklog")["shows"], "on")
        self.assertEqual(self.entry("spheres", catalog.OWNER)["shows"], "no spheres")
        self.assertEqual(self.entry("customers", catalog.OWNER)["shows"], "no customers")
        self.assertEqual(self.entry("worklog_leave_out", catalog.OWNER)["shows"], "nothing")

    def test_a_value_shows_a_character_that_draws_nothing_written_out(self) -> None:
        """Covers: B194"""
        save_profile(self.store, {**PROFILE, "owner": f"Al{ZERO_WIDTH_SPACE}ex"})

        owner = self.entry("owner", catalog.OWNER)

        self.assertEqual(owner["shows"], "Al<U+200B>ex")
        self.assertEqual(owner["value"], "Al<U+200B>ex")
        self.assertNotIn(ZERO_WIDTH_SPACE, self.run_command("settings", "--json")[1])
        self.assertNotIn(ZERO_WIDTH_SPACE, self.run_command("settings")[1])

    def test_a_model_the_switch_does_not_offer_is_shown_as_it_is(self) -> None:
        """Covers: B194"""
        self.assertEqual(self.run_command("config", "set", "curation.model", "opus")[0], cli.EXIT_OK)

        model = self.entry("curation.model")

        self.assertEqual((model["value"], model["shows"], model["choices"]), ("opus", "opus", ["haiku", "sonnet"]))

    def test_the_settings_of_the_curation_run_are_marked_and_whether_this_machine_curates_is_said(self) -> None:
        """Covers: B194"""
        marked = sorted(entry["key"] for entry in self.listed()["settings"] if entry["curation"])

        self.assertEqual(marked, sorted(f"curation.{key}" for key in machine.CURATION_KEYS))
        raw = json.loads((self.store_root / STORE_SETTINGS_FILE_NAME).read_text(encoding="utf-8"))
        raw["curating_machine"] = "sb-test-other"
        (self.store_root / STORE_SETTINGS_FILE_NAME).write_text(json.dumps(raw), encoding="utf-8")
        self.assertIs(self.listed()["curates"], False)

    def test_a_store_that_cannot_be_read_leaves_its_settings_listed_as_not_read(self) -> None:
        """Covers: B194"""
        (self.store_root / STORE_SETTINGS_FILE_NAME).write_text("{ no json", encoding="utf-8")

        answer = self.listed()

        self.assertEqual(sorted(answer["not_read"]), ["store.json"])
        self.assertEqual(
            answer["not_read"]["store.json"],
            "store.json in the store does not follow its format; m2b status says where",
        )
        self.assertIsNone(answer["curates"])
        for entry in answer["settings"]:
            with self.subTest(key=entry["key"]):
                if entry["scope"] == catalog.STORE:
                    self.assertEqual((entry["read"], entry["value"], entry["shows"]), (False, None, None))
                else:
                    self.assertIs(entry["read"], True)
        code, out, _ = self.run_command("settings")
        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("\n  not read: store.json in the store does not follow its format; m2b status says where\n", out)
        self.assertIn("\n  curating_machine: not read\n", out)
        self.assertIn("\n  tasks.timeout_seconds: not read\n", out)

    def test_a_store_without_a_profile_and_one_out_of_reach_say_so_per_file(self) -> None:
        """Covers: B194"""
        (self.store_root / "profile.json").unlink()

        answer = self.listed()

        self.assertEqual(sorted(answer["not_read"]), ["profile.json"])
        self.assertIn("no profile.json in the store", answer["not_read"]["profile.json"])
        self.assertIs(self.entry("language", catalog.OWNER)["read"], False)
        self.assertEqual(self.entry("language", catalog.OWNER)["choices"], ["de", "en"])

        self.run_command("config", "set", "store.path", str(self.store_root.parent / "sb-test-gone"))
        answer = self.listed()

        self.assertEqual(sorted(answer["not_read"]), ["profile.json", "store.json"])
        self.assertIs(self.entry("store.path")["read"], True)

    def test_without_a_machine_config_the_command_names_setup(self) -> None:
        """Covers: B194"""
        self.machine.config_file.unlink()

        code, out, err = self.run_command("settings", "--json")

        self.assertEqual((code, out), (cli.EXIT_USAGE, ""))
        self.assertIn("no machine config", err)

    def test_as_text_every_setting_is_listed_under_its_file(self) -> None:
        """Covers: B194"""
        code, out, err = self.run_command("settings")

        self.assertEqual((code, err), (cli.EXIT_OK, ""))
        self.assertTrue(out.startswith("This machine (config.json)\n  version: 1\n"), out[:80])
        self.assertTrue(out.endswith("'<the whole list as JSON>'\n"), out[-80:])
        self.assertIn(
            "\n  tasks.timeout_seconds: 20\n"
            "      How many seconds a call to the task list may take. No command writes it.\n"
            "      by hand: edit tasks.timeout_seconds in store.json, in the store folder\n",
            out,
        )
        self.assertEqual(out.count("\n\n"), 2)
        headings = [line for line in out.splitlines() if line and not line.startswith(" ")]
        self.assertEqual(
            headings,
            [
                "This machine (config.json)",
                "The store, for every machine (store.json)",
                "The owner, for every machine (profile.json)",
            ],
        )
        for setting in catalog.settings():
            self.assertIn(f"\n  {setting.key}: ", out)
        self.assertIn(
            "\n  curation.paused: off\n"
            f"      {catalog.named('curation.paused')[0].does}\n"
            "      switch: m2b settings set curation.paused true|false\n",
            out,
        )
        self.assertIn("\n  machine_id: sb-test-m1\n", out)
        self.assertIn("      kept by m2b, never changed by hand\n", out)
        self.assertIn("      change: m2b curate take-over\n", out)
        self.assertIn("      set up with /m2b:setup\n", out)

    def test_as_text_a_value_that_is_not_the_default_names_the_default(self) -> None:
        """Covers: B194"""
        self.run_command("settings", "set", "curation.paused", "true")
        self.run_command("config", "set", "calendar.timeout_seconds", "45")

        out = self.run_command("settings")[1]

        self.assertIn("\n  curation.paused: on (default off)\n", out)
        self.assertIn("\n  calendar.timeout_seconds: 45 (default 20)\n", out)
        self.assertIn("\n  curation.git_commit: on\n", out)


class SettingsSetTest(SettingsFixture):
    def test_a_switch_of_the_machine_is_turned_on_and_off(self) -> None:
        """Covers: B195"""
        for key, on in (
            ("curation.paused", True),
            ("curation.read_sessions", True),
            ("curation.git_commit", False),
            ("band.topics", True),
        ):
            with self.subTest(key=key):
                section, _, name = key.partition(".")
                code, out, err = self.run_command("settings", "set", key, json.dumps(on))
                self.assertEqual((code, out, err), (cli.EXIT_OK, "", ""))
                self.assertIs(getattr(getattr(load_machine_config(self.machine), section), name), on)
                self.assertIs(self.entry(key)["value"], on)
                self.assertEqual(self.run_command("settings", "set", key, json.dumps(not on))[0], cli.EXIT_OK)
                self.assertIs(getattr(getattr(load_machine_config(self.machine), section), name), not on)

    def test_the_key_and_the_value_may_follow_two_dashes_as_the_band_hands_them_on(self) -> None:
        """Covers: B195"""
        code, out, err = self.run_command("settings", "set", "--", "curation.paused", "true")

        self.assertEqual((code, out, err), (cli.EXIT_OK, "", ""))
        self.assertTrue(load_machine_config(self.machine).curation.paused)

    def test_a_switch_of_a_few_names_takes_one_of_them(self) -> None:
        """Covers: B195"""
        self.assertEqual(self.run_command("settings", "set", "curation.model", "sonnet")[0], cli.EXIT_OK)
        self.assertEqual(load_machine_config(self.machine).curation.model, "sonnet")

        for way in ("list", "off", "count"):
            with self.subTest(way=way):
                self.assertEqual(self.run_command("settings", "set", "band.due_tasks", way)[0], cli.EXIT_OK)
                self.assertEqual(load_machine_config(self.machine).band.due_tasks, way)
                self.assertEqual(self.entry("band.due_tasks")["value"], way)

        self.assertEqual(self.run_command("settings", "set", "language", "de")[0], cli.EXIT_OK)
        loaded = load_profile(self.store)
        assert loaded is not None
        self.assertEqual((loaded.language, loaded.owner, loaded.customers), ("de", "Alex", ("Globex", "Initech")))

    def test_a_value_the_switch_does_not_have_is_refused_with_one_line(self) -> None:
        """Covers: B195"""
        for key, value, expected in (
            ("curation.paused", "1", "curation.paused is true or false, not 1"),
            ("curation.paused", "yes", "curation.paused is true or false, not yes"),
            ("curation.paused", '"true"', 'curation.paused is true or false, not "true"'),
            ("band.topics", "0", "band.topics is true or false, not 0"),
            ("band.due_tasks", "true", "band.due_tasks is off or count or list, not true"),
            ("band.due_tasks", "all", "band.due_tasks is off or count or list, not all"),
            ("curation.model", "opus", "curation.model is haiku or sonnet here, not opus"),
            ("curation.model", "true", "curation.model is haiku or sonnet here, not true"),
            ("language", "fr", "language is de or en, not fr"),
        ):
            with self.subTest(key=key, value=value):
                self.assertIn(expected, self.refused(key, value))
        self.assertIn("m2b config set curation.model", self.refused("curation.model", "opus"))
        self.assertNotIn("m2b config set", self.refused("band.due_tasks", "all"))

    def test_a_refusal_stays_one_line_whatever_was_typed(self) -> None:
        """Covers: B195"""
        for typed, written in (
            ("true" + LINE_BREAK + "m2b: done", "not true<U+000A>m2b: done"),
            ("tr" + ZERO_WIDTH_SPACE + "ue", "not tr<U+200B>ue"),
            ("tr" + HANGUL_FILLER + "ue", "not tr<U+3164>ue"),
            ("on" + ESCAPE + "[2K", "not on<U+001B>[2K"),
        ):
            with self.subTest(written=written):
                self.assertIn(written, self.refused("curation.paused", typed))
        self.assertIn("curation.pau<U+200B>sed;", self.refused("curation.pau" + ZERO_WIDTH_SPACE + "sed", "true"))
        self.assertIn("curation<U+000A>m2b: done;", self.refused("curation" + LINE_BREAK + "m2b: done", "true"))

    def test_every_setting_that_is_no_switch_is_refused_with_one_line_that_says_how_it_changes(self) -> None:
        """Covers: B195"""
        for setting in catalog.settings():
            if setting.kind == catalog.SWITCH:
                continue
            with self.subTest(key=setting.key):
                line = self.refused(setting.key, "true")
                self.assertIn(f"{setting.key} is no switch", line)
                if setting.change is not None:
                    self.assertIn(setting.change, line)
                else:
                    self.assertIn("never changed by hand", line)
        self.assertIn(
            "calendar.timeout_seconds is no switch, and m2b settings set changes a switch only: "
            "change it with m2b config set calendar.timeout_seconds <seconds>",
            self.refused("calendar.timeout_seconds", "45"),
        )
        self.assertIn("/m2b:setup changes it", self.refused("calendar.backend", "apple-calendar"))
        self.assertIn(
            "tasks.timeout_seconds is no switch, and m2b settings set changes a switch only: no command writes it; "
            "edit tasks.timeout_seconds in store.json, in the store folder",
            self.refused("tasks.timeout_seconds", "45"),
        )
        self.assertIn("m2b keeps it, and it is never changed by hand", self.refused("machine_id", "sb-test-m2"))

    def test_a_key_no_setting_has_is_refused_with_one_line(self) -> None:
        """Covers: B195"""
        for key in ("curation", "sessions", "store.colour", "addons.backup.target", "executables.claude", ""):
            with self.subTest(key=key):
                self.assertIn("m2b settings lists them", self.refused(key, "true"))
        self.assertIn("no setting is named ''; ", self.refused("", "true"))
        self.assertIn("no setting is named store.colour; ", self.refused("store.colour", "true"))

    def test_a_whole_section_cannot_carry_a_switch_past_the_command(self) -> None:
        """Covers: B195"""
        self.refused("sessions", '{"propose": true}')
        self.refused("curation", '{"paused": true, "git_directory": "/srv/sb-test-elsewhere"}')

    def test_the_language_of_a_store_without_a_profile_names_what_is_missing(self) -> None:
        (self.store_root / "profile.json").unlink()

        code, _, err = self.run_command("settings", "set", "language", "de")

        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertIn("no profile.json in the store", err)

    def test_every_switch_has_a_file_the_command_writes(self) -> None:
        """Covers: B195"""
        for setting in catalog.settings():
            if setting.kind == catalog.SWITCH:
                self.assertIn(setting.scope, settings_commands.SWITCH_WRITERS, setting.key)


class RulesOfAChangeTest(SettingsFixture):
    """What no change of the machine config may do holds for ``config set`` and ``settings set`` alike."""

    def test_neither_command_turns_handing_in_on_inside_a_claude_code_session(self) -> None:
        """Covers: B196"""
        self.environ["CLAUDECODE"] = "1"
        for command in ("config", "settings"):
            with self.subTest(command=command):
                code, out, err = self.run_command(command, "set", "sessions.propose", "true")
                self.assertEqual((code, out), (cli.EXIT_USAGE, ""))
                self.assertIn(OUTSIDE_CLAUDE_CODE, err)
                self.assertEqual(err.count("\n"), 1)
                self.assertFalse(load_machine_config(self.machine).sessions.propose)

    def test_both_commands_say_the_refusal_in_the_same_words(self) -> None:
        """Covers: B196"""
        self.environ["CLAUDECODE"] = "1"

        lines = {self.run_command(command, "set", "sessions.propose", "true")[2] for command in ("config", "settings")}

        self.assertEqual(len(lines), 1)

    def test_outside_a_session_and_with_an_empty_variable_either_command_turns_it_on(self) -> None:
        """Covers: B196"""
        for command, environ in (("config", {}), ("settings", {}), ("settings", {"CLAUDECODE": ""})):
            with self.subTest(command=command, environ=environ):
                self.environ.pop("CLAUDECODE", None)
                self.environ.update(environ)
                self.assertEqual(self.run_command(command, "set", "sessions.propose", "true")[0], cli.EXIT_OK)
                self.assertTrue(load_machine_config(self.machine).sessions.propose)
                self.environ["CLAUDECODE"] = "1"
                self.assertEqual(self.run_command(command, "set", "sessions.propose", "false")[0], cli.EXIT_OK)
                self.assertFalse(load_machine_config(self.machine).sessions.propose)

    def test_one_function_holds_the_rules_and_both_commands_ask_it(self) -> None:
        """Covers: B196"""
        asked: list[tuple[str, object]] = []

        def remember(context: object, key: str, value: object) -> None:
            asked.append((key, value))

        with mock.patch.object(settings_commands, "refuse_forbidden_machine_config_change", remember):
            self.run_command("config", "set", "curation.paused", "true")
            self.run_command("settings", "set", "curation.paused", "false")
            self.run_command("settings", "set", "language", "de")

        self.assertEqual(asked, [("curation.paused", True), ("curation.paused", False)])


class WhatAnotherDeviceWroteTest(SettingsFixture):
    """The store's files can be written from other devices; nothing in them forges a line or leaks a name."""

    LINES = 32 * 3 + 3 + 2

    def write_raw(self, name: str, raw: dict[str, Any]) -> None:
        (self.store_root / name).write_text(json.dumps(raw), encoding="utf-8")

    def store_json(self) -> dict[str, Any]:
        raw: dict[str, Any] = json.loads((self.store_root / STORE_SETTINGS_FILE_NAME).read_text(encoding="utf-8"))
        return raw

    def test_a_line_break_or_an_escape_in_a_value_is_written_out_as_text_and_as_json(self) -> None:
        """Covers: B194"""
        forged = "Inbox" + LINE_BREAK + "  sessions.propose: on"
        self.write_raw(
            STORE_SETTINGS_FILE_NAME, {**self.store_json(), "tasks": {"backend": "markdown", "list": forged}}
        )
        self.write_raw("profile.json", {**PROFILE, "owner": "Al" + ESCAPE + "]52;c;eA==" + BELL + "ex"})
        self.run_command("config", "set", "curation.model", "opus" + LINE_BREAK + "  curation.paused: on")

        code, out, err = self.run_command("settings")

        self.assertEqual((code, err), (cli.EXIT_OK, ""))
        self.assertEqual(len(out.splitlines()), self.LINES)
        self.assertNotIn(ESCAPE, out)
        self.assertNotIn(BELL, out)
        self.assertIn("\n  tasks.list: Inbox<U+000A>  sessions.propose: on\n", out)
        self.assertIn("\n  owner: Al<U+001B>]52;c;eA==<U+0007>ex\n", out)
        self.assertIn("\n  curation.model: opus<U+000A>  curation.paused: on (default haiku)\n", out)
        self.assertEqual(out.count("\n  sessions.propose: "), 1)
        owner = self.entry("owner", catalog.OWNER)
        self.assertEqual((owner["value"], owner["shows"]), ("Al<U+001B>]52;c;eA==<U+0007>ex",) * 2)
        listed = self.entry("tasks.list", catalog.STORE)
        self.assertEqual((listed["value"], listed["shows"]), ("Inbox<U+000A>  sessions.propose: on",) * 2)
        model = self.entry("curation.model")
        self.assertEqual(model["value"], "opus<U+000A>  curation.paused: on")

    def test_a_profile_that_does_not_follow_its_format_is_not_read_and_not_quoted(self) -> None:
        """Covers: B194"""
        for broken in (
            {**PROFILE, "spheres": [{"id": "Globex-AG"}]},
            {**PROFILE, "spheres": [{"id": "globex"}, {"id": "globex"}]},
            {**PROFILE, "worklog_leave_out": {"path_under": ["/Users/alex/code/globex"]}},
            {**PROFILE, "customers": "Globex"},
        ):
            with self.subTest(broken=sorted(broken)):
                self.write_raw("profile.json", broken)
                answer = self.listed()
                self.assertEqual(
                    answer["not_read"],
                    {"profile.json": NO_FORMAT.format("profile.json", "m2b profile get")},
                )
                for mode in ((), ("--json",)):
                    out = self.run_command("settings", *mode)[1]
                    self.assertNotIn("lobex", out)
                self.assertIn("lobex", self.run_command("profile", "get")[2])

    def test_a_key_the_store_does_not_know_is_not_quoted_either(self) -> None:
        """Covers: B194"""
        self.write_raw(STORE_SETTINGS_FILE_NAME, {**self.store_json(), "x" + LINE_BREAK + "  forged: on": 1})

        code, out, _ = self.run_command("settings")

        self.assertEqual(code, cli.EXIT_OK)
        self.assertEqual(len(out.splitlines()), self.LINES + 1)
        self.assertNotIn("forged", out)
        self.assertIn("\n  not read: store.json in the store does not follow its format; m2b status says where\n", out)
        self.assertIn("forged", self.run_json("status")["store_error"])

    def test_a_store_out_of_reach_names_its_folder_on_one_line(self) -> None:
        """Covers: B194"""
        gone = str(self.store_root.parent / ("sb-test-gone" + LINE_BREAK + "  forged: on"))
        config = json.loads(self.machine.config_file.read_text(encoding="utf-8"))
        config["store"]["path"] = gone
        self.machine.config_file.write_text(json.dumps(config), encoding="utf-8")

        answer = self.listed()

        self.assertEqual(sorted(answer["not_read"]), ["profile.json", "store.json"])
        for reason in answer["not_read"].values():
            self.assertIn("sb-test-gone<U+000A>  forged: on cannot be reached", reason)
        out = self.run_command("settings")[1]
        self.assertEqual(len(out.splitlines()), self.LINES + 2)
        self.assertEqual(out.count("forged: on"), 3)
        self.assertIn("sb-test-gone<U+000A>  forged: on\n", out)

    def test_a_language_this_m2b_has_no_texts_for_is_shown_as_the_file_names_it(self) -> None:
        """Covers: B194"""
        for version in (1, 2, 3):
            with self.subTest(version=version):
                self.write_raw("profile.json", {**PROFILE, "version": version, "language": "fr"})
                language = self.entry("language", catalog.OWNER)
                self.assertEqual(
                    (language["value"], language["shows"], language["choices"]), ("fr", "fr", ["de", "en"])
                )
                self.assertIn("\n  language: fr (default en)\n", self.run_command("settings")[1])
                self.assertEqual(self.entry("owner", catalog.OWNER)["value"], "Alex")

    def test_a_separator_that_ends_a_line_for_some_readers_is_written_out(self) -> None:
        """Covers: B194"""
        forged = "Inbox" + LINE_SEPARATOR + "  sessions.propose: on" + PARAGRAPH_SEPARATOR
        self.write_raw(
            STORE_SETTINGS_FILE_NAME, {**self.store_json(), "tasks": {"backend": "markdown", "list": forged}}
        )

        out = self.run_command("settings")[1]

        self.assertEqual(len(out.splitlines()), self.LINES)
        self.assertIn("\n  tasks.list: Inbox<U+2028>  sessions.propose: on<U+2029>\n", out)
        self.assertNotIn(LINE_SEPARATOR, self.run_command("settings", "--json")[1])

    def test_a_switch_of_the_owner_is_refused_without_a_word_of_a_profile_that_does_not_follow_its_format(self) -> None:
        """Covers: B195"""
        for broken in (
            {**PROFILE, "worklog_leave_out": {"path_under": ["/Users/alex/code/globex"]}},
            {**PROFILE, "x" + LINE_BREAK + "  forged" + ESCAPE + "[2J": 1},
        ):
            with self.subTest(broken=sorted(broken)[-1][:8]):
                self.write_raw("profile.json", broken)
                line = self.refused("language", "de")
                self.assertEqual(line, "m2b: " + NO_FORMAT.format("profile.json", "m2b profile get") + LINE_BREAK)


if __name__ == "__main__":
    test_commands.unittest.main()
