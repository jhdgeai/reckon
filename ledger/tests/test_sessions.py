#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Session records -- spec-core.md §3.6, R7 of package/RECKON-1.2-SPEC.md.

Synthetic transcripts only. Nothing here reads the archive or the real store.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import recorder  # noqa: E402
import sessions  # noqa: E402
from test_recorder import PRICES, RAILS, SESSION, assistant, write_session  # noqa: E402


def typed(text, timestamp="2026-09-01T10:00:00.000Z", **extra):
    record = {"type": "user", "sessionId": SESSION, "timestamp": timestamp,
              "message": {"role": "user", "content": text}}
    record.update(extra)
    return record


def said(text, timestamp, stop_reason="end_turn", msg_id=None, tools=()):
    record = assistant(msg_id or f"m-{timestamp}", timestamp=timestamp,
                       stop_reason=stop_reason, tools=tools)
    record["message"]["content"][0]["text"] = text
    return record


def result(timestamp, is_error=False):
    return {"type": "user", "sessionId": SESSION, "timestamp": timestamp,
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "x", "is_error": is_error,
                 "content": "boom" if is_error else "ok"}]}}


OUTCOME = [{"name": "Bash", "input": {"command": "python3 store/store.py --outcome P-0001-T64 --text x"}}]


def started(at, task):
    return {"kind": "SessionStarted", "at": at, "task_ref": task}


class TheMarker(unittest.TestCase):

    def test_it_is_read_from_the_first_typed_message(self):
        records = [typed("register-task: P-0001-T64\n\nBuild the session records.")]
        self.assertEqual(sessions.marker_task(records)[0], "P-0001-T64")

    def test_a_system_reminder_before_it_does_not_hide_it(self):
        records = [typed("<system-reminder>\nboilerplate\n</system-reminder>"
                         "register-task: P-0001-T64\n\nGo.")]
        self.assertEqual(sessions.marker_task(records)[0], "P-0001-T64")

    def test_a_marker_in_a_later_message_is_ignored(self):
        records = [typed("Hello."),
                   typed("register-task: P-0001-T64", timestamp="2026-09-01T10:05:00.000Z")]
        self.assertIsNone(sessions.marker_task(records)[0])

    def test_a_marker_quoted_mid_line_is_ignored(self):
        records = [typed("this session's text begins register-task: P-0001-T64 as usual")]
        self.assertIsNone(sessions.marker_task(records)[0])

    def test_a_marker_inside_a_system_reminder_is_ignored(self):
        records = [typed("<system-reminder>\nregister-task: P-0001-T64\n</system-reminder>Hi.")]
        self.assertIsNone(sessions.marker_task(records)[0])

    def test_a_tool_result_is_not_the_first_typed_message(self):
        records = [result("2026-09-01T09:59:00.000Z"),
                   typed("register-task: P-0001-T64")]
        self.assertEqual(sessions.marker_task(records)[0], "P-0001-T64")

    def test_two_different_markers_name_no_task(self):
        records = [typed("register-task: P-0001-T64\nregister-task: P-0001-T68")]
        self.assertIsNone(sessions.marker_task(records)[0])


class TheLink(unittest.TestCase):
    AT = "2026-09-01T10:00:30.000Z"

    def test_no_marker_and_no_board_start_is_null_never_a_guess(self):
        task, method, _, notes = sessions.link_task(
            [typed("Please work on P-0001-T64.")], self.AT, [])
        self.assertIsNone(task)
        self.assertIsNone(method)
        self.assertIn("no record links this session to a task", notes[-1])

    def test_marker_and_board_start_agreeing_is_marker(self):
        task, method, detail, _ = sessions.link_task(
            [typed("register-task: P-0001-T64")], self.AT,
            [started("2026-09-01T10:00:00Z", "P-0001-T64")])
        self.assertEqual((task, method), ("P-0001-T64", "marker"))
        self.assertEqual(detail["task_ref_board_start"], "P-0001-T64")

    def test_only_a_board_start_is_board_start(self):
        task, method, _, _ = sessions.link_task(
            [typed("Go.")], self.AT, [started("2026-09-01T09:59:00Z", "P-0001-T68")])
        self.assertEqual((task, method), ("P-0001-T68", "board_start"))

    def test_marker_and_board_start_disagreeing_is_conflict_with_both_kept(self):
        task, method, detail, _ = sessions.link_task(
            [typed("register-task: P-0001-T64")], self.AT,
            [started("2026-09-01T10:00:00Z", "P-0001-T68")])
        self.assertIsNone(task)
        self.assertEqual(method, "conflict")
        self.assertEqual((detail["task_ref_marker"], detail["task_ref_board_start"]),
                         ("P-0001-T64", "P-0001-T68"))

    def test_a_board_start_more_than_two_minutes_before_is_not_taken(self):
        task, _, _, _ = sessions.link_task(
            [typed("Go.")], self.AT, [started("2026-09-01T09:58:00Z", "P-0001-T68")])
        self.assertIsNone(task)

    def test_a_board_start_after_the_transcript_began_is_not_taken(self):
        task, _, _, _ = sessions.link_task(
            [typed("Go.")], self.AT, [started("2026-09-01T10:01:00Z", "P-0001-T68")])
        self.assertIsNone(task)

    def test_two_board_starts_in_the_window_are_ambiguous(self):
        task, _, _, notes = sessions.link_task(
            [typed("Go.")], self.AT, [started("2026-09-01T09:59:30Z", "P-0001-T68"),
                                      started("2026-09-01T10:00:00Z", "P-0001-T64")])
        self.assertIsNone(task)
        self.assertTrue(any("2 Board starts" in n for n in notes))

    def test_a_hand_link_is_used_only_where_nothing_automatic_exists(self):
        task, method, _, _ = sessions.link_task(
            [typed("Go.")], self.AT, [], hand_link={"task_ref": "P-0001-T03"})
        self.assertEqual((task, method), ("P-0001-T03", "hand"))

    def test_a_hand_link_disagreeing_with_the_marker_is_conflict(self):
        task, method, _, _ = sessions.link_task(
            [typed("register-task: P-0001-T64")], self.AT, [],
            hand_link={"task_ref": "P-0001-T03"})
        self.assertEqual((task, method), (None, "conflict"))


class ActiveTime(unittest.TestCase):

    def test_a_forty_minute_gap_is_excluded(self):
        records = [typed("Go.", timestamp="2026-09-01T10:00:00.000Z"),
                   said("a", "2026-09-01T10:05:00.000Z"),
                   said("b", "2026-09-01T10:45:00.000Z"),
                   said("c", "2026-09-01T10:48:00.000Z")]
        self.assertEqual(sessions.minutes(records, idle_gap_minutes=10), (8.0, 48.0))

    def test_the_threshold_is_a_parameter_not_a_constant(self):
        records = [typed("Go.", timestamp="2026-09-01T10:00:00.000Z"),
                   said("a", "2026-09-01T10:15:00.000Z")]
        self.assertEqual(sessions.minutes(records, idle_gap_minutes=10)[0], 0.0)
        self.assertEqual(sessions.minutes(records, idle_gap_minutes=20)[0], 15.0)

    def test_no_timestamps_is_none_not_zero(self):
        self.assertEqual(sessions.minutes([{"type": "user"}]), (None, None))


class Endings(unittest.TestCase):

    def ending(self, records, **kw):
        return sessions.ending(records, **kw)[0]

    def test_finished(self):
        records = [typed("Go."), said("done", "2026-09-01T10:01:00.000Z", tools=OUTCOME)]
        self.assertEqual(self.ending(records), "finished")

    def test_end_turn_without_a_recorded_outcome_is_unknown(self):
        records = [typed("Go."), said("done", "2026-09-01T10:01:00.000Z")]
        self.assertEqual(self.ending(records), "unknown")

    def test_stopped_at_ceiling_by_marker(self):
        records = [typed("Go."), said("Handing off.\nregister-ended: ceiling",
                                      "2026-09-01T10:01:00.000Z", tools=OUTCOME)]
        ended, basis = sessions.ending(records, assistant_messages=12, ceiling_messages=90)
        self.assertEqual(ended, "stopped_at_ceiling")
        self.assertIn("the marker wins", basis)

    def test_stopped_at_ceiling_by_message_count(self):
        records = [typed("Go."), said("working", "2026-09-01T10:01:00.000Z",
                                      stop_reason="tool_use")]
        self.assertEqual(self.ending(records, assistant_messages=90, ceiling_messages=90),
                         "stopped_at_ceiling")
        self.assertEqual(self.ending(records, assistant_messages=89, ceiling_messages=90),
                         "unknown")

    def test_a_finished_session_past_the_count_is_still_finished(self):
        records = [typed("Go."), said("done", "2026-09-01T10:01:00.000Z", tools=OUTCOME)]
        self.assertEqual(self.ending(records, assistant_messages=120, ceiling_messages=90),
                         "finished")

    def test_stopped_by_owner_on_an_interrupt(self):
        records = [typed("Go."), said("working", "2026-09-01T10:01:00.000Z", stop_reason="tool_use"),
                   typed("[Request interrupted by user]", timestamp="2026-09-01T10:02:00.000Z")]
        self.assertEqual(self.ending(records), "stopped_by_owner")

    def test_stopped_by_owner_from_the_board(self):
        records = [typed("Go."), said("working", "2026-09-01T10:01:00.000Z", stop_reason="tool_use")]
        stood = {"kind": "SessionStoodDown", "at": "2026-09-01T11:00:00Z",
                 "task_ref": "P-0001-T64", "started_at": "2026-09-01T09:59:50Z"}
        self.assertEqual(self.ending(records, task_ref="P-0001-T64",
                                     board_started_at="2026-09-01T09:59:50Z",
                                     decisions=[stood]), "stopped_by_owner")
        self.assertEqual(self.ending(records, task_ref="P-0001-T64",
                                     board_started_at="2026-09-01T08:00:00Z",
                                     decisions=[stood]), "unknown")

    def test_failed_on_an_api_error(self):
        error = said("API Error: overloaded", "2026-09-01T10:02:00.000Z", stop_reason="stop_sequence")
        error["isApiErrorMessage"] = True
        error["message"]["model"] = "<synthetic>"
        self.assertEqual(self.ending([typed("Go."), error]), "failed")

    def test_failed_on_a_tool_error_with_nothing_after(self):
        records = [typed("Go."), said("run", "2026-09-01T10:01:00.000Z", stop_reason="tool_use"),
                   result("2026-09-01T10:01:05.000Z", is_error=True)]
        self.assertEqual(self.ending(records), "failed")

    def test_unknown_is_a_real_value(self):
        records = [typed("Go."), said("run", "2026-09-01T10:01:00.000Z", stop_reason="tool_use")]
        self.assertEqual(self.ending(records), "unknown")

    def test_censored_follows_the_ending(self):
        interrupted = [typed("Go."), typed("[Request interrupted by user]",
                                           timestamp="2026-09-01T10:02:00.000Z")]
        record = sessions.session_record(interrupted, started_at="2026-09-01T10:00:00.000Z",
                                         assistant_messages=0)
        self.assertTrue(record["censored"])
        finished = [typed("Go."), said("done", "2026-09-01T10:01:00.000Z", tools=OUTCOME)]
        record = sessions.session_record(finished, started_at="2026-09-01T10:00:00.000Z",
                                         assistant_messages=1)
        self.assertFalse(record["censored"])


class OnTheRun(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "archive"
        self.source.mkdir()

    def test_the_recorder_puts_every_section_3_2_field_on_the_run(self):
        write_session(self.source, SESSION, [
            typed("register-task: P-0001-T64\n\nGo."),
            said("done", "2026-09-01T10:01:00.000Z", tools=OUTCOME)])
        runs, _, _ = recorder.build(self.source, PRICES, RAILS, {},
                                    decisions=[started("2026-09-01T09:59:55Z", "P-0001-T64")],
                                    settings={"idle_gap_minutes": 10, "ceiling_messages": 90})
        run = runs[0]
        for field in ("task_ref", "task_link_method", "ended_how", "ended_how_basis",
                      "active_minutes", "wall_minutes", "idle_gap_minutes",
                      "assistant_messages", "censored"):
            self.assertIn(field, run)
        self.assertEqual((run["task_ref"], run["task_link_method"], run["ended_how"]),
                         ("P-0001-T64", "marker", "finished"))
        self.assertEqual(run["active_minutes"], 1.0)

    def test_settings_come_from_the_gate_file(self):
        gate = self.root / "gate.json"
        gate.write_text(json.dumps({"session_ceiling_assistant_messages": 90,
                                    "session_idle_gap_minutes": 15}))
        self.assertEqual(recorder.load_session_settings(gate),
                         {"idle_gap_minutes": 15, "ceiling_messages": 90})

    def test_decisions_are_read_for_board_records_only(self):
        folder = self.root / "decisions"
        folder.mkdir()
        (folder / "2026-09.jsonl").write_text(
            json.dumps(started("2026-09-01T10:00:00Z", "P-0001-T64")) + "\n"
            + json.dumps({"kind": "TaskTransition", "at": "2026-09-01T10:00:00Z"}) + "\n"
            + "{not json\n")
        self.assertEqual([r["kind"] for r in recorder.load_decisions(folder)], ["SessionStarted"])


class Accounts(unittest.TestCase):
    STATED = {"observed_on": "2026-09-16",
              "cross_check_rule": {"stated_switch_at": "2026-09-15T07:00:00Z",
                                   "account_after": "account-2"}}

    def line(self, owner, stamp):
        return {"type": "user", "timestamp": stamp, "ownerAccountUuid": owner}

    def test_labels_follow_first_appearance_and_never_carry_the_id(self):
        labels = sessions.account_labels([[self.line("zzz", "2026-09-15T20:00:00Z")],
                                          [self.line("aaa", "2026-09-03T10:00:00Z")]])
        self.assertEqual(labels, {"aaa": "account-1", "zzz": "account-2"})
        account, basis = sessions.account_for([self.line("zzz", "2026-09-15T20:00:00Z")],
                                              labels, "2026-09-15T20:00:00Z", self.STATED)
        self.assertEqual(account, "account-2")
        self.assertNotIn("zzz", basis)

    def test_a_session_after_the_stated_switch_on_the_first_account_says_so(self):
        labels = {"aaa": "account-1", "zzz": "account-2"}
        account, basis = sessions.account_for([self.line("aaa", "2026-09-15T09:00:00Z")],
                                              labels, "2026-09-15T09:00:00Z", self.STATED)
        self.assertEqual(account, "account-1")
        self.assertIn("DISAGREES", basis)

    def test_before_the_stated_switch_there_is_nothing_to_disagree_with(self):
        labels = {"aaa": "account-1"}
        _, basis = sessions.account_for([self.line("aaa", "2026-09-14T09:00:00Z")],
                                        labels, "2026-09-14T09:00:00Z", self.STATED)
        self.assertNotIn("DISAGREES", basis)

    def test_an_owner_on_a_line_with_no_timestamp_is_dated_by_its_session(self):
        """How the transcripts actually carry it: one bookkeeping line, no timestamp."""
        early = [{"type": "user", "timestamp": "2026-09-03T10:00:00Z"},
                 {"type": "bridge-session", "ownerAccountUuid": "zzz"}]
        late = [{"type": "user", "timestamp": "2026-09-15T20:00:00Z"},
                {"type": "bridge-session", "ownerAccountUuid": "aaa"}]
        self.assertEqual(sessions.account_labels([late, early]),
                         {"zzz": "account-1", "aaa": "account-2"})

    def test_two_accounts_in_one_session_is_mixed_and_none_is_null(self):
        labels = {"aaa": "account-1", "zzz": "account-2"}
        self.assertEqual(sessions.account_for(
            [self.line("aaa", "2026-09-15T09:00:00Z"), self.line("zzz", "2026-09-15T09:01:00Z")],
            labels, "2026-09-15T09:00:00Z")[0], "mixed")
        self.assertIsNone(sessions.account_for([{"type": "user"}], labels, None)[0])


class TestTheDesktopSignInNamesAnUnlabelledSession(unittest.TestCase):
    """17 September 2026: 12 of September's runs named no account, because Claude
    Code writes the owner only while Remote Control is on. The desktop app's usage
    history names the signed-in account every ~15 minutes, keyed by organisation."""

    LABELS = {"aaa": "account-1", "zzz": "account-2"}
    BARE = [{"type": "user", "timestamp": "2026-09-16T10:05:00Z"}]

    def account(self, desktop, records=None, ended="2026-09-16T10:20:00Z"):
        return sessions.account_for(records or self.BARE, self.LABELS, "2026-09-16T10:05:00Z",
                                    desktop=desktop, ended_at=ended)

    def test_one_account_over_the_span_names_it_and_says_it_is_the_second_source(self):
        account, basis = self.account([("2026-09-16T09:57:00Z", "account-2"),
                                       ("2026-09-16T10:12:00Z", "account-2")])
        self.assertEqual(account, "account-2")
        self.assertIn("desktop app's sign-in", basis)
        self.assertIn("Remote Control", basis)

    def test_two_accounts_over_the_span_is_not_guessed(self):
        account, basis = self.account([("2026-09-16T09:57:00Z", "account-1"),
                                       ("2026-09-16T10:12:00Z", "account-2")])
        self.assertIsNone(account)
        self.assertIn("more than one account", basis)

    def test_an_organisation_no_transcript_names_is_not_an_answer(self):
        self.assertIsNone(self.account([("2026-09-16T10:00:00Z", None)])[0])

    def test_no_sample_over_the_span_says_so(self):
        account, basis = self.account([("2026-09-16T08:00:00Z", "account-2")])
        self.assertIsNone(account)
        self.assertIn("no sample", basis)

    def test_the_transcript_wins_where_it_names_the_owner(self):
        records = [{"type": "bridge-session", "ownerAccountUuid": "aaa"}]
        self.assertEqual(self.account([("2026-09-16T10:00:00Z", "account-2")], records)[0],
                         "account-1")

    def test_the_join_is_by_hashed_organisation_and_never_holds_the_id(self):
        records = [[{"type": "bridge-session", "ownerAccountUuid": "aaa",
                     "ownerOrganizationUuid": "org-1"}]]
        joined = sessions.org_labels(records, self.LABELS, lambda org: "h:" + org[::-1])
        self.assertEqual(joined, {"h:1-gro": "account-1"})


if __name__ == "__main__":
    unittest.main()


class WhatCountsAsFinished(unittest.TestCase):
    """P-0001-T64, 17 September 2026. Until today only an outcome counted, so a
    session that wrote the next brief and committed was recorded as an ending
    nobody could name. Absence of one command was read as absence of a close."""

    @staticmethod
    def _transcript(command):
        return [
            {"type": "user", "timestamp": "2026-09-17T10:00:00Z",
             "message": {"content": [{"type": "text", "text": "go"}]}},
            {"type": "assistant", "timestamp": "2026-09-17T10:01:00Z",
             "message": {"stop_reason": "end_turn", "content": [
                 {"type": "tool_use", "name": "Bash", "input": {"command": command}}]}},
        ]

    def test_a_commit_is_a_close(self):
        how, basis = sessions.ending(self._transcript("git commit -F /tmp/m.txt"))
        self.assertEqual(how, "finished")
        self.assertIn("committed its work", basis)

    def test_a_handoff_is_a_close(self):
        how, basis = sessions.ending(self._transcript("python3 store/store.py --handoff P-0001-T33 --text-file x"))
        self.assertEqual(how, "finished")
        self.assertIn("next session", basis)

    def test_an_outcome_is_still_a_close(self):
        how, basis = sessions.ending(self._transcript("python3 store/store.py --outcome P-0001-T33 --text x"))
        self.assertEqual(how, "finished")
        self.assertIn("recorded an outcome", basis)

    def test_saying_it_finished_is_not_finishing(self):
        records = [
            {"type": "user", "timestamp": "2026-09-17T10:00:00Z",
             "message": {"content": [{"type": "text", "text": "go"}]}},
            {"type": "assistant", "timestamp": "2026-09-17T10:01:00Z",
             "message": {"stop_reason": "end_turn", "content": [
                 {"type": "text", "text": "I committed the work and wrote the handoff."}]}},
        ]
        how, basis = sessions.ending(records)
        self.assertEqual(how, "unknown")
        self.assertIn("none of the closing acts", basis)

    def test_closing_at_the_ceiling_keeps_the_ceiling_in_the_basis(self):
        how, basis = sessions.ending(self._transcript("git commit -m x"),
                                     assistant_messages=180, ceiling_messages=180)
        self.assertEqual(how, "finished")
        self.assertIn("message ceiling", basis)
