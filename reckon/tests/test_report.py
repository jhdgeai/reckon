# SPDX-License-Identifier: Apache-2.0
"""Tests for reckon/report.py: RECKON-1.1-SPEC.md decision 7's comparison."""

import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from reckon import report  # noqa: E402


class TestCostByTask(unittest.TestCase):
    def test_sums_cost_per_task_ref_and_drops_runs_with_no_task(self):
        runs = [{"task_ref": "P-0001-T08", "cost_usd": 5.0},
                {"task_ref": "P-0001-T08", "cost_usd": 2.0},
                {"task_ref": None, "cost_usd": 3.0}]
        self.assertEqual(report.cost_by_task(runs), {"P-0001-T08": 7.0})


class TestOverruns(unittest.TestCase):
    def test_lists_only_tasks_more_than_ten_percent_over(self):
        # The spec's own worked numbers: T08 in range, T09 9% (not listed), T10 listed.
        tasks = {
            "P-0001-T08": {"fields": {"est_p95_usd": 12.55}},
            "P-0001-T09": {"fields": {"est_p95_usd": 4.00}},
            "P-0001-T10": {"fields": {"est_p95_usd": 14.00}},
        }
        totals = {"P-0001-T08": 12.55, "P-0001-T09": 4.37, "P-0001-T10": 30.13}
        rows = report.overruns(tasks, totals)
        self.assertEqual([r["ref"] for r in rows], ["P-0001-T10"])

    def test_a_task_with_no_estimate_or_no_recorded_spend_is_skipped(self):
        tasks = {"A": {"fields": {"est_p95_usd": None}}, "B": {"fields": {"est_p95_usd": 5.0}}}
        totals = {"A": 100.0}
        self.assertEqual(report.overruns(tasks, totals), [])

    def test_an_estimate_held_as_text_is_read_as_a_number(self):
        """A real store's est_p95_usd is a string -- front matter is flat text
        (wrapper/launch.py's parse_front_matter). Found running the real
        walkthrough against sample/register-sample.json (RECKON-1.1-SPEC.md R3)."""
        tasks = {"P-0001-T10": {"fields": {"est_p95_usd": "14.0"}}}
        totals = {"P-0001-T10": 30.13}
        rows = report.overruns(tasks, totals)
        self.assertEqual([r["ref"] for r in rows], ["P-0001-T10"])

    def test_worst_overrun_first(self):
        tasks = {"A": {"fields": {"est_p95_usd": 10.0}}, "B": {"fields": {"est_p95_usd": 10.0}}}
        totals = {"A": 15.0, "B": 30.0}
        rows = report.overruns(tasks, totals)
        self.assertEqual([r["ref"] for r in rows], ["B", "A"])


class TestRun(unittest.TestCase):
    def test_prints_the_not_a_bill_wording_and_the_overrun_list(self):
        out = io.StringIO()
        live = ({"P-0001-T10": {"fields": {"est_p95_usd": 14.0}}},
               [{"task_ref": "P-0001-T10", "cost_usd": 30.13}])
        with mock.patch.object(report, "_load_live", return_value=live):
            rc = report.run(out=out)
        text = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("not a bill", text.lower())
        self.assertIn("P-0001-T10", text)
        self.assertIn("+115%", text)

    def test_no_overruns_says_so_plainly(self):
        out = io.StringIO()
        live = ({"P-0001-T09": {"fields": {"est_p95_usd": 4.0}}},
                [{"task_ref": "P-0001-T09", "cost_usd": 4.37}])
        with mock.patch.object(report, "_load_live", return_value=live):
            report.run(out=out)
        self.assertIn("No task's recorded cost is more than 10%", out.getvalue())
        self.assertNotIn("No tasks in this store yet", out.getvalue())


class TestEmptyStore(unittest.TestCase):
    """RECKON-USER-SPEC.md R4: a store with no tasks says so, instead of reading
    the same as a store where nothing ran over its estimate."""

    def report_on(self, tasks, runs):
        out = io.StringIO()
        with mock.patch.object(report, "_load_live", return_value=(tasks, runs)):
            rc = report.run(out=out)
        self.assertEqual(rc, 0)
        return out.getvalue()

    def test_no_tasks_and_no_runs_says_both(self):
        text = self.report_on({}, [])
        self.assertIn("No tasks in this store yet", text)
        self.assertIn("Runs recorded: none yet", text)
        self.assertIn("not a bill", text.lower())
        self.assertNotIn("No task's recorded cost is more than", text)

    def test_no_tasks_with_runs_gives_their_count_and_list_price_total(self):
        runs = [{"task_ref": None, "cost_usd": 1.25}, {"task_ref": None, "cost_usd": 0.75},
                {"task_ref": None, "cost_usd": None}]
        text = self.report_on({}, runs)
        self.assertIn("No tasks in this store yet", text)
        self.assertIn("Runs recorded: 3, $2.00 at list rates.", text)
        self.assertIn("not a bill", text.lower())
        self.assertNotIn("No task's recorded cost is more than", text)

    def test_tasks_with_runs_are_reported_as_before(self):
        text = self.report_on({"P-0001-T10": {"fields": {"est_p95_usd": 14.0}}},
                              [{"task_ref": "P-0001-T10", "cost_usd": 30.13}])
        self.assertNotIn("No tasks in this store yet", text)
        self.assertNotIn("Runs recorded", text)
        self.assertIn("Tasks more than 10% over their estimate:", text)
        self.assertIn("P-0001-T10     estimate $14.00   recorded $30.13   (+115%)", text)

    def test_sample_mode_reads_the_sample_file_not_the_live_store(self):
        with __import__("tempfile").TemporaryDirectory() as tmp:
            sample_path = Path(tmp) / "register-sample.json"
            sample_path.write_text(json.dumps({
                "tasks": {"P-0001-T99": {"fields": {"est_p95_usd": 1.0}}},
                "runs": [{"task_ref": "P-0001-T99", "cost_usd": 5.0}],
            }), encoding="utf-8")
            out = io.StringIO()
            with mock.patch.object(report, "SAMPLE_PATH", sample_path), \
                 mock.patch.object(report, "_load_live",
                                   side_effect=AssertionError("must not read the live store")):
                rc = report.run(sample=True, out=out)
        self.assertEqual(rc, 0)
        self.assertIn("P-0001-T99", out.getvalue())
        self.assertIn("sample", out.getvalue().lower())


class TestTheMeterBesideMeasuredCost(unittest.TestCase):
    """R8 of RECKON-1.2-SPEC.md: the account meter for the same period beside
    Claude Code's measured cost, with the floor sentence."""

    NOW = __import__("datetime").datetime(2026, 9, 17, 12, 0,
                                          tzinfo=__import__("datetime").timezone.utc)
    RUNS = [{"task_ref": None, "cost_usd": 4.0, "started_at": "2026-09-16T10:00:00Z"},
            {"task_ref": None, "cost_usd": 6.0, "started_at": "2026-09-15T10:00:00.5Z"},
            {"task_ref": None, "cost_usd": 99.0, "started_at": "2026-09-01T10:00:00Z"},
            {"task_ref": None, "cost_usd": 1.0}]

    def report_on(self, meter, sample=False):
        out = io.StringIO()
        with mock.patch.object(report, "_load_live", return_value=({}, self.RUNS)):
            report.run(out=out, now=self.NOW, meter=meter, sample=sample)
        return out.getvalue()

    def test_a_week_shows_both_and_the_floor_sentence(self):
        meter = {"sources": [{"source": "desktop app's file", "account": "account-2",
                              "coverage_percent": 60,
                              "figures": {"five_hour": {"readings": 40, "highest": 91,
                                                        "first": 3, "last": 20},
                                          "seven_day": {"readings": 40, "highest": 49,
                                                        "first": 10, "last": 49}}}],
                 "spans_weekly_break": False}
        text = self.report_on(meter)
        self.assertIn("The last 7 days, 10 September to 17 September 2026:", text)
        self.assertIn("Claude Code, measured: 2 session(s), $10.00 at list rates.", text)
        self.assertIn("desktop app's file, account-2, covering 60% of the period", text)
        self.assertIn("seven-day  highest 49%, from 10% to 49% across 40 reading(s)", text)
        self.assertIn("This register sees Claude Code only", text)
        self.assertIn("floor", text)
        self.assertNotIn("13 September", text)

    def test_a_store_with_no_readings_says_there_are_none(self):
        text = self.report_on({"sources": [], "spans_weekly_break": False})
        self.assertIn("no readings for this period, from any source", text)
        self.assertIn("This register sees Claude Code only", text)

    def test_a_period_across_the_weekly_change_says_so(self):
        text = self.report_on({"sources": [], "spans_weekly_break": True})
        self.assertIn("The weekly limit changed on 13 September 2026", text)

    def test_a_meter_that_cannot_be_read_does_not_stop_the_report(self):
        out = io.StringIO()
        with mock.patch.object(report, "_load_live", return_value=({}, self.RUNS)), \
                mock.patch.object(report, "_ledger", side_effect=ImportError("gone")):
            rc = report.run(out=out, now=self.NOW)
        self.assertEqual(rc, 0)
        self.assertIn("The account meter: not read (ImportError: gone)", out.getvalue())
        self.assertIn("Runs recorded: 4", out.getvalue())


if __name__ == "__main__":
    unittest.main()
