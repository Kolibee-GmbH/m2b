"""The verdict as the model hands it back, checked against the schema and against the facts it judges.

The schema holds the shape; the facts hold what the shape may name: every session judged once and
none invented, only blocks the session has, only a sphere of the profile, and only a customer from
the customer list, which the worklog never extends (B29). At most three candidates, and no line
break in a text the note puts on one line, where it would start a heading of its own. Each problem
names its place, so the model can fix the verdict and hand it in again.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from m2b_worklog import schema

MAX_CANDIDATES = 3
ONE_LINE_FIELDS = ("topic", "state_detail", "note")
BOOKING_LINE_FIELDS = ("project", "activity")


def problems_of(verdict: Any, facts: Mapping[str, Any]) -> list[str]:
    found = schema.check(verdict, schema.load(schema.VERDICT_SCHEMA))
    if found:
        return found
    sessions = {s["key"]: s for s in facts["sessions"]}
    spheres = {s["id"] for s in facts["spheres"]}
    customers = set(facts["customers"])
    judged: set[str] = set()
    for index, session in enumerate(verdict["sessions"]):
        place = f"$.sessions[{index}]"
        key = session["key"]
        if key not in sessions:
            found.append(f"{place}: {key!r} is not a session of the facts")
            continue
        if key in judged:
            found.append(f"{place}: {key!r} is judged twice")
        judged.add(key)
        sphere = session.get("sphere")
        if sphere is not None and sphere not in spheres:
            found.append(f"{place}.sphere: {sphere!r} is not one of the profile's spheres {sorted(spheres)}")
        found += _line_break_problems(place, session)
        found += _block_problems(place, session["blocks"], sessions[key], customers)
    found += [f"$.sessions: {key!r} is not judged" for key in sessions if key not in judged]
    candidates = verdict["candidates"]
    if len(candidates) > MAX_CANDIDATES:
        found.append(f"$.candidates: {len(candidates)} candidates, at most {MAX_CANDIDATES}")
    for index, candidate in enumerate(candidates):
        if _has_line_break(candidate.get("text")):
            found.append(f"$.candidates[{index}].text: holds a line break")
        session_key = candidate.get("session")
        if session_key is not None and session_key not in sessions:
            found.append(f"$.candidates[{index}].session: {session_key!r} is not a session of the facts")
    return found


def _line_break_problems(place: str, session: Mapping[str, Any]) -> list[str]:
    return [f"{place}.{name}: holds a line break" for name in ONE_LINE_FIELDS if _has_line_break(session.get(name))]


def _has_line_break(text: Any) -> bool:
    return isinstance(text, str) and len(text.splitlines()) > 1


def _block_problems(
    place: str, blocks: Mapping[str, Any], session: Mapping[str, Any], customers: set[str]
) -> list[str]:
    found = []
    known = {block["id"] for block in session["blocks"]}
    for block_id, booking in blocks.items():
        if block_id not in known:
            found.append(f"{place}.blocks: {block_id!r} is not a block of this session {sorted(known)}")
        elif booking is not None and booking["customer"] not in customers:
            found.append(
                f"{place}.blocks.{block_id}.customer: {booking['customer']!r} is not in the customer list "
                f"{sorted(customers)}; use one of them or null"
            )
        if booking is not None:
            found += [
                f"{place}.blocks.{block_id}.{name}: holds a line break"
                for name in BOOKING_LINE_FIELDS
                if _has_line_break(booking.get(name))
            ]
    return found
