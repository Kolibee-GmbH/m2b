"""The ``folder`` backend: any folder, synced by whatever the user chooses or not at all.

On macOS the guard runs here too, because Dropbox and OneDrive keep files on demand through
the same system mechanism as iCloud Drive. No conflict copies are recognized: the naming of
other sync services is not known.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from m2b.store.base import ConflictCopy, FetchError, Store

MATERIALIZE_SCRIPT = Path(__file__).with_name("materialize.py")


class FolderStore(Store):
    def _start_download(self, relative: str, timeout_seconds: float) -> None:
        command = [sys.executable, str(MATERIALIZE_SCRIPT), str(self.path(relative))]
        try:
            subprocess.run(command, capture_output=True, timeout=timeout_seconds, check=False)
        except subprocess.TimeoutExpired as error:
            raise FetchError(f"{relative} did not download within {timeout_seconds:g} seconds") from error

    def conflict_copies(self, folder: str = "") -> list[ConflictCopy]:
        return []
