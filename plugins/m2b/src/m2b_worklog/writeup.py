"""What one worklog writes, decided before anything is written: the note, the ledger spans, the candidates.

The plan is pure: facts and a checked verdict in, a ``Plan`` out. The writer (``daily``) records it
as its intent first and then carries it out piece by piece, so a rerun after a crash carries out
the same plan and never a second one.

The note's name is the period's end in UTC with a suffix from a hash of the period, so a rerun
finds the note it wrote, in the inbox or already filed into the corpus. A booking proposal comes
only from a block of a billable sphere with a customer from the list; the owner books,
because a wrong booking ends up on an invoice (B29).
"""

from __future__ import annotations

import datetime
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

SOURCE = "worklog"
KIND = "worklog"
ID_CHARACTERS = 12

HEADINGS = {
    "en": {
        "title": "Worklog {start} to {end}",
        "sessions": "Sessions",
        "no_sessions": "No sessions in this period.",
        "commits": "Commits",
        "bookings": "Booking proposals",
        "no_bookings": "None.",
        "candidates": "Proposed for memory",
        "unread": "Could not read",
        "not_recorded": "Not recorded",
        "not_recorded_why": "herdr was not running, the machine was asleep, recording was off or the recorder's "
        "timer did not run:",
        "span": "{start} to {end}",
        "minutes": "{minutes} min",
        "hours": "{hours} h {minutes} min",
        "state": {"done": "done", "open": "open", "waiting": "waiting for the owner"},
    },
    "de": {
        "title": "Worklog {start} bis {end}",
        "sessions": "Sessions",
        "no_sessions": "Keine Sessions in diesem Zeitraum.",
        "commits": "Commits",
        "bookings": "Buchungsvorschläge",
        "no_bookings": "Keine.",
        "candidates": "Zum Merken vorgeschlagen",
        "unread": "Nicht lesbar",
        "not_recorded": "Nicht aufgezeichnet",
        "not_recorded_why": "herdr lief nicht, der Rechner schlief, die Aufzeichnung war aus oder der Zeitgeber "
        "des Recorders lief nicht:",
        "span": "{start} bis {end}",
        "minutes": "{minutes} Min.",
        "hours": "{hours} Std. {minutes} Min.",
        "state": {"done": "erledigt", "open": "offen", "waiting": "wartet auf den Besitzer"},
    },
}


@dataclass(frozen=True)
class Plan:
    period_id: str
    start: str
    end: str
    note_name: str
    note_text: str
    spans: list[dict[str, Any]]
    candidates: list[str]

    def as_json(self) -> dict[str, Any]:
        return {
            "period": {"id": self.period_id, "start": self.start, "end": self.end},
            "note": {"name": self.note_name, "text": self.note_text},
            "spans": self.spans,
            "candidates": self.candidates,
        }

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> Plan:
        period, note = raw["period"], raw["note"]
        return cls(
            str(period["id"]),
            str(period["start"]),
            str(period["end"]),
            str(note["name"]),
            str(note["text"]),
            [dict(span) for span in raw["spans"]],
            [str(text) for text in raw["candidates"]],
        )


def period_id(start: str, end: str) -> str:
    return hashlib.sha256(f"{start}/{end}".encode()).hexdigest()[:ID_CHARACTERS]


def note_name(end: datetime.datetime, identifier: str) -> str:
    utc = end.astimezone(datetime.timezone.utc)
    return f"{utc:%Y%m%dT%H%M%S}Z-{SOURCE}-{identifier[:4]}.md"


def build(facts: Mapping[str, Any], verdict: Mapping[str, Any], language: str) -> Plan:
    words = HEADINGS.get(language, HEADINGS["en"])
    start, end = facts["period"]["start"], facts["period"]["end"]
    identifier = period_id(start, end)
    spheres = {s["id"]: s for s in facts["spheres"]}
    default = next((s["id"] for s in facts["spheres"] if s["default"]), None)
    judged = {s["key"]: s for s in verdict["sessions"]}
    sessions = [
        _Session(session, judged[session["key"]], _sphere(session, judged[session["key"]], spheres, default))
        for session in facts["sessions"]
        if session["key"] in judged
    ]
    spans = [span for session in sessions for span in session.spans(identifier, spheres)]
    candidates = _unique([c["text"].strip() for c in verdict["candidates"]])
    text = _note(facts, sessions, spans, candidates, spheres, words)
    return Plan(identifier, start, end, note_name(_time(end), identifier), text, spans, candidates)


@dataclass(frozen=True)
class _Session:
    facts: Mapping[str, Any]
    verdict: Mapping[str, Any]
    sphere: str | None

    def spans(self, identifier: str, spheres: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
        billable = self.sphere is not None and spheres[self.sphere]["billable"] is True
        found = []
        for block in self.facts["blocks"]:
            booking = self.verdict["blocks"].get(block["id"]) if billable else None
            found.append(
                {
                    "period": identifier,
                    "session": self.facts["key"],
                    "block": block["id"],
                    "start": block["start"],
                    "end": block["end"],
                    "minutes": block["minutes"],
                    "minutes_present": block["minutes_present"],
                    "sphere": self.sphere,
                    "billable": billable,
                    "topic": self.verdict["topic"],
                    "customer": booking["customer"] if booking else None,
                    "project": booking.get("project") if booking else None,
                    "activity": booking["activity"] if booking else None,
                }
            )
        return found


def is_booking(span: Mapping[str, Any]) -> bool:
    return span["billable"] is True and span["customer"] is not None


def _sphere(
    session: Mapping[str, Any], judged: Mapping[str, Any], spheres: Mapping[str, Any], default: str | None
) -> str | None:
    """The profile's rule first; the verdict only where the rules left it open; then the default."""
    if session["sphere"] is not None:
        return str(session["sphere"])
    if judged.get("sphere") in spheres:
        return str(judged["sphere"])
    return default


def _note(
    facts: Mapping[str, Any],
    sessions: Sequence[_Session],
    spans: Sequence[Mapping[str, Any]],
    candidates: Sequence[str],
    spheres: Mapping[str, Mapping[str, Any]],
    words: Mapping[str, Any],
) -> str:
    start, end = _time(facts["period"]["start"]), _time(facts["period"]["end"])
    lines = [
        "---",
        f"created: {facts['period']['end']}",
        f"source: {SOURCE}",
        f"kind: {KIND}",
        "---",
        "",
        "# " + words["title"].format(start=f"{start:%Y-%m-%d %H:%M}", end=f"{end:%Y-%m-%d %H:%M}"),
        "",
        f"## {words['sessions']}",
        "",
    ]
    if not sessions:
        lines += [words["no_sessions"], ""]
    is_dated = _spans_more_than_one_day(sessions)
    for session in sessions:
        lines += _session_lines(session, spheres, words, is_dated)
    bookings = [span for span in spans if is_booking(span)]
    lines += [f"## {words['bookings']}", ""]
    lines += [_booking_line(span, words) for span in bookings] or [words["no_bookings"]]
    lines.append("")
    if candidates:
        lines += [f"## {words['candidates']}", "", *[f"- {text}" for text in candidates], ""]
    unread = _unread(facts)
    if unread:
        lines += [f"## {words['unread']}", "", *[f"- {line}" for line in unread], ""]
    if facts["not_recorded"]:
        stretches = [f"- {_stretch(stretch, words)}" for stretch in facts["not_recorded"]]
        lines += [f"## {words['not_recorded']}", "", words["not_recorded_why"], "", *stretches, ""]
    return "\n".join(lines)


def _spans_more_than_one_day(sessions: Sequence[_Session]) -> bool:
    """Whether the blocks of the note start or end on more than one date, so their times need it."""
    days = set()
    for session in sessions:
        for block in session.facts["blocks"]:
            days.add(_time(block["start"]).date())
            # A block ending at midnight ends on its own day.
            days.add((_time(block["end"]) - datetime.timedelta(microseconds=1)).date())
    return len(days) > 1


def _block_time(start: datetime.datetime, end: datetime.datetime, is_dated: bool) -> str:
    """``10:00-10:40``, with the date in front when the note covers more than one day, and at the end
    again when the block crosses midnight, so its end never reads as earlier than its start."""
    if not is_dated:
        return f"{start:%H:%M}-{end:%H:%M}"
    shown_end = f"{end:%H:%M}" if end.date() == start.date() else f"{end:%Y-%m-%d %H:%M}"
    return f"{start:%Y-%m-%d %H:%M}-{shown_end}"


def _session_lines(
    session: _Session, spheres: Mapping[str, Mapping[str, Any]], words: Mapping[str, Any], is_dated: bool
) -> list[str]:
    facts, verdict = session.facts, session.verdict
    place = facts["repo"] or facts["label"] or facts["folder"] or facts["key"]
    sphere = spheres[session.sphere]["label"] or session.sphere if session.sphere is not None else None
    minutes = sum(block["minutes"] for block in facts["blocks"])
    state = words["state"][verdict["state"]]
    detail = f": {verdict['state_detail']}" if verdict.get("state_detail") else ""
    lines = [f"### {verdict['topic']}", ""]
    lines.append(f"- {place}" + (f" ({sphere})" if sphere else "") + f", {_duration(minutes, words)}, {state}{detail}")
    times = ", ".join(_block_time(_time(b["start"]), _time(b["end"]), is_dated) for b in facts["blocks"])
    if times:
        lines.append(f"- {times}")
    if facts["commits"]:
        lines.append(f"- {words['commits']}: " + "; ".join(commit["subject"] for commit in facts["commits"]))
    if verdict.get("note"):
        lines.append(f"- {verdict['note']}")
    return [*lines, ""]


def _booking_line(span: Mapping[str, Any], words: Mapping[str, Any]) -> str:
    start, end = _time(span["start"]), _time(span["end"])
    what = ", ".join(part for part in (span["customer"], span["project"], span["activity"]) if part)
    return f"- {_block_time(start, end, is_dated=True)} ({_duration(span['minutes'], words)}): {what}"


def _unread(facts: Mapping[str, Any]) -> list[str]:
    """Every source that could not be read, so a missing herdr never reads as a day without work (X20)."""
    lines = [f"{name}: {state['detail']}" for name, state in facts["sources"].items() if state["state"] != "read"]
    for session in facts["sessions"]:
        if session["git"]["state"] != "read":
            lines.append(f"git in {session['folder'] or session['key']}: {session['git']['detail']}")
    return lines


def _stretch(stretch: Mapping[str, Any], words: Mapping[str, Any]) -> str:
    """A stretch nobody recorded, with the date again at its end when it crosses midnight (B89)."""
    start, end = _time(stretch["start"]), _time(stretch["end"])
    shown_end = f"{end:%H:%M}" if end.date() == start.date() else f"{end:%Y-%m-%d %H:%M}"
    return str(words["span"].format(start=f"{start:%Y-%m-%d %H:%M}", end=shown_end))


def _duration(minutes: int, words: Mapping[str, Any]) -> str:
    if minutes < 60:
        return str(words["minutes"].format(minutes=minutes))
    return str(words["hours"].format(hours=minutes // 60, minutes=minutes % 60))


def _time(text: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(text)


def _unique(texts: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    found = []
    for text in texts:
        folded = " ".join(text.split()).casefold()
        if text and folded not in seen:
            seen.add(folded)
            found.append(text)
    return found
