"""The worklog's sources. Each says whether it could be read, so a failure never looks like "nothing"."""

from __future__ import annotations

from dataclasses import dataclass

READ = "read"
COULD_NOT_READ = "could not read"


@dataclass(frozen=True)
class SourceState:
    state: str
    detail: str = ""

    @classmethod
    def read(cls) -> SourceState:
        return cls(READ)

    @classmethod
    def failed(cls, detail: str) -> SourceState:
        return cls(COULD_NOT_READ, detail)

    @property
    def is_read(self) -> bool:
        return self.state == READ
