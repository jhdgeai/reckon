#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The desktop app's usage meter -- R1 and R2 of package/RECKON-1.2-SPEC.md.

Synthetic samples only. Nothing here reads the real usage file, the real
archive or the copies in ledger/plan-usage/.

THE IDENTIFIERS IN THESE FIXTURES ARE INVENTED and they are still never written
out: several tests below assert that whatever went in does not appear in the
report, in the archive, or in a line this module prints. That is the property,
not the fixture.
"""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import plan_usage  # noqa: E402

ORG_ONE = "00000000-1111-2222-3333-444444444444"
ORG_TWO = "99999999-8888-7777-6666-555555555555"

MINUTE = 60_000
QUARTER_HOUR = 15 * MINUTE
HOUR = 60 * MINUTE
DAY = 24 * HOUR

#: 16 August 2026 20:41 UTC, the oldest sample the app held on 16 September.
START = 1_786_999_260_000


def sample(offset, org=ORG_ONE, fh=4, sd=15, spend=None):
    usage = {"fh": fh, "sd": sd}
    if spend is not None:
        usage["xu"] = spend
    return {"t": START + offset, "org": org, "u": usage}


def write(path, samples, version=2):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": version, "samples": samples}), encoding="utf-8")
    return path


class PlanUsageTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.live = self.root / "plan-usage-history.json"
        self.archive = self.root / "archive" / "plan-usage-history.json"
        self.copies = self.root / "copies"

    def tearDown(self):
        self._tmp.cleanup()

    def report(self, **kwargs):
        kwargs.setdefault("live", self.live)
        kwargs.setdefault("archive", self.archive)
        kwargs.setdefault("copies", self.copies)
        return plan_usage.report(**kwargs)


class TheSeriesNamesItsAccount(PlanUsageTestCase):
    """R1: the series names its ACCOUNT rather than its machine -- and it does
    that without ever holding on to the account's identifier."""

    def test_accounts_are_numbered_by_first_appearance(self):
        write(self.live, [sample(0, ORG_ONE), sample(QUARTER_HOUR, ORG_TWO)])
        labels = [a["account"] for a in self.report()["accounts"]]
        self.assertEqual(labels, ["account-1", "account-2"])

    def test_the_later_account_is_account_two_whichever_order_the_file_holds_it(self):
        """Position in the file is not evidence of anything; time is."""
        write(self.live, [sample(QUARTER_HOUR, ORG_TWO), sample(0, ORG_ONE)])
        labels = plan_usage.account_labels(
            plan_usage.read_source(self.live)["samples"])
        self.assertEqual(sorted(labels.values()), ["account-1", "account-2"])
        self.assertEqual(labels[plan_usage.account_key(ORG_ONE)], "account-1")
        self.assertEqual(labels[plan_usage.account_key(ORG_TWO)], "account-2")

    def test_the_identifier_never_appears_in_the_report(self):
        write(self.live, [sample(0, ORG_ONE), sample(QUARTER_HOUR, ORG_TWO)])
        text = json.dumps(self.report())
        self.assertNotIn(ORG_ONE, text)
        self.assertNotIn(ORG_TWO, text)

    def test_the_identifier_never_appears_in_what_is_printed(self):
        write(self.live, [sample(0, ORG_ONE)])
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            plan_usage.main(["--source", str(self.live),
                             "--archive-path", str(self.archive),
                             "--copies", str(self.copies)])
        self.assertNotIn(ORG_ONE, buffer.getvalue())
        self.assertIn("account-1", buffer.getvalue())

    def test_the_key_is_one_way_and_stable(self):
        self.assertEqual(plan_usage.account_key(ORG_ONE), plan_usage.account_key(ORG_ONE))
        self.assertNotEqual(plan_usage.account_key(ORG_ONE), plan_usage.account_key(ORG_TWO))
        self.assertNotIn(ORG_ONE, plan_usage.account_key(ORG_ONE))

    def test_a_sample_with_no_account_is_counted_in_no_account(self):
        write(self.live, [sample(0, ORG_ONE), {"t": START + QUARTER_HOUR, "u": {"fh": 1, "sd": 2}}])
        data = self.report()
        self.assertEqual(data["unlabelled_samples"], 1)
        self.assertEqual(data["accounts"][0]["coverage"]["sample_count"], 1)


class OverlappingCopiesMerge(PlanUsageTestCase):
    """R1's first acceptance test: two overlapping copies merge with no
    duplicates. This is the normal case, not the edge one -- the live file and
    the archive share thousands of samples every single run."""

    def test_two_overlapping_copies_produce_one_sample_each(self):
        shared = [sample(0), sample(QUARTER_HOUR), sample(2 * QUARTER_HOUR)]
        write(self.live, shared + [sample(3 * QUARTER_HOUR)])
        write(self.archive, [sample(-QUARTER_HOUR)] + shared)
        data = self.report()
        self.assertEqual(data["sample_count"], 5)

    def test_a_copy_only_the_archive_has_is_kept(self):
        write(self.live, [sample(0)])
        write(self.archive, [sample(-30 * DAY), sample(0)])
        data = self.report()
        self.assertEqual(data["sample_count"], 2)

    def test_hand_taken_copies_in_the_folder_are_merged_too(self):
        write(self.live, [sample(0)])
        write(self.copies / "plan-usage-history-2026-09-07T1010Z.json", [sample(-DAY)])
        self.assertEqual(self.report()["sample_count"], 2)

    def test_the_same_time_on_two_accounts_is_two_samples(self):
        """A timestamp alone is not unique across accounts, and collapsing them
        would silently delete one account's reading."""
        write(self.live, [sample(0, ORG_ONE), sample(0, ORG_TWO)])
        self.assertEqual(self.report()["sample_count"], 2)


class TheSpendFigure(PlanUsageTestCase):
    """R1: a sample with no `xu` is not read as zero spend. The file states no
    unit for it and it FELL between two samples, so it is never a currency."""

    def test_a_sample_without_a_spend_figure_is_not_zero(self):
        write(self.live, [sample(0), sample(QUARTER_HOUR, spend=11.7)])
        spend = self.report()["accounts"][0]["spend_figure"]
        self.assertEqual(spend["samples_with_a_figure"], 1)
        self.assertEqual(spend["samples_without_one"], 1)
        self.assertEqual(spend["lowest"], 11.7)

    def test_no_spend_figure_at_all_reports_none_not_zero(self):
        write(self.live, [sample(0), sample(QUARTER_HOUR)])
        spend = self.report()["accounts"][0]["spend_figure"]
        self.assertEqual(spend["samples_with_a_figure"], 0)
        self.assertIsNone(spend["lowest"])
        self.assertIsNone(spend["highest"])

    def test_the_unit_is_reported_as_unknown(self):
        write(self.live, [sample(0, spend=84.33)])
        spend = self.report()["accounts"][0]["spend_figure"]
        self.assertEqual(spend["unit"], "not stated by the file")

    def test_it_is_never_printed_with_a_currency_symbol(self):
        write(self.live, [sample(0, spend=84.33), sample(QUARTER_HOUR, spend=63.44)])
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            plan_usage.main(["--source", str(self.live),
                             "--archive-path", str(self.archive),
                             "--copies", str(self.copies)])
        printed = buffer.getvalue()
        self.assertIn("84.33", printed)
        for symbol in ("£", "$", "€", "GBP", "USD"):
            self.assertNotIn(symbol, printed)

    def test_a_figure_that_fell_is_noticed(self):
        """spec-core.md 4.1 calls it a running total of spend. It fell, so it
        is not one, and the reader says so rather than smoothing it."""
        write(self.live, [sample(0, spend=84.33), sample(QUARTER_HOUR, spend=63.44)])
        self.assertTrue(self.report()["accounts"][0]["spend_figure"]["fell_at_some_point"])


class Coverage(PlanUsageTestCase):
    """R1: every gap over an hour, so a quiet stretch is never read as low
    usage. The app writes only while it runs."""

    def test_first_and_last_sample_are_reported(self):
        write(self.live, [sample(0), sample(2 * DAY)])
        cover = self.report()["accounts"][0]["coverage"]
        self.assertEqual(cover["first_sample_at"], plan_usage._stamp(START))
        self.assertEqual(cover["last_sample_at"], plan_usage._stamp(START + 2 * DAY))

    def test_a_quarter_hour_cadence_has_no_gaps(self):
        write(self.live, [sample(i * QUARTER_HOUR) for i in range(20)])
        self.assertEqual(self.report()["accounts"][0]["coverage"]["gap_count"], 0)

    def test_a_gap_over_an_hour_is_reported_with_its_length(self):
        write(self.live, [sample(0), sample(3 * HOUR), sample(3 * HOUR + QUARTER_HOUR)])
        cover = self.report()["accounts"][0]["coverage"]
        self.assertEqual(cover["gap_count"], 1)
        self.assertEqual(cover["gaps"][0]["hours"], 3.0)
        self.assertEqual(cover["longest_gap_hours"], 3.0)

    def test_gaps_over_three_hours_are_counted_separately(self):
        write(self.live, [sample(0), sample(2 * HOUR), sample(2 * HOUR + 74 * HOUR)])
        cover = self.report()["accounts"][0]["coverage"]
        self.assertEqual(cover["gap_count"], 2)
        self.assertEqual(cover["gaps_over_three_hours"], 1)
        self.assertEqual(cover["longest_gap_hours"], 74.0)

    def test_the_gap_threshold_is_a_setting(self):
        write(self.live, [sample(0), sample(90 * MINUTE)])
        self.assertEqual(self.report(gap_minutes=60)["accounts"][0]["coverage"]["gap_count"], 1)
        self.assertEqual(self.report(gap_minutes=120)["accounts"][0]["coverage"]["gap_count"], 0)

    def test_the_covered_fraction_says_how_much_of_the_span_is_real(self):
        write(self.live, [sample(0), sample(QUARTER_HOUR), sample(QUARTER_HOUR + 10 * HOUR)])
        cover = self.report()["accounts"][0]["coverage"]
        self.assertLess(cover["covered_fraction"], 0.05)


class TheNewestReading(PlanUsageTestCase):
    """R1 and R5: the newest sample, its timestamp, and both percentages as
    whole numbers."""

    def test_both_percentages_are_whole_numbers(self):
        write(self.live, [sample(0, fh=4, sd=15), sample(QUARTER_HOUR, fh=9, sd=22)])
        new = self.report()["accounts"][0]["newest"]
        self.assertEqual(new["five_hour_percent"], 9)
        self.assertEqual(new["seven_day_percent"], 22)
        self.assertIsInstance(new["five_hour_percent"], int)

    def test_the_newest_sample_carries_its_own_timestamp(self):
        write(self.live, [sample(0), sample(QUARTER_HOUR)])
        self.assertEqual(self.report()["accounts"][0]["newest"]["at"],
                         plan_usage._stamp(START + QUARTER_HOUR))

    def test_each_account_has_its_own_newest_reading(self):
        write(self.live, [sample(0, ORG_ONE, fh=37, sd=100),
                          sample(QUARTER_HOUR, ORG_TWO, fh=1, sd=2)])
        newest = {a["account"]: a["newest"]["five_hour_percent"]
                  for a in self.report()["accounts"]}
        self.assertEqual(newest, {"account-1": 37, "account-2": 1})


class AMissingOrBrokenSource(PlanUsageTestCase):
    """R1: a missing file is reported and NOT fatal. The desktop app may simply
    never have run on this machine, and that is a fact to state, not a crash."""

    def test_a_missing_file_is_reported(self):
        source = plan_usage.read_source(self.root / "nope.json")
        self.assertFalse(source["exists"])
        self.assertEqual(source["problem"], "no file here")

    def test_a_missing_file_does_not_stop_the_others_being_read(self):
        write(self.archive, [sample(0)])
        data = self.report()
        self.assertEqual(data["sample_count"], 1)
        self.assertTrue(any(not s["exists"] for s in data["sources"]))

    def test_every_source_missing_is_still_an_answer(self):
        data = self.report()
        self.assertEqual(data["sample_count"], 0)
        self.assertEqual(data["accounts"], [])
        self.assertTrue(any("NO SOURCE EXISTS" in note for note in data["notes"]))

    def test_the_command_does_not_fail_when_nothing_is_there(self):
        with contextlib.redirect_stdout(io.StringIO()):
            rc = plan_usage.main(["--source", str(self.root / "nope.json"),
                                  "--archive-path", str(self.archive),
                                  "--copies", str(self.copies)])
        self.assertEqual(rc, 0)

    def test_unreadable_json_is_reported_not_raised(self):
        self.live.write_text("{not json", encoding="utf-8")
        source = plan_usage.read_source(self.live)
        self.assertIn("could not be read", source["problem"])
        self.assertEqual(source["samples"], [])

    def test_a_file_that_is_not_a_usage_history_says_so(self):
        self.live.write_text(json.dumps({"version": 2}), encoding="utf-8")
        self.assertIn("no samples in it", plan_usage.read_source(self.live)["problem"])

    def test_a_sample_with_no_timestamp_is_left_out_and_counted(self):
        write(self.live, [sample(0), {"org": ORG_ONE, "u": {"fh": 1, "sd": 2}}])
        source = plan_usage.read_source(self.live)
        self.assertEqual(source["sample_count"], 1)
        self.assertIn("no usable timestamp", source["problem"])


class TheWeeklyScaleBreak(PlanUsageTestCase):
    """The weekly limit changed on 13 September 2026. A seven-day series that
    spans that day is two scales, and the report says so rather than letting a
    trend be read across it."""

    def test_a_series_spanning_the_break_is_flagged(self):
        write(self.live, [{"t": 1_789_000_000_000, "org": ORG_ONE, "u": {"fh": 1, "sd": 90}},
                          {"t": 1_789_600_000_000, "org": ORG_ONE, "u": {"fh": 1, "sd": 20}}])
        self.assertTrue(self.report()["accounts"][0]["weekly_series_spans_the_scale_break"])

    def test_a_series_entirely_after_the_break_is_not(self):
        write(self.live, [{"t": 1_789_600_000_000, "org": ORG_ONE, "u": {"fh": 1, "sd": 20}},
                          {"t": 1_789_700_000_000, "org": ORG_ONE, "u": {"fh": 1, "sd": 21}}])
        self.assertFalse(self.report()["accounts"][0]["weekly_series_spans_the_scale_break"])


class TheArchive(PlanUsageTestCase):
    """R2: a sample older than thirty days is still readable after the desktop
    app has dropped it, and running the copy twice adds nothing the second
    time."""

    def archive_run(self, dry_run=False):
        return plan_usage.archive_run(live=self.live, archive=self.archive, dry_run=dry_run)

    def archived(self):
        return plan_usage.read_source(self.archive)["samples"]

    def test_the_first_run_copies_everything(self):
        write(self.live, [sample(0), sample(QUARTER_HOUR)])
        added, kept, problem = self.archive_run()
        self.assertIsNone(problem)
        self.assertEqual((added, kept), (2, 0))
        self.assertEqual(len(self.archived()), 2)

    def test_running_it_twice_adds_nothing_the_second_time(self):
        write(self.live, [sample(0), sample(QUARTER_HOUR)])
        self.archive_run()
        added, kept, _ = self.archive_run()
        self.assertEqual(added, 0)
        self.assertEqual(kept, 2)
        self.assertEqual(len(self.archived()), 2)

    def test_a_sample_the_app_has_dropped_is_still_readable(self):
        """The whole point. Thirty days pass, the app forgets the oldest day,
        and the register still has it."""
        write(self.live, [sample(0), sample(31 * DAY)])
        self.archive_run()
        write(self.live, [sample(31 * DAY)])          # the app dropped the old one
        self.archive_run()

        kept = {s["t"] for s in self.archived()}
        self.assertEqual(kept, {START, START + 31 * DAY})
        self.assertEqual(self.report()["sample_count"], 2)

    def test_the_archive_holds_no_identifier(self):
        write(self.live, [sample(0, ORG_ONE), sample(QUARTER_HOUR, ORG_TWO)])
        self.archive_run()
        text = self.archive.read_text(encoding="utf-8")
        self.assertNotIn(ORG_ONE, text)
        self.assertNotIn(ORG_TWO, text)
        self.assertIn(plan_usage.account_key(ORG_ONE), text)

    def test_the_archive_round_trips_to_the_same_labels(self):
        write(self.live, [sample(0, ORG_ONE), sample(QUARTER_HOUR, ORG_TWO)])
        self.archive_run()
        self.live.unlink()
        self.assertEqual([a["account"] for a in self.report()["accounts"]],
                         ["account-1", "account-2"])

    def test_a_spend_figure_survives_the_archive_and_an_absent_one_stays_absent(self):
        write(self.live, [sample(0, spend=84.33), sample(QUARTER_HOUR)])
        self.archive_run()
        spend = self.report()["accounts"][0]["spend_figure"]
        self.assertEqual(spend["samples_with_a_figure"], 1)
        self.assertEqual(spend["samples_without_one"], 1)

    def test_a_dry_run_writes_nothing(self):
        write(self.live, [sample(0)])
        added, _, _ = self.archive_run(dry_run=True)
        self.assertEqual(added, 1)
        self.assertFalse(self.archive.exists())

    def test_a_missing_live_file_is_a_problem_reported_not_raised(self):
        added, kept, problem = self.archive_run()
        self.assertEqual(added, 0)
        self.assertIn("no desktop usage file", problem)

    def test_the_command_reports_the_copy(self):
        write(self.live, [sample(0)])
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            rc = plan_usage.main(["--archive", "--source", str(self.live),
                                  "--archive-path", str(self.archive)])
        self.assertEqual(rc, 0)
        self.assertIn("1 new sample", buffer.getvalue())


class WhatTheReportSaysOutLoud(PlanUsageTestCase):
    """The figures are the account's own meter. They are not a bill, and a gap
    is not low usage. Both sentences are on the face of the report."""

    def test_it_says_it_is_not_a_bill(self):
        write(self.live, [sample(0)])
        self.assertTrue(any("not a bill" in note for note in self.report()["notes"]))

    def test_it_says_a_gap_is_not_low_usage(self):
        write(self.live, [sample(0)])
        self.assertTrue(any("never an hour of low usage" in note
                            for note in self.report()["notes"]))

    def test_it_says_the_identifiers_are_not_written_down(self):
        write(self.live, [sample(0)])
        self.assertTrue(any("never written down" in note for note in self.report()["notes"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
