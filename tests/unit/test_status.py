"""``m2b status``: inbox, due or running, the run record and the backends, for the status line under the prompt."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any
from unittest import mock

import test_runner
from m2b import cli, handed_in, proposal_answers, proposals
from m2b.curate import machine_state
from m2b.run_record import RUN_RECORD
from m2b.store.base import StoreError
from m2b.store.guard import DatalessGuard


def _iso(moment: datetime.datetime) -> str:
    return moment.isoformat(timespec="seconds")


class StatusTest(test_runner.RunnerTest):
    def status(self) -> dict[str, Any]:
        result: dict[str, Any] = self.run_json("status")
        return result

    def record(self, **fields: Any) -> None:
        self.write(RUN_RECORD, json.dumps({"machine_id": "sb-test-m1", **fields}))

    def test_it_counts_what_sessions_handed_in_and_has_no_line_while_nothing_waits(self) -> None:
        """Covers: B240"""
        self.curating()
        self.assertEqual(self.run_json("status")["handed_in"], {"count": 0, "evicted": 0})
        self.assertNotIn("handed in", self.run_command("status")[1])

        self.write(f"{handed_in.FOLDER}/s1.a1b2c3d4e5f6.json", "{}")
        self.write(f"{handed_in.FOLDER}/s2.b2c3d4e5f6a1.json", "words no check has seen")

        self.assertEqual(self.run_json("status")["handed_in"], {"count": 2, "evicted": 0})
        out = self.run_command("status")[1]
        self.assertIn("handed in: 2 waiting for the next curation run\n", out)
        self.assertNotIn("words no check has seen", out)

    def test_it_says_how_many_lessons_every_session_starts_with_and_which_are_kept_at_their_source(self) -> None:
        """Covers: B258"""
        self.curating()
        lesson = (
            "---\nkind: knowledge\ntarget: every project\nkept: 2026-11-20\n{more}---\n# A lesson\n\nSay it once.\n"
        )
        self.write("memory/lessons/once.md", lesson.format(more=""))
        self.write("memory/lessons/checks.md", lesson.format(more="kept_at: ~/.claude/CLAUDE.md\n"))

        self.assertEqual(
            self.run_json("status")["lessons"],
            {"in_every_session": 1, "kept_at_source": [{"name": "checks.md", "source": "~/.claude/CLAUDE.md"}]},
        )
        self.assertIn(
            "lessons: 1 in every session; checks.md is kept at its source, ~/.claude/CLAUDE.md\n",
            self.run_command("status")[1],
        )

    def test_a_folder_of_handed_in_proposals_that_cannot_be_listed_is_said_and_the_other_parts_answer(self) -> None:
        """Covers: B240"""
        self.curating()
        self.capture()
        failure = StoreError("state/core/handed-in cannot be listed")

        with mock.patch("m2b.handed_in.waiting", side_effect=failure):
            answer = self.run_json("status")
            out = self.run_command("status")[1]

        self.assertEqual(answer["handed_in"], {"error": "state/core/handed-in cannot be listed"})
        self.assertEqual(answer["inbox"]["count"], 1)
        self.assertIn("handed in: could not look: state/core/handed-in cannot be listed\n", out)
        self.assertIn("inbox: 1\n", out)

    def test_a_handed_in_file_that_is_not_downloaded_is_counted_and_named_as_such(self) -> None:
        """Covers: B240"""
        self.curating()
        self.write(f"{handed_in.FOLDER}/s1.a1b2c3d4e5f6.json", "{}")
        self.write(f"{handed_in.FOLDER}/s2.b2c3d4e5f6a1.json", "{}")

        evicted = mock.patch.object(
            DatalessGuard, "is_evicted", side_effect=lambda path: Path(path).name == "s2.b2c3d4e5f6a1.json"
        )
        with evicted:
            answer = self.run_json("status")["handed_in"]
            out = self.run_command("status")[1]

        self.assertEqual(answer, {"count": 2, "evicted": 1})
        self.assertIn("handed in: 2 waiting for the next curation run (1 not downloaded)\n", out)

    def test_on_the_curating_machine_it_reports_inbox_due_run_and_backends(self) -> None:
        self.curating()
        self.capture()
        self.capture("20261107T070100Z-cli-c3d4.md")
        finished = datetime.datetime.now().astimezone() - datetime.timedelta(hours=2)
        self.record(state="succeeded", started_at=_iso(finished), finished_at=_iso(finished))

        status = self.status()

        self.assertEqual(status["machine_id"], "sb-test-m1")
        self.assertTrue(status["this_machine_curates"])
        self.assertEqual(status["inbox"], {"count": 2, "evicted": 0})
        self.assertEqual(status["due"]["due"], True)
        self.assertEqual(status["run"]["state"], "succeeded")
        self.assertEqual(status["run"]["finished_at"], _iso(finished))
        self.assertEqual(status["backends"]["store"]["state"], "reachable")
        self.assertEqual(status["backends"]["tasks"]["state"], "reachable")
        self.assertEqual(status["backends"]["calendar"]["state"], "not configured")
        self.assertEqual(status["addons"], {"worklog": False})

    def test_a_run_holding_the_lock_is_running(self) -> None:
        self.curating()
        start = datetime.datetime.now().astimezone() - datetime.timedelta(minutes=2)
        self.record(state="running", started_at=_iso(start), deadline_at=_iso(start + datetime.timedelta(minutes=30)))
        lock = machine_state.RunLock(self.machine)
        self.assertTrue(lock.acquire())
        self.addCleanup(lock.release)

        status = self.status()

        self.assertEqual(status["run"]["state"], "running")
        self.assertFalse(status["due"]["due"])

    def test_a_running_record_without_its_lock_on_this_machine_is_an_interrupted_run(self) -> None:
        self.curating()
        start = datetime.datetime.now().astimezone() - datetime.timedelta(minutes=2)
        self.record(state="running", started_at=_iso(start), deadline_at=_iso(start + datetime.timedelta(minutes=30)))

        self.assertEqual(self.status()["run"]["state"], "interrupted")

    def test_another_machines_running_record_counts_as_running_until_its_deadline(self) -> None:
        self.curating()
        start = datetime.datetime.now().astimezone() - datetime.timedelta(minutes=2)
        self.record(
            machine_id="sb-test-m2",
            state="running",
            started_at=_iso(start),
            deadline_at=_iso(start + datetime.timedelta(minutes=30)),
        )
        self.set_curating("sb-test-m2")

        status = self.status()
        self.assertEqual(status["run"]["state"], "running")
        self.assertFalse(status["this_machine_curates"])
        self.assertIsNone(status["due"])

        late = start - datetime.timedelta(hours=2)
        self.record(
            machine_id="sb-test-m2",
            state="running",
            started_at=_iso(late),
            deadline_at=_iso(late + datetime.timedelta(minutes=30)),
        )
        self.assertEqual(self.status()["run"]["state"], "interrupted")

    def test_a_record_that_cannot_be_read_says_so_instead_of_nothing(self) -> None:
        self.curating()
        self.write(RUN_RECORD, "{broken")

        status = self.status()

        self.assertIn("cannot be read", status["run"]["error"])

    def test_no_run_yet_is_state_none(self) -> None:
        self.curating()
        self.assertEqual(self.status()["run"], {"state": "none"})

    def test_an_unreachable_backend_says_so(self) -> None:
        self.curating(tasks={"backend": "apple-reminders", "list": "sb-test-missing"})

        tasks = self.status()["backends"]["tasks"]

        self.assertEqual(tasks["state"], "not reachable")
        self.assertIn("sb-test-missing", tasks["detail"])

    def test_the_backend_probes_are_cached_for_five_minutes(self) -> None:
        self.curating()
        with mock.patch("m2b.commands.status.probe_backends", wraps=_counting()) as probes:
            self.status()
            self.status()
            self.assertEqual(probes.call_count, 1)
            cache = self.machine.state_dir / "status-cache.json"
            raw = json.loads(cache.read_text(encoding="utf-8"))
            old = datetime.datetime.fromisoformat(raw["checked_at"]) - datetime.timedelta(minutes=6)
            raw["checked_at"] = old.isoformat()
            cache.write_text(json.dumps(raw), encoding="utf-8")
            self.status()
            self.assertEqual(probes.call_count, 2)

    def test_a_later_attempt_that_was_not_due_is_shown_beside_the_last_run(self) -> None:
        self.curating()
        now = datetime.datetime.now().astimezone()
        finished = now - datetime.timedelta(hours=2)
        self.record(state="succeeded", started_at=_iso(finished), finished_at=_iso(finished))
        tried = now - datetime.timedelta(hours=1)
        machine_state.record_attempt(self.machine, machine_state.NOT_DUE, "the last successful run was at ...", tried)

        status = self.status()
        _, out, _ = self.run_command("status")

        self.assertEqual(
            status["last_attempt"],
            {"kind": "not_due", "at": _iso(tried), "message": "the last successful run was at ..."},
        )
        self.assertIn(f"last attempt: not due at {_iso(tried)}", out)

    def test_a_paused_machine_says_so_beside_what_is_due(self) -> None:
        """Covers: B161"""
        self.curating(curation={"paused": True})
        self.capture()

        status = self.status()
        _, out, _ = self.run_command("status")

        self.assertTrue(status["paused"])
        self.assertEqual(status["due"]["due"], True)
        self.assertIn("paused: no curation run starts by itself on this machine", out)

    def test_a_scheduled_attempt_on_a_paused_machine_shows_as_the_last_attempt(self) -> None:
        """Covers: B161"""
        self.curating(curation={"paused": True})

        self.run_command("curate")
        _, out, _ = self.run_command("status")

        self.assertIn("last attempt: paused at ", out)

    def test_a_machine_that_is_not_paused_has_no_line_about_it(self) -> None:
        self.curating()

        status = self.status()
        _, out, _ = self.run_command("status")

        self.assertFalse(status["paused"])
        self.assertNotIn("paused", out)

    def test_an_attempt_older_than_the_last_run_is_not_shown(self) -> None:
        self.curating()
        now = datetime.datetime.now().astimezone()
        machine_state.record_attempt(self.machine, machine_state.NOT_DUE, "x", now - datetime.timedelta(hours=3))
        finished = now - datetime.timedelta(hours=2)
        self.record(state="succeeded", started_at=_iso(finished), finished_at=_iso(finished))

        self.assertIsNone(self.status()["last_attempt"])

    def test_the_text_form_is_short_lines(self) -> None:
        self.curating()
        self.capture()

        code, out, _ = self.run_command("status")

        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("inbox: 1", out)
        self.assertIn("tasks: reachable", out)
        self.assertIn("add-ons on: none", out)

    def proposed(self, *ended: tuple[str, float], counts: dict[str, proposals.Tally] | None = None) -> None:
        """Proposals in the store, one per state given, settled (or added) so many days ago."""
        now = datetime.datetime.now().astimezone()
        entries = {
            f"{number:012x}": proposals.Entry(
                "person",
                f"Fact {number}.",
                f"the words of fact {number}",
                now.date(),
                state,
                now - datetime.timedelta(days=days),
            )
            for number, (state, days) in enumerate(ended)
        }
        proposals.save(self.store, proposals.Proposals(entries, counts=counts or {}))

    def test_it_shows_the_share_kept_of_what_was_answered_in_the_last_thirty_days(self) -> None:
        """Covers: B133"""
        self.curating(curation={"read_sessions": True})
        self.proposed(
            ("kept", 0),
            ("kept", 29.9),
            ("kept", 30.1),
            ("dropped", 12),
            ("expired", 3),
            ("open", 20),
            counts={"person": proposals.Tally(proposed=9, kept=5, dropped=1, expired=1, not_quoted=2)},
        )

        status = self.status()
        _, out, _ = self.run_command("status")

        nothing = {"proposed": 0, "kept": 0, "dropped": 0, "expired": 0, "not_quoted": 0}
        self.assertEqual(
            status["proposal_answers"],
            {
                "days": 30,
                "kept": 2,
                "dropped": 1,
                "expired": 1,
                "keep_rate": 0.67,
                "counts": {
                    "person": {"proposed": 9, "kept": 5, "dropped": 1, "expired": 1, "not_quoted": 2},
                    "agreement": nothing,
                    "commitment": nothing,
                    "personal": nothing,
                    "lesson": nothing,
                    "project": nothing,
                },
                "ways": {"reading": {"typed": {"waiting": 1, "answered": 0, "kept": 2, "dropped": 1, "expired": 1}}},
            },
        )
        self.assertIn("\nproposals: kept 2 of 3 answered in the last 30 days (67%), 1 expired without an answer\n", out)
        self.assertIn(
            "\nproposals a reading found in typed words: 1 waiting, 2 kept, 1 dropped, 1 expired in the last 30 days\n",
            out,
        )

    def test_it_counts_per_way_and_source_what_waits_and_how_the_thirty_days_ended(self) -> None:
        """Covers: B181"""
        self.curating()
        now = datetime.datetime.now().astimezone()

        def entry(number: int, state: str, days: float, source: str, by: str | None, tool: str | None = None) -> Any:
            since = now - datetime.timedelta(days=days)
            return proposals.Entry(
                "person",
                f"Fact {number}.",
                f"the words of fact {number}",
                now.date(),
                state,
                since,
                None,
                None,
                source,
                tool,
                by,
            )

        entries = {
            "000000000001": entry(1, "open", 1, "tool", "session", "Read"),
            "000000000002": entry(2, "kept", 2, "tool", "session", "Read"),
            "000000000003": entry(3, "dropped", 31, "tool", "session", "Read"),
            "000000000004": entry(4, "open", 1, "agent", "session"),
            "000000000005": entry(5, "expired", 5, "pasted", None),
            "000000000006": entry(6, "open", 1, "worked", None),
        }
        proposals.save(self.store, proposals.Proposals(entries))

        status = self.status()
        _, out, _ = self.run_command("status")

        self.assertEqual(
            status["proposal_answers"]["ways"],
            {
                "reading": {
                    "pasted": {"waiting": 0, "answered": 0, "kept": 0, "dropped": 0, "expired": 1},
                    "worked": {"waiting": 1, "answered": 0, "kept": 0, "dropped": 0, "expired": 0},
                },
                "session": {
                    "agent": {"waiting": 1, "answered": 0, "kept": 0, "dropped": 0, "expired": 0},
                    "tool": {"waiting": 1, "answered": 0, "kept": 1, "dropped": 0, "expired": 0},
                },
            },
        )
        for line in (
            "proposals a reading found in pasted text: 0 waiting, 0 kept, 0 dropped, 1 expired in the last 30 days",
            "proposals a reading found in repositories worked in on two days: 1 waiting, 0 kept, 0 dropped, "
            "0 expired in the last 30 days",
            "proposals sessions handed in from an answer of Claude: 1 waiting, 0 kept, 0 dropped, 0 expired "
            "in the last 30 days",
            "proposals sessions handed in from a tool's result: 1 waiting, 1 kept, 0 dropped, 0 expired "
            "in the last 30 days",
        ):
            self.assertIn(f"\n{line}\n", out)

    def test_a_proposal_the_person_answered_is_not_counted_as_waiting_for_an_answer(self) -> None:
        """Covers: B181"""
        self.curating(curation={"read_sessions": True})
        self.proposed(("open", 1), ("open", 1), ("open", 1))
        proposal_answers.give(self.store, [f"{0:012x}"], proposal_answers.KEEP)
        proposal_answers.give(self.store, [f"{1:012x}"], proposal_answers.DROP)

        status = self.status()
        _, out, _ = self.run_command("status")

        self.assertEqual(
            status["proposal_answers"]["ways"],
            {"reading": {"typed": {"waiting": 1, "answered": 2, "kept": 0, "dropped": 0, "expired": 0}}},
        )
        self.assertIn(
            "\nproposals a reading found in typed words: 1 waiting, 2 answered for the next run, "
            "0 kept, 0 dropped, 0 expired in the last 30 days\n",
            out,
        )

    def test_an_expired_proposal_kept_late_counts_as_answered_as_the_list_of_proposals_counts_it(self) -> None:
        """Covers: B181"""
        self.curating(curation={"read_sessions": True})
        self.proposed(("expired", 40), ("expired", 3), ("expired", 3))
        proposal_answers.give(self.store, [f"{0:012x}"], proposal_answers.KEEP)
        proposal_answers.give(self.store, [f"{1:012x}"], proposal_answers.DROP)

        ways = self.status()["proposal_answers"]["ways"]

        self.assertEqual(
            ways, {"reading": {"typed": {"waiting": 0, "answered": 1, "kept": 0, "dropped": 0, "expired": 2}}}
        )
        self.assertEqual(proposal_answers.waiting(self.store).answered, 1)

    def test_a_machine_that_only_lets_sessions_hand_in_has_the_part_too(self) -> None:
        """Covers: B181"""
        self.set_up(calendar="none", sessions={"propose": True})

        answers = self.status()["proposal_answers"]

        self.assertEqual((answers["kept"], answers["ways"]), (0, {}))

    def test_without_an_answer_in_the_thirty_days_it_shows_no_rate_instead_of_none_kept(self) -> None:
        """Covers: B133"""
        self.curating()
        self.proposed(("kept", 31), ("open", 2))

        status = self.status()
        _, out, _ = self.run_command("status")

        answers = status["proposal_answers"]
        self.assertEqual((answers["kept"], answers["dropped"], answers["expired"]), (0, 0, 0))
        self.assertIsNone(answers["keep_rate"])
        self.assertIn("\nproposals: no answer in the last 30 days\n", out)
        self.assertNotIn("%", out)

    def test_proposals_that_only_expired_are_named_and_give_no_rate(self) -> None:
        """Covers: B133"""
        self.curating()
        self.proposed(("expired", 1), ("expired", 2))

        _, out, _ = self.run_command("status")

        self.assertIsNone(self.status()["proposal_answers"]["keep_rate"])
        self.assertIn("\nproposals: no answer in the last 30 days, 2 expired without an answer\n", out)

    def test_a_machine_that_reads_no_sessions_in_a_store_without_proposals_shows_nothing_of_it(self) -> None:
        """Covers: B133"""
        self.curating()

        _, out, _ = self.run_command("status")

        self.assertNotIn("proposal_answers", self.status())
        self.assertNotIn("proposals", out)

    def test_a_store_that_only_holds_counts_of_proposals_long_gone_still_shows_the_part(self) -> None:
        """Covers: B133"""
        self.curating()
        self.proposed(counts={"agreement": proposals.Tally(proposed=2, dropped=2)})

        answers = self.status()["proposal_answers"]

        self.assertEqual(answers["counts"]["agreement"]["dropped"], 2)
        self.assertIsNone(answers["keep_rate"])

    def test_a_machine_that_reads_the_sessions_shows_the_part_before_anything_was_proposed(self) -> None:
        """Covers: B133"""
        self.curating(curation={"read_sessions": True})

        _, out, _ = self.run_command("status")

        self.assertIsNone(self.status()["proposal_answers"]["keep_rate"])
        self.assertIn("\nproposals: no answer in the last 30 days\n", out)

    def test_a_proposals_file_that_cannot_be_used_says_so_instead_of_nothing(self) -> None:
        """Covers: B133"""
        self.curating()
        self.write(proposals.PROPOSALS_FILE, json.dumps({"format": proposals.FORMAT + 1, "proposals": {}}))

        _, out, _ = self.run_command("status")

        self.assertIn(f"format {proposals.FORMAT + 1}", self.status()["proposal_answers"]["error"])
        self.assertIn("\nproposals: could not look: ", out)

    def set_curating(self, machine_id: str) -> None:
        path = self.store_root / "store.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["curating_machine"] = machine_id
        path.write_text(json.dumps(raw), encoding="utf-8")


def _counting() -> Any:
    from m2b.commands import status

    return status.probe_backends


if __name__ == "__main__":
    import unittest

    unittest.main()
