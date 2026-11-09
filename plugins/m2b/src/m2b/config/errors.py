"""Errors of the config files; each message is one line a user can act on."""

from __future__ import annotations

SETUP_COMMAND = "/m2b:m2b setup"


class ConfigError(Exception):
    """A config file is missing, invalid or newer than this version understands."""


class NotSetUpError(ConfigError):
    """Something setup writes does not exist yet."""

    def __init__(self, what: str) -> None:
        super().__init__(f"not set up: {what}. Run {SETUP_COMMAND} in Claude Code.")


class InvalidConfigError(ConfigError):
    """A config file exists but does not follow its format."""


class FormatTooNewError(ConfigError):
    """A file was written by a newer version of m2b."""

    def __init__(self, what: str, found: int, known: int) -> None:
        super().__init__(
            f"{what} has format {found}, newer than this version of m2b knows ({known}); "
            "update the plugin before changing it."
        )


class StoreUnreachableError(Exception):
    """The configured store cannot be reached, which is not the same as not set up."""

    def __init__(self, store_root: object) -> None:
        super().__init__(f"the store {store_root} cannot be reached: the folder does not exist or is not mounted")
