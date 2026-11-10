"""The daily worklog: once a day, the verdict through the model step, the writer's order, reruns."""

from __future__ import annotations

import csv
import datetime
import io
import json
import os
import subprocess
import sys
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest import mock

from m2b_worklog import daily, ledger, writeup
from m2b_worklog.daily import DailyError, Sources
from m2b_worklog.paths import WorklogPaths
from m2b_worklog.sources import SourceState
from test_facts import NOW, PROFILE, Fixture, at

COMMAND = Path(__file__).resolve().parents[3] / "bin" / "m2b-worklog"
DAY_BEFORE = at(9) - datetime.timedelta(days=1)
STATE = Path("state") / "addons" / "worklog"


class Crash(Exception):
    """Stands for the process dying between two pieces of the write."""


def judged(found: dict[str, Any]) -> dict[str, Any]:
    """What the verdict skill hands in for the day of work: one session, b1 booked, one candidate."""
    sessions = []
    for session in found["sessions"]:
        blocks: dict[str, Any] = {block["id"]: None for block in session["blocks"]}
        blocks["b1"] = {"customer": "Globex", "project": "Invoices", "activity": "development"}
        sessions.append(
            {
                "key": session["key"],
                "topic": "Invoice export",
                "state": "waiting",
                "state_detail": "an approval",
                "blocks": blocks,
            }
        )
    return {
        "version": 1,
        "sessions": sessions,
        "candidates": [
            {"text": "Dana reviews the invoice export on Fridays"},
            {"text": "dana reviews the invoice  export on fridays"},
        ],
    }


class FakeCore:
    """The core as the worklog sees it; its model step hands in a verdict the way the skill does."""

    def __init__(self, paths: WorklogPaths, store: Path, profile: dict[str, Any], judge: Callable[..., Any]) -> None:
        self.paths, self._store, self._profile, self._judge = paths, store, profile, judge
        self.model_calls: list[tuple[str, tuple[str, ...]]] = []
        self.proposed: list[str] = []
        self.attempts: list[str] = []

    def store(self) -> Path:
        return self._store

    def profile(self) -> dict[str, Any]:
        return self._profile

    def model(self, skill: str, allow: Any) -> None:
        self.model_calls.append((skill, tuple(allow)))
        verdict = self._judge(daily.facts_for_model(self.paths)["facts"])
        if verdict is not None:
            self._accept(verdict)

    def _accept(self, verdict: dict[str, Any]) -> None:
        problems = daily.accept_verdict(self.paths, json.dumps(verdict))
        if problems:
            raise AssertionError(problems)

    def propose(self, text: str) -> None:
        # The core refuses a text it holds open already, with exit 0 (B35).
        self.attempts.append(text)
        if text not in self.proposed:
            self.proposed.append(text)


class DailyFixture(Fixture):
    def setUp(self) -> None:
        super().setUp()
        self.paths = WorklogPaths(self.home)
        self.profile: dict[str, Any] = {**PROFILE, "language": "en"}
        self.core = FakeCore(self.paths, self.store, self.profile, judged)
        self.herdr = SourceState.read()

    def run_daily(self, now: datetime.datetime = NOW) -> str:
        environ_backup = dict(os.environ)
        os.environ.update({"GIT_CONFIG_GLOBAL": str(self.base / "gitconfig"), "GIT_CONFIG_NOSYSTEM": "1"})
        try:
            return daily.run(self.paths, self.core, now, Sources(self.projects, self.herdr))
        finally:
            os.environ.clear()
            os.environ.update(environ_backup)

    def a_due_day(self) -> None:
        self.a_day_of_work()
        self.watermark(DAY_BEFORE)

    def store_files(self) -> dict[str, bytes]:
        return {
            path.relative_to(self.store).as_posix(): path.read_bytes()
            for path in sorted(self.store.rglob("*"))
            if path.is_file()
        }

    def worklog_notes(self) -> list[str]:
        return sorted(p.relative_to(self.store).as_posix() for p in self.store.rglob("*-worklog-*.md"))

    def watermark_end(self) -> str | None:
        path = self.store / STATE / "watermark.json"
        return json.loads(path.read_text(encoding="utf-8"))["end"] if path.exists() else None

    def ledger_periods(self) -> dict[str, Any]:
        periods: dict[str, Any] = ledger.read(self.store / STATE)["periods"]
        return periods


class DueTest(DailyFixture):
    def test_the_last_worklog_less_than_20_hours_ago_means_nothing_to_do(self) -> None:
        self.a_day_of_work()
        self.watermark(NOW - datetime.timedelta(hours=19, minutes=59))
        before = self.store_files()

        message = self.run_daily()

        self.assertIn("not due", message)
        self.assertEqual(self.core.model_calls, [])
        self.assertEqual(self.store_files(), before)

    def test_20_hours_after_the_last_worklog_it_is_due(self) -> None:
        self.a_day_of_work()
        self.watermark(NOW - datetime.timedelta(hours=20))

        self.run_daily()

        self.assertEqual(len(self.core.model_calls), 1)

    def test_a_first_worklog_is_due(self) -> None:
        self.run_daily()

        self.assertEqual(self.watermark_end(), NOW.isoformat())

    def test_a_period_without_sessions_needs_no_model_and_writes_no_note(self) -> None:
        self.projects.mkdir(parents=True, exist_ok=True)
        self.watermark(DAY_BEFORE)

        message = self.run_daily()

        self.assertIn("no sessions", message)
        self.assertEqual(self.core.model_calls, [])
        self.assertEqual(self.worklog_notes(), [])
        self.assertFalse((self.store / STATE / "ledger.json").exists())
        self.assertEqual(self.watermark_end(), NOW.isoformat())

    def test_a_period_without_sessions_but_a_source_it_could_not_read_goes_to_the_model(self) -> None:
        """No session may mean "could not look"; the note names what was not read."""
        self.herdr = SourceState.failed("herdr did not answer (herdr was not found)")
        self.projects.mkdir(parents=True, exist_ok=True)
        self.watermark(DAY_BEFORE)

        self.run_daily()

        self.assertEqual(len(self.core.model_calls), 1)
        self.assertEqual(len(self.worklog_notes()), 1)


class WriteTest(DailyFixture):
    def test_the_verdict_runs_fenced_with_the_worklog_rules(self) -> None:
        self.a_due_day()

        self.run_daily()

        [(skill, rules)] = self.core.model_calls
        self.assertEqual(skill, "m2b:worklog-verdict")
        self.assertEqual(
            rules,
            (
                "Bash(m2b-worklog facts *)",
                "Bash(m2b-worklog verdict *)",
                "Bash(m2b search *)",
                "Bash(m2b tasks list *)",
                "Bash(m2b curate report *)",
                "Read(<store>/memory/**)",
                "Read(<store>/inbox/**)",
            ),
        )

    def test_a_worklog_writes_the_note_the_ledger_the_exports_the_candidates_and_the_watermark(self) -> None:
        """Covers: B28"""
        self.a_due_day()

        self.run_daily()

        period = writeup.period_id(DAY_BEFORE.isoformat(), NOW.isoformat())
        name = f"20260314T170000Z-worklog-{period[:4]}.md"
        self.assertEqual(self.worklog_notes(), [f"inbox/{name}"])
        note = (self.store / "inbox" / name).read_text(encoding="utf-8")
        self.assertTrue(note.startswith(f"---\ncreated: {NOW.isoformat()}\nsource: worklog\nkind: worklog\n---\n"))
        self.assertIn("### Invoice export", note)
        self.assertIn("waiting for the owner: an approval", note)
        self.assertIn("fix(export): round per line", note)
        self.assertIn("- 2026-03-14 10:00-10:50 (50 min): Globex, Invoices, development", note)
        spans = self.ledger_periods()[period]["spans"]
        self.assertEqual([(s["block"], s["customer"]) for s in spans], [("b1", "Globex"), ("b2", None)])
        self.assertEqual(self.core.proposed, ["Dana reviews the invoice export on Fridays"])
        self.assertEqual(self.watermark_end(), NOW.isoformat())
        self.assertFalse((self.store / STATE / "intent.json").exists())

    def test_the_exports_hold_every_span_and_come_out_the_same_twice(self) -> None:
        self.a_due_day()
        self.run_daily()
        folder = self.store / STATE
        first = (folder / "ledger.csv").read_bytes(), (folder / "ledger.xlsx").read_bytes()

        ledger.export(folder)

        self.assertEqual(((folder / "ledger.csv").read_bytes(), (folder / "ledger.xlsx").read_bytes()), first)
        rows = list(csv.DictReader(io.StringIO(first[0].decode("utf-8"))))
        self.assertEqual(
            (rows[0]["start"], rows[0]["minutes"], rows[0]["minutes_present"], rows[0]["customer"]),
            (at(10).isoformat(), "50", "22", "Globex"),
        )
        with zipfile.ZipFile(io.BytesIO(first[1])) as workbook:
            self.assertIn("xl/workbook.xml", workbook.namelist())
            sheet = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertIn("<t>Globex</t>", sheet)
        self.assertIn('<c r="D2"><v>50</v></c>', sheet)
        self.assertIn('<c r="E2"><v>22</v></c>', sheet)

    def test_a_span_carries_its_minutes_and_the_minutes_the_owner_was_there(self) -> None:
        """Covers: B86"""
        self.a_due_day()

        self.run_daily()

        [period] = self.ledger_periods().values()
        # b1 is 10:00 to 10:50: 50 minutes of work, 22 of them with the workspace in focus.
        self.assertEqual([(s["minutes"], s["minutes_present"]) for s in period["spans"]], [(50, 22), (40, 20)])

    def test_a_ledger_written_before_the_second_column_still_exports(self) -> None:
        """Covers: B86"""
        folder = self.store / STATE
        folder.mkdir(parents=True)
        old_span = {"period": "p0", "session": "workspace:w1:", "block": "b1", "start": at(10).isoformat()}
        old_span.update({"end": at(11).isoformat(), "minutes": 60, "sphere": "acme", "billable": False})
        old_span.update({"topic": "Invoices", "customer": None, "project": None, "activity": None})
        old = {
            "version": 1,
            "periods": {"p0": {"start": at(9).isoformat(), "end": at(12).isoformat(), "spans": [old_span]}},
        }
        (folder / "ledger.json").write_text(json.dumps(old), encoding="utf-8")

        ledger.export(folder)

        [row] = list(csv.DictReader(io.StringIO((folder / "ledger.csv").read_text(encoding="utf-8"))))
        self.assertEqual((row["minutes"], row["minutes_present"]), ("60", ""))


class LedgerOverlapTest(DailyFixture):
    def span(self, session: str, start: datetime.datetime, end: datetime.datetime) -> dict[str, Any]:
        return {"session": session, "block": "b1", "start": start.isoformat(), "end": end.isoformat(), "minutes": 1}

    def test_a_span_overlapping_one_of_the_same_session_is_refused_and_nothing_is_added(self) -> None:
        """Covers: B87"""
        folder = self.store / STATE
        ledger.add(folder, "p1", at(9).isoformat(), at(12).isoformat(), [self.span("s1", at(10), at(11))])
        before = (folder / "ledger.json").read_bytes()

        with self.assertRaises(ledger.LedgerError) as caught:
            ledger.add(folder, "p2", at(9).isoformat(), at(13).isoformat(), [self.span("s1", at(10, 30), at(12))])

        self.assertIn("s1", str(caught.exception))
        self.assertIn(at(10).isoformat(), str(caught.exception))
        self.assertIn("m2b-worklog state", str(caught.exception))
        self.assertEqual((folder / "ledger.json").read_bytes(), before)

    def test_a_period_that_only_touches_the_last_one_is_added(self) -> None:
        """Covers: B87"""
        folder = self.store / STATE
        ledger.add(folder, "p1", at(9).isoformat(), at(11).isoformat(), [self.span("s1", at(10), at(11))])

        added = ledger.add(
            folder,
            "p2",
            at(11).isoformat(),
            at(13).isoformat(),
            [self.span("s2", at(11), at(12)), self.span("s1", at(11), at(12))],
        )

        self.assertTrue(added)

    def test_a_period_overlapping_a_held_one_is_refused_whatever_its_sessions_are_called(self) -> None:
        """Covers: B87"""
        # A workspace reopened under a new id: the same minutes come back under another session key.
        folder = self.store / STATE
        held = [self.span("workspace:w2:", at(10), at(11))]
        ledger.add(folder, "p1", at(9).isoformat(), at(12).isoformat(), held)

        with self.assertRaises(ledger.LedgerError) as caught:
            again = [self.span("workspace:w1:", at(10), at(11))]
            ledger.add(folder, "p2", at(8).isoformat(), at(13).isoformat(), again)

        self.assertIn(f"the period from {at(9).isoformat()} to {at(12).isoformat()}", str(caught.exception))

    def test_a_worklog_after_a_reset_watermark_writes_nothing_and_says_how_to_look(self) -> None:
        """Covers: B87"""
        self.a_due_day()
        self.run_daily()
        (self.store / STATE / "watermark.json").unlink()
        notes_before = self.worklog_notes()

        with self.assertRaises(ledger.LedgerError) as caught:
            self.run_daily(NOW + datetime.timedelta(hours=1))

        self.assertIn("m2b-worklog state", str(caught.exception))
        self.assertEqual(self.worklog_notes(), notes_before)
        self.assertEqual(len(self.ledger_periods()), 1)
        self.assertFalse((self.store / STATE / "intent.json").exists())


class StateTest(DailyFixture):
    def test_the_state_names_the_watermark_an_unfinished_worklog_and_the_last_period(self) -> None:
        """Covers: B87"""
        self.a_due_day()
        self.run_daily()

        shown = daily.state(self.store)

        period = writeup.period_id(DAY_BEFORE.isoformat(), NOW.isoformat())
        self.assertEqual(shown["watermark"], NOW.isoformat())
        self.assertIsNone(shown["unfinished"])
        self.assertEqual(
            shown["ledger"],
            {"periods": 1, "last": {"id": period, "start": DAY_BEFORE.isoformat(), "end": NOW.isoformat()}},
        )

    def test_the_messages_about_broken_state_name_the_state_command_and_never_say_remove(self) -> None:
        """Covers: B87"""
        self.a_due_day()
        folder = self.store / STATE
        (folder / "watermark.json").write_text("{", encoding="utf-8")
        (folder / "intent.json").write_text("{", encoding="utf-8")

        with self.assertRaises(DailyError) as intent:
            daily.read_intent(folder)
        from m2b_worklog import facts

        with self.assertRaises(facts.FactsError) as watermark:
            facts.read_watermark(self.store)

        for message in (str(intent.exception), str(watermark.exception)):
            with self.subTest(message=message):
                self.assertIn("m2b-worklog state", message)
                self.assertNotIn("remove", message)

    def test_a_sphere_without_billable_gets_no_booking_proposal(self) -> None:
        """Covers: B29"""
        self.profile["spheres"] = [{**PROFILE["spheres"][0], "billable": False}, PROFILE["spheres"][1]]
        self.a_due_day()

        self.run_daily()

        [period] = self.ledger_periods().values()
        self.assertEqual({span["customer"] for span in period["spans"]}, {None})
        [note] = self.worklog_notes()
        self.assertIn("## Booking proposals\n\nNone.\n", (self.store / note).read_text(encoding="utf-8"))

    def test_nothing_is_written_outside_the_inbox_and_the_worklog_state(self) -> None:
        """Covers: B29"""
        self.a_due_day()
        before = self.store_files()

        self.run_daily()

        changed = {path for path, data in self.store_files().items() if before.get(path) != data}
        self.assertTrue(changed)
        self.assertEqual({p for p in changed if not p.startswith(("inbox/", f"{STATE.as_posix()}/"))}, set())

    def test_the_handed_facts_are_gone_after_a_worklog_so_facts_answers_only_inside_one(self) -> None:
        self.a_due_day()

        self.run_daily()

        self.assertEqual(list(self.paths.run_dir.iterdir()), [])
        with self.assertRaisesRegex(DailyError, "no worklog is being judged"):
            daily.facts_for_model(self.paths)

    def test_the_handed_facts_are_gone_after_a_failed_verdict_too(self) -> None:
        self.core = FakeCore(self.paths, self.store, self.profile, lambda found: None)
        self.a_due_day()

        with self.assertRaises(DailyError):
            self.run_daily()

        self.assertEqual(list(self.paths.run_dir.iterdir()), [])

    def test_a_store_without_an_inbox_folder_gets_one_for_the_note(self) -> None:
        self.a_due_day()
        (self.store / "inbox").rmdir()

        self.run_daily()

        self.assertEqual(len(self.worklog_notes()), 1)

    def test_a_herdr_that_did_not_answer_is_named_in_the_note(self) -> None:
        """Covers: X20"""
        self.herdr = SourceState.failed("herdr did not answer (herdr was not found)")
        self.a_due_day()

        self.run_daily()

        [note] = self.worklog_notes()
        self.assertIn(
            "## Could not read\n\n- herdr: herdr did not answer", (self.store / note).read_text(encoding="utf-8")
        )

    def test_a_stretch_the_recorder_did_not_record_is_named_in_the_note(self) -> None:
        """Covers: B89"""
        self.a_due_day()
        self.alive(at(9), at(10, 50))
        self.alive(at(13), at(18))

        self.run_daily()

        [note] = self.worklog_notes()
        text = (self.store / note).read_text(encoding="utf-8")
        self.assertIn(
            "## Not recorded\n\nherdr was not running, the machine was asleep, recording was off or the recorder's "
            "timer did not run:\n\n"
            "- 2026-03-14 10:55 to 13:00\n",
            text,
        )
        self.assertNotIn("## Could not read", text)

    def test_a_stretch_over_midnight_carries_both_dates(self) -> None:
        """Covers: B89"""
        self.a_due_day()
        self.alive(DAY_BEFORE, DAY_BEFORE + datetime.timedelta(hours=10))
        self.alive(at(8, 30), at(18))

        self.run_daily()

        [note] = self.worklog_notes()
        self.assertIn("- 2026-03-13 19:05 to 2026-03-14 08:30\n", (self.store / note).read_text("utf-8"))

    def test_the_heading_of_stretches_not_recorded_follows_the_language(self) -> None:
        self.profile["language"] = "de"
        self.a_due_day()
        self.alive(at(9), at(10, 50))
        self.alive(at(13), at(18))

        self.run_daily()

        [note] = self.worklog_notes()
        text = (self.store / note).read_text("utf-8")
        self.assertIn("## Nicht aufgezeichnet\n\nherdr lief nicht", text)
        self.assertIn("- 2026-03-14 10:55 bis 13:00\n", text)

    def test_the_note_follows_the_profiles_language(self) -> None:
        self.profile["language"] = "de"
        self.a_due_day()

        self.run_daily()

        [note] = self.worklog_notes()
        self.assertIn("## Buchungsvorschläge", (self.store / note).read_text(encoding="utf-8"))


class VerdictTest(DailyFixture):
    def test_no_verdict_from_the_model_step_fails_and_writes_nothing(self) -> None:
        self.core = FakeCore(self.paths, self.store, self.profile, lambda found: None)
        self.a_due_day()
        before = self.store_files()

        with self.assertRaisesRegex(DailyError, "handed in no verdict"):
            self.run_daily()

        self.assertEqual(self.store_files(), before)

    def test_a_verdict_that_does_not_fit_the_facts_is_refused_with_its_places(self) -> None:
        self.a_due_day()
        handed: list[dict[str, Any]] = []
        self.core = FakeCore(self.paths, self.store, self.profile, lambda found: handed.append(found))
        with self.assertRaises(DailyError):
            self.run_daily()
        [found] = handed
        daily.hand_to_model(self.paths, self.store, "en", found)
        [key] = [s["key"] for s in found["sessions"]]
        good = judged(found)

        unknown_customer = json.loads(json.dumps(good))
        unknown_customer["sessions"][0]["blocks"]["b1"]["customer"] = "Hooli"
        invented = {**good, "sessions": [*good["sessions"], {**good["sessions"][0], "key": "folder:/elsewhere"}]}
        unjudged = {**good, "sessions": []}
        wrong_block = json.loads(json.dumps(good))
        wrong_block["sessions"][0]["blocks"]["b9"] = None

        self.assertIn(
            "'Hooli' is not in the customer list", daily.accept_verdict(self.paths, json.dumps(unknown_customer))[0]
        )
        self.assertIn("is not a session of the facts", daily.accept_verdict(self.paths, json.dumps(invented))[0])
        self.assertEqual(daily.accept_verdict(self.paths, json.dumps(unjudged)), [f"$.sessions: {key!r} is not judged"])
        self.assertIn("'b9' is not a block", daily.accept_verdict(self.paths, json.dumps(wrong_block))[0])
        self.assertIn("is not JSON", daily.accept_verdict(self.paths, "{")[0])
        self.assertFalse((self.paths.run_dir / "verdict.json").exists())
        self.assertEqual(daily.accept_verdict(self.paths, json.dumps(good)), [])


class RerunTest(DailyFixture):
    """A crash after any piece: the rerun writes each missing piece once and nothing twice (B28)."""

    def clean_result(self) -> dict[str, bytes]:
        clean = DailyFixture("run_daily")
        clean.setUp()
        try:
            clean.a_due_day()
            clean.run_daily()
            return {path: data for path, data in clean.store_files().items()}
        finally:
            clean.doCleanups()

    @contextmanager
    def crash_after(self, target: Any, name: str) -> Iterator[None]:
        original = getattr(target, name)

        def piece(*arguments: Any, **keywords: Any) -> Any:
            original(*arguments, **keywords)
            raise Crash(name)

        with mock.patch.object(target, name, side_effect=piece):
            yield

    def assert_rerun_completes(self, target: Any, name: str) -> None:
        self.a_due_day()
        with self.crash_after(target, name), self.assertRaises(Crash):
            self.run_daily()

        message = self.run_daily()

        self.assertIn("resumed", message)
        self.assertEqual(len(self.core.model_calls), 1)
        self.assertEqual(len(self.worklog_notes()), 1)
        self.assertEqual(len(self.ledger_periods()), 1)
        self.assertEqual(self.core.proposed, ["Dana reviews the invoice export on Fridays"])
        self.assertEqual(self.watermark_end(), NOW.isoformat())
        self.assertFalse((self.store / STATE / "intent.json").exists())

    def test_a_crash_after_the_intent(self) -> None:
        """Covers: B28"""
        self.assert_rerun_completes(daily, "_write_intent")

    def test_a_crash_after_the_note(self) -> None:
        """Covers: B28"""
        self.assert_rerun_completes(daily, "_write_note")

    def test_a_crash_after_the_ledger(self) -> None:
        """Covers: B28"""
        self.assert_rerun_completes(ledger, "add")

    def test_a_crash_after_the_exports(self) -> None:
        """Covers: B28"""
        self.assert_rerun_completes(ledger, "export")

    def test_a_crash_after_a_candidate_was_proposed(self) -> None:
        """Covers: B28"""
        self.assert_rerun_completes(self.core, "propose")
        self.assertEqual(len(self.core.attempts), 2)

    def test_a_crash_after_the_watermark(self) -> None:
        """Covers: B28"""
        self.assert_rerun_completes(daily, "_move_watermark")

    def test_every_rerun_ends_where_a_clean_run_ends(self) -> None:
        """Covers: B28"""
        clean = self.clean_result()
        self.a_due_day()
        with self.crash_after(ledger, "add"), self.assertRaises(Crash):
            self.run_daily()
        self.run_daily()

        self.assertEqual(sorted(self.store_files()), sorted(clean))
        for path in (
            f"{STATE.as_posix()}/ledger.json",
            f"{STATE.as_posix()}/ledger.csv",
            f"{STATE.as_posix()}/watermark.json",
        ):
            self.assertEqual(self.store_files()[path], clean[path], path)

    def test_a_note_ingest_filed_before_the_rerun_is_not_written_again(self) -> None:
        """Covers: B28"""
        self.a_due_day()
        with self.crash_after(daily, "_write_note"), self.assertRaises(Crash):
            self.run_daily()
        [note] = self.worklog_notes()
        filed = self.store / "corpus" / "2026" / "03" / Path(note).name
        filed.parent.mkdir(parents=True)
        (self.store / note).rename(filed)

        self.run_daily()

        self.assertEqual(self.worklog_notes(), [filed.relative_to(self.store).as_posix()])

    def test_a_rerun_with_an_intent_does_not_wait_for_the_day(self) -> None:
        self.a_due_day()
        with self.crash_after(ledger, "export"), self.assertRaises(Crash):
            self.run_daily()

        self.run_daily(NOW + datetime.timedelta(minutes=5))

        self.assertEqual(self.watermark_end(), NOW.isoformat())

    def test_an_evicted_ledger_names_the_fetch_command(self) -> None:
        (self.store / STATE).mkdir(parents=True)
        (self.store / STATE / "ledger.json").write_text("{}", encoding="utf-8")

        with (
            mock.patch.object(ledger, "is_evicted", return_value=True),
            self.assertRaises(ledger.LedgerError) as raised,
        ):
            ledger.read(self.store / STATE)

        self.assertIn("m2b store fetch state/addons/worklog/ledger.json downloads it", str(raised.exception))

    def test_an_unreadable_intent_stops_the_worklog(self) -> None:
        (self.store / STATE).mkdir(parents=True)
        (self.store / STATE / "intent.json").write_text("{", encoding="utf-8")

        with self.assertRaisesRegex(DailyError, "repair it by hand: m2b-worklog state"):
            self.run_daily()


class CommandTest(DailyFixture):
    """``m2b-worklog run`` through a fake launcher: the core's commands as the worklog calls them."""

    def launcher(self) -> Path:
        launcher = self.home / ".local" / "bin" / "m2b"
        launcher.parent.mkdir(parents=True)
        calls = self.base / "launcher-calls.txt"
        verdict = self.base / "verdict.json"
        script = f"""#!{sys.executable}
import json, subprocess, sys
arguments = sys.argv[1:]
with open({str(calls)!r}, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(arguments) + "\\n")
if arguments == ["config", "get", "store.path", "--json"]:
    print(json.dumps({str(self.store)!r}))
elif arguments == ["profile", "get", "--json"]:
    print({json.dumps(self.profile)!r})
elif arguments[:2] == ["curate", "model"]:
    # The model may hand in a verdict that is refused; the step itself still ends well.
    subprocess.run([{str(COMMAND)!r}, "verdict", open({str(verdict)!r}).read()])
elif arguments[:3] == ["tasks", "add", "--candidate"]:
    print("aaaa00000001")
else:
    sys.exit(f"unexpected: {{arguments}}")
"""
        launcher.write_text(script, encoding="utf-8")
        launcher.chmod(0o755)
        return calls

    def command(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environ = {
            "PATH": os.environ.get("PATH", ""),
            "M2B_HOME": str(self.home),
            "HOME": str(self.home),
            "M2B_PYTHON": sys.executable,
            "M2B_HERDR": str(self.base / "no-herdr"),
            "GIT_CONFIG_GLOBAL": str(self.base / "gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        return subprocess.run([str(COMMAND), *arguments], capture_output=True, text=True, env=environ, timeout=60)

    def test_run_asks_the_core_for_the_model_step_and_the_candidates(self) -> None:
        calls = self.launcher()
        self.a_due_day()
        collected = self.command("collect", "--now", NOW.isoformat())
        (self.base / "verdict.json").write_text(json.dumps(judged(json.loads(collected.stdout))), encoding="utf-8")

        result = self.command("run", "--now", NOW.isoformat())

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("note written", result.stdout)
        made = [json.loads(line) for line in calls.read_text(encoding="utf-8").splitlines()]
        [model] = [call for call in made if call[:2] == ["curate", "model"]]
        self.assertEqual(model[:5], ["curate", "model", "--skill", "m2b:worklog-verdict", "--allow"])
        self.assertIn("Read(<store>/inbox/**)", model)
        self.assertIn(["tasks", "add", "--candidate", "--", "Dana reviews the invoice export on Fridays"], made)
        [note] = self.worklog_notes()
        self.assertIn("- herdr: herdr did not answer", (self.store / note).read_text(encoding="utf-8"))

    def test_state_shows_the_watermark_and_the_last_period_and_names_a_broken_file(self) -> None:
        """Covers: B87"""
        self.launcher()
        self.a_due_day()
        self.run_daily()
        (self.store / STATE / "intent.json").write_text("{", encoding="utf-8")

        shown = self.command("state")

        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn(f"watermark: {NOW.isoformat()}", shown.stdout)
        self.assertIn("unfinished worklog: cannot be read", shown.stdout)
        self.assertIn(f"ledger: 1 period, the last from {DAY_BEFORE.isoformat()} to {NOW.isoformat()}", shown.stdout)

        (self.store / STATE / "watermark.json").unlink()
        missing = self.command("state")

        self.assertIn(f"watermark: missing; it belongs at {NOW.isoformat()}", missing.stdout)

    def test_facts_and_verdict_are_what_the_model_step_calls(self) -> None:
        self.launcher()
        (self.base / "verdict.json").write_text("{}", encoding="utf-8")
        self.a_due_day()

        failed = self.command("run", "--now", NOW.isoformat())
        outside = self.command("facts", "--json")
        collected = self.command("collect", "--now", NOW.isoformat())
        daily.hand_to_model(self.paths, self.store, "en", json.loads(collected.stdout))
        handed = self.command("facts", "--json")
        refused = self.command("verdict", "{}")
        accepted = self.command("verdict", json.dumps(judged(json.loads(handed.stdout)["facts"])))

        self.assertEqual(failed.returncode, 1)
        self.assertIn("handed in no verdict", failed.stderr)
        self.assertEqual(outside.returncode, 1)
        self.assertIn("no worklog is being judged", outside.stderr)
        self.assertEqual(json.loads(handed.stdout)["store"], str(self.store))
        self.assertEqual(json.loads(handed.stdout)["language"], "en")
        self.assertEqual(refused.returncode, 1)
        self.assertIn("- $: version is missing", refused.stderr)
        self.assertEqual((accepted.returncode, accepted.stdout), (0, "verdict accepted\n"))

    def test_recordings_delete_removes_what_the_recorder_wrote_and_any_facts_handed_over(self) -> None:
        self.events("w1", (at(10), "focus", None))
        self.paths.run_dir.mkdir(parents=True)
        (self.paths.run_dir / "facts.json").write_text("{}", encoding="utf-8")

        result = self.command("recordings", "delete")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.recordings.exists())
        self.assertFalse(self.paths.run_dir.exists())

    def test_an_unreadable_ledger_fails_the_run_with_one_line(self) -> None:
        self.launcher()
        self.a_due_day()
        collected = self.command("collect", "--now", NOW.isoformat())
        (self.base / "verdict.json").write_text(json.dumps(judged(json.loads(collected.stdout))), encoding="utf-8")
        (self.store / STATE).mkdir(parents=True, exist_ok=True)
        (self.store / STATE / "ledger.json").write_text("{", encoding="utf-8")

        result = self.command("run", "--now", NOW.isoformat())

        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stderr, r"\Am2b-worklog: [^\n]*ledger\.json cannot be read[^\n]*\n\Z")
