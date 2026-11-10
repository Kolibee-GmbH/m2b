"""Periods from a fixed set of events and an injected "now"."""

from __future__ import annotations

import datetime
import tempfile
import unittest
from pathlib import Path

from m2b_worklog import periods
from m2b_worklog.periods import AGENT, BLOCKED, FOCUS, HUMAN, RULES, Block, Event, Period

ZONE = datetime.timezone(datetime.timedelta(hours=1))
DAY = datetime.datetime(2026, 3, 14, 9, 0, tzinfo=ZONE)


def at(minutes: float) -> datetime.datetime:
    return DAY + datetime.timedelta(minutes=minutes)


def event(minutes: float, kind: str, workspace: str = "w1", pane: str | None = "p1") -> Event:
    return Event(at(minutes), kind, workspace, pane)


def of_kind(found: list[Period], kind: str) -> list[tuple[float, float, str]]:
    return [
        ((p.start - DAY).total_seconds() / 60, (p.end - DAY).total_seconds() / 60, p.workspace)
        for p in found
        if p.kind == kind
    ]


class RulesTest(unittest.TestCase):
    def test_the_numbers_live_in_one_table(self) -> None:
        self.assertEqual(
            (RULES.agent_silence, RULES.piece_cap, RULES.block_gap, RULES.tick_interval, RULES.recording_gap),
            (
                datetime.timedelta(minutes=30),
                datetime.timedelta(minutes=10),
                datetime.timedelta(minutes=15),
                datetime.timedelta(minutes=5),
                datetime.timedelta(minutes=10),
            ),
        )


class AgentPeriodsTest(unittest.TestCase):
    def test_opens_at_the_first_start_and_closes_at_the_first_stop_of_the_same_pane(self) -> None:
        found = periods.derive_periods(
            [
                event(0, "agent_working"),
                event(3, "agent_working"),
                event(5, "agent_working", pane="p2"),
                event(20, "agent_stopped", pane="p2"),
                event(30, "agent_stopped"),
                event(40, "agent_stopped"),
            ],
            now=at(120),
        )

        self.assertEqual(of_kind(found, AGENT), [(0, 30, "w1"), (5, 20, "w1")])

    def test_blocked_interrupts_an_agent_period_and_working_ends_the_blocked_one(self) -> None:
        found = periods.derive_periods(
            [
                event(0, "agent_working"),
                event(10, "agent_blocked"),
                event(14, "agent_working"),
                event(30, "agent_stopped"),
            ],
            now=at(120),
        )

        self.assertEqual(of_kind(found, AGENT), [(0, 10, "w1"), (14, 30, "w1")])
        self.assertEqual(of_kind(found, BLOCKED), [(10, 14, "w1")])

    def test_an_open_period_runs_to_now_while_its_last_sign_of_life_is_recent(self) -> None:
        found = periods.derive_periods([event(0, "agent_working"), event(20, "agent_working")], now=at(44))

        self.assertEqual(of_kind(found, AGENT), [(0, 44, "w1")])

    def test_an_agent_counts_at_most_thirty_minutes_past_its_last_sign_of_life(self) -> None:
        """Covers: B84"""
        # Working at 17:50, the lid closed, the stop arrives at 08:00 after waking up.
        stopped_after_sleep = periods.derive_periods(
            [event(0, "agent_working"), event(850, "agent_stopped")], now=at(900)
        )
        open_at_the_cut = periods.derive_periods([event(0, "agent_working")], now=at(120))

        self.assertEqual(of_kind(stopped_after_sleep, AGENT), [(0, 30, "w1")])
        self.assertEqual(of_kind(open_at_the_cut, AGENT), [(0, 30, "w1")])

    def test_transcript_stamps_keep_an_agent_counting_up_to_the_cut(self) -> None:
        """Covers: B84"""
        stamps = [at(minutes) for minutes in range(5, 60, 10)]

        found = periods.derive_periods([event(0, "agent_working")], now=at(60), evidence={"w1": stamps})

        self.assertEqual(of_kind(found, AGENT), [(0, 60, "w1")])

    def test_a_silent_stretch_inside_a_period_counts_only_its_first_thirty_minutes(self) -> None:
        """Covers: B84"""
        stamps = [at(10), at(100)]

        found = periods.derive_periods(
            [event(0, "agent_working"), event(110, "agent_stopped")], now=at(200), evidence={"w1": stamps}
        )

        self.assertEqual(of_kind(found, AGENT), [(0, 40, "w1"), (100, 110, "w1")])

    def test_a_closed_workspace_stops_its_panes(self) -> None:
        found = periods.derive_periods(
            [event(0, "agent_working"), event(4, "agent_working", "w2", "p9"), event(6, "workspace_closed", pane=None)],
            now=at(8),
        )

        self.assertEqual(of_kind(found, AGENT), [(0, 6, "w1"), (4, 8, "w2")])


class FocusPeriodsTest(unittest.TestCase):
    def test_focus_is_split_at_every_event_of_its_workspace_and_each_piece_is_capped(self) -> None:
        found = periods.derive_periods(
            [
                event(0, "focus", pane=None),
                event(4, "agent_working", "w2", "p9"),
                event(30, "focus", "w2", None),
                event(33, "agent_stopped", "w2", "p9"),
            ],
            now=at(60),
        )

        self.assertEqual(of_kind(found, FOCUS), [(0, 10, "w1"), (30, 33, "w2"), (33, 43, "w2")])

    def test_events_of_another_workspace_do_not_keep_focus_alive(self) -> None:
        """Covers: B84"""
        # Focus on w1 at 18:00, then only an agent in w2 flipping its state every four minutes until 23:00.
        others = [
            event(minutes, "agent_working" if minutes % 8 == 0 else "agent_stopped", "w2", "p9")
            for minutes in range(4, 300, 4)
        ]

        found = periods.derive_periods([event(0, "focus", pane=None), *others], now=at(300))

        self.assertEqual(of_kind(found, FOCUS), [(0, 10, "w1")])
        self.assertEqual(of_kind(found, HUMAN), [(0, 10, "w1")])

    def test_human_is_focus_while_no_agent_in_that_workspace_works(self) -> None:
        found = periods.derive_periods(
            [
                event(0, "focus", pane=None),
                event(2, "agent_working"),
                event(6, "agent_working", "w2", "p9"),
                event(8, "agent_stopped"),
                event(12, "focus", pane=None),
            ],
            now=at(15),
        )

        self.assertEqual(of_kind(found, HUMAN), [(0, 2, "w1"), (8, 12, "w1"), (12, 15, "w1")])
        self.assertEqual(of_kind(found, FOCUS), [(0, 2, "w1"), (2, 8, "w1"), (8, 12, "w1"), (12, 15, "w1")])

    def test_an_agent_left_working_by_a_herdr_that_quit_does_not_hide_human_time_later(self) -> None:
        found = periods.derive_periods(
            [event(0, "focus", pane=None), event(1, "agent_working"), event(120, "focus", pane=None)], now=at(125)
        )

        self.assertEqual(of_kind(found, AGENT), [(1, 31, "w1")])
        self.assertEqual(of_kind(found, HUMAN), [(0, 1, "w1"), (120, 125, "w1")])

    def test_a_blocked_agent_counts_as_not_working(self) -> None:
        found = periods.derive_periods(
            [event(0, "focus", pane=None), event(1, "agent_working"), event(3, "agent_blocked")], now=at(5)
        )

        self.assertEqual(of_kind(found, HUMAN), [(0, 1, "w1"), (3, 5, "w1")])

    def test_closing_the_focused_workspace_ends_its_focus(self) -> None:
        found = periods.derive_periods(
            [event(0, "focus", pane=None), event(5, "workspace_closed", pane=None)], now=at(9)
        )

        self.assertEqual(of_kind(found, FOCUS), [(0, 5, "w1")])


class BlocksTest(unittest.TestCase):
    def test_blocks_are_separated_by_gaps_of_more_than_fifteen_minutes(self) -> None:
        found = [
            Period(AGENT, "w1", "p1", at(0), at(10)),
            Period(FOCUS, "w2", None, at(25), at(30)),
            Period(AGENT, "w1", "p1", at(46), at(50)),
            Period(HUMAN, "w1", None, at(48), at(48)),
        ]

        self.assertEqual(periods.activity_blocks(found), [Block(at(0), at(30)), Block(at(46), at(50))])


class LoadTest(unittest.TestCase):
    def test_reads_every_workspace_file_in_time_order_and_skips_broken_lines(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "w1.jsonl").write_text(
                '{"time": "2026-03-14T09:05:00+01:00", "kind": "agent_working", "workspace": "w1", "pane": "p1"}\n'
                '{"time": "2026-03-14T09:0\n'
                '{"time": "2026-03-14T09:06:00", "kind": "focus", "workspace": "w1", "pane": null}\n'
                '{"time": "2026-03-14T09:07:00+01:00", "kind": "typing", "workspace": "w1", "pane": null}\n',
                encoding="utf-8",
            )
            Path(folder, "w2.jsonl").write_text(
                '{"time": "2026-03-14T09:01:00+01:00", "kind": "focus", "workspace": "w2", "pane": null}\n',
                encoding="utf-8",
            )
            Path(folder, "workspaces.json").write_text("{}", encoding="utf-8")

            events = periods.load_events(Path(folder))

        self.assertEqual([(e.workspace, e.kind) for e in events], [("w2", "focus"), ("w1", "agent_working")])


def spans(found: list[Block]) -> list[tuple[float, float]]:
    return [((b.start - DAY).total_seconds() / 60, (b.end - DAY).total_seconds() / 60) for b in found]


def ticks(first: float, last: float) -> list[datetime.datetime]:
    return [at(minute) for minute in range(int(first), int(last) + 1, 5)]


class NotRecordedTest(unittest.TestCase):
    """Stretches without a sign of life from the recorder: herdr was not running, the machine slept."""

    def test_a_silence_of_more_than_two_ticks_is_named_from_the_tick_that_did_not_come(self) -> None:
        """Covers: B89"""
        found = periods.not_recorded([*ticks(0, 10), *ticks(200, 210)], at(0), at(0), at(210))

        self.assertEqual(spans(found), [(15, 200)])

    def test_exactly_ten_minutes_of_silence_names_nothing_a_second_more_does(self) -> None:
        """Covers: B89"""
        self.assertEqual(periods.not_recorded([at(0), at(10)], at(0), at(0), at(10)), [])
        self.assertEqual(
            spans(periods.not_recorded([at(0), at(10 + 1 / 60)], at(0), at(0), at(11))), [(5, 10 + 1 / 60)]
        )

    def test_one_late_tick_names_nothing(self) -> None:
        found = periods.not_recorded([at(0), at(5), at(14), at(20)], at(0), at(0), at(25))

        self.assertEqual(found, [])

    def test_herdrs_start_and_an_event_are_signs_of_life_too(self) -> None:
        """Covers: B89"""
        found = periods.not_recorded([at(0), at(8), at(16), at(24), at(30)], at(0), at(0), at(30))

        self.assertEqual(found, [])

    def test_the_stretch_is_clipped_to_the_period_and_runs_to_its_end(self) -> None:
        """Covers: B89"""
        found = periods.not_recorded([at(-120), at(30)], at(-600), at(0), at(100))

        self.assertEqual(spans(found), [(0, 30), (35, 100)])

    def test_without_a_tick_ever_nothing_is_named(self) -> None:
        """Covers: B89"""
        self.assertEqual(periods.not_recorded([at(-600), at(0), at(5)], None, at(0), at(100)), [])

    def test_nothing_is_named_before_the_first_tick(self) -> None:
        """Covers: B89"""
        found = periods.not_recorded([at(-600), at(0), *ticks(50, 60)], at(50), at(0), at(100))

        self.assertEqual(spans(found), [(65, 100)])

    def test_ticks_that_began_before_what_was_read_name_a_silence_from_the_periods_start(self) -> None:
        """Covers: B89"""
        found = periods.not_recorded(ticks(300, 330), at(-6000), at(0), at(330))

        self.assertEqual(spans(found), [(0, 300)])

    def test_less_than_a_minute_is_not_named(self) -> None:
        found = periods.not_recorded([at(-20)], at(-100), at(0), at(0.5))

        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
