"""Note file names: ``YYYYMMDDTHHMMSSZ-<source>-<4 hex>.<ext>``, the time in UTC.

UTC names sort in capture order across time zones and daylight saving changes. A name never
changes after capture, because links point to it.
"""

from __future__ import annotations

import datetime
import re
import secrets
from dataclasses import dataclass

SOURCE_PATTERN = r"[a-z][a-z0-9-]*"
_SOURCE = re.compile(rf"{SOURCE_PATTERN}\Z")
_EXTENSION = re.compile(r"[A-Za-z0-9]+\Z")
_SUFFIX = re.compile(r"[0-9a-f]{4}\Z")
_NAME = re.compile(rf"(\d{{8}}T\d{{6}})Z-({SOURCE_PATTERN})-([0-9a-f]{{4}})\.([A-Za-z0-9]+)\Z")
_TIME_FORMAT = "%Y%m%dT%H%M%S"
_SUFFIX_BYTES = 2


@dataclass(frozen=True)
class NoteName:
    time: datetime.datetime
    source: str
    suffix: str
    extension: str = "md"

    def __str__(self) -> str:
        return f"{self.time.strftime(_TIME_FORMAT)}Z-{self.source}-{self.suffix}.{self.extension}"

    @classmethod
    def for_capture(
        cls, created: datetime.datetime, source: str, suffix: str | None = None, extension: str = "md"
    ) -> NoteName:
        """The name of a new capture; ``created`` must carry its offset."""
        if created.utcoffset() is None:
            raise ValueError(f"the capture time {created.isoformat()} has no offset")
        if not _SOURCE.match(source):
            raise ValueError(f"the source {source!r} is not a lowercase token like claude or my-app")
        if not _EXTENSION.match(extension):
            raise ValueError(f"the extension {extension!r} must be letters and digits, like md or heic")
        suffix = suffix if suffix is not None else secrets.token_hex(_SUFFIX_BYTES)
        if not _SUFFIX.match(suffix):
            raise ValueError(f"the suffix {suffix!r} must be four lowercase hex characters")
        utc = created.astimezone(datetime.timezone.utc).replace(microsecond=0)
        return cls(utc, source, suffix, extension)

    @classmethod
    def parse(cls, name: str) -> NoteName | None:
        """The parts of a conforming name, or None for any other name (ingest renames those)."""
        match = _NAME.match(name)
        if match is None:
            return None
        try:
            time = datetime.datetime.strptime(match.group(1), _TIME_FORMAT).replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            return None
        return cls(time, match.group(2), match.group(3), match.group(4))
