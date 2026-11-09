"""Opening the store a machine config names."""

from __future__ import annotations

import sys
from pathlib import Path

from m2b.config.errors import StoreUnreachableError
from m2b.config.machine import StoreLocation
from m2b.store.base import Store, UnsupportedStoreError
from m2b.store.folder import FolderStore
from m2b.store.guard import DatalessGuard, guard_for_platform
from m2b.store.icloud import ICloudStore


def open_store(location: StoreLocation, temp_dir: Path, platform: str = sys.platform) -> Store:
    """The store backend for ``location``; on macOS the guard is on for this whole process."""
    if not location.path.is_dir():
        raise StoreUnreachableError(location.path)
    if location.backend == "icloud" and platform != "darwin":
        raise UnsupportedStoreError("the icloud backend runs on macOS only; use the folder backend here")
    guard: DatalessGuard = guard_for_platform(platform)
    if location.backend == "icloud":
        return ICloudStore(location.path, temp_dir, guard)
    return FolderStore(location.path, temp_dir, guard)
