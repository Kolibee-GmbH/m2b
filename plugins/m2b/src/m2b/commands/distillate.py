"""``distillate off / on``: projects whose sessions get no distillate, for work the owner keeps apart."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from m2b.commands import Context
from m2b.config.machine import DistillateSettings, load_machine_config, set_machine_config_value
from m2b.paths import expand

KEY = "distillate.skip_under"


def distillate_off(arguments: argparse.Namespace, context: Context) -> int:
    folder = _folder(arguments, context)
    config = load_machine_config(context.machine)
    if config.distillate.covering(folder) is not None:
        print(f"sessions in {folder} get no distillate already")
        return 0
    written = [str(path) for path in config.distillate.skip_under]
    set_machine_config_value(context.machine, KEY, [*written, str(folder)])
    print(f"sessions in {folder} and below get no distillate from now on")
    return 0


def distillate_on(arguments: argparse.Namespace, context: Context) -> int:
    folder = _folder(arguments, context)
    config = load_machine_config(context.machine)
    kept = tuple(path for path in config.distillate.skip_under if path.resolve() != folder)
    if len(kept) != len(config.distillate.skip_under):
        set_machine_config_value(context.machine, KEY, [str(path) for path in kept])
    covering = DistillateSettings(kept).covering(folder)
    if covering is not None:
        print(f"sessions in {folder} still get no distillate: {covering} is turned off; m2b distillate on {covering}")
        return 0
    print(f"sessions in {folder} get the distillate")
    return 0


def _folder(arguments: argparse.Namespace, context: Context) -> Path:
    written = arguments.folder or context.environ.get("PWD") or os.getcwd()
    return expand(written, context.machine.home).resolve()
