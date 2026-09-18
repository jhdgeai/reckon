#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Where the account stands now -- R5 and R6 of package/RECKON-1.2-SPEC.md.

Synthetic readings only. Nothing here reads the real usage file, pastes or
status-line readings.
"""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import plan_usage  # noqa: E402
import usage_status as us  # noqa: E402

ORG = "00000000-1111-2222-3333-444444444444"
NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)


def desktop(*points):
    """(hours before NOW, five-hour %, seven-day %) -> merged desktop samples."""
    raw = [{"t": int((NOW - timedelta(hours=h)).timestamp() * 1000), "org": ORG,
            "u": {"fh": fh, "sd": sd}} for h, fh, sd in points]
    return plan_usage.merge([plan_usage.normalise(r) for r in raw])


def paste(hours_ago, fh, sd, split=None):
    return {"kind": "PlanUsageObservation", "taken_at": us._stamp(NOW - timedelta(hours=hours_ago)),
            "five_hour_percent": fh, "seven_day_percent": sd,
            "five_hour_resets_at_text": "11:00 AM", "seven_day_resets_at_text": "Saturday 8:00 AM",
            "product_split_percent": split or {}}


def line(hours_ago, fh, sd, fh_reset=None):
    return {"kind": "StatusLineUsage", "taken_at": us._stamp(NOW - timedelta(hours=hours_ago)),
            "five_hour_percent": fh, "seven_day_percent": sd,
            "five_hour_resets_at": fh_reset, "seven_day_resets_at": None}


def run(samples=(), pastes=(), statusline=()):
    with tempfile.TemporaryDirectory() as tmp:
        return us.status(samples=list(samples), pastes=list(pastes), statusline=list(statusline),
                         limits_path=Path(tmp) / "none.json", now=NOW)


def sources(result, figure):
    return [e["source"] for e in result["figures"][figure]]


class R5TheStatus(unittest.TestCase):
    def test_answers_from_the_desktop_file_alone(self):
        result = run(samples=desktop((1, 20, 40), (0.25, 22, 41)))
        self.assertEqual(sources(result, "five_hour"), [us.SOURCE_DESKTOP])
        self.assertEqual(result["figures"]["five_hour"][0]["percent"], 22)
        self.assertEqual(result["figures"]["seven_day"][0]["percent"], 41)

    def test_answers_from_a_paste_alone_with_its_reset_text(self):
        result = run(pastes=[paste(1, 9, 22)])
        entry = result["figures"]["five_hour"][0]
        self.assertEqual((entry["source"], entry["percent"], entry["resets_at_text"]),
                         (us.SOURCE_PASTE, 9, "11:00 AM"))

    def test_answers_from_both_and_names_the_source_of_each(self):
        result = run(samples=desktop((0.5, 6, 21)), pastes=[paste(0.2, 9, 22)])
        self.assertEqual(sources(result, "five_hour"), [us.SOURCE_PASTE, us.SOURCE_DESKTOP])
        text = "\n".join(us.lines(result))
        self.assertIn("9%  paste of the usage page", text)
        self.assertIn("6%  desktop app's file", text)

    def test_the_status_line_reading_carries_its_reset_time(self):
        result = run(statusline=[line(0.1, 30, 50, fh_reset="2026-09-17T14:00:00Z")])
        self.assertEqual(result["figures"]["five_hour"][0]["resets_at"], "2026-09-17T14:00:00Z")

    def test_a_reading_older_than_its_window_is_named_not_shown(self):
        result = run(samples=desktop((6, 70, 40)))
        five = result["figures"]["five_hour"][0]
        self.assertIsNone(five["percent"])
        self.assertIn("older than its own five-hour window", five["stale"])
        self.assertEqual(result["figures"]["seven_day"][0]["percent"], 40)

    def test_a_reading_whose_window_has_reset_is_not_shown(self):
        result = run(statusline=[line(2, 90, 50, fh_reset="2026-09-17T11:00:00Z")])
        self.assertIsNone(result["figures"]["five_hour"][0]["percent"])
        self.assertEqual(result["warnings"], [])

    def test_the_product_split_shows_only_while_fresh(self):
        fresh = run(pastes=[paste(1, 9, 22, {"Claude Code": 98, "Chats": 0})])
        self.assertEqual(fresh["product_split"]["percent"]["Claude Code"], 98)
        old = run(pastes=[paste(24 * 8, 9, 22, {"Claude Code": 98})])
        self.assertIsNone(old["product_split"])

    def test_no_source_at_all_says_so(self):
        text = "\n".join(us.lines(run()))
        self.assertIn("no reading from any source", text)

    def test_the_cross_check_is_read_from_the_limits_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "limits.json"
            path.write_text(json.dumps({
                "generated_at": "2026-09-17T11:00:00Z", "window": "five_hour",
                "current_window": {"all_classes": 500},
                "observed_ceilings": {"five_hour": {"lowest_refusal_tokens": 1000,
                                                    "observations": 2}}}))
            check = us.cross_check(path)
        self.assertEqual((check["percent_of_observed_ceiling"], check["refusals"]), (50, 2))

    def test_only_the_most_recent_account_is_read_as_a_series(self):
        other = plan_usage.normalise({"t": int((NOW - timedelta(hours=2)).timestamp() * 1000),
                                      "org": "another", "u": {"fh": 99, "sd": 99}})
        result = run(samples=plan_usage.merge(desktop((0.5, 10, 20)), [other]))
        self.assertEqual(result["figures"]["five_hour"][0]["percent"], 10)

    def test_no_identifier_is_printed(self):
        text = json.dumps(run(samples=desktop((0.5, 10, 20))))
        self.assertNotIn(ORG, text)


class R6TheWarning(unittest.TestCase):
    def test_80_warns_and_79_does_not(self):
        self.assertEqual(len(run(samples=desktop((1, 60, 30), (0.1, 80, 31)))["warnings"]), 1)
        self.assertEqual(run(samples=desktop((1, 60, 30), (0.1, 79, 31)))["warnings"], [])

    def test_the_warning_is_in_words_with_the_day_it_reaches_100(self):
        warning = run(samples=desktop((2, 60, 30), (0, 80, 31)))["warnings"][0]
        # 20 points in 2 hours, 20 more to go: 14:00 UTC on Thursday 17 September.
        self.assertIn("five-hour limit is at 80%", warning)
        self.assertIn("Thursday 17 September at about 14:00 UTC", warning)

    def test_either_limit_warns(self):
        warnings = run(samples=desktop((24, 10, 70), (0, 12, 85)))["warnings"]
        self.assertEqual(len(warnings), 1)
        self.assertIn("seven-day limit is at 85%", warnings[0])

    def test_the_run_starts_after_the_percentage_last_fell(self):
        points = [{"at": NOW - timedelta(hours=h), "percent": p, "resets_at": None}
                  for h, p in ((4, 90), (2, 10), (1, 50), (0, 90))]
        projection = us.project(points, "five_hour", NOW)
        self.assertIn("3 readings", projection["reason"])

    def test_a_weekly_series_spanning_13_september_refuses_the_projection(self):
        before = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
        after = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
        points = [{"at": before, "percent": 60, "resets_at": None},
                  {"at": after, "percent": 85, "resets_at": None}]
        projection = us.project(points, "seven_day", after)
        self.assertIsNone(projection["reaches_100_at"])
        self.assertIn("13 September 2026 (Pacific time), when Claude's weekly limit changed",
                      projection["reason"])

    def test_the_change_is_the_end_of_13_september_pacific_not_utc_midnight(self):
        points = [{"at": datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc), "percent": 60,
                   "resets_at": None},
                  {"at": datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc), "percent": 85,
                   "resets_at": None}]
        self.assertIsNone(us.project(points, "seven_day")["reaches_100_at"])
        after = [dict(p, at=p["at"] + timedelta(days=1)) for p in points]
        self.assertIsNotNone(us.project(after, "seven_day")["reaches_100_at"])

    def test_one_reading_or_a_flat_series_gives_no_projection_but_still_warns(self):
        result = run(pastes=[paste(0.5, 85, 20)])
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("no rate to project from", result["warnings"][0])


class R8ThePeriod(unittest.TestCase):
    def test_a_period_summarises_each_source_with_its_coverage(self):
        samples = desktop((30, 50, 99), (3, 10, 40), (2, 30, 45), (1, 20, 47))
        start, end = NOW - timedelta(hours=4), NOW
        result = us.period(start, end, samples=samples, pastes=[paste(2, 9, 22)],
                           statusline=[line(0.5, 25, 48)])
        desk = result["sources"][0]
        self.assertEqual((desk["source"], desk["account"]), (us.SOURCE_DESKTOP, "account-1"))
        self.assertEqual(desk["figures"]["five_hour"],
                         {"readings": 3, "highest": 30, "first": 10, "last": 20,
                          "first_at": "2026-09-17T09:00:00Z", "last_at": "2026-09-17T11:00:00Z"})
        self.assertEqual(desk["coverage_percent"], 19)
        self.assertEqual([r["source"] for r in result["sources"]],
                         [us.SOURCE_DESKTOP, us.SOURCE_STATUSLINE, us.SOURCE_PASTE])
        self.assertFalse(result["spans_weekly_break"])

    def test_no_readings_in_the_period_gives_no_sources(self):
        result = us.period(NOW - timedelta(days=1), NOW, samples=desktop((48, 10, 20)),
                           pastes=[], statusline=[])
        self.assertEqual(result["sources"], [])

    def test_a_period_across_13_september_says_so(self):
        result = us.period(datetime(2026, 9, 10, tzinfo=timezone.utc), NOW,
                           samples=[], pastes=[], statusline=[])
        self.assertTrue(result["spans_weekly_break"])



class TestTheBoardShowsEveryAccountSideBySide(unittest.TestCase):
    """P-0001-T55. Two accounts with different weekly resets, never averaged."""

    NOW = datetime(2026, 9, 17, 13, 0, tzinfo=timezone.utc)

    def sample(self, key, at, five, week):
        return {"t": int(datetime.fromisoformat(at.replace("Z", "+00:00")).timestamp() * 1000),
                "at": at, "account_key": key, "five_hour_percent": five,
                "seven_day_percent": week}

    def result(self, samples=(), pastes=(), statusline=()):
        return us.by_account(samples=list(samples), pastes=list(pastes),
                                       statusline=list(statusline), now=self.NOW)

    def test_both_accounts_get_a_column_and_nothing_is_averaged(self):
        out = self.result([self.sample("k1", "2026-09-15T08:00:00Z", 10, 30),
                           self.sample("k2", "2026-09-17T12:45:00Z", 42, 56)])
        self.assertEqual([c["account"] for c in out["accounts"]], ["account-1", "account-2"])
        week = {c["account"]: c["figures"]["seven_day"]["current"]["percent"]
                for c in out["accounts"]}
        self.assertEqual(week, {"account-1": 30, "account-2": 56})

    def test_a_newer_paste_goes_on_top_of_an_older_desktop_reading(self):
        out = self.result([self.sample("k1", "2026-09-15T08:00:00Z", 10, 30)],
                          [{"taken_at": "2026-09-17T12:27:00Z", "account": "account-1",
                            "five_hour_percent": 36, "seven_day_percent": 6,
                            "seven_day_resets_at_text": "Thu 9:00 AM"}])
        week = out["accounts"][0]["figures"]["seven_day"]
        self.assertEqual(week["current"]["percent"], 6)
        self.assertEqual(week["others"], [], "a reading from before the reset is not shown")

    def test_two_sources_close_together_are_both_shown(self):
        out = self.result([self.sample("k1", "2026-09-17T12:20:00Z", 30, 8)],
                          [{"taken_at": "2026-09-17T12:27:00Z", "account": "account-1",
                            "five_hour_percent": 36, "seven_day_percent": 6}])
        week = out["accounts"][0]["figures"]["seven_day"]
        self.assertEqual(week["current"]["percent"], 6)
        self.assertEqual(week["others"][0]["percent"], 8)

    def test_eighty_percent_warns_and_seventy_nine_does_not(self):
        out = self.result([self.sample("k1", "2026-09-17T12:50:00Z", 79, 80)])
        figs = out["accounts"][0]["figures"]
        self.assertFalse(figs["five_hour"]["at_or_over_warning"])
        self.assertTrue(figs["seven_day"]["at_or_over_warning"])
        self.assertEqual(len(out["accounts"][0]["warnings"]), 1)

    def test_a_reading_older_than_its_window_is_not_current(self):
        out = self.result([self.sample("k1", "2026-09-17T06:00:00Z", 90, 20)])
        five = out["accounts"][0]["figures"]["five_hour"]
        self.assertIsNone(five["current"])
        self.assertFalse(five["at_or_over_warning"])
        self.assertIsNotNone(five["others"][0]["stale"])

    def test_a_status_line_reading_is_not_guessed_into_an_account(self):
        out = self.result(statusline=[{"taken_at": "2026-09-17T12:59:00Z",
                                       "five_hour_percent": 12}])
        self.assertEqual(out["accounts"], [])
        self.assertEqual(out["unassigned"]["figures"]["five_hour"]["current"]["percent"], 12)


if __name__ == "__main__":
    unittest.main()


class AStatusLineReadingBelongsToAnAccount(unittest.TestCase):
    """The owner, 17 September 2026, minutes after the first status-line reading was
    ever written on this Mac: "why do we have three accounts showing in the
    board?" It named no account, so the screen showed it as a third one."""

    def test_the_status_line_keys_its_account_the_same_way_the_desktop_file_does(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import statusline as sl
        import plan_usage as pu
        self.assertEqual(sl._KEY_PREFIX, pu._KEY_PREFIX)
        self.assertEqual(sl.ACCOUNT_KEY_LENGTH, pu.ACCOUNT_KEY_LENGTH)

    def test_a_reading_with_no_key_takes_the_account_being_sampled_around_it(self):
        samples = [{"at": "2026-09-17T13:30:00Z", "account_key": "k1"},
                   {"at": "2026-09-17T13:40:00Z", "account_key": "k1"}]
        labels = {"k1": "account-1"}
        self.assertEqual(
            us._account_around("2026-09-17T13:33:00Z", samples, labels), "account-1")

    def test_two_accounts_around_it_leave_it_unassigned(self):
        samples = [{"at": "2026-09-17T13:30:00Z", "account_key": "k1"},
                   {"at": "2026-09-17T13:40:00Z", "account_key": "k2"}]
        labels = {"k1": "account-1", "k2": "account-2"}
        self.assertIsNone(us._account_around("2026-09-17T13:33:00Z", samples, labels))

    def test_a_reading_far_from_any_sample_stays_unassigned(self):
        samples = [{"at": "2026-09-17T09:00:00Z", "account_key": "k1"}]
        labels = {"k1": "account-1"}
        self.assertIsNone(us._account_around("2026-09-17T13:33:00Z", samples, labels))
