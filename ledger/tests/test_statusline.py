#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The status line's reading -- R3 of package/RECKON-1.2-SPEC.md.

Synthetic input shaped like Claude Code's documented status-line JSON. Nothing
here writes to the real readings file.
"""

import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import statusline as sl  # noqa: E402
import usage_status as us  # noqa: E402

NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)


def payload(fh=14.0, sd=48, fh_reset=1789653600, sd_reset="2026-09-19T07:00:00Z"):
    return {"session_id": "s1", "model": {"display_name": "Opus"},
            "rate_limits": {"five_hour": {"used_percentage": fh, "resets_at": fh_reset},
                            "seven_day": {"used_percentage": sd, "resets_at": sd_reset}}}


def run(stdin, path, now=NOW):
    printed = io.StringIO()
    old = sys.stdout
    sys.stdout = printed
    try:
        sl.main(stdin=io.StringIO(stdin), path=path, now=now)
    finally:
        sys.stdout = old
    return printed.getvalue().strip()


class R3TheStatusLine(unittest.TestCase):
    def test_a_reading_carries_both_percentages_and_their_reset_times(self):
        reading = sl.reading(payload(), NOW)
        self.assertEqual((reading["five_hour_percent"], reading["seven_day_percent"]), (14.0, 48))
        self.assertEqual(reading["five_hour_resets_at"], "2026-09-17T14:00:00Z")
        self.assertEqual(reading["seven_day_resets_at"], "2026-09-19T07:00:00Z")

    def test_it_prints_one_short_line_and_appends_one_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "readings.jsonl"
            printed = run(json.dumps(payload()), path)
            self.assertEqual(len(printed.splitlines()), 1)
            self.assertIn("5h 14%", printed)
            self.assertIn("7d 48%", printed)
            self.assertEqual(len(path.read_text().splitlines()), 1)

    def test_an_unchanged_reading_is_not_written_again_within_fifteen_minutes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "readings.jsonl"
            run(json.dumps(payload()), path)
            run(json.dumps(payload()), path, NOW + timedelta(minutes=5))
            self.assertEqual(len(path.read_text().splitlines()), 1)
            run(json.dumps(payload(fh=15)), path, NOW + timedelta(minutes=6))
            run(json.dumps(payload(fh=15)), path, NOW + timedelta(minutes=30))
            self.assertEqual(len(path.read_text().splitlines()), 3)

    def test_input_with_no_meter_writes_nothing_and_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "readings.jsonl"
            printed = run(json.dumps({"session_id": "s1"}), path)
            self.assertEqual(printed, "usage: no meter yet")
            self.assertFalse(path.exists())

    def test_bad_input_never_fails_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "readings.jsonl"
            printed = run("{not json", path)
            self.assertTrue(printed.startswith("usage: not read"))
            self.assertFalse(path.exists())

    def test_the_status_command_reads_what_the_status_line_wrote(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "readings.jsonl"
            run(json.dumps(payload()), path)
            readings = us._read_jsonl(path)
            result = us.status(samples=[], pastes=[], statusline=readings,
                               limits_path=Path(tmp) / "none.json",
                               now=NOW + timedelta(minutes=1))
        entry = result["figures"]["five_hour"][0]
        self.assertEqual((entry["source"], entry["percent"], entry["resets_at"]),
                         (us.SOURCE_STATUSLINE, 14.0, "2026-09-17T14:00:00Z"))


class T79WhenTheStatusLineLastRan(unittest.TestCase):
    def test_every_call_notes_when_it_ran_and_whether_it_had_a_meter(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "readings.jsonl"
            run(json.dumps({"session_id": "s1"}), path)
            self.assertEqual(sl.read_called(path),
                             {"called_at": "2026-09-17T12:00:00Z", "had_meter": False})
            run(json.dumps(payload()), path, NOW + timedelta(minutes=2))
            self.assertEqual(sl.read_called(path)["had_meter"], True)
            run("{not json", path, NOW + timedelta(minutes=3))
            self.assertEqual(sl.read_called(path)["called_at"], "2026-09-17T12:03:00Z")

    def test_status_says_the_status_line_never_ran_when_there_is_no_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = us.status(samples=[], pastes=[], statusline_path=Path(tmp) / "r.jsonl",
                               limits_path=Path(tmp) / "none.json", now=NOW)
        self.assertIsNone(result["statusline_called"])
        self.assertIn("has never run on this machine", "\n".join(us.lines(result)))

    def test_status_says_when_it_last_ran(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.jsonl"
            run(json.dumps({"session_id": "s1"}), path)
            result = us.status(samples=[], pastes=[], statusline_path=path,
                               limits_path=Path(tmp) / "none.json", now=NOW)
        text = "\n".join(us.lines(result))
        self.assertIn("last ran 2026-09-17 12:00 UTC with no meter", text)


if __name__ == "__main__":
    unittest.main()
