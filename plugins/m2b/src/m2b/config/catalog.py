"""The catalog of the settings: every key of the three files once, with what it does and how it changes.

``m2b settings`` prints it, so a list of the settings, the command that changes a switch and
whatever draws them read one source. A setting is one of three kinds. A ``switch`` is on or off,
or one of a few named values, and is the only kind ``m2b settings set`` changes. A ``shown``
setting comes with its value. A ``named`` one holds a list, paths or an add-on's own settings and
comes as a count, never with what it holds: that can be a customer's name or a folder of a
customer's work. Each is changed by a command, by a setup skill, by hand in its file where no
command writes it, or never by hand.

The store's files can be written from other devices, so a text from them is given with each
character that draws nothing or steers a terminal written out, as a value and in words.

The catalog is held to the keys the three parsers take (``setting_keys`` of each file's module),
and each default here to what a file without the key reads as.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from m2b import addons, locale
from m2b.config import machine, store_settings
from m2b.config.machine import CONFIG_FILE_NAME, MachineConfig
from m2b.config.profile import PROFILE_FILE_NAME, Profile
from m2b.config.store_settings import STORE_SETTINGS_FILE_NAME, StoreSettings
from m2b.notes.characters import with_unseen_written_out

MACHINE, STORE, OWNER = "machine", "store", "owner"
FILES = {MACHINE: CONFIG_FILE_NAME, STORE: STORE_SETTINGS_FILE_NAME, OWNER: PROFILE_FILE_NAME}
SWITCH, SHOWN, NAMED = "switch", "shown", "named"
COMMAND, SETUP, HAND, NEVER = "command", "setup", "by hand", "never by hand"

ON_OFF = (True, False)
SETUP_SKILL = "/m2b:setup"
CURATION_SECTION = "curation."


@dataclass(frozen=True)
class Setting:
    key: str
    scope: str
    kind: str
    title: str
    # One or two sentences for the person deciding about it.
    does: str
    how: str
    # The command or the skill that changes it, or where to edit it by hand; None for one never
    # changed by hand.
    change: str | None = None
    # What a file without the key reads as; None where the key is required or unset means "none".
    default: Any = None
    # A switch's values, the ones ``m2b settings set`` takes.
    choices: tuple[Any, ...] = ()

    @property
    def file(self) -> str:
        return FILES[self.scope]

    @property
    def of_curation(self) -> bool:
        """Whether it steers the curation run, which only the curating machine starts."""
        return self.scope == MACHINE and self.key.startswith(CURATION_SECTION)


@dataclass(frozen=True)
class Shown:
    # The value as JSON data, a text as ``shows`` has it; None for a named setting, whose content
    # stays in its file.
    value: Any
    # The value in words: ``on``, ``not set``, ``2 customers``.
    shows: str


def _switch(scope: str, key: str, title: str, does: str, default: Any, choices: tuple[Any, ...] = ON_OFF) -> Setting:
    change = f"m2b settings set {key} {'|'.join(as_argument(choice) for choice in choices)}"
    return Setting(key, scope, SWITCH, title, does, COMMAND, change, default, tuple(choices))


def _by_command(scope: str, key: str, title: str, does: str, change: str, default: Any = None) -> Setting:
    return Setting(key, scope, SHOWN, title, does, COMMAND, change, default)


def _by_setup(scope: str, key: str, title: str, does: str, default: Any = None, skill: str = SETUP_SKILL) -> Setting:
    return Setting(key, scope, SHOWN, title, does, SETUP, skill, default)


def _kept_by_m2b(scope: str, key: str, title: str, does: str, default: Any = None) -> Setting:
    return Setting(key, scope, SHOWN, title, does, NEVER, None, default)


def as_argument(value: object) -> str:
    """A switch's value as it is typed after ``m2b settings set <key>``."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _of_this_machine() -> tuple[Setting, ...]:
    return (
        _kept_by_m2b(MACHINE, "version", "Version of the config", "The version of this file's layout."),
        _kept_by_m2b(
            MACHINE,
            "machine_id",
            "This machine's name",
            "The name this machine has in the store's settings. Setup made it up from the host name and a random part.",
        ),
        _by_setup(
            MACHINE,
            "store.backend",
            "Kind of store",
            "Where the store lives: icloud is a folder in iCloud Drive on macOS, folder is any folder.",
        ),
        _by_command(
            MACHINE,
            "store.path",
            "Store folder",
            "The folder your notes live in. After moving the store, name its new folder here.",
            "m2b config set store.path <folder>",
        ),
        _by_setup(
            MACHINE,
            "calendar.backend",
            "Calendar",
            "Whether m2b reads your calendar and adds events to it: none, or apple-calendar on macOS. "
            "Setup turns it on, because it also needs the path of a program and your yes to the access; "
            "m2b config set calendar.backend none turns it off.",
            machine.CalendarSettings().backend,
        ),
        _by_command(
            MACHINE,
            "calendar.timeout_seconds",
            "Time limit of a calendar call",
            "How many seconds a call to the calendar may take.",
            "m2b config set calendar.timeout_seconds <seconds>",
            machine.DEFAULT_BACKEND_TIMEOUT_SECONDS,
        ),
        Setting(
            "executables",
            MACHINE,
            NAMED,
            "Programs m2b starts",
            f"The absolute paths of {', '.join(machine.EXECUTABLES)}, as setup found them, for runs outside a "
            "terminal, whose PATH is short.",
            COMMAND,
            "m2b config set executables.<program> <path>",
        ),
        _by_command(
            MACHINE,
            "curation.model_timeout_minutes",
            "Time limit of a model step",
            "How many minutes one model step of a curation run may take before it is stopped.",
            "m2b config set curation.model_timeout_minutes <minutes>",
            machine.DEFAULT_MODEL_TIMEOUT_MINUTES,
        ),
        _switch(
            MACHINE,
            "curation.model",
            "Model of curation",
            f"The model of each model step of a curation run: {machine.DEFAULT_CURATION_MODEL} keeps a daily run "
            "cheap, a larger one files better at a higher cost. m2b config set curation.model takes any name "
            "claude --model takes.",
            machine.DEFAULT_CURATION_MODEL,
            machine.CURATION_MODELS,
        ),
        _by_command(
            MACHINE,
            "curation.max_turns",
            "Turns of a model step",
            "How many turns one model step may take before it stops and is reported.",
            "m2b config set curation.max_turns <turns>",
            machine.DEFAULT_MAX_TURNS,
        ),
        _by_command(
            MACHINE,
            "curation.max_budget_usd",
            "Spending cap of a model step",
            "A cap per model step in US dollars, from Claude Code's own estimate of API cost, which says little "
            "on a subscription. Not set, there is no cap.",
            "m2b config set curation.max_budget_usd <dollars>",
        ),
        _switch(
            MACHINE,
            "curation.read_sessions",
            "Curation reads your sessions",
            "A curation run on this machine reads what you typed and pasted in Claude Code since the last "
            "reading, never Claude's answers, and a model proposes facts from it for your memory. Pasted text can "
            "be someone else's. Nothing is filed before you keep it.",
            False,
        ),
        _switch(
            MACHINE,
            "curation.git_commit",
            "A git commit per run",
            "A curation run on this machine ends with a git commit of what it changed. It does nothing where the "
            "store folder is not the top of a git repository.",
            True,
        ),
        _by_command(
            MACHINE,
            "curation.git_directory",
            "Git directory of the store",
            "The git directory a run commits into when the store folder's .git is a file that points at one kept "
            "outside the folder. Not set, a run commits only into a .git folder of the store itself.",
            "m2b config set curation.git_directory <path>",
        ),
        _switch(
            MACHINE,
            "curation.paused",
            "Curation paused",
            "This machine starts no curation run by itself, none at a session start and none from a schedule. "
            "m2b curate --force still runs one, and captures keep reaching the inbox.",
            False,
        ),
        Setting(
            "distillate.skip_under",
            MACHINE,
            NAMED,
            "Folders m2b is left out of",
            "The folders in and below which a session gets no distillate and no facts of a topic.",
            COMMAND,
            "m2b distillate off|on [<folder>]",
        ),
        _switch(
            MACHINE,
            "band.due_tasks",
            "Due tasks in the band",
            "The band shows your tasks due today or overdue below the candidates.",
            True,
        ),
        _switch(
            MACHINE,
            "sessions.propose",
            "Sessions hand in proposals",
            "An agent of a session may propose a fact for your memory by itself, with words from what it read "
            "for you: a mail, a document, a tool's result. Nothing is filed before you keep it. A session's shell "
            "does not turn this on: there the command refuses.",
            False,
        ),
        *(
            Setting(
                f"{machine.ADDONS_KEY}.{addon.name}",
                MACHINE,
                NAMED,
                f"Add-on {addon.name}",
                f"Whether the add-on runs on this machine: {addon.summary}. m2b addons off {addon.name} turns it "
                "off and keeps its settings.",
                SETUP,
                f"/m2b:{addon.name}-setup",
            )
            for addon in addons.ADDONS
        ),
    )


def _of_the_store() -> tuple[Setting, ...]:
    return (
        _kept_by_m2b(
            STORE,
            "format",
            "Store format",
            "Counts the rules for curated content. A curation run of a newer m2b raises it; a machine with an "
            "older m2b still captures into the store.",
        ),
        _by_setup(
            STORE,
            "tasks.backend",
            "Task list",
            "Where your tasks live: apple-reminders on macOS, or markdown, one file per task in the store.",
        ),
        _by_setup(STORE, "tasks.list", "Reminders list", "The list in Reminders that holds your tasks."),
        Setting(
            "tasks.timeout_seconds",
            STORE,
            SHOWN,
            "Time limit of a tasks call",
            "How many seconds a call to the task list may take. No command writes it.",
            HAND,
            f"edit tasks.timeout_seconds in {STORE_SETTINGS_FILE_NAME}, in the store folder",
            store_settings.DEFAULT_TASKS_TIMEOUT_SECONDS,
        ),
        _by_command(
            STORE,
            "curating_machine",
            "Curating machine",
            "The one machine that runs curation for this store.",
            "m2b curate take-over",
        ),
        _kept_by_m2b(
            STORE,
            "journal_since",
            "Journal since",
            "The first day the journal of completed tasks covers, the day setup made the store.",
        ),
    )


def _of_the_owner() -> tuple[Setting, ...]:
    worklog_setup = "/m2b:worklog-setup"
    return (
        _kept_by_m2b(OWNER, "version", "Version of the profile", "The version of this file's layout."),
        _by_command(
            OWNER,
            "owner",
            "Your name",
            "Your name, as the curator writes about you.",
            "m2b profile set owner <name>",
        ),
        _switch(
            OWNER,
            "language",
            "Language",
            "The language task titles, notes and the worklog are written in.",
            locale.DEFAULT_LANGUAGE,
            locale.available_languages(),
        ),
        Setting(
            "spheres",
            OWNER,
            NAMED,
            "Spheres of work",
            "For the worklog: your areas of work, how each is recognized and which are billable.",
            SETUP,
            worklog_setup,
        ),
        Setting(
            "customers",
            OWNER,
            NAMED,
            "Customers",
            "For the worklog: the only names its booking proposals may use.",
            SETUP,
            worklog_setup,
        ),
        Setting(
            "worklog_leave_out",
            OWNER,
            NAMED,
            "Work m2b leaves out",
            "Work that reaches no worklog and no reading of your sessions, named by folders under your home "
            "folder and by parts of the URLs of git remotes. A change replaces the whole list: "
            "m2b profile get worklog_leave_out shows what it holds.",
            COMMAND,
            "m2b profile set worklog_leave_out.path_under|git_remote_contains '<the whole list as JSON>'",
        ),
    )


def settings() -> tuple[Setting, ...]:
    """Every setting, in the order a list shows them: this machine, the store, the owner."""
    return (*_of_this_machine(), *_of_the_store(), *_of_the_owner())


def named(key: str) -> tuple[Setting, ...]:
    """The settings with this key: one, none, or one per file for a key two files have (``version``)."""
    return tuple(setting for setting in settings() if setting.key == key)


def values(config: MachineConfig, store: StoreSettings | None, profile: Profile | None) -> dict[tuple[str, str], Shown]:
    """Each setting's value by scope and key; a file that was not read (None) has none."""
    read = {(MACHINE, key): shown for key, shown in _machine_values(config).items()}
    if store is not None:
        read.update({(STORE, key): shown for key, shown in _store_values(store).items()})
    if profile is not None:
        read.update({(OWNER, key): shown for key, shown in _owner_values(profile).items()})
    return read


def _machine_values(config: MachineConfig) -> dict[str, Shown]:
    curation = config.curation
    return {
        "version": _plain(config.version),
        "machine_id": _plain(config.machine_id),
        "store.backend": _plain(config.store.backend),
        "store.path": _plain(str(config.store.path)),
        "calendar.backend": _plain(config.calendar.backend),
        "calendar.timeout_seconds": _plain(config.calendar.timeout_seconds),
        "executables": _counted(len(config.executables), "none named", "{} named", "{} named"),
        "curation.model_timeout_minutes": _plain(curation.model_timeout_minutes),
        "curation.model": _plain(curation.model),
        "curation.max_turns": _plain(curation.max_turns),
        "curation.max_budget_usd": _plain(curation.max_budget_usd),
        "curation.read_sessions": _plain(curation.read_sessions),
        "curation.git_commit": _plain(curation.git_commit),
        "curation.git_directory": _plain(None if curation.git_directory is None else str(curation.git_directory)),
        "curation.paused": _plain(curation.paused),
        "distillate.skip_under": _counted(len(config.distillate.skip_under), "no folders", "{} folder", "{} folders"),
        "band.due_tasks": _plain(config.band.due_tasks),
        "sessions.propose": _plain(config.sessions.propose),
        **{
            f"{machine.ADDONS_KEY}.{name}": Shown(None, "on" if addons.is_on(config.addons, name) else "off")
            for name in addons.addon_names()
        },
    }


def _store_values(store: StoreSettings) -> dict[str, Shown]:
    return {
        "format": _plain(store.format),
        "tasks.backend": _plain(store.tasks.backend),
        "tasks.list": _plain(store.tasks.list_name),
        "tasks.timeout_seconds": _plain(store.tasks.timeout_seconds),
        "curating_machine": _plain(store.curating_machine),
        "journal_since": _plain(store.journal_since.isoformat()),
    }


def _owner_values(profile: Profile) -> dict[str, Shown]:
    left_out = profile.worklog_leave_out
    folders = _number(len(left_out.path_under), "{} folder", "{} folders")
    remotes = _number(len(left_out.git_remote_contains), "{} remote", "{} remotes")
    return {
        "version": _plain(profile.version),
        "owner": _plain(profile.owner),
        "language": _plain(profile.language),
        "spheres": _counted(len(profile.spheres), "no spheres", "{} sphere", "{} spheres"),
        "customers": _counted(len(profile.customers), "no customers", "{} customer", "{} customers"),
        "worklog_leave_out": Shown(None, ", ".join(part for part in (folders, remotes) if part) or "nothing"),
    }


def _plain(value: object) -> Shown:
    words = in_words(value)
    return Shown(words if isinstance(value, str) else value, words)


def in_words(value: object) -> str:
    """A value as a list shows it, on one line: a character that draws nothing is written out, because
    a name without it reads as another one, and so is one that steers a terminal or breaks the line."""
    if isinstance(value, bool):
        return "on" if value else "off"
    if value is None:
        return "not set"
    return with_unseen_written_out(str(value))


def _counted(count: int, none: str, one: str, several: str) -> Shown:
    return Shown(None, _number(count, one, several) or none)


def _number(count: int, one: str, several: str) -> str:
    """``1 folder``, ``2 folders``, and nothing for none."""
    if count == 0:
        return ""
    return (one if count == 1 else several).format(count)


def entry(setting: Setting, shown: Shown | None) -> dict[str, Any]:
    """One setting as ``m2b settings --json`` answers it; ``shown`` None: its file was not read."""
    return {
        "key": setting.key,
        "file": setting.file,
        "scope": setting.scope,
        "kind": setting.kind,
        "title": setting.title,
        "does": setting.does,
        "read": shown is not None,
        "value": None if shown is None else shown.value,
        "shows": None if shown is None else shown.shows,
        "default": setting.default,
        "choices": list(setting.choices),
        "changed_by": setting.how,
        "change": setting.change,
        "curation": setting.of_curation,
    }


def entries(read: Mapping[tuple[str, str], Shown]) -> list[dict[str, Any]]:
    return [entry(setting, read.get((setting.scope, setting.key))) for setting in settings()]
