#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The usage page, pasted whole -- R4 of package/RECKON-1.2-SPEC.md.

Usage: python3 usage_paste.py --file <the paste> [--taken-at ...] [--yes] [--json]

WHY THIS EXISTS. The desktop app's file (ledger/plan_usage.py) has no reset
times and no product split, and it is only written while the app is running, so
its newest sample can be hours old. When a live reading is needed and the file
is stale, the page in Claude's settings is asked for. THE WHOLE PANEL IS PASTED
AND THIS MODULE PICKS OUT WHAT IT WANTS. It never asks for a field at a time:
The owner's standing rule is paste it all, the machine dedupes.

WHAT IT TAKES OUT of the panel: the plan, the five-hour (session) percentage and
its reset time, the seven-day (week) percentage and its reset time, the usage
credit balance as written, this week's split by product, the forecast sentence,
the "last updated" line, and any notice about the limits changing. EVERY LINE IT
DID NOT RECOGNISE IS KEPT VERBATIM, because a panel that has grown a new row
should show up as an unread line rather than silently vanish.

WHAT IT REFUSES. A panel with no session percentage and no week percentage is a
panel this module cannot read: it says so and saves nothing. Nothing is guessed
and no missing figure is filled in with a zero.

THREE THINGS IT DELIBERATELY DOES NOT DO:

  * It does not turn a percentage into money. Decision 4 of the 1.2.0 spec, and
    the same rule that keeps `cost_to_date_gbp` null. The credit balance is kept
    as the text the page showed ("$0"), never converted and never re-rated.
  * It does not resolve a reset time into a date. The page gives a clock time
    only ("11:00 AM", "Saturday 8:00 AM") with no date and no zone, so resolving
    it would be this module inventing a timezone. The text is kept and the
    moment the paste was taken is kept beside it; that is enough to read it and
    not enough to be wrong.
  * It does not name the account. The page does not say which account it is;
    whoever was signed in when it was taken is a fact about the moment, not
    about the text. Pass --account when it is known.

THE WEEKLY SCALE BREAK is carried through: the summer promotion ended on
13 September 2026 and the weekly limit rose about 25%, so a week percentage from
before that date and one from after are not two readings of the same thing.

No third-party dependencies, no network.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_OBSERVATIONS = HERE / "plan-usage-observations.jsonl"

WEEKLY_SCALE_BREAK = "2026-09-13"
KIND = "PlanUsageObservation"

PERCENT = re.compile(r"(\d{1,3})\s*%")
MONEY = re.compile(r"([$£€])\s*([\d,]+(?:\.\d{1,2})?)")
PLAN = re.compile(r"\b(free|pro|max(?:\s*\d+\s*x)?|team|enterprise)\s+plan\b", re.I)
RESET = re.compile(r"\breset(?:s|ting|ting\s+in)?\b\s*(?:at\s+|on\s+|in\s+)?(.*)$", re.I)
PRODUCT_HEADING = re.compile(r"\bby product\b", re.I)
PRODUCT_ROW = re.compile(r"^(.+?)[\s.:…-]*(\d{1,3})\s*%\s*$")
LAST_UPDATED = re.compile(r"^last updated\s*:?\s*(.+?)\s*$", re.I)
CREDITS = re.compile(r"\busage credits?\b", re.I)
TURN_ON = re.compile(r"\bturn on\b|\benable\b|\bbuy\b|\badd credits?\b", re.I)
SESSION_LABEL = re.compile(r"\b(current\s+session|session|five[-\s]?hour|5[-\s]?hour)\b", re.I)
WEEK_LABEL = re.compile(r"\b(this\s+week|week(?:ly)?|seven[-\s]?day|7[-\s]?day)\b", re.I)
FORECAST = re.compile(r"\bon track\b|\byou should reach\b|\byou(?:'ll| will) (?:run out|reach)\b"
                      r"|\bwith room to spare\b|\bat this rate\b", re.I)
NOTICE = re.compile(r"\bpromotion\b|\blimit is now\b|\bhigher than\b|\bchanged on\b", re.I)

# THE CREDITS BLOCK, added 17 September 2026 (P-0001-T19).
#
# The 17 September paste of account-1 kept NINE lines verbatim and four of them
# were the whole credits answer: a monthly credit spend limit of GBP 150.00,
# 81% of it used, resetting Oct 1, and a current balance of GBP 0.00 with
# auto-reload off. Every one was legible to a person and none of it reached a
# field, so the question this register raised on 6 September -- do runs bill to
# credits -- could not be answered from what the machine had saved.
#
# THE LAYOUT PROBLEM, and it is why this is not four more label regexes in the
# main loop. On that page the money sits on its OWN line and the label that
# names it can arrive either side of it: the paste has "GBP 150.00" and then
# "Monthly credit spend limit", while the 16 September panel has "Usage credits"
# and then "$0". So each label claims the nearest bare-money line that no other
# label has claimed, preferring the one before it on a tie, and a line no label
# claims stays unrecognised rather than being attached to the closest guess.
#
# `Current balance.Auto-reloadOff` arrives as one run of text with the labels
# glued together, so labels are matched inside a segment rather than against it.
SPEND_LIMIT_LABEL = re.compile(r"\b(?:monthly\s+)?credit\s+spend\s+limit\b", re.I)
BALANCE_LABEL = re.compile(r"\bcurrent\s+balance\b", re.I)
AUTO_RELOAD = re.compile(r"\bauto[-\s]?reload\s*[:.\u00b7-]?\s*(on|off)?", re.I)
PERCENT_USED = re.compile(r"(\d{1,3})\s*%\s*used\b", re.I)
# A money line of its own, with the one trailing word the page sometimes puts
# on it ("\u00a3121.50 spent"). The real 17 September paste carries that word and
# the reassembled one did not, which is exactly the difference a real paste
# was asked for to find. The word is evidence, not noise: "spent" says which
# of the two things a credits figure is, and the page saying so beats this
# module inferring it from the presence of a spend limit.
BARE_MONEY = re.compile(r"^([$\u00a3\u20ac]\s*[\d,]+(?:\.\d{1,2})?)"
                        r"(?:\s+(spent|used|remaining|left))?$", re.I)
# How far a label may reach for the figure it names. The page can put the money
# above the label or below it, but never across the panel: without this, "Usage
# credits" reached six lines down and claimed the SPEND LIMIT as the balance.
CLAIM_WINDOW = 2
# The five-hour limit resets in hours and the week resets on a weekday. The only
# thing on this page that resets on a calendar date is the credit spend limit,
# so a reset naming a month belongs to it and to nothing else.
MONTH = (r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec")
DATED_RESET = re.compile(
    r"^resets?\s+(?:on\s+)?((?:" + MONTH + r")[a-z]*\.?\s+\d{1,2}"
    r"|\d{1,2}\s+(?:" + MONTH + r")[a-z]*\.?"
    r"|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\s*$", re.I)
# The page's navigation furniture, and only that. Kept out of the unrecognised
# list so the list keeps meaning what it says: a row this parser has never seen.
# Deliberately narrow -- "Usage", "All models" and anything else that might one
# day carry a figure or a scope stay unrecognised and visible, because a row
# quietly dropped is the one failure this list exists to prevent.
CHROME = re.compile(r"^(?:learn more\b.*|manage\b.*|upgrade\b.*)$", re.I)
# "Plan usage limitsPro" -- the heading with the plan name run onto it.
PLAN_HEADING = re.compile(r"\bplan usage limits\s*"
                          r"(free|pro|max(?:\s*\d+\s*x)?|team|enterprise)\b", re.I)
PLAN_BARE_HEADING = re.compile(r"^plan usage limits$", re.I)
PLAN_WORD = re.compile(r"free|pro|max(?:\s*\d+\s*x)?|team|enterprise", re.I)


def _segments(line):
    """A panel line as the one-or-more readings it holds.

    The page renders a label, its percentage and its reset time on separate
    lines; copied out of a browser they can arrive on one comma-separated line
    instead ("Session 9% resetting at 11:00 AM, Week 22% resetting Saturday
    8:00 AM"). Splitting on commas only where a line carries more than one
    percentage keeps "Resets Saturday 8:00 AM" and any prose sentence whole.
    """
    if len(PERCENT.findall(line)) > 1 and "," in line:
        return [part.strip() for part in line.split(",") if part.strip()]
    return [line.strip()] if line.strip() else []


def _is_labelled(segment):
    return bool(SESSION_LABEL.search(segment) or WEEK_LABEL.search(segment)
                or CREDITS.search(segment) or PLAN.search(segment)
                or NOTICE.search(segment) or FORECAST.search(segment)
                or PRODUCT_HEADING.search(segment))


def _product_row_segments(segments):
    """The segments of ONE line that are a split by product with no heading.

    The panel normally announces the split ("This week's usage by product") and
    then lists it. Flattened onto one line by a browser's copy, the heading can
    be lost and only the rows arrive. Two or more name-and-percentage segments
    on a single line, none of them a label this parser already knows, is that
    list; one on its own is not, because one is what an unread row looks like.
    """
    rows = [s for s in segments if PRODUCT_ROW.match(s) and not _is_labelled(s)]
    return set(rows) if len(rows) > 1 else set()


def _whole_percent(text):
    found = PERCENT.search(text)
    if not found:
        return None
    value = int(found.group(1))
    return value if 0 <= value <= 100 else None


def _reset_text(text):
    found = RESET.search(text)
    if not found:
        return None
    rest = found.group(1).strip(" .…")
    return rest or None


def _split_glued(segment):
    """`Current balance.Auto-reloadOff` as its parts. The page glues adjacent
    labels together when it is copied, so a label is looked for INSIDE a
    segment; this only exists so the parts can be reported separately."""
    return [part.strip() for part in re.split(r"[\u00b7|]", segment) if part.strip()]


def _read_credits(segments):
    """The credits block, read as a whole rather than line by line.

    `segments` is every segment of the paste in order. Returns what was read and
    the set of segment positions it used, so the main loop can skip them and the
    unrecognised list stays honest.

    Each label claims the nearest bare-money segment that no other label has
    claimed, preferring the one before it where the distance is equal, because
    the page puts the figure above its label as often as beside it. A money line
    no label claims is not attached to anything.
    """
    found = {"usage_credits_text": None, "credit_spend_limit_text": None,
             "credit_spend_limit_percent_used": None,
             "credit_spend_limit_resets_text": None, "credit_balance_text": None,
             "credit_spend_this_month_text": None, "auto_reload": None}
    used = set()

    money_at = {i: BARE_MONEY.match(seg) for i, seg in enumerate(segments)
                if BARE_MONEY.match(seg)}
    claimed = set()

    def claim(index):
        """The nearest unclaimed money segment within reach of `index`.

        Returns the money as the page wrote it and the one qualifying word it
        carried, if any. Out of reach is None: a label with no figure beside it
        has no figure, and the line stays unrecognised.
        """
        candidates = sorted((abs(i - index), 0 if i < index else 1, i)
                            for i in money_at
                            if i not in claimed and abs(i - index) <= CLAIM_WINDOW)
        if not candidates:
            return None, None
        _, _, at = candidates[0]
        claimed.add(at)
        used.add(at)
        found_at = money_at[at]
        return found_at.group(1).replace(" ", ""), (found_at.group(2) or "").lower()

    # Order matters only in that each label takes its own nearest line first.
    labels = [(CREDITS, "usage_credits_text"),
              (SPEND_LIMIT_LABEL, "credit_spend_limit_text"),
              (BALANCE_LABEL, "credit_balance_text")]
    region = None
    for index, segment in enumerate(segments):
        if SESSION_LABEL.search(segment) or WEEK_LABEL.search(segment):
            region = "limits"
        if (CREDITS.search(segment) or SPEND_LIMIT_LABEL.search(segment)
                or BALANCE_LABEL.search(segment) or AUTO_RELOAD.search(segment)):
            region = "credits"
        for part in _split_glued(segment):
            for pattern, field in labels:
                if not pattern.search(part) or found[field] is not None:
                    continue
                if pattern is CREDITS and TURN_ON.search(part) and not MONEY.search(part):
                    # "Turn on usage credits" is a button, not a reading.
                    used.add(index)
                    continue
                inline = MONEY.search(part)
                if inline:
                    found[field], qualifier = inline.group(0).replace(" ", ""), ""
                else:
                    found[field], qualifier = claim(index)
                if found[field] is not None:
                    used.add(index)
                    if field == "usage_credits_text" and qualifier == "spent":
                        # The page said which of the two it is, so nothing is
                        # inferred from the presence of a limit.
                        found["credit_spend_this_month_text"] = found[field]
            reload_at = AUTO_RELOAD.search(part)
            if reload_at and found["auto_reload"] is None:
                # The state can be glued on ("Auto-reloadOff") or sit on the
                # next segment of its own. Only on/off is read; anything else
                # is left unrecognised rather than guessed at.
                state = reload_at.group(1)
                if not state and index + 1 < len(segments):
                    following = segments[index + 1].strip()
                    if following.lower() in ("on", "off"):
                        state, _ = following, used.add(index + 1)
                if state:
                    found["auto_reload"] = state.lower()
                    used.add(index)

        percent_used = PERCENT_USED.match(segment.strip())
        if (percent_used and region == "credits"
                and found["credit_spend_limit_percent_used"] is None):
            # A bare "81% used" standing in the credits block. The session and
            # the week write their percentages exactly the same way, so this is
            # read by which block it is in and by nothing else; a bare
            # percentage in neither block stays unrecognised.
            found["credit_spend_limit_percent_used"] = int(percent_used.group(1))
            used.add(index)

        dated = DATED_RESET.match(segment.strip())
        if dated and found["credit_spend_limit_resets_text"] is None:
            found["credit_spend_limit_resets_text"] = dated.group(1)
            used.add(index)

    return found, used


def parse(text, taken_at=None, account=None):
    """The panel, read. Returns a dict in the shape ledger/plan_usage.py reports
    a sample in, plus what only the page carries.

    `readable` is False where neither percentage was found; the caller saves
    nothing in that case and says why.
    """
    reading = {
        "kind": KIND,
        "source": "paste of the usage page in Claude's settings",
        "taken_at": taken_at,
        "account": account,
        "plan": None,
        "five_hour_percent": None,
        "five_hour_resets_at_text": None,
        "seven_day_percent": None,
        "seven_day_resets_at_text": None,
        "usage_credits_text": None,
        # The credits block (P-0001-T19). Kept as the page wrote them and never
        # converted, the same rule the balance has always had.
        "credit_spend_limit_text": None,
        "credit_spend_limit_percent_used": None,
        "credit_spend_limit_resets_text": None,
        "credit_spend_this_month_text": None,
        "credit_balance_text": None,
        "auto_reload": None,
        "product_split_percent": {},
        "forecast": None,
        "notices": [],
        "last_updated_text": None,
        "unrecognised_lines": [],
        "readable": False,
        "problems": [],
        "notes": [],
    }

    pending = None            # "five_hour", "seven_day" or "credits"
    in_products = False

    # The credits block is read first and as a whole, because its labels and
    # its figures are on separate lines and either can come first (P-0001-T19).
    # `credit_used` is the positions it consumed, in the same flat numbering the
    # loop below counts with, so nothing is read twice and nothing it took is
    # reported as unrecognised.
    lines = (text or "").splitlines()
    flat = [segment for line in lines for segment in _segments(line)]
    credits_found, credit_used = _read_credits(flat)
    reading.update({key: value for key, value in credits_found.items()
                    if value is not None})

    position = -1
    for line in lines:
        recognised = False
        segments = _segments(line)
        headless_products = _product_row_segments(segments)
        for segment in segments:
            position += 1
            if position in credit_used:
                recognised = True
                continue
            if CHROME.match(segment.strip()):
                # The page's own furniture, so the unrecognised list keeps
                # meaning "a row this parser has never seen".
                recognised = True
                continue
            if PLAN_HEADING.search(segment) and reading["plan"] is None:
                reading["plan"] = PLAN_HEADING.search(segment).group(1).strip().title()
                recognised = True
                continue
            if PLAN_BARE_HEADING.match(segment.strip()) and reading["plan"] is None:
                # "Plan usage limits" with the plan name on the line below it,
                # which is how the real page renders it. The name alone is not
                # read as a plan anywhere else: it only counts directly under
                # this heading.
                following = flat[position + 1].strip() if position + 1 < len(flat) else ""
                if PLAN_WORD.fullmatch(following):
                    reading["plan"] = following.title()
                    credit_used.add(position + 1)   # it was read, so it is not unread
                recognised = True
                continue
            if segment in headless_products:
                row = PRODUCT_ROW.match(segment)
                reading["product_split_percent"][row.group(1).strip()] = int(row.group(2))
                recognised = True
                continue

            if LAST_UPDATED.match(segment):
                reading["last_updated_text"] = LAST_UPDATED.match(segment).group(1)
                in_products = False
                recognised = True
                continue

            if PRODUCT_HEADING.search(segment):
                in_products, pending = True, None
                recognised = True
                # the heading may carry the first row with it
                row = PRODUCT_ROW.match(PRODUCT_HEADING.sub("", segment).strip())
                if row and _whole_percent(segment) is not None:
                    reading["product_split_percent"][row.group(1).strip()] = int(row.group(2))
                continue

            if PLAN.search(segment) and reading["plan"] is None:
                reading["plan"] = PLAN.search(segment).group(1).strip().title()
                recognised = True
                continue

            # Prose is checked BEFORE the labels, and this order is load-bearing.
            # The notice the page carried on 16 September reads "your weekly limit
            # is now 25% higher than before the promotion": read as a label it
            # would be a week reading of 25%, which is a sentence about the scale
            # turned into a measurement on it.
            if NOTICE.search(segment):
                reading["notices"].append(segment)
                in_products = False
                recognised = True
                continue

            if FORECAST.search(segment):
                reading["forecast"] = segment
                in_products = False
                recognised = True
                continue

            if CREDITS.search(segment):
                in_products = False
                money = MONEY.search(segment)
                if money:
                    reading["usage_credits_text"] = money.group(0).replace(" ", "")
                    pending = None
                elif not TURN_ON.search(segment):
                    pending = "credits"
                recognised = True
                continue

            is_session = bool(SESSION_LABEL.search(segment))
            is_week = bool(WEEK_LABEL.search(segment)) and not is_session
            if is_session or is_week:
                in_products = False
                pending = "five_hour" if is_session else "seven_day"
                percent = _whole_percent(segment)
                if percent is not None and reading[f"{pending}_percent"] is None:
                    reading[f"{pending}_percent"] = percent
                reset = _reset_text(segment)
                if reset and not reading[f"{pending}_resets_at_text"]:
                    reading[f"{pending}_resets_at_text"] = reset
                recognised = True
                continue

            if in_products:
                row = PRODUCT_ROW.match(segment)
                if row:
                    reading["product_split_percent"][row.group(1).strip()] = int(row.group(2))
                    recognised = True
                    continue

            if pending in ("five_hour", "seven_day"):
                percent = _whole_percent(segment)
                if percent is not None and reading[f"{pending}_percent"] is None:
                    reading[f"{pending}_percent"] = percent
                    recognised = True
                    continue
                reset = _reset_text(segment)
                if reset and not reading[f"{pending}_resets_at_text"]:
                    reading[f"{pending}_resets_at_text"] = reset
                    recognised = True
                    continue

            if pending == "credits":
                money = MONEY.search(segment)
                if money:
                    reading["usage_credits_text"] = money.group(0).replace(" ", "")
                    pending = None
                    recognised = True
                    continue

        if not recognised and line.strip():
            reading["unrecognised_lines"].append(line.rstrip())

    return _judge(reading)


def _judge(reading):
    """Say plainly what was read and what was not. Nothing is filled in."""
    if reading["five_hour_percent"] is None:
        reading["problems"].append("no session (five-hour) percentage in this panel")
    if reading["seven_day_percent"] is None:
        reading["problems"].append("no week (seven-day) percentage in this panel")
    reading["readable"] = not reading["problems"]

    if reading["readable"]:
        for field, name in (("five_hour_resets_at_text", "session"),
                            ("seven_day_resets_at_text", "week")):
            if not reading[field]:
                reading["notes"].append(
                    f"no reset time for the {name} limit: the percentage is here but the "
                    f"clock it runs against is not, so it cannot say how long it has to last")
        if not reading["product_split_percent"]:
            reading["notes"].append(
                "no split by product: this panel does not say how much of the account "
                "Claude Code accounts for")
        if not reading["taken_at"]:
            reading["notes"].append(
                "the moment this was taken was not recorded, and the page gives clock times "
                "with no dates, so the reset times cannot be placed")
    # WHAT THE CREDITS BLOCK MEANS, said only where the page itself said it.
    # No percentage becomes money here and no figure is derived from another --
    # these are statements about which reading is which, which is the thing
    # P-0001-T19 could not get out of a saved record on 17 September.
    if reading["credit_spend_limit_text"] and reading["usage_credits_text"]:
        reading["credit_spend_this_month_text"] = reading["usage_credits_text"]
        reading["notes"].append(
            "this page carries a monthly credit spend limit, so the usage-credits figure "
            "is what has been SPENT this month, not a balance: the balance is its own line")
    if reading["credit_balance_text"] and reading["auto_reload"] == "off":
        zero = re.fullmatch(r"[$\u00a3\u20ac]\s*0(?:\.0{1,2})?", reading["credit_balance_text"])
        reading["notes"].append(
            "the balance is nothing and auto-reload is off, so this account stops at its "
            "plan limit rather than spending" if zero else
            "auto-reload is off, so this balance is not topped up when it runs out")
    if reading["account"] is None:
        reading["notes"].append(
            "the page does not say which account it is; pass the account where it is known")
    reading["notes"].append(
        f"the weekly limit changed on {WEEKLY_SCALE_BREAK}: a week percentage from before "
        f"that date and one from after are not two readings of the same scale")
    reading["notes"].append(
        "every figure here is the account's own meter as its settings page showed it. It is "
        "not a bill, and the credit balance is kept as written and never converted")
    return reading


def describe(reading):
    """What was read, in words, for a person to agree to before it is saved."""
    out = ["Read from the paste:"]
    if reading["plan"]:
        out.append(f"  plan: {reading['plan']}")
    out.append(f"  session (five-hour): {_show(reading['five_hour_percent'])}"
               f"{_reset(reading['five_hour_resets_at_text'])}")
    out.append(f"  week (seven-day):    {_show(reading['seven_day_percent'])}"
               f"{_reset(reading['seven_day_resets_at_text'])}")
    if reading["usage_credits_text"]:
        out.append(f"  usage credits, as the page wrote it: {reading['usage_credits_text']}")
    if reading["credit_spend_limit_text"]:
        share = ("" if reading["credit_spend_limit_percent_used"] is None
                 else f", {reading['credit_spend_limit_percent_used']}% of it used")
        resets = ("" if not reading["credit_spend_limit_resets_text"]
                  else f", resets {reading['credit_spend_limit_resets_text']}")
        out.append(f"  monthly credit spend limit: "
                   f"{reading['credit_spend_limit_text']}{share}{resets}")
    if reading["credit_balance_text"]:
        out.append(f"  current balance: {reading['credit_balance_text']}")
    if reading["auto_reload"]:
        out.append(f"  auto-reload: {reading['auto_reload']}")
    if reading["product_split_percent"]:
        out.append("  this week by product: " + ", ".join(
            f"{name} {value}%" for name, value in reading["product_split_percent"].items()))
    if reading["forecast"]:
        out.append(f"  forecast: {reading['forecast']}")
    for notice in reading["notices"]:
        out.append(f"  notice: {notice}")
    if reading["last_updated_text"]:
        out.append(f"  last updated: {reading['last_updated_text']}")
    out.append(f"  taken at: {reading['taken_at'] or 'NOT RECORDED'}")
    out.append(f"  account: {reading['account'] or 'not stated by the page'}")
    if reading["unrecognised_lines"]:
        out.append(f"  {len(reading['unrecognised_lines'])} line(s) not recognised, kept "
                   f"verbatim:")
        out += [f"    | {line}" for line in reading["unrecognised_lines"]]
    for problem in reading["problems"]:
        out.append(f"  COULD NOT READ: {problem}")
    for note in reading["notes"]:
        out.append(f"  * {note}")
    return out


def _show(value):
    return "not found" if value is None else f"{value}%"


def _reset(text):
    return f", resets {text}" if text else ", no reset time on the page"


def save(reading, path=None, text=None):
    """Append one observation. Never an overwrite: two readings that disagree
    are both kept and both shown (1.2.0 decision 3).

    THE PASTE ITSELF IS KEPT, from 17 September (P-0001-T19). Twice now a gap
    in this parser has been found after the fact and the text it was found in
    was gone: the 16 September panel had to be REASSEMBLED from two prose
    records to serve as a test fixture, and the 17 September paste that showed
    the credits block missing could only be recovered as the nine lines it
    failed to read. A parser that keeps what it could not understand and throws
    away what it could cannot be improved against its own history. The page
    carries percentages and money about one account and names no one.
    """
    path = Path(path) if path else DEFAULT_OBSERVATIONS
    record = dict(reading)
    if text is not None:
        record["paste_text"] = text
    record["recorded_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return path


def run(text=None, file=None, taken_at=None, account=None, observations=None,
        assume_yes=False, as_json=False, out=None, ask=None):
    """The command. Returns an exit code.

    0 read and saved, or read and declined. 2 could not be read -- and nothing
    is saved in that case, which is R4's own acceptance test.
    """
    out = out or sys.stdout
    if file:
        try:
            text = Path(file).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"ERROR: could not read the paste: {exc}", file=out)
            return 2
    if not (text or "").strip():
        print("ERROR: nothing was pasted. Paste the whole usage panel, not one field.",
              file=out)
        return 2

    reading = parse(text, taken_at=taken_at, account=account)
    if as_json:
        print(json.dumps(reading, indent=2, sort_keys=True), file=out)
    else:
        print("\n".join(describe(reading)), file=out)

    if not reading["readable"]:
        print("\nNothing saved: this panel could not be read. "
              "Paste the usage page again, whole.", file=out)
        return 2

    if not assume_yes:
        ask = ask or (lambda: input("\nSave this reading? [y/N] ") if sys.stdin.isatty() else "")
        answer = (ask() or "").strip().lower()
        if answer not in ("y", "yes"):
            print("Nothing saved.", file=out)
            return 0

    path = save(reading, observations, text=text)
    print(f"\nSaved one observation to {path}", file=out)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("paste", nargs="?", help="the panel as text (prefer --file)")
    parser.add_argument("--file", help="read the paste from a file")
    parser.add_argument("--taken-at", dest="taken_at",
                        help="when the page was read, ISO 8601. The page gives clock times "
                             "with no dates, so a paste is only usable with this")
    parser.add_argument("--account", help="account-1 / account-2, where it is known")
    parser.add_argument("--observations", help="where observations are appended")
    parser.add_argument("--yes", action="store_true",
                        help="save without asking. Without it, what was read is shown first")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    taken_at = args.taken_at
    if not taken_at and not args.file and not args.paste:
        pass
    return run(text=args.paste if args.paste else (None if args.file else sys.stdin.read()),
               file=args.file, taken_at=taken_at, account=args.account,
               observations=args.observations, assume_yes=args.yes, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
