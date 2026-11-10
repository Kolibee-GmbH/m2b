"""Collect: the facts of a period from recorder journals, transcripts, git and the inbox, in a fixture."""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from m2b_worklog import facts, schema
from m2b_worklog.facts import FactsError, Inputs
from m2b_worklog.sources import herdr_events
from m2b_worklog.sources.transcripts import prompt_text, redact
from worklog_fixtures import load_recorder

ZONE = datetime.timezone(datetime.timedelta(hours=1))
NOW = datetime.datetime(2026, 3, 14, 18, 0, tzinfo=ZONE)
COMMAND = Path(__file__).resolve().parents[3] / "bin" / "m2b-worklog"
PROFILE = {
    "version": 1,
    "owner": "Alex",
    "spheres": [
        {"id": "acme", "label": "Acme Ltd", "billable": True, "match": {"path_under": ["~/code/acme"]}},
        {"id": "private", "default": True},
    ],
    "customers": ["Globex", "Initech"],
}


def at(hour: int, minute: int = 0) -> datetime.datetime:
    return NOW.replace(hour=hour, minute=minute)


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.base = Path(self._temp.name)
        self.home = self.base / "home"
        self.store = self.base / "sb-test-store"
        (self.store / "inbox").mkdir(parents=True)
        self.recordings = self.home / ".local" / "state" / "m2b" / "worklog"
        self.recordings.mkdir(parents=True)
        self.projects = self.home / ".claude" / "projects"
        self.repo = self.home / "code" / "acme" / "invoices"
        self.repo.mkdir(parents=True)
        self.git_env = {
            **os.environ,
            "GIT_CONFIG_GLOBAL": str(self.base / "gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "alex@example.invalid")
        self.git("config", "user.name", "Alex")

    def git(self, *arguments: str, when: datetime.datetime | None = None, email: str | None = None) -> None:
        environ = dict(self.git_env)
        if when is not None:
            environ["GIT_AUTHOR_DATE"] = environ["GIT_COMMITTER_DATE"] = when.isoformat()
        if email is not None:
            environ["GIT_AUTHOR_EMAIL"] = email
        subprocess.run(["git", "-C", str(self.repo), *arguments], check=True, env=environ, capture_output=True)

    def commit(self, subject: str, when: datetime.datetime, email: str | None = None) -> None:
        self.git("commit", "-q", "--allow-empty", "-m", subject, when=when, email=email)

    def events(
        self, workspace: str, *lines: tuple[datetime.datetime, str, str | None], cwd: Path | None = None
    ) -> None:
        with (self.recordings / f"{workspace}.jsonl").open("a", encoding="utf-8") as handle:
            for moment, kind, pane in lines:
                folder = str(cwd) if cwd is not None and pane is not None else None
                record = {"time": moment.isoformat(), "kind": kind, "workspace": workspace, "pane": pane, "cwd": folder}
                handle.write(json.dumps(record) + "\n")

    def alive(self, start: datetime.datetime, end: datetime.datetime) -> None:
        """The timer's ticks every five minutes from ``start`` up to ``end``; the first one ever is noted."""
        folder = self.recordings / "alive"
        folder.mkdir(exist_ok=True)
        if not (folder / "first-tick").exists():
            (folder / "first-tick").write_text(start.isoformat() + "\n", encoding="utf-8")
        moment = start
        while moment <= end:
            with (folder / f"{moment:%Y-%m}.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"time": moment.isoformat(), "kind": "recorder_alive"}) + "\n")
            moment += datetime.timedelta(minutes=5)

    def cache(self, entries: dict[str, list[dict[str, Any]]]) -> None:
        (self.recordings / "workspaces.json").write_text(json.dumps(entries), encoding="utf-8")

    def transcript(self, name: str, cwd: Path, records: list[dict[str, Any]], headless: bool = False) -> None:
        folder = self.projects / "-home-alex-code"
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / f"{name}.jsonl").open("w", encoding="utf-8") as handle:
            for record in records:
                full = {"cwd": str(cwd), "sessionId": name, "entrypoint": "sdk-cli" if headless else "cli", **record}
                handle.write(json.dumps(full) + "\n")

    def capture(self, name: str, created: datetime.datetime, source: str) -> None:
        (self.store / "inbox" / name).write_text(
            f"---\ncreated: {created.isoformat()}\nsource: {source}\n---\n\nA note.\n", encoding="utf-8"
        )

    def watermark(self, moment: datetime.datetime) -> None:
        path = self.store / "state" / "addons" / "worklog" / "watermark.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"end": moment.isoformat()}), encoding="utf-8")

    def collect(self) -> dict[str, Any]:
        inputs = Inputs(self.store, self.recordings, self.projects, self.home, PROFILE, NOW)
        environ_backup = dict(os.environ)
        os.environ.update({"GIT_CONFIG_GLOBAL": str(self.base / "gitconfig"), "GIT_CONFIG_NOSYSTEM": "1"})
        try:
            found = facts.collect(inputs)
        finally:
            os.environ.clear()
            os.environ.update(environ_backup)
        self.assertEqual(schema.check(found, schema.load(schema.FACTS_SCHEMA)), [])
        return found

    def a_day_of_work(self) -> None:
        self.watermark(at(9))
        self.cache(
            {"w1": [{"repo": "invoices", "label": "invoices", "folder": str(self.repo), "since": at(8).isoformat()}]}
        )
        self.events(
            "w1",
            (at(10), "focus", None),
            (at(10, 2), "agent_working", "p1"),
            (at(10, 40), "agent_stopped", "p1"),
            (at(14), "agent_working", "p1"),
            (at(14, 30), "agent_blocked", "p1"),
        )
        self.transcript(
            "s1",
            self.repo / "src",
            [
                {"type": "user", "timestamp": "2026-03-14T09:01:00Z", "message": {"content": "Fix the invoice export"}},
                {
                    "type": "assistant",
                    "timestamp": "2026-03-14T09:30:00Z",
                    "message": {"content": [{"type": "text", "text": "The export now rounds per line."}]},
                },
                {
                    "type": "user",
                    "timestamp": "2026-03-14T13:05:00Z",
                    "message": {"content": "Add a test for the totals"},
                },
            ],
        )
        self.commit("fix(export): round per line", at(10, 30))
        self.commit("chore(deps): bump by a colleague", at(10, 35), email="dana@example.invalid")
        self.commit("feat(export): yesterday", at(9) - datetime.timedelta(days=1))


class CollectTest(Fixture):
    def test_a_session_has_its_blocks_prompts_commits_and_state(self) -> None:
        """Covers: X17"""
        self.a_day_of_work()

        found = self.collect()

        self.assertEqual(found["period"], {"start": at(9).isoformat(), "end": NOW.isoformat(), "origin": "watermark"})
        self.assertEqual(found["spheres"][0], {"id": "acme", "label": "Acme Ltd", "billable": True, "default": False})
        self.assertEqual(found["customers"], ["Globex", "Initech"])
        [session] = found["sessions"]
        self.assertEqual((session["workspace"], session["repo"], session["folder"]), ("w1", "invoices", str(self.repo)))
        self.assertEqual(session["sphere"], "acme")
        self.assertEqual(
            [(b["id"], b["start"], b["end"]) for b in session["blocks"]],
            [
                # The focus piece after the agent stopped counts up to 10 minutes past that event.
                ("b1", at(10).isoformat(), at(10, 50).isoformat()),
                ("b2", at(14).isoformat(), at(14, 40).isoformat()),
            ],
        )
        # Transcript times are UTC: 09:01Z is 10:01 here.
        self.assertEqual(session["blocks"][0]["prompts"], ["Fix the invoice export"])
        self.assertEqual(session["blocks"][1]["prompts"], ["Add a test for the totals"])
        self.assertEqual(session["git"], {"state": "read", "detail": ""})
        self.assertEqual([c["subject"] for c in session["commits"]], ["fix(export): round per line"])
        # Blocked since 14:30 without a later event: by the open-period rule the agent no longer counts.
        # Blocked since 14:30: an agent waiting for an approval still waits hours later.
        self.assertEqual(session["state"], {"agent": "blocked", "last_answer": "The export now rounds per line."})
        self.assertEqual(session["minutes"]["agent"], 38 + 30)

    def test_a_session_seen_for_less_than_two_minutes_is_left_out(self) -> None:
        """Covers: B33"""
        self.a_day_of_work()
        cache = json.loads((self.recordings / "workspaces.json").read_text(encoding="utf-8"))
        cache["w2"] = [{"repo": None, "label": "notes", "folder": str(self.home / "notes"), "since": at(8).isoformat()}]
        self.cache(cache)
        self.events("w2", (at(15), "focus", None))
        self.events("w1", (at(15, 1), "focus", None))

        found = self.collect()

        self.assertEqual([s["workspace"] for s in found["sessions"]], ["w1"])

    def test_a_blocks_minutes_are_the_time_worked_inside_it_not_its_bounds(self) -> None:
        self.watermark(at(9))
        self.cache(
            {"w1": [{"repo": "invoices", "label": "invoices", "folder": str(self.repo), "since": at(8).isoformat()}]}
        )
        self.events(
            "w1",
            (at(10), "agent_working", "p1"),
            (at(10, 10), "agent_stopped", "p1"),
            (at(10, 20), "agent_working", "p1"),
            (at(10, 30), "agent_stopped", "p1"),
        )

        [session] = self.collect()["sessions"]

        self.assertEqual(
            [(b["start"], b["end"], b["minutes"]) for b in session["blocks"]],
            [(at(10).isoformat(), at(10, 30).isoformat(), 20)],
        )

    def test_a_session_without_prompts_or_commits_needs_fifteen_minutes_of_work(self) -> None:
        """A workspace looked at, or an agent running on, without anything typed: below 15 minutes it is noise."""
        self.projects.mkdir(parents=True)
        # git log fails in a repository without a commit, which would keep every session.
        self.commit("chore: start", at(9) - datetime.timedelta(days=1))
        self.watermark(at(9))
        self.cache(
            {
                "w1": [{"repo": "invoices", "label": "invoices", "folder": str(self.repo), "since": at(8).isoformat()}],
                "w2": [
                    {
                        "repo": "invoices",
                        "label": "review",
                        "folder": str(self.repo / "review"),
                        "since": at(8).isoformat(),
                    }
                ],
            }
        )
        (self.repo / "review").mkdir()
        self.events("w1", (at(10), "agent_working", "p1"), (at(10, 14), "agent_stopped", "p1"))
        self.events("w2", (at(11), "agent_working", "p2"), (at(11, 15), "agent_stopped", "p2"))

        found = self.collect()

        self.assertEqual([s["workspace"] for s in found["sessions"]], ["w2"])

    def test_a_short_session_whose_git_could_not_be_read_stays(self) -> None:
        """Covers: X20"""
        self.projects.mkdir(parents=True)
        self.watermark(at(9))
        gone = self.home / "merged-worktree"
        self.cache({"w1": [{"repo": "invoices", "label": "fix", "folder": str(gone), "since": at(8).isoformat()}]})
        self.events("w1", (at(10), "agent_working", "p1"), (at(10, 5), "agent_stopped", "p1"))

        [session] = self.collect()["sessions"]

        self.assertEqual(session["git"]["state"], "could not read")

    def test_a_commit_another_worktree_made_does_not_keep_a_short_session(self) -> None:
        self.projects.mkdir(parents=True)
        self.a_day_of_work()
        cache = json.loads((self.recordings / "workspaces.json").read_text(encoding="utf-8"))
        cache["w2"] = [{"repo": "invoices", "label": "other", "folder": str(self.repo), "since": at(8).isoformat()}]
        self.cache(cache)
        self.events("w2", (at(16), "agent_working", "p2"), (at(16, 5), "agent_stopped", "p2"))

        found = self.collect()

        self.assertEqual([s["workspace"] for s in found["sessions"]], ["w1"])

    def test_a_block_with_less_than_a_minute_of_work_is_dropped(self) -> None:
        self.watermark(at(9))
        self.cache(
            {"w1": [{"repo": "invoices", "label": "invoices", "folder": str(self.repo), "since": at(8).isoformat()}]}
        )
        second = datetime.timedelta(seconds=1)
        self.events(
            "w1",
            (at(10), "agent_working", "p1"),
            (at(10, 20), "agent_stopped", "p1"),
            (at(12), "agent_working", "p1"),
            (at(12) + 20 * second, "agent_stopped", "p1"),
            (at(12) + 70 * second, "agent_working", "p1"),
            (at(12) + 80 * second, "agent_stopped", "p1"),
        )

        [session] = self.collect()["sessions"]

        self.assertEqual([b["start"] for b in session["blocks"]], [at(10).isoformat()])

    def test_a_git_failure_reads_could_not_read_never_no_commits(self) -> None:
        """Covers: X20"""
        self.a_day_of_work()
        (self.repo / ".git").rename(self.repo / "not-git")

        [session] = self.collect()["sessions"]

        self.assertEqual(session["git"]["state"], "could not read")
        self.assertTrue(session["git"]["detail"])

    def test_missing_recordings_read_could_not_read_never_no_sessions(self) -> None:
        """Covers: X20"""
        self.recordings.rename(self.base / "gone")

        found = self.collect()

        self.assertEqual(found["sources"]["recorder"]["state"], "could not read")
        self.assertEqual(found["sources"]["transcripts"]["state"], "could not read")


class NotRecordedTest(Fixture):
    def test_a_stretch_without_a_sign_of_life_is_named_not_recorded(self) -> None:
        """Covers: B89"""
        self.a_day_of_work()
        self.alive(at(9), at(10, 50))
        self.alive(at(13), at(18))

        found = self.collect()

        self.assertEqual(
            found["not_recorded"],
            [{"start": "2026-03-14T10:55:00+01:00", "end": "2026-03-14T13:00:00+01:00", "minutes": 125}],
        )

    def test_a_recorder_without_its_timer_names_nothing(self) -> None:
        """Covers: B89"""
        self.a_day_of_work()

        self.assertEqual(self.collect()["not_recorded"], [])

    def test_signs_of_two_months_and_herdrs_starts_are_read_and_an_old_file_is_skipped(self) -> None:
        """Covers: B89"""
        self.watermark(at(9))
        self.alive(
            datetime.datetime(2026, 2, 28, 23, 50, tzinfo=ZONE), datetime.datetime(2026, 3, 1, 0, 5, tzinfo=ZONE)
        )
        self.alive(at(9) - datetime.timedelta(hours=1), at(12))
        self.alive(at(16, 5), at(18))
        folder = self.recordings / "alive"
        with (folder / "2026-03.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"time": at(16).isoformat(), "kind": "herdr_started"}) + "\n")
        # A file last written long ago holds nothing newer, whatever its lines say: it is not read.
        (folder / "2025-11.jsonl").write_text(json.dumps({"time": at(14).isoformat(), "kind": "recorder_alive"}) + "\n")
        os.utime(folder / "2025-11.jsonl", (0, 0))

        found = self.collect()

        self.assertEqual(
            [(s["start"], s["end"]) for s in found["not_recorded"]],
            [("2026-03-14T12:05:00+01:00", "2026-03-14T16:00:00+01:00")],
        )

    def test_the_sign_kinds_are_the_ones_the_recorder_writes(self) -> None:
        recorder_script = load_recorder()

        self.assertEqual(herdr_events.SIGN_KINDS, (recorder_script.ALIVE, recorder_script.HERDR_STARTED))

    def test_a_week_away_names_the_whole_period_before_herdr_came_back(self) -> None:
        """Covers: B89"""
        self.watermark(at(9) - datetime.timedelta(days=7))
        self.alive(at(9) - datetime.timedelta(days=9), at(9) - datetime.timedelta(days=9, minutes=-10))
        self.alive(at(15), at(18))

        found = self.collect()

        self.assertEqual(
            [(s["start"], s["end"]) for s in found["not_recorded"]],
            [("2026-03-11T18:00:00+01:00", "2026-03-14T15:00:00+01:00")],
        )


class PeriodTest(Fixture):
    def test_a_period_crossing_the_watermark_is_clipped_there(self) -> None:
        """Covers: B28, X19"""
        self.watermark(at(10, 20))
        self.cache(
            {"w1": [{"repo": "invoices", "label": "invoices", "folder": str(self.repo), "since": at(8).isoformat()}]}
        )
        self.events("w1", (at(10), "agent_working", "p1"), (at(10, 30), "agent_stopped", "p1"))

        [session] = self.collect()["sessions"]

        self.assertEqual(session["minutes"]["agent"], 10)
        self.assertEqual(session["blocks"][0]["start"], at(10, 20).isoformat())

    def test_without_a_watermark_and_with_an_old_one_it_reaches_three_days_back(self) -> None:
        three_days = (NOW - datetime.timedelta(days=3)).isoformat()
        self.assertEqual(self.collect()["period"], {"start": three_days, "end": NOW.isoformat(), "origin": "first run"})

        self.watermark(NOW - datetime.timedelta(days=9))
        self.assertEqual(
            self.collect()["period"],
            {"start": three_days, "end": NOW.isoformat(), "origin": "watermark, limited to three days"},
        )

    def test_a_watermark_that_cannot_be_read_or_lies_ahead_is_an_error(self) -> None:
        path = self.store / "state" / "addons" / "worklog" / "watermark.json"
        path.parent.mkdir(parents=True)
        for text in ["not json", '{"end": "2026-03-14T09:00:00"}', '{"end": "2026-03-15T09:00:00+01:00"}']:
            with self.subTest(text):
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(FactsError):
                    facts.collect(Inputs(self.store, self.recordings, self.projects, self.home, PROFILE, NOW))


class SourcesTest(Fixture):
    def test_worklog_notes_and_harvested_candidates_are_not_sources(self) -> None:
        self.watermark(at(9))
        self.capture("20260314-100000-mac-a1b2.md", at(10), "mac")
        self.capture("20260314-120000-mac-c3d4.md", at(12), "worklog")
        self.capture("20260314-130000-mac-e5f6.md", at(13), "candidate")
        self.capture("20260313-100000-mac-0a0b.md", at(10) - datetime.timedelta(days=1), "watch")

        found = self.collect()

        self.assertEqual(
            found["captures"], [{"name": "20260314-100000-mac-a1b2.md", "created": at(10).isoformat(), "source": "mac"}]
        )

    def test_a_transcript_of_a_headless_run_is_left_out(self) -> None:
        self.watermark(at(9))
        self.transcript(
            "curation",
            self.home / "work",
            [
                {"type": "user", "timestamp": "2026-03-14T09:01:00Z", "message": {"content": "Run the ingest"}},
                {"type": "user", "timestamp": "2026-03-14T09:20:00Z", "message": {"content": "Again"}},
            ],
            headless=True,
        )

        self.assertEqual(self.collect()["sessions"], [])

    def test_a_transcript_outside_any_workspace_is_a_session_of_its_own(self) -> None:
        self.watermark(at(9))
        self.transcript(
            "s2",
            self.home / "scratch",
            [
                {"type": "user", "timestamp": "2026-03-14T09:01:00Z", "message": {"content": "Sketch a plan"}},
                {"type": "user", "timestamp": "2026-03-14T09:10:00Z", "message": {"content": "Shorter please"}},
            ],
        )

        [session] = self.collect()["sessions"]

        self.assertEqual((session["key"], session["workspace"]), (f"folder:{self.home / 'scratch'}", None))
        self.assertEqual(session["minutes"]["transcript"], 9)
        self.assertEqual(session["git"]["state"], "could not read")

    def test_a_transcript_belongs_to_the_folder_it_started_in_not_where_a_command_went(self) -> None:
        # Claude Code writes the Bash tool's folder into every record, so a `cd /tmp` moves the record's cwd.
        self.watermark(at(9))
        self.transcript(
            "s3",
            self.home / "scratch",
            [
                {"type": "user", "timestamp": "2026-03-14T09:01:00Z", "message": {"content": "Sketch a plan"}},
                {"type": "user", "timestamp": "2026-03-14T09:10:00Z", "message": {"content": "Shorter please"}},
            ],
        )
        with (self.projects / "-home-alex-code" / "s3.jsonl").open("a", encoding="utf-8") as handle:
            moved = {"cwd": "/tmp", "type": "assistant", "timestamp": "2026-03-14T09:12:00Z", "message": {}}
            handle.write(json.dumps(moved) + "\n")

        [session] = self.collect()["sessions"]

        self.assertEqual(session["key"], f"folder:{self.home / 'scratch'}")

    def test_prompts_lose_system_wrappers_keep_pasted_text_and_are_redacted(self) -> None:
        self.assertEqual(
            prompt_text("<command-name>/m2b:search</command-name><command-args>old maps</command-args>"),
            "m2b:search old maps",
        )
        self.assertEqual(prompt_text('<pasted_content id="x">line one\nline two</pasted_content>'), "line one line two")
        self.assertIsNone(prompt_text("<system-reminder>be brief</system-reminder>"))
        self.assertIsNone(prompt_text([{"type": "tool_result", "content": "ok"}]))
        self.assertEqual(len(prompt_text("word " * 100) or ""), 240)
        self.assertEqual(redact("the api key is abc123"), "the api key is [removed]")
        self.assertEqual(redact("use a1b2c3d4e5f6g7h8i9j0k1l2m3 here"), "use [removed] here")
        self.assertEqual(redact("see /home/alex/code/acme and 20260314"), "see /home/alex/code/acme and 20260314")


class CommandTest(Fixture):
    def test_collect_asks_the_core_for_the_store_and_the_profile(self) -> None:
        self.watermark(at(9))
        launcher = self.home / ".local" / "bin" / "m2b"
        launcher.parent.mkdir(parents=True)
        answers = {
            "config get store.path --json": json.dumps(str(self.store)),
            "profile get --json": json.dumps(PROFILE),
        }
        launcher.write_text(
            f"#!{sys.executable}\nimport sys\nanswers = {answers!r}\nprint(answers[' '.join(sys.argv[1:])])\n",
            encoding="utf-8",
        )
        launcher.chmod(0o755)
        environ = {
            "PATH": os.environ.get("PATH", ""),
            "M2B_HOME": str(self.home),
            "HOME": str(self.home),
            "M2B_PYTHON": sys.executable,
            "M2B_HERDR": str(self.base / "no-herdr"),
        }

        result = subprocess.run(
            [str(COMMAND), "collect", "--now", NOW.isoformat()], capture_output=True, text=True, env=environ, timeout=30
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["period"]["origin"], "watermark")


class VerdictSchemaTest(unittest.TestCase):
    def test_the_verdict_schema_takes_a_judged_session(self) -> None:
        """Covers: X17"""
        verdict_schema = schema.load(schema.VERDICT_SCHEMA)
        verdict = {
            "version": 1,
            "sessions": [
                {
                    "key": "workspace:w1:",
                    "topic": "Invoice export",
                    "state": "open",
                    "blocks": {"b1": {"customer": "Globex", "activity": "development"}, "b2": None},
                }
            ],
            "candidates": [{"text": "Dana reviews the export on Fridays", "session": "workspace:w1:"}],
        }

        self.assertEqual(schema.check(verdict, verdict_schema), [])
        self.assertNotEqual(
            schema.check({**verdict, "sessions": [{**verdict["sessions"][0], "state": "maybe"}]}, verdict_schema), []
        )


class SharedRepositoryTest(Fixture):
    def test_a_commit_seen_from_two_worktrees_stays_with_the_session_active_then(self) -> None:
        self.watermark(at(9))
        other = self.repo.parent / "invoices-review"
        self.git("worktree", "add", "-q", "-b", "review", str(other))
        self.cache(
            {
                "w1": [{"repo": "invoices", "label": "invoices", "folder": str(self.repo), "since": at(8).isoformat()}],
                "w2": [{"repo": "invoices", "label": "review", "folder": str(other), "since": at(8).isoformat()}],
            }
        )
        self.events("w1", (at(10), "agent_working", "p1"), (at(10, 30), "agent_stopped", "p1"))
        self.events("w2", (at(15), "agent_working", "p2"), (at(15, 30), "agent_stopped", "p2"))
        self.commit("fix(export): round per line", at(10, 20))

        sessions = {s["workspace"]: s for s in self.collect()["sessions"]}

        self.assertEqual([c["subject"] for c in sessions["w1"]["commits"]], ["fix(export): round per line"])
        self.assertEqual(sessions["w2"]["commits"], [])

    def test_with_two_worktrees_active_the_commit_stays_on_the_branch_it_was_made_on(self) -> None:
        self.watermark(at(9))
        other = self.repo.parent / "invoices-review-longer"
        self.git("worktree", "add", "-q", "-b", "review", str(other))
        self.cache(
            {
                "w1": [{"repo": "invoices", "label": "invoices", "folder": str(self.repo), "since": at(8).isoformat()}],
                "w2": [{"repo": "invoices", "label": "review", "folder": str(other), "since": at(8).isoformat()}],
            }
        )
        self.events("w1", (at(10), "agent_working", "p1"), (at(10, 30), "agent_stopped", "p1"))
        self.events("w2", (at(10), "agent_working", "p2"), (at(10, 30), "agent_stopped", "p2"))
        self.commit("fix(export): round per line", at(10, 20))

        sessions = {s["workspace"]: s for s in self.collect()["sessions"]}

        self.assertEqual([c["subject"] for c in sessions["w1"]["commits"]], ["fix(export): round per line"])
        self.assertEqual(sessions["w2"]["commits"], [])

    def test_only_the_owners_exact_address_counts_and_stashes_are_no_commits(self) -> None:
        self.a_day_of_work()
        self.commit("feat(export): by someone with a longer address", at(10, 31), email="malex@example.invalid")
        (self.repo / "draft.txt").write_text("draft\n", encoding="utf-8")
        self.git("add", "draft.txt")
        self.git("stash", "-q", when=at(10, 33))

        [session] = self.collect()["sessions"]

        self.assertEqual([c["subject"] for c in session["commits"]], ["fix(export): round per line"])


class OneStretchOfWorkTest(Fixture):
    """The same minutes never land in two sessions."""

    def prompts(self, name: str, cwd: Path, *minutes_utc: tuple[int, int]) -> None:
        self.transcript(
            name,
            cwd,
            [
                {"type": "user", "timestamp": f"2026-03-14T{h:02d}:{m:02d}:00Z", "message": {"content": "Go on"}}
                for h, m in minutes_utc
            ],
        )

    def test_a_workspace_closed_and_opened_again_on_its_folder_is_one_session(self) -> None:
        """Covers: B85"""
        self.watermark(at(9))
        self.cache(
            {
                "w1": [{"repo": "invoices", "label": "invoices", "folder": str(self.repo), "since": at(8).isoformat()}],
                "w2": [
                    {"repo": "invoices", "label": "invoices", "folder": str(self.repo), "since": at(12).isoformat()}
                ],
            }
        )
        self.events("w1", (at(10), "focus", None), (at(10, 5), "agent_working", "p1"))
        self.events("w1", (at(10, 50), "agent_stopped", "p1"), (at(11, 30), "workspace_closed", None))
        self.events("w2", (at(12), "focus", None), (at(12, 5), "agent_working", "p2"))
        self.events("w2", (at(14), "agent_stopped", "p2"))
        # 11:05Z to 12:55Z is 12:05 to 13:55 here, while only w2 is open.
        self.prompts("s1", self.repo, *[(11 + (m // 60), m % 60) for m in range(5, 120, 10)])

        [session] = self.collect()["sessions"]

        spans = [(b["start"], b["end"]) for b in session["blocks"]]
        self.assertEqual(
            spans, [(at(10).isoformat(), at(11).isoformat()), (at(12).isoformat(), at(14, 10).isoformat())]
        )

    def test_a_transcript_goes_to_the_workspace_whose_pane_sat_in_its_folder(self) -> None:
        """Covers: B85"""
        self.watermark(at(9))
        elsewhere = self.home / "code" / "acme" / "reports"
        elsewhere.mkdir(parents=True)
        self.cache(
            {
                "w1": [{"repo": None, "label": "scratch", "folder": None, "since": at(8).isoformat()}],
                "w2": [{"repo": "invoices", "label": "invoices", "folder": str(self.repo), "since": at(8).isoformat()}],
            }
        )
        self.events("w1", (at(10), "focus", None), (at(10, 5), "agent_working", "p1"), cwd=self.repo)
        self.events("w1", (at(11), "agent_stopped", "p1"), cwd=self.repo)
        self.events("w2", (at(13), "focus", None), (at(13, 5), "agent_working", "p2"), cwd=elsewhere)
        self.events("w2", (at(14), "agent_stopped", "p2"), cwd=elsewhere)
        self.prompts("s1", self.repo / "src", (9, 5), (9, 15), (9, 25), (9, 35), (9, 45), (9, 55))
        self.prompts("s2", elsewhere, (12, 5), (12, 15), (12, 25), (12, 35), (12, 45), (12, 55))

        found = self.collect()["sessions"]

        self.assertEqual(sorted(s["workspace"] for s in found), ["w1", "w2"])
        by_workspace = {s["workspace"]: s for s in found}
        self.assertEqual(by_workspace["w1"]["minutes"]["transcript"], 50)
        self.assertEqual(by_workspace["w2"]["minutes"]["transcript"], 50)
        # A workspace without a folder of its own takes the folder its transcript was written in.
        self.assertEqual((by_workspace["w1"]["folder"], by_workspace["w1"]["sphere"]), (str(self.repo), "acme"))

    def test_a_folderless_workspace_with_panes_in_two_folders_stays_one_session(self) -> None:
        """Covers: B85"""
        self.watermark(at(9))
        reports = self.home / "code" / "acme" / "reports"
        reports.mkdir(parents=True)
        self.cache({"w1": [{"repo": None, "label": "scratch", "folder": None, "since": at(8).isoformat()}]})
        self.events("w1", (at(10), "focus", None), (at(10, 1), "agent_working", "p1"), cwd=self.repo)
        self.events("w1", (at(10, 2), "agent_working", "p2"), cwd=reports)
        self.events("w1", (at(11), "agent_stopped", "p1"), (at(11), "agent_stopped", "p2"), cwd=self.repo)
        self.prompts("s1", self.repo, (9, 5), (9, 15), (9, 25), (9, 35), (9, 45), (9, 55))
        self.prompts("s2", reports, (9, 6), (9, 16), (9, 26), (9, 36), (9, 46), (9, 56))

        [session] = self.collect()["sessions"]

        self.assertEqual(session["minutes"]["transcript"], 51)

    def test_a_transcript_goes_to_the_use_of_a_reused_workspace_id_it_was_written_in(self) -> None:
        """Covers: B85"""
        self.watermark(at(9))
        reports = self.home / "code" / "acme" / "reports"
        reports.mkdir(parents=True)
        self.cache(
            {
                "w1": [
                    {"repo": "invoices", "label": "invoices", "folder": str(self.repo), "since": at(8).isoformat()},
                    {"repo": "reports", "label": "reports", "folder": str(reports), "since": at(12).isoformat()},
                ]
            }
        )
        self.events("w1", (at(10), "focus", None), (at(10, 5), "agent_working", "p1"), cwd=self.repo)
        self.events("w1", (at(10, 50), "agent_stopped", "p1"), (at(11), "workspace_closed", None), cwd=self.repo)
        self.events("w1", (at(13), "focus", None), (at(13, 5), "agent_working", "p2"), cwd=reports)
        self.events("w1", (at(14), "agent_stopped", "p2"), cwd=reports)
        self.prompts("s1", reports, (12, 5), (12, 15), (12, 25), (12, 35), (12, 45), (12, 55))

        found = {s["folder"]: s for s in self.collect()["sessions"]}

        self.assertEqual(found[str(reports)]["minutes"]["transcript"], 50)
        self.assertEqual(found[str(self.repo)]["minutes"]["transcript"], 0)

    def test_a_pane_that_wanders_into_another_workspaces_folder_does_not_take_its_transcript(self) -> None:
        """Covers: B85"""
        self.watermark(at(9))
        main_clone = self.home / "code" / "acme" / "invoices-main"
        main_clone.mkdir(parents=True)
        self.cache(
            {
                "w1": [{"repo": "invoices", "label": "feature", "folder": str(self.repo), "since": at(8).isoformat()}],
                "w2": [{"repo": "invoices", "label": "main", "folder": str(main_clone), "since": at(9).isoformat()}],
            }
        )
        self.events("w1", (at(10), "focus", None), (at(10, 5), "agent_working", "p1"), cwd=self.repo)
        self.events("w1", (at(11), "agent_stopped", "p1"), cwd=self.repo)
        self.events("w2", (at(10, 30), "focus", None), (at(10, 31), "agent_working", "p2"), cwd=self.repo)
        self.events("w2", (at(10, 33), "agent_stopped", "p2"), cwd=self.repo)
        self.prompts("s1", self.repo, (9, 5), (9, 15), (9, 25), (9, 35), (9, 45), (9, 55))

        found = {s["workspace"]: s for s in self.collect()["sessions"]}

        self.assertEqual(found["w1"]["minutes"]["transcript"], 50)
        self.assertNotIn("w2", [w for w, s in found.items() if s["minutes"]["transcript"]])

    def test_a_transcript_stays_with_the_session_of_its_folder_when_a_twin_workspace_slept(self) -> None:
        """Covers: B85"""
        self.watermark(at(9))
        yesterday = at(8) - datetime.timedelta(days=1)
        self.cache(
            {
                "w1": [
                    {"repo": "invoices", "label": "invoices", "folder": str(self.repo), "since": yesterday.isoformat()}
                ],
                "w2": [
                    {
                        "repo": "invoices",
                        "label": "invoices",
                        "folder": str(self.repo),
                        "since": (yesterday + datetime.timedelta(hours=7)).isoformat(),
                    }
                ],
            }
        )
        # w2 was used yesterday and left open; today only w1 is at work.
        self.events("w2", (yesterday + datetime.timedelta(hours=8), "focus", None))
        self.events("w1", (at(10), "focus", None), (at(10, 5), "agent_working", "p1"), (at(11), "agent_stopped", "p1"))
        self.prompts("s1", self.repo, (9, 5), (9, 15), (9, 25), (9, 35), (9, 45), (9, 55))

        [session] = self.collect()["sessions"]

        self.assertEqual(session["minutes"]["transcript"], 50)

    def test_stamps_just_before_the_cut_keep_the_agent_counting_after_it(self) -> None:
        """Covers: B84"""
        # The last worklog ended at 10:00. The agent wrote at 09:58, then ran a 25-minute command.
        self.watermark(at(10))
        self.cache(
            {"w1": [{"repo": "invoices", "label": "invoices", "folder": str(self.repo), "since": at(8).isoformat()}]}
        )
        self.events("w1", (at(9), "agent_working", "p1"), (at(10, 40), "agent_stopped", "p1"))
        self.prompts("s1", self.repo, (8, 0), (8, 10), (8, 20), (8, 30), (8, 40), (8, 50), (8, 58), (9, 23), (9, 33))

        [session] = self.collect()["sessions"]

        self.assertEqual(session["minutes"]["agent"], 40)


class AgentStateTest(Fixture):
    def setUp(self) -> None:
        super().setUp()
        self.watermark(at(9))
        self.cache(
            {"w1": [{"repo": "invoices", "label": "invoices", "folder": str(self.repo), "since": at(8).isoformat()}]}
        )

    def test_a_closed_workspace_has_no_working_agent(self) -> None:
        self.events("w1", (at(10), "agent_working", "p1"), (at(10, 30), "workspace_closed", None))

        [session] = self.collect()["sessions"]

        self.assertEqual(session["state"]["agent"], "idle")

    def test_an_agent_herdr_never_stopped_is_not_working_at_the_end(self) -> None:
        self.events("w1", (at(10), "agent_working", "p1"), (at(14, 30), "agent_working", "p1"))

        [session] = self.collect()["sessions"]

        self.assertEqual(session["state"]["agent"], "idle")

    def test_an_agent_blocked_at_the_end_is_blocked(self) -> None:
        self.events("w1", (at(17, 50), "agent_working", "p1"), (at(17, 57), "agent_blocked", "p1"))

        [session] = self.collect()["sessions"]

        self.assertEqual(session["state"]["agent"], "blocked")

    def test_an_agent_blocked_for_hours_is_still_blocked(self) -> None:
        self.events("w1", (at(10), "agent_working", "p1"), (at(10, 30), "agent_blocked", "p1"))

        [session] = self.collect()["sessions"]

        self.assertEqual(session["state"]["agent"], "blocked")

    def test_an_agent_blocked_then_closed_is_idle(self) -> None:
        self.events(
            "w1",
            (at(10), "agent_working", "p1"),
            (at(10, 30), "agent_blocked", "p1"),
            (at(11), "workspace_closed", None),
        )

        [session] = self.collect()["sessions"]

        self.assertEqual(session["state"]["agent"], "idle")

    def test_an_agent_blocked_then_answered_and_stopped_is_idle(self) -> None:
        self.events(
            "w1",
            (at(10), "agent_working", "p1"),
            (at(10, 30), "agent_blocked", "p1"),
            (at(10, 40), "agent_working", "p1"),
            (at(10, 50), "agent_stopped", "p1"),
        )

        [session] = self.collect()["sessions"]

        self.assertEqual(session["state"]["agent"], "idle")

    def test_events_older_than_three_days_before_the_period_are_not_read(self) -> None:
        """Covers: B87"""
        weeks_ago = at(10) - datetime.timedelta(days=8)
        self.events("w1", (at(10), "agent_working", "p1"), (at(10, 20), "agent_stopped", "p1"))
        without = self.collect()["sessions"][0]
        self.events("w1", (weeks_ago, "agent_working", "p9"), (weeks_ago, "agent_blocked", "p9"))

        [session] = self.collect()["sessions"]

        self.assertEqual(session["minutes"], without["minutes"])
        self.assertEqual(session["state"]["agent"], "idle")

    def test_focus_set_before_the_reach_still_counts_inside_the_period(self) -> None:
        """Covers: B87"""
        # The owner left w1 in focus over a long weekend; only its agent sends events now.
        self.events("w1", (at(10) - datetime.timedelta(days=4), "focus", None))
        self.events("w1", (at(10), "agent_working", "p1"), (at(10, 20), "agent_stopped", "p1"))

        [session] = self.collect()["sessions"]

        self.assertEqual(session["minutes"]["focus"], 20)
        self.assertEqual(session["blocks"][0]["minutes_present"], 20)

    def test_an_agent_working_at_the_end_is_working(self) -> None:
        self.events("w1", (at(17, 57), "agent_working", "p1"))

        [session] = self.collect()["sessions"]

        self.assertEqual(session["state"]["agent"], "working")


class TextTest(unittest.TestCase):
    def test_a_command_keeps_its_arguments_after_a_newline(self) -> None:
        text = (
            "<command-message>m2b:search</command-message>\n<command-name>/m2b:search</command-name>\n"
            "<command-args>old maps</command-args>"
        )
        self.assertEqual(prompt_text(text), "m2b:search old maps")

    def test_credentials_in_env_and_json_form_are_redacted(self) -> None:
        self.assertEqual(redact("DB_PASSWORD=hunter22"), "DB_PASSWORD=[removed]")
        self.assertEqual(redact("client_secret: s3cr3tvalue"), "client_secret: [removed]")
        self.assertEqual(redact('{"password": "hunter22"}'), '{"password": [removed]')
        self.assertEqual(redact("MY_TOKEN=abc123"), "MY_TOKEN=[removed]")

    def test_the_last_answer_keeps_up_to_500_characters(self) -> None:
        self.assertEqual(len(prompt_text("word " * 200, limit=500) or ""), 500)


class FactsShapeTest(Fixture):
    def test_every_time_is_written_in_the_period_ends_offset(self) -> None:
        self.watermark(at(9))
        self.transcript(
            "s2",
            self.home / "scratch",
            [
                {"type": "user", "timestamp": "2026-03-14T09:01:00Z", "message": {"content": "Sketch a plan"}},
                {"type": "user", "timestamp": "2026-03-14T09:10:00Z", "message": {"content": "Shorter please"}},
            ],
        )

        [session] = self.collect()["sessions"]

        self.assertEqual(session["blocks"][0]["start"], at(10, 1).isoformat())

    def test_the_default_sphere_is_named(self) -> None:
        self.assertEqual(
            self.collect()["spheres"],
            [
                {"id": "acme", "label": "Acme Ltd", "billable": True, "default": False},
                {"id": "private", "label": None, "billable": False, "default": True},
            ],
        )

    def test_nested_transcript_folders_outside_a_workspace_do_not_depend_on_file_order(self) -> None:
        self.watermark(at(9))
        records = [
            {"type": "user", "timestamp": "2026-03-14T09:01:00Z", "message": {"content": "One"}},
            {"type": "user", "timestamp": "2026-03-14T09:10:00Z", "message": {"content": "Two"}},
        ]
        self.transcript("a-outer", self.home / "scratch", records)
        self.transcript("b-inner", self.home / "scratch" / "inner", records)

        keys = sorted(s["key"] for s in self.collect()["sessions"])

        self.assertEqual(keys, [f"folder:{self.home / 'scratch'}", f"folder:{self.home / 'scratch' / 'inner'}"])


class EvictedFilesTest(Fixture):
    def test_a_capture_that_is_not_downloaded_is_counted_not_read(self) -> None:
        from m2b_worklog.sources import inbox

        self.watermark(at(9))
        self.capture("20260314-100000-mac-a1b2.md", at(10), "mac")
        self.capture("20260314-110000-mac-c3d4.md", at(11), "mac")
        evicted = self.store / "inbox" / "20260314-110000-mac-c3d4.md"
        original = inbox.is_evicted
        inbox.is_evicted = lambda path: path == evicted  # type: ignore[assignment]
        try:
            found = self.collect()
        finally:
            inbox.is_evicted = original  # type: ignore[assignment]

        self.assertEqual([c["name"] for c in found["captures"]], ["20260314-100000-mac-a1b2.md"])
        self.assertEqual(found["sources"]["inbox"]["state"], "read")
        self.assertIn("1 not downloaded", found["sources"]["inbox"]["detail"])

    def test_a_watermark_that_is_not_downloaded_is_an_error_naming_the_fetch(self) -> None:
        self.watermark(at(9))
        original = facts.is_evicted
        facts.is_evicted = lambda path: True  # type: ignore[assignment]
        try:
            with self.assertRaises(FactsError) as raised:
                facts.collect(Inputs(self.store, self.recordings, self.projects, self.home, PROFILE, NOW))
        finally:
            facts.is_evicted = original  # type: ignore[assignment]

        self.assertIn("m2b store fetch", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
