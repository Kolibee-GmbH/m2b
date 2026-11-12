"""The ``folder`` backend: any folder, synced by whatever the user chooses or not at all.

On macOS the guard runs here too, because Dropbox and OneDrive keep files on demand through
the same system mechanism as iCloud Drive.

Which service syncs the folder is not known here, and a setting for it could be wrong or missing
and would then recognize nothing without a word. So the conflict copies of two services are
always recognized, by name. Dropbox puts a label in brackets before the extension,
``plan (Dana's conflicted copy 2026-11-05).md``; clients and languages differ in what stands
around the phrase (a name or none, a day, a number), so the phrase in the label is what counts.
Syncthing writes ``plan.sync-conflict-20261105-081500-ABCDEFG.md``: day, time, and the first
seven characters of the device's ID, which older versions left out. A person could give a file
either name, as with iCloud's, so the name is only a candidate: what makes it a copy, and what
allows removing it, is decided for every backend in ``Store.conflict_copies``. The names of
other services are not recognized.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from m2b.store.base import DownloadTimeoutError, Store

MATERIALIZE_SCRIPT = Path(__file__).with_name("materialize.py")

# What Dropbox calls the copy in the file name, by the language of the account.
DROPBOX_PHRASES = ("conflicted copy", "in Konflikt stehende Kopie")
_DROPBOX_COPY_NAME = re.compile(
    r"(?P<stem>.+) \([^()]*(?i:"
    + "|".join(re.escape(phrase) for phrase in DROPBOX_PHRASES)
    + r")[^()]*\)(?P<extension>\.[^.]+)?\Z"
)
_SYNCTHING_COPY_NAME = re.compile(
    r"(?P<stem>.+)\.sync-conflict-[0-9]{8}-[0-9]{6}(?:-[A-Z2-7]{0,7})?(?P<extension>\.[^.]+)?\Z"
)


class FolderStore(Store):
    def _start_download(self, relative: str, timeout_seconds: float) -> None:
        command = [sys.executable, str(MATERIALIZE_SCRIPT), str(self.path(relative))]
        try:
            subprocess.run(command, capture_output=True, timeout=timeout_seconds, check=False)
        except subprocess.TimeoutExpired as error:
            raise DownloadTimeoutError(f"{relative} did not download within {timeout_seconds:g} seconds") from error

    def _original_name(self, name: str) -> str | None:
        match = _SYNCTHING_COPY_NAME.match(name) or _DROPBOX_COPY_NAME.match(name)
        if match is None:
            return None
        return match.group("stem") + (match.group("extension") or "")
