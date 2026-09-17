#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The usage page, pasted -- R4 of package/RECKON-1.2-SPEC.md.

THE FIXTURE. R4's acceptance test is "the 16 September paste in this spec parses
to 9%, 22%, the two reset times and the four product figures". The owner's paste of
about 06:20 BST on 16 September 2026 was NOT kept verbatim anywhere in this
repository -- only its contents, bulleted, in section 2 of the spec and in
P-0001-T64's outcome. PANEL below is therefore the page reassembled from those
two records, line by line, and it is a reconstruction rather than a transcript.
Every figure in it is one of theirs and none is invented. Where the real page
differs it will differ in wording and layout, which is exactly what the parser
is written to survive, and what the unrecognised-lines list is for.

Nothing here is a bill, and no percentage is turned into money.
"""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import usage_paste  # noqa: E402

#: Reassembled from package/RECKON-1.2-SPEC.md section 2 and P-0001-T64's
#: session-1 outcome. See the module docstring.
PANEL = """Usage
Pro plan
On track. You should reach Saturday's reset with room to spare.
Current session
9% used
Resets at 11:00 AM
This week
22% used
Resets Saturday 8:00 AM
Usage credits
$0
Turn on usage credits
This week's usage by product
Claude Code 98%
Chats 0%
Cowork 2%
Other 0%
Last updated: just now
The summer promotion ended on 13 September and your weekly limit is now 25% higher than before the promotion."""

#: The same reading as one line, the way it arrives when a browser's copy
#: flattens the panel.
ONE_LINE = ("Session 9% resetting at 11:00 AM, Week 22% resetting Saturday 8:00 AM, "
            "Claude Code 98%, Chats 0%, Cowork 2%, Other 0%")

TAKEN_AT = "2026-09-16T05:20:00Z"


class TheSixteenthOfSeptemberPaste(unittest.TestCase):
    """R4's own acceptance test, figure by figure."""

    def setUp(self):
        self.reading = usage_paste.parse(PANEL, taken_at=TAKEN_AT)

    def test_it_is_readable(self):
        self.assertTrue(self.reading["readable"], self.reading["problems"])

    def test_the_session_percentage_is_nine(self):
        self.assertEqual(self.reading["five_hour_percent"], 9)

    def test_the_week_percentage_is_twenty_two(self):
        self.assertEqual(self.reading["seven_day_percent"], 22)

    def test_both_reset_times_are_read(self):
        self.assertEqual(self.reading["five_hour_resets_at_text"], "11:00 AM")
        self.assertEqual(self.reading["seven_day_resets_at_text"], "Saturday 8:00 AM")

    def test_the_four_product_figures_are_read(self):
        self.assertEqual(self.reading["product_split_percent"],
                         {"Claude Code": 98, "Chats": 0, "Cowork": 2, "Other": 0})

    def test_the_plan_is_read(self):
        self.assertEqual(self.reading["plan"], "Pro")

    def test_the_credit_balance_is_kept_as_the_page_wrote_it(self):
        self.assertEqual(self.reading["usage_credits_text"], "$0")

    def test_the_forecast_sentence_is_kept(self):
        self.assertIn("room to spare", self.reading["forecast"])

    def test_the_notice_about_the_changed_limit_is_kept(self):
        self.assertEqual(len(self.reading["notices"]), 1)
        self.assertIn("promotion", self.reading["notices"][0])

    def test_the_notice_is_not_read_as_a_week_percentage_of_twenty_five(self):
        """The notice says the weekly limit is 25% higher. That is a sentence
        about the scale, and reading it as a measurement on the scale would put
        a number in the record that nothing on the page ever claimed."""
        self.assertEqual(self.reading["seven_day_percent"], 22)

    def test_last_updated_is_kept_as_text(self):
        self.assertEqual(self.reading["last_updated_text"], "just now")

    def test_the_moment_it_was_taken_is_carried(self):
        self.assertEqual(self.reading["taken_at"], TAKEN_AT)

    def test_a_line_it_did_not_recognise_is_kept_verbatim(self):
        self.assertEqual(self.reading["unrecognised_lines"], ["Usage"])

    def test_it_says_the_weekly_scale_changed(self):
        self.assertTrue(any(usage_paste.WEEKLY_SCALE_BREAK in note
                            for note in self.reading["notes"]))

    def test_no_percentage_becomes_money(self):
        text = json.dumps(self.reading)
        self.assertNotIn("gbp", text.lower())
        self.assertEqual(text.count("$"), 1)      # the credit balance, as written


class TheFlattenedPaste(unittest.TestCase):
    """The same reading with the panel copied onto one line."""

    def setUp(self):
        self.reading = usage_paste.parse(ONE_LINE, taken_at=TAKEN_AT)

    def test_both_percentages_survive_the_flattening(self):
        self.assertEqual(self.reading["five_hour_percent"], 9)
        self.assertEqual(self.reading["seven_day_percent"], 22)

    def test_both_reset_times_survive_the_flattening(self):
        self.assertEqual(self.reading["five_hour_resets_at_text"], "11:00 AM")
        self.assertEqual(self.reading["seven_day_resets_at_text"], "Saturday 8:00 AM")

    def test_the_product_split_survives_the_flattening(self):
        self.assertEqual(self.reading["product_split_percent"]["Claude Code"], 98)


class APanelItCannotRead(unittest.TestCase):
    """R4: a panel it cannot read says so and saves nothing."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.observations = Path(self._tmp.name) / "observations.jsonl"

    def tearDown(self):
        self._tmp.cleanup()

    def run_it(self, text, **kwargs):
        buffer = io.StringIO()
        rc = usage_paste.run(text=text, observations=self.observations, out=buffer,
                             assume_yes=True, **kwargs)
        return rc, buffer.getvalue()

    def test_prose_with_no_figures_is_refused(self):
        rc, printed = self.run_it("Your usage is fine, do not worry about it.")
        self.assertEqual(rc, 2)
        self.assertIn("could not be read", printed)
        self.assertFalse(self.observations.exists())

    def test_an_empty_paste_is_refused(self):
        rc, printed = self.run_it("   \n  ")
        self.assertEqual(rc, 2)
        self.assertIn("nothing was pasted", printed.lower())
        self.assertFalse(self.observations.exists())

    def test_half_a_panel_is_refused_and_says_which_half(self):
        rc, printed = self.run_it("Current session\n9% used\nResets at 11:00 AM")
        self.assertEqual(rc, 2)
        self.assertIn("no week (seven-day) percentage", printed)
        self.assertFalse(self.observations.exists())

    def test_a_missing_percentage_is_never_filled_in_with_a_zero(self):
        reading = usage_paste.parse("Current session\n9% used")
        self.assertIsNone(reading["seven_day_percent"])

    def test_a_percentage_over_a_hundred_is_not_taken(self):
        reading = usage_paste.parse("Current session\n900% used\nThis week\n22% used")
        self.assertIsNone(reading["five_hour_percent"])
        self.assertFalse(reading["readable"])


class WhatItSaysWhenSomethingIsMissing(unittest.TestCase):
    """A reading can be usable and still be incomplete. It says which."""

    def test_no_reset_time_is_a_note_not_a_refusal(self):
        reading = usage_paste.parse("Current session\n9% used\nThis week\n22% used")
        self.assertTrue(reading["readable"])
        self.assertTrue(any("no reset time for the session limit" in note
                            for note in reading["notes"]))

    def test_no_product_split_is_a_note(self):
        reading = usage_paste.parse("Current session\n9% used\nThis week\n22% used")
        self.assertTrue(any("no split by product" in note for note in reading["notes"]))

    def test_no_moment_taken_is_a_note(self):
        reading = usage_paste.parse(PANEL)
        self.assertTrue(any("was not recorded" in note for note in reading["notes"]))

    def test_the_account_is_null_unless_it_is_given(self):
        self.assertIsNone(usage_paste.parse(PANEL)["account"])
        self.assertEqual(usage_paste.parse(PANEL, account="account-2")["account"], "account-2")

    def test_it_never_claims_to_know_which_account_the_page_was(self):
        reading = usage_paste.parse(PANEL, taken_at=TAKEN_AT)
        self.assertTrue(any("does not say which account" in note
                            for note in reading["notes"]))


class SavingIsAnObservation(unittest.TestCase):
    """Decision 3: every reading is an observation, appended. Never an
    overwrite -- two sources that disagree are both kept."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.observations = Path(self._tmp.name) / "observations.jsonl"

    def tearDown(self):
        self._tmp.cleanup()

    def saved(self):
        return [json.loads(line) for line in
                self.observations.read_text(encoding="utf-8").splitlines() if line.strip()]

    def run_it(self, text=PANEL, **kwargs):
        buffer = io.StringIO()
        kwargs.setdefault("taken_at", TAKEN_AT)
        rc = usage_paste.run(text=text, observations=self.observations, out=buffer, **kwargs)
        return rc, buffer.getvalue()

    def test_a_yes_saves_one_record(self):
        rc, printed = self.run_it(assume_yes=True)
        self.assertEqual(rc, 0)
        self.assertIn("Saved one observation", printed)
        self.assertEqual(len(self.saved()), 1)
        self.assertEqual(self.saved()[0]["five_hour_percent"], 9)

    def test_it_shows_what_it_read_before_it_asks(self):
        asked = []

        def ask():
            asked.append(True)
            return "y"

        buffer = io.StringIO()
        usage_paste.run(text=PANEL, taken_at=TAKEN_AT, observations=self.observations,
                        out=buffer, ask=ask)
        shown = buffer.getvalue()
        self.assertIn("session (five-hour): 9%", shown)
        self.assertIn("week (seven-day):    22%", shown)
        self.assertTrue(asked)
        self.assertEqual(len(self.saved()), 1)

    def test_anything_but_a_yes_saves_nothing(self):
        buffer = io.StringIO()
        rc = usage_paste.run(text=PANEL, taken_at=TAKEN_AT, observations=self.observations,
                             out=buffer, ask=lambda: "")
        self.assertEqual(rc, 0)
        self.assertIn("Nothing saved", buffer.getvalue())
        self.assertFalse(self.observations.exists())

    def test_a_second_reading_is_appended_not_an_overwrite(self):
        self.run_it(assume_yes=True)
        self.run_it(assume_yes=True, taken_at="2026-09-16T09:00:00Z")
        records = self.saved()
        self.assertEqual(len(records), 2)
        self.assertEqual([r["taken_at"] for r in records],
                         [TAKEN_AT, "2026-09-16T09:00:00Z"])

    def test_every_record_is_stamped_with_when_it_was_recorded(self):
        self.run_it(assume_yes=True)
        self.assertTrue(self.saved()[0]["recorded_at"].endswith("Z"))

    def test_the_record_names_its_source(self):
        self.run_it(assume_yes=True)
        self.assertIn("paste", self.saved()[0]["source"])
        self.assertEqual(self.saved()[0]["kind"], usage_paste.KIND)

    def test_a_paste_read_from_a_file(self):
        path = Path(self._tmp.name) / "paste.txt"
        path.write_text(PANEL, encoding="utf-8")
        buffer = io.StringIO()
        rc = usage_paste.run(file=str(path), taken_at=TAKEN_AT, assume_yes=True,
                             observations=self.observations, out=buffer)
        self.assertEqual(rc, 0)
        self.assertEqual(self.saved()[0]["seven_day_percent"], 22)

    def test_a_file_that_is_not_there_is_reported(self):
        buffer = io.StringIO()
        rc = usage_paste.run(file=str(Path(self._tmp.name) / "nope.txt"), out=buffer)
        self.assertEqual(rc, 2)
        self.assertIn("could not read the paste", buffer.getvalue())


class ToleratingADifferentPanel(unittest.TestCase):
    """The page is Anthropic's and it will change. A panel this parser has not
    seen should degrade into unread lines, never into wrong figures."""

    def test_a_row_it_does_not_know_is_kept_verbatim(self):
        reading = usage_paste.parse(PANEL + "\nSomething new: 3 widgets")
        self.assertIn("Something new: 3 widgets", reading["unrecognised_lines"])

    def test_five_hour_and_seven_day_wording_is_understood_too(self):
        reading = usage_paste.parse("Five-hour limit\n40% used\nSeven-day limit\n61% used")
        self.assertEqual(reading["five_hour_percent"], 40)
        self.assertEqual(reading["seven_day_percent"], 61)

    def test_a_max_plan_is_read(self):
        self.assertEqual(usage_paste.parse("Max 20x plan\n" + PANEL)["plan"], "Max 20X")

    def test_the_two_blocks_may_come_in_either_order(self):
        """The page puts the session above the week. A panel that puts them the
        other way round is still the same two readings.

        WHAT IS NOT CLAIMED: that any order works. The page writes a label and
        then its value, and a parser that ignored that order would have to guess
        which label a loose percentage belonged to. It reads forwards, and a
        panel scrambled line by line is one it should fail on rather than
        silently attach 22% to the wrong limit."""
        reading = usage_paste.parse(
            "This week\n22% used\nResets Saturday 8:00 AM\n"
            "Current session\n9% used\nResets at 11:00 AM")
        self.assertEqual(reading["five_hour_percent"], 9)
        self.assertEqual(reading["seven_day_percent"], 22)
        self.assertEqual(reading["five_hour_resets_at_text"], "11:00 AM")

    def test_a_split_by_product_with_its_heading_lost_is_still_read(self):
        reading = usage_paste.parse(
            "Current session\n9% used\nThis week\n22% used\n"
            "Claude Code 98%, Chats 0%, Cowork 2%, Other 0%")
        self.assertEqual(reading["product_split_percent"],
                         {"Claude Code": 98, "Chats": 0, "Cowork": 2, "Other": 0})

    def test_one_unknown_row_on_its_own_is_not_guessed_to_be_a_product(self):
        reading = usage_paste.parse(PANEL + "\nSome new row 44%")
        self.assertNotIn("Some new row", reading["product_split_percent"])
        self.assertIn("Some new row 44%", reading["unrecognised_lines"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
