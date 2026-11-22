"""Points the marketplace at a release's plugin zip: ``scripts/pin-release vX.Y.Z``.

A marketplace entry with a path is read from ``main``, so a new install would get whatever was
merged since the last release. Pinned to the zip the release workflow attached to the tag, with
its SHA-256, every install and every ``/plugin update`` gets exactly the release, and Claude Code
refuses a download that does not match. The command fetches the zip, hashes it and rewrites the
plugin's entry in ``.claude-plugin/marketplace.json``; the pull request that commits it is the last
step of a release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path

from repo_tools import REPO_ROOT

MARKETPLACE = REPO_ROOT / ".claude-plugin" / "marketplace.json"
PLUGIN_NAME = "m2b"
REPOSITORY = "Kolibee-GmbH/m2b"
ZIP_NAME = "m2b-plugin.zip"
TAG = re.compile(r"v(\d+\.\d+\.\d+)")
FETCH_TIMEOUT_SECONDS = 60
EXIT_PINNED, EXIT_NOT_FETCHED, EXIT_USAGE = 0, 1, 2

Fetch = Callable[[str], bytes]


def zip_url(tag: str) -> str:
    return f"https://github.com/{REPOSITORY}/releases/download/{tag}/{ZIP_NAME}"


def fetch_url(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT_SECONDS) as response:
        return bytes(response.read())


def pinned(marketplace: dict[str, object], tag: str, version: str, sha256: str) -> dict[str, object]:
    """The marketplace with the plugin's entry installing the tag's zip; every other key kept."""
    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list):
        raise ValueError("the marketplace has no list of plugins")
    entries = [entry for entry in plugins if isinstance(entry, dict) and entry.get("name") == PLUGIN_NAME]
    if len(entries) != 1:
        raise ValueError(f"the marketplace has {len(entries)} entries named {PLUGIN_NAME}, not one")
    entries[0]["source"] = {"source": "archive", "url": zip_url(tag), "sha256": sha256}
    entries[0]["version"] = version
    return marketplace


def _parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="pin-release", description=__doc__.split("\n", 1)[0])
    parser.add_argument("tag", help="the release's tag, vX.Y.Z")
    parser.add_argument("--marketplace", type=Path, default=MARKETPLACE, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None, fetch: Fetch = fetch_url) -> int:
    """``fetch`` stands in for the download in a test."""
    arguments = _parse_arguments(sys.argv[1:] if argv is None else argv)
    match = TAG.fullmatch(arguments.tag)
    if match is None:
        print(f"pin-release: {arguments.tag!r} is not a tag of the form vX.Y.Z", file=sys.stderr)
        return EXIT_USAGE
    url = zip_url(arguments.tag)
    try:
        data = fetch(url)
    except OSError as error:
        print(f"pin-release: could not fetch {url}: {error}", file=sys.stderr)
        return EXIT_NOT_FETCHED
    sha256 = hashlib.sha256(data).hexdigest()
    try:
        marketplace = json.loads(arguments.marketplace.read_text(encoding="utf-8"))
        changed = pinned(marketplace, arguments.tag, match.group(1), sha256)
    except (OSError, ValueError) as error:
        print(f"pin-release: {arguments.marketplace}: {error}", file=sys.stderr)
        return EXIT_USAGE
    arguments.marketplace.write_text(json.dumps(changed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"pin-release: {PLUGIN_NAME} installs {arguments.tag} from {url} (sha256 {sha256})")
    return EXIT_PINNED


if __name__ == "__main__":
    sys.exit(main())
