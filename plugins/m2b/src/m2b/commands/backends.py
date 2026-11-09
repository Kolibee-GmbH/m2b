"""Opening the store, the tasks and the calendar this machine is configured for."""

from __future__ import annotations

from m2b.calendar.base import Calendar
from m2b.calendar.factory import open_calendar
from m2b.config.machine import MachineConfig
from m2b.config.store_settings import load_store_settings
from m2b.paths import MachinePaths
from m2b.store.base import Store
from m2b.store.factory import open_store
from m2b.tasks.base import Tasks
from m2b.tasks.factory import open_tasks


def configured_store(config: MachineConfig, machine: MachinePaths) -> Store:
    return open_store(config.store, machine.temp_dir)


def configured_tasks(config: MachineConfig, machine: MachinePaths) -> Tasks:
    """The tasks backend and list ``store.json`` names, so every machine uses the same list."""
    store = configured_store(config, machine)
    return open_tasks(load_store_settings(store).tasks, store, config.executables)


def configured_calendar(config: MachineConfig) -> Calendar:
    return open_calendar(config.calendar, config.executables)
