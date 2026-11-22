"""Pinning the marketplace to a release's plugin zip."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from repo_tools import pin_release

MARKETPLACE = {
    "name": "m2b",
    "description": "m2b, your second brain for Claude Code.",
    "owner": {"name": "Kolibee GmbH"},
    "plugins": [{"name": "m2b", "source": "./plugins/m2b", "description": "Your second brain."}],
}
ZIP = b"PK\x03\x04 an invented plugin zip"


class PinTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.marketplace = Path(self._temp.name) / "marketplace.json"
        self.marketplace.write_text(json.dumps(MARKETPLACE, indent=2) + "\n", encoding="utf-8")
        self.fetched: list[str] = []

    def fetch(self, url: str) -> bytes:
        self.fetched.append(url)
        return ZIP

    def run_command(self, *arguments: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = pin_release.main([*arguments, "--marketplace", str(self.marketplace)], fetch=self.fetch)
        return code, out.getvalue(), err.getvalue()

    def test_the_entry_installs_the_zip_of_the_tag_with_its_sha256_and_version(self) -> None:
        code, out, _ = self.run_command("v0.13.0")

        url = "https://github.com/Kolibee-GmbH/m2b/releases/download/v0.13.0/m2b-plugin.zip"
        (entry,) = json.loads(self.marketplace.read_text(encoding="utf-8"))["plugins"]
        self.assertEqual(code, 0)
        self.assertEqual(self.fetched, [url])
        self.assertEqual(entry["source"], {"source": "archive", "url": url, "sha256": hashlib.sha256(ZIP).hexdigest()})
        self.assertEqual(entry["version"], "0.13.0")
        self.assertEqual((entry["name"], entry["description"]), ("m2b", "Your second brain."))
        self.assertIn("v0.13.0", out)

    def test_the_rest_of_the_marketplace_and_its_form_stay_as_they_are(self) -> None:
        self.run_command("v0.13.0")

        written = self.marketplace.read_text(encoding="utf-8")
        data = json.loads(written)
        self.assertEqual(
            {key: data[key] for key in ("name", "description", "owner")},
            {key: MARKETPLACE[key] for key in ("name", "description", "owner")},
        )
        self.assertTrue(written.endswith("}\n"))
        self.assertIn('\n  "plugins": [\n', written)

    def test_a_tag_that_is_not_a_version_is_refused_before_anything_is_fetched(self) -> None:
        code, _, err = self.run_command("0.13.0")

        self.assertEqual((code, self.fetched), (2, []))
        self.assertIn("vX.Y.Z", err)
        self.assertEqual(json.loads(self.marketplace.read_text(encoding="utf-8")), MARKETPLACE)

    def test_a_zip_that_cannot_be_fetched_leaves_the_marketplace_alone(self) -> None:
        def unreachable(url: str) -> bytes:
            raise OSError("HTTP Error 404: Not Found")

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = pin_release.main(["v0.13.0", "--marketplace", str(self.marketplace)], fetch=unreachable)

        self.assertEqual(code, 1)
        self.assertIn("404", err.getvalue())
        self.assertEqual(json.loads(self.marketplace.read_text(encoding="utf-8")), MARKETPLACE)

    def test_the_real_marketplace_has_one_entry_named_as_the_plugin(self) -> None:
        data = json.loads(pin_release.MARKETPLACE.read_text(encoding="utf-8"))

        self.assertEqual([entry["name"] for entry in data["plugins"]], [pin_release.PLUGIN_NAME])
