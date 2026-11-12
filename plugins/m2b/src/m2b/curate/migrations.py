"""Migrations: what brings a store's content up to the rules of this m2b, one format at a time.

``format`` in ``store.json`` counts the rules for curated content (``memory/``) and the keys of
``store.json`` (``config.store_settings.KEYS_BY_FORMAT``). When a rule change needs content already
in a store to change, or an older m2b must not curate content written under the new rule, or
``store.json`` gets a new key, the change raises ``KNOWN_STORE_FORMAT`` by one and adds a migration
here whose ``target`` is the new number; for a new key it changes nothing in ``memory/``. The
curating machine runs the due ones at the start of a curation run, before any other step, each as
a step of its own (``migrate-<target>``):

- ``apply`` changes ``memory/`` and nothing else. It is code; a change that needs judgment would run
  as a fenced model step with exact rules, like the other model steps.
- ``problem`` compares ``memory/`` before and after in code and names anything the migration may
  not change. A migration that raises, or whose ``problem`` names something, puts ``memory/`` back
  and leaves ``format`` as it was, and the run stops there: the other steps follow rules the store
  does not hold yet.
- ``apply`` finds nothing to do in content that already follows its rule, so a run that dies after
  the content changed and before ``format`` was written repeats it without harm.

The inbox is not part of ``format``: its file names and frontmatter (``created``, ``source``) stay
the same across formats, so a machine with an older m2b still captures into a newer store.

Format 2 adds ``## Earlier`` to fact files: ingest keeps a changed fact's old value there with the
last day it held. Content of format 1 needs no change for it; the migration only raises the format,
so an m2b that knows format 1, whose ingest and refresh do not know the section, stops curating.

Format 3 lets current items stand under topics in ``## Current``, so they reach only the sessions
that name the topic. Content of format 2 needs no change for it either; the migration only raises
the format, so an m2b that knows format 2, whose lint reports such a heading as an error and whose
sessions get every current item, stops curating.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from m2b.curate.memory_guard import Snapshot
from m2b.store.base import Store

__all__ = ["MIGRATIONS", "Migration", "Snapshot", "due", "step_name"]


@dataclass(frozen=True)
class Migration:
    target: int
    summary: str
    apply: Callable[[Store], None]
    problem: Callable[[Snapshot, Snapshot], str | None]


def _unchanged(before: Snapshot, after: Snapshot) -> str | None:
    return None if before.files == after.files else "memory/ changed, and this migration changes nothing"


MIGRATIONS: tuple[Migration, ...] = (
    Migration(2, "fact files may keep earlier values under ## Earlier", lambda store: None, _unchanged),
    Migration(3, "current items may stand under topics in ## Current", lambda store: None, _unchanged),
)


def due(store_format: int, migrations: Sequence[Migration] | None = None) -> list[Migration]:
    """The migrations a store of ``store_format`` still needs, in the order they run."""
    known = MIGRATIONS if migrations is None else migrations
    return sorted((migration for migration in known if migration.target > store_format), key=lambda m: m.target)


def step_name(migration: Migration) -> str:
    return f"migrate-{migration.target}"
