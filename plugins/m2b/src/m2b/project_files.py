"""The files a session wrote in a project's repository, as a reading shows them and points to them.

A reading of the sessions gives each session the files Claude wrote (``sessions.Session.written``),
by the path its call named. A pointer can only be kept into a project topic, so the model is shown
the files of a session only where its folder lies in a repository a project topic names, each by
its path in that repository; every other session shows none. A kept pointer then names its file by
that path and goes under that project's topic.

The caller says which folder lies in which project (``Project``): the curation step from the notes
of the session start and the distillate (``curate.glean_step``), the eval of the reading from its
invented day. Both show the model the same thing that way.
"""

from __future__ import annotations

import dataclasses
import datetime
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from m2b import glean
from m2b.repository_places import can_point_to
from m2b.sessions import Session


@dataclass(frozen=True)
class Project:
    """The project topic a folder's repository has: the topic's name, the repository's folder on this
    machine and its addresses."""

    topic: str
    top: str
    addresses: tuple[str, ...]


def shown(read: Sequence[Session], projects: Mapping[str, Project]) -> list[Session]:
    """The sessions, each with only the files it wrote in its project's repository, by their path
    there; ``projects`` maps a session's folder to its project, and a session in no project shows none."""
    return [
        dataclasses.replace(session, written=_in_project(session, projects.get(session.folder))) for session in read
    ]


def pointed(
    placed: Sequence[tuple[glean.Proposal, datetime.datetime]],
    read: Sequence[Session],
    projects: Mapping[str, Project],
) -> list[tuple[glean.Proposal, datetime.datetime]]:
    """The proposals, each pointer under its project's topic, naming its repository, its text the line
    it becomes: the sentence, `` → `` and the file. ``glean.check`` keeps only a pointer whose file its
    session wrote, and only a session in a project shows one, so no pointer is without a project."""
    folders = {session.session_id: session.folder for session in read}
    result: list[tuple[glean.Proposal, datetime.datetime]] = []
    for proposal, typed_at in placed:
        project = projects.get(folders.get(proposal.session, ""))
        if proposal.pointer is None:
            result.append((proposal, typed_at))
        elif project is not None:
            pointer = dataclasses.replace(proposal.pointer, repositories=project.addresses)
            text = f"{proposal.text.rstrip().rstrip('.')} → {pointer.path}"
            result.append((dataclasses.replace(proposal, text=text, topic=project.topic, pointer=pointer), typed_at))
    return result


def in_repository(path: str, top: str) -> str | None:
    """``path`` relative to the repository's folder ``top``, as a pointer can name it; None outside it."""
    if not os.path.isabs(path):
        return None
    relative = os.path.relpath(os.path.normpath(path), os.path.normpath(top))
    if relative.startswith(os.pardir) or relative == os.curdir:
        return None
    posix = relative.replace(os.sep, "/")
    return posix if can_point_to(posix) else None


def _in_project(session: Session, project: Project | None) -> tuple[str, ...]:
    if project is None:
        return ()
    return tuple(path for path in (in_repository(each, project.top) for each in session.written) if path)
