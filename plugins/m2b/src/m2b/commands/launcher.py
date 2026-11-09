"""``launcher install / resolve``."""

from __future__ import annotations

import argparse
import sys

from m2b import launcher
from m2b.commands import Context
from m2b.config.errors import NotSetUpError
from m2b.config.machine import load_machine_config

EXIT_NOT_INSTALLED = 3


def launcher_install(arguments: argparse.Namespace, context: Context) -> int:
    """Writes the launcher with the recorded python3, or the one running now before setup recorded one."""
    try:
        python = load_machine_config(context.machine).executables.get("python3") or sys.executable
    except NotSetUpError:
        python = sys.executable
    print(launcher.install_launcher(context.machine, python))
    return 0


def launcher_resolve(arguments: argparse.Namespace, context: Context) -> int:
    found = launcher.resolve_install_path(arguments.plugin, context.environ)
    if found is None:
        print(
            f"m2b: the plugin {arguments.plugin}@{launcher.MARKETPLACE} is not installed for this user",
            file=sys.stderr,
        )
        return EXIT_NOT_INSTALLED
    print(found)
    return 0
