from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from m2b.config import profile
from m2b.config.errors import FormatTooNewError, InvalidConfigError, NotSetUpError
from m2b.store.base import EvictedFileError
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard
from store_contract import FakeEviction

INVENTED_PROFILE: dict[str, Any] = {
    "version": 1,
    "owner": "Alex",
    "language": "en",
    "spheres": [
        {
            "id": "acme",
            "label": "Acme Ltd",
            "billable": True,
            "match": {"git_remote_contains": ["github.com/acme-ltd/"], "path_under": ["~/code/acme"]},
        },
        {"id": "private", "default": True},
    ],
    "customers": ["Globex", "Initech"],
}


def _profile(**changes: Any) -> dict[str, Any]:
    raw = copy.deepcopy(INVENTED_PROFILE)
    raw.update(changes)
    return raw


class ParseTest(unittest.TestCase):
    def test_the_documented_example_parses(self) -> None:
        parsed = profile.parse_profile(INVENTED_PROFILE)

        self.assertEqual(parsed.owner, "Alex")
        self.assertEqual(parsed.language, "en")
        self.assertEqual(parsed.customers, ("Globex", "Initech"))
        acme, private = parsed.spheres
        self.assertEqual((acme.id, acme.label, acme.billable, acme.default), ("acme", "Acme Ltd", True, False))
        self.assertEqual(acme.match.git_remote_contains, ("github.com/acme-ltd/",))
        self.assertEqual((private.id, private.label, private.billable, private.default), ("private", None, False, True))

    def test_folders_of_a_sphere_are_relative_to_each_machines_home(self) -> None:
        acme = profile.parse_profile(INVENTED_PROFILE).spheres[0]

        self.assertEqual(acme.match.folders(Path("/home/alex")), (Path("/home/alex/code/acme"),))
        self.assertEqual(acme.match.folders(Path("/Users/dana")), (Path("/Users/dana/code/acme"),))

    def test_an_absolute_sphere_folder_is_refused(self) -> None:
        raw = _profile(spheres=[{"id": "acme", "match": {"path_under": ["/Users/alex/code"]}}])

        with self.assertRaises(InvalidConfigError) as caught:
            profile.parse_profile(raw)

        self.assertIn("spheres[0].match.path_under", str(caught.exception))

    def test_a_language_without_a_locale_names_the_available_ones(self) -> None:
        with self.assertRaises(InvalidConfigError) as caught:
            profile.parse_profile(_profile(language="fr"))

        self.assertIn("de, en", str(caught.exception))

    def test_two_spheres_with_one_id_are_refused(self) -> None:
        with self.assertRaises(InvalidConfigError):
            profile.parse_profile(_profile(spheres=[{"id": "acme"}, {"id": "acme"}]))

    def test_two_default_spheres_are_refused(self) -> None:
        with self.assertRaises(InvalidConfigError):
            profile.parse_profile(_profile(spheres=[{"id": "a", "default": True}, {"id": "b", "default": True}]))

    def test_a_sphere_id_must_be_a_lowercase_token(self) -> None:
        with self.assertRaises(InvalidConfigError):
            profile.parse_profile(_profile(spheres=[{"id": "Acme Ltd"}]))

    def test_what_the_worklog_leaves_out_is_folders_under_the_home_folder(self) -> None:
        """Covers: B111"""
        raw = _profile(worklog_leave_out={"path_under": ["~/code/globex", "~/worktrees/globex"]})

        self.assertEqual(
            profile.parse_profile(raw).worklog_leave_out.path_under, ("~/code/globex", "~/worktrees/globex")
        )
        self.assertEqual(profile.parse_profile(INVENTED_PROFILE).worklog_leave_out.path_under, ())

    def test_what_the_worklog_leaves_out_is_also_named_by_parts_of_git_remote_urls(self) -> None:
        """Covers: B153"""
        raw = _profile(worklog_leave_out={"git_remote_contains": ["git.globex.example/", "globex-ag/"]})

        left_out = profile.parse_profile(raw).worklog_leave_out

        self.assertEqual(left_out.git_remote_contains, ("git.globex.example/", "globex-ag/"))
        self.assertEqual(left_out.path_under, ())
        self.assertEqual(profile.parse_profile(INVENTED_PROFILE).worklog_leave_out.git_remote_contains, ())

    def test_the_folders_left_out_are_under_each_machines_home_however_they_are_written(self) -> None:
        raw = _profile(worklog_leave_out={"path_under": ["~/code/globex", "worktrees/globex"]})

        self.assertEqual(
            profile.parse_profile(raw).worklog_leave_out.folders(Path("/home/alex")),
            (Path("/home/alex/code/globex"), Path("/home/alex/worktrees/globex")),
        )

    def test_what_the_worklog_leaves_out_is_checked_like_a_spheres_folders(self) -> None:
        """Covers: B111"""
        for left_out, named in (
            ({"path_under": ["/Users/alex/code"]}, "worklog_leave_out.path_under"),
            ({"folders": ["~/code"]}, "folders"),
            ({"git_remote_contains": [""]}, "worklog_leave_out.git_remote_contains"),
            ({"git_remote_contains": "globex-ag/"}, "worklog_leave_out.git_remote_contains"),
            (["~/code"], "worklog_leave_out"),
        ):
            with self.subTest(left_out=left_out), self.assertRaises(InvalidConfigError) as caught:
                profile.parse_profile(_profile(worklog_leave_out=left_out))
            self.assertIn(named, str(caught.exception))

    def test_an_unknown_key_is_refused_and_named(self) -> None:
        with self.assertRaisesRegex(InvalidConfigError, "colour.*is not a known key"):
            profile.parse_profile(_profile(colour="teal"))

    def test_a_newer_profile_with_a_new_key_still_says_to_update(self) -> None:
        with self.assertRaises(FormatTooNewError):
            profile.parse_profile(_profile(version=3, added_in_version_three=True))

    def test_a_folder_of_another_user_is_refused(self) -> None:
        raw = _profile(spheres=[{"id": "acme", "match": {"path_under": ["~dana/code"]}}])

        with self.assertRaises(InvalidConfigError):
            profile.parse_profile(raw)

    def test_a_newer_profile_version_says_to_update(self) -> None:
        with self.assertRaises(FormatTooNewError):
            profile.parse_profile(_profile(version=3))


class ReadingAProfileOfANewerMachineTest(unittest.TestCase):
    def test_a_language_without_a_locale_here_reads_as_english(self) -> None:
        read = profile.parse_profile(_profile(language="fr"), for_writing=False)

        self.assertEqual(profile.language_for_clients(read), "en")

    def test_a_newer_version_is_read_without_its_new_keys(self) -> None:
        read = profile.parse_profile(_profile(version=3, added_in_version_three=True), for_writing=False)

        self.assertEqual(read.owner, "Alex")

    def test_a_newer_version_that_does_not_validate_says_to_update(self) -> None:
        with self.assertRaises(FormatTooNewError):
            profile.parse_profile(_profile(version=3, owner=["Alex", "Dana"]), for_writing=False)

    def test_the_known_version_is_still_checked_when_reading(self) -> None:
        with self.assertRaises(InvalidConfigError):
            profile.parse_profile(_profile(ownr="typo"), for_writing=False)


class LanguageTest(unittest.TestCase):
    def test_client_functions_use_english_without_a_profile(self) -> None:
        self.assertEqual(profile.language_for_clients(None), "en")

    def test_client_functions_use_the_profile_language(self) -> None:
        self.assertEqual(profile.language_for_clients(profile.parse_profile(_profile(language="de"))), "de")


class MergeTest(unittest.TestCase):
    def test_merging_spheres_keeps_owner_and_customers(self) -> None:
        current = {"version": 1, "owner": "Alex", "customers": ["Globex"]}

        merged = profile.merge_profile(current, {"spheres": [{"id": "acme", "billable": True}]})

        self.assertEqual(merged["owner"], "Alex")
        self.assertEqual(merged["customers"], ["Globex"])
        self.assertEqual(merged["spheres"], [{"id": "acme", "billable": True}])

    def test_a_sphere_with_a_known_id_replaces_it_in_place(self) -> None:
        merged = profile.merge_profile(INVENTED_PROFILE, {"spheres": [{"id": "acme", "label": "Acme"}, {"id": "lab"}]})

        self.assertEqual([s["id"] for s in merged["spheres"]], ["acme", "private", "lab"])
        self.assertEqual(merged["spheres"][0], {"id": "acme", "label": "Acme"})

    def test_customers_are_added_once_in_order(self) -> None:
        merged = profile.merge_profile(INVENTED_PROFILE, {"customers": ["Initech", "Hooli"]})

        self.assertEqual(merged["customers"], ["Globex", "Initech", "Hooli"])

    def test_a_customer_named_twice_in_the_patch_is_added_once(self) -> None:
        merged = profile.merge_profile(INVENTED_PROFILE, {"customers": ["Hooli", "Hooli", "Globex"]})

        self.assertEqual(merged["customers"], ["Globex", "Initech", "Hooli"])

    def test_a_merge_into_no_profile_starts_one(self) -> None:
        merged = profile.merge_profile(None, {"owner": "Dana"})

        self.assertEqual(merged, {"version": 1, "owner": "Dana"})

    def test_the_inputs_are_not_changed(self) -> None:
        before = copy.deepcopy(INVENTED_PROFILE)

        profile.merge_profile(INVENTED_PROFILE, {"spheres": [{"id": "acme"}], "customers": ["Hooli"]})

        self.assertEqual(INVENTED_PROFILE, before)


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

    def _saved(self) -> dict[str, Any]:
        data: dict[str, Any] = json.loads((self.store / "profile.json").read_text(encoding="utf-8"))
        return data

    def test_no_profile_file_means_no_profile_for_clients(self) -> None:
        self.assertIsNone(profile.load_profile(self.files))

    def test_an_evicted_profile_is_not_read_and_not_taken_for_a_missing_one(self) -> None:
        """Covers: B6"""
        (self.store / "profile.json").write_text(json.dumps(INVENTED_PROFILE), encoding="utf-8")
        self.eviction.evicted.add(self.store / "profile.json")

        for call in (profile.load_profile, profile.require_profile):
            with self.subTest(call=call.__name__), self.assertRaises(EvictedFileError):
                call(self.files)

    def test_an_evicted_profile_is_never_written_over(self) -> None:
        (self.store / "profile.json").write_text(json.dumps(INVENTED_PROFILE), encoding="utf-8")
        self.eviction.evicted.add(self.store / "profile.json")

        with self.assertRaises(EvictedFileError):
            profile.merge_into_profile(self.files, {"customers": ["Hooli"]})

        self.assertEqual(self._saved(), INVENTED_PROFILE)

    def test_clients_read_a_profile_written_by_a_newer_machine(self) -> None:
        (self.store / "profile.json").write_text(json.dumps(_profile(language="fr")), encoding="utf-8")

        self.assertEqual(profile.language_for_clients(profile.load_profile(self.files)), "en")

    def test_loading_the_profile_for_curation_names_setup(self) -> None:
        with self.assertRaises(NotSetUpError) as caught:
            profile.require_profile(self.files)

        self.assertIn("/m2b:m2b setup", str(caught.exception))

    def test_merge_into_the_stored_profile_keeps_what_was_there(self) -> None:
        profile.save_profile(self.files, {"version": 1, "owner": "Alex", "customers": ["Globex"]})

        profile.merge_into_profile(self.files, {"spheres": [{"id": "acme"}]})

        saved = self._saved()
        self.assertEqual((saved["owner"], saved["customers"], saved["spheres"]), ("Alex", ["Globex"], [{"id": "acme"}]))

    def test_a_profile_is_written_as_version_two_only_once_it_holds_what_version_two_added(self) -> None:
        """Covers: B111"""
        profile.save_profile(self.files, {"version": 1, "owner": "Alex"})
        profile.merge_into_profile(self.files, {"customers": ["Globex"]})
        self.assertEqual(self._saved()["version"], 1)

        profile.merge_into_profile(self.files, {"worklog_leave_out": {"path_under": ["~/code/globex"]}})

        self.assertEqual(self._saved()["version"], 2)
        self.assertEqual(profile.load_profile(self.files).worklog_leave_out.path_under, ("~/code/globex",))

    def test_a_machine_before_version_two_reads_the_profile_without_what_it_added(self) -> None:
        """Covers: B111"""
        # What an m2b that knows version 1 does with the file: it reads a newer version without the
        # keys it added and refuses to write it, where a version 1 file with the key fails to read.
        raw = {"version": 2, "owner": "Alex", "worklog_leave_out": {"path_under": ["~/code/globex"]}}
        with mock.patch.object(profile, "KNOWN_PROFILE_VERSION", 1):
            self.assertEqual(profile.parse_profile(raw, for_writing=False).owner, "Alex")
            with self.assertRaises(FormatTooNewError):
                profile.parse_profile(raw)

    def test_set_of_one_key_leaves_the_others(self) -> None:
        profile.save_profile(self.files, INVENTED_PROFILE)

        profile.set_profile_value(self.files, "language", "de")

        self.assertEqual(self._saved(), _profile(language="de"))

    def test_a_stored_value_that_is_not_a_list_is_refused_not_split_into_letters(self) -> None:
        (self.store / "profile.json").write_text(json.dumps(_profile(customers="Globex")), encoding="utf-8")

        for patch in ({"customers": ["Hooli"]}, {"spheres": [{"id": "lab"}]}):
            with self.subTest(patch=patch), self.assertRaises(InvalidConfigError):
                profile.merge_into_profile(self.files, patch)

    def test_setting_an_unknown_key_is_refused_and_nothing_is_written(self) -> None:
        profile.save_profile(self.files, INVENTED_PROFILE)

        for write in (
            lambda: profile.set_profile_value(self.files, "colour", "teal"),
            lambda: profile.merge_into_profile(self.files, {"colour": "teal"}),
        ):
            with self.subTest(write=write), self.assertRaisesRegex(InvalidConfigError, "is not a known key"):
                write()
        self.assertEqual(self._saved(), INVENTED_PROFILE)

    def test_set_without_a_profile_names_setup(self) -> None:
        with self.assertRaises(NotSetUpError):
            profile.set_profile_value(self.files, "language", "de")

    def test_an_invalid_profile_is_never_written(self) -> None:
        with self.assertRaises(InvalidConfigError):
            profile.save_profile(self.files, _profile(language="fr"))

        self.assertFalse((self.store / "profile.json").exists())

    def test_a_store_of_a_newer_format_refuses_profile_writes(self) -> None:
        (self.store / "store.json").write_text(
            json.dumps(
                {"format": 99, "tasks": {"backend": "markdown"}, "curating_machine": "m", "journal_since": "2026-11-06"}
            ),
            encoding="utf-8",
        )

        with self.assertRaises(FormatTooNewError):
            profile.save_profile(self.files, INVENTED_PROFILE)


if __name__ == "__main__":
    unittest.main()
