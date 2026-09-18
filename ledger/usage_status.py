#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Where the account stands now -- R5 and R6 of package/RECKON-1.2-SPEC.md.

Usage: python3 usage_status.py [--json]

R5. Both percentages, each from every source that has one: the desktop app's
file (ledger/plan_usage.py), pasted copies of the usage page
(ledger/usage_paste.py), and the reading Claude Code hands to a status line
(ledger/statusline.py, R3). Each figure says which source it came from, how
old it is, and its reset time where the source gives one. A reading older than
its own window -- five hours, or seven days -- is named and NOT shown as a
percentage, because it describes a window that has already ended. The product
split is shown where a paste of this week gives one. The refusal-based
estimate from ledger/limits.py sits underneath as a cross-check.

R6. At 80 per cent of either limit, a line in words, with the moment the
readings project it to reach 100. The projection is a straight line through
the readings since the percentage last fell, from one source and one account,
never a blend. It is REFUSED for a weekly series that spans 13 September 2026,
when the weekly limit changed, because the two halves are percentages of
different limits.

Nothing here is a bill, and nothing is converted into money. Read-only: this
module writes nothing.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import plan_usage  # noqa: E402
import usage_paste  # noqa: E402

WARN_AT = 80
WINDOWS = {"five_hour": timedelta(hours=5), "seven_day": timedelta(days=7)}
NAMES = {"five_hour": "five-hour", "seven_day": "seven-day"}
WEEKLY_SCALE_BREAK = plan_usage.WEEKLY_SCALE_BREAK
#: The moment the weekly limit changed for every Pro, Max, Team and seat-based
#: Enterprise plan: the +50% promotion ended at 11:59 pm Pacific on 13 September
#: 2026 and a permanent +25% on the base limit replaced it. A projection is not
#: drawn through readings either side of it.
WEEKLY_CHANGE_AT = datetime(2026, 9, 14, 6, 59, 59, tzinfo=timezone.utc)
LIMITS_PATH = HERE / "limits.json"

SOURCE_DESKTOP = "desktop app's file"
SOURCE_PASTE = "paste of the usage page"
SOURCE_STATUSLINE = "Claude Code status line"
#: How close in time another source's reading must be to be shown beside the
#: current one on the Board (by_account).
OTHERS_WITHIN = timedelta(hours=1)
UNREAD = object()   # the status line's last-call note was not looked for


def _now(now=None):
    return now or datetime.now(timezone.utc)


def _parse(value):
    if not value or not isinstance(value, str):
        return None
    text = value.replace("Z", "+00:00")
    # Python 3.9's fromisoformat takes a fraction of exactly 3 or 6 digits.
    text = re.sub(r"\.(\d{1,6})(?=[+-]|$)", lambda m: "." + m.group(1).ljust(6, "0"), text)
    try:
        when = datetime.fromisoformat(text)
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _stamp(when):
    return when.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            out.append(record)
    return out


# --------------------------------------------------------------------------
# the three sources, each as a list of points: {at, percent, resets_at, ...}


def desktop_series(samples):
    """The desktop file's samples for the account seen most recently.

    One account only: two accounts' percentages are two meters, and a series
    that switches between them is not a series.
    """
    if not samples:
        return None, {}
    labels = plan_usage.account_labels(samples)
    last = max(samples, key=lambda s: s["t"])
    key = last.get("account_key")
    mine = sorted((s for s in samples if s.get("account_key") == key), key=lambda s: s["t"])
    series = {}
    for figure in WINDOWS:
        series[figure] = [
            {"at": _parse(s["at"]), "percent": s[f"{figure}_percent"], "resets_at": None}
            for s in mine if isinstance(s.get(f"{figure}_percent"), (int, float))]
    return labels.get(key), series


def paste_series(readings):
    series = {figure: [] for figure in WINDOWS}
    for r in readings:
        at = _parse(r.get("taken_at"))
        if at is None:
            continue
        for figure in WINDOWS:
            if isinstance(r.get(f"{figure}_percent"), (int, float)):
                series[figure].append({
                    "at": at, "percent": r[f"{figure}_percent"],
                    "resets_at": None,
                    "resets_at_text": r.get(f"{figure}_resets_at_text"),
                    "account": r.get("account")})
    for figure in series:
        series[figure].sort(key=lambda p: p["at"])
    return series


def statusline_series(readings):
    series = {figure: [] for figure in WINDOWS}
    for r in readings:
        at = _parse(r.get("taken_at"))
        if at is None:
            continue
        for figure in WINDOWS:
            if isinstance(r.get(f"{figure}_percent"), (int, float)):
                series[figure].append({
                    "at": at, "percent": r[f"{figure}_percent"],
                    "resets_at": _parse(r.get(f"{figure}_resets_at"))})
    for figure in series:
        series[figure].sort(key=lambda p: p["at"])
    return series


# --------------------------------------------------------------------------
# judging one figure


def current_run(points):
    """The points since the percentage last fell: the current window's readings."""
    run = []
    for point in points:
        if run and point["percent"] < run[-1]["percent"]:
            run = []
        run.append(point)
    return run


def project(points, figure, now=None):
    """When a straight line through the current run reaches 100, or why not.

    Returns {"reaches_100_at": ISO or None, "reason": words}.
    """
    run = current_run(points)
    if len(run) < 2:
        return {"reaches_100_at": None,
                "reason": "one reading in this window, so there is no rate to project from"}
    first, last = run[0], run[-1]
    if figure == "seven_day" and first["at"] <= WEEKLY_CHANGE_AT < last["at"]:
        return {"reaches_100_at": None,
                "reason": ("no projection: these readings span the end of 13 September 2026 "
                           "(Pacific time), when Claude's weekly limit changed, so they are "
                           "percentages of two different limits")}
    hours = (last["at"] - first["at"]).total_seconds() / 3600
    rise = last["percent"] - first["percent"]
    if hours <= 0 or rise <= 0:
        return {"reaches_100_at": None,
                "reason": "the readings in this window are not rising, so there is no projection"}
    if last["percent"] >= 100:
        return {"reaches_100_at": _stamp(last["at"]), "reason": "already at 100"}
    at = last["at"] + timedelta(hours=(100 - last["percent"]) * hours / rise)
    reason = (f"a straight line through {len(run)} readings since "
              f"{_stamp(first['at'])[:16].replace('T', ' ')} UTC")
    if last.get("resets_at") and at > last["resets_at"]:
        reason += "; the window resets before then"
    return {"reaches_100_at": _stamp(at), "reason": reason}


def judge(figure, source, points, now=None, account=None):
    """The newest point from one source, judged against its own window."""
    if not points:
        return None
    now = _now(now)
    last = points[-1]
    age = now - last["at"]
    entry = {
        "figure": figure,
        "source": source,
        "account": account or last.get("account"),
        "taken_at": _stamp(last["at"]),
        "age_hours": round(age.total_seconds() / 3600, 1),
        "percent": last["percent"],
        "resets_at": _stamp(last["resets_at"]) if last.get("resets_at") else None,
        "resets_at_text": last.get("resets_at_text"),
        "stale": None,
        "warning": None,
        "projection": None,
    }
    if age > WINDOWS[figure]:
        entry["stale"] = (f"older than its own {NAMES[figure]} window, so it describes a "
                          f"window that has ended and is not shown")
        entry["percent"] = None
    elif last.get("resets_at") and now >= last["resets_at"]:
        entry["stale"] = "its window reset after it was taken, so it is not shown"
        entry["percent"] = None
    if entry["percent"] is not None and entry["percent"] >= WARN_AT:
        entry["projection"] = project(points, figure, now)
        entry["warning"] = warning_text(figure, entry)
    return entry


def warning_text(figure, entry):
    words = f"WARNING: the {NAMES[figure]} limit is at {entry['percent']}% ({entry['source']})"
    projection = entry["projection"] or {}
    when = _parse(projection.get("reaches_100_at"))
    if when is not None:
        words += (f". At the rate of these readings it reaches 100% on "
                  f"{when.strftime('%A %d %B')} at about {when.strftime('%H:%M')} UTC "
                  f"({projection['reason']}).")
    else:
        words += f"; {projection.get('reason', 'no projection')}."
    return words


def cross_check(path=None, now=None):
    """The refusal-based estimate, if one is on file. A cross-check, not a gauge."""
    path = Path(path) if path else LIMITS_PATH
    if not path.exists():
        return {"available": False,
                "note": "no refusal-based estimate on file (ledger/limits.py writes one)"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"available": False, "note": f"refusal-based estimate unreadable: {exc}"}
    window = data.get("window", "five_hour")
    ceiling = (data.get("observed_ceilings") or {}).get(window) or {}
    current = data.get("current_window") or {}
    tokens = ceiling.get("lowest_refusal_tokens")
    percent = (round(current.get("all_classes", 0) / tokens * 100) if tokens else None)
    return {"available": True, "window": window,
            "computed_at": data.get("generated_at"),
            "percent_of_observed_ceiling": percent,
            "refusals": ceiling.get("observations", 0),
            "note": ("tokens in the window against the lowest point a request was refused at; "
                     "observed, not published, and a shape rather than a gauge")}


# --------------------------------------------------------------------------
# the status


def status(samples=None, pastes=None, statusline=None, limits_path=None, now=None,
           live=None, archive=None, copies=None, observations=None, statusline_path=None,
           statusline_called=UNREAD):
    now = _now(now)
    if samples is None:
        samples = plan_usage.merge(*[s["samples"] for s in _desktop_sources(live, archive, copies)])
    if pastes is None:
        pastes = _read_jsonl(observations or usage_paste.DEFAULT_OBSERVATIONS)
    called = statusline_called
    if statusline is None:
        import statusline as sl
        statusline = _read_jsonl(statusline_path or sl.DEFAULT_READINGS)
        if called is UNREAD:
            called = sl.read_called(statusline_path)

    account, desktop = desktop_series(samples)
    pasted = paste_series(pastes)
    live_line = statusline_series(statusline)

    figures = {}
    for figure in WINDOWS:
        entries = [e for e in (
            judge(figure, SOURCE_DESKTOP, desktop.get(figure, []), now, account),
            judge(figure, SOURCE_PASTE, pasted[figure], now),
            judge(figure, SOURCE_STATUSLINE, live_line[figure], now),
        ) if e]
        entries.sort(key=lambda e: e["taken_at"], reverse=True)
        figures[figure] = entries

    split = None
    fresh = [r for r in pastes if r.get("product_split_percent") and _parse(r.get("taken_at"))
             and now - _parse(r["taken_at"]) <= WINDOWS["seven_day"]]
    if fresh:
        newest = max(fresh, key=lambda r: _parse(r["taken_at"]))
        split = {"taken_at": newest["taken_at"], "percent": newest["product_split_percent"]}

    warnings = [e["warning"] for figure in WINDOWS for e in figures[figure] if e["warning"]]
    result = {
        "generated_at": _stamp(now),
        "figures": figures,
        "warnings": warnings,
        "product_split": split,
        "credits": credits_seen(pastes),
        "cross_check": cross_check(limits_path, now),
        "notes": [
            "The account's own meter, from every source that has a reading. Where two sources "
            "disagree both are shown; nothing is averaged.",
            "Not a bill, and nothing here is converted into money.",
        ],
    }
    if called is not UNREAD:
        result["statusline_called"] = called
    return result


def credits_seen(pastes):
    """The credits block from the newest paste that carries one (P-0001-T19).

    Only a paste of the usage page has this: the desktop app's file and the
    status line carry percentages and nothing about money. NO AGE LIMIT is
    applied, and that is deliberate -- a spend limit and a balance are the
    account's standing arrangement rather than a gauge that moves by the hour,
    and the alternative to an old reading here is no reading at all, which is
    how this went unanswered from 6 September. The reading says when it was
    taken and the caller says how old that is.

    Every figure is the text the page showed. Nothing is converted, nothing is
    compared with this register's own estimates, and the percentage is the
    page's own, not one computed here.
    """
    carrying = [r for r in pastes
                if r.get("credit_spend_limit_text") or r.get("credit_balance_text")
                or r.get("usage_credits_text")]
    if not carrying:
        return None
    newest = max(carrying, key=lambda r: r.get("taken_at") or "")
    return {field: newest.get(field) for field in (
        "taken_at", "account", "usage_credits_text", "credit_spend_this_month_text",
        "credit_spend_limit_text", "credit_spend_limit_percent_used",
        "credit_spend_limit_resets_text", "credit_balance_text", "auto_reload")}


STATUSLINE_ATTRIBUTION_WINDOW = timedelta(minutes=30)


def _account_around(taken_at, samples, labels):
    """The one account the desktop file was sampling around this moment, or None."""
    at = _parse(taken_at)
    if at is None:
        return None
    near = {labels.get(s.get("account_key"))
            for s in samples or []
            if abs(_parse(s["at"]) - at) <= STATUSLINE_ATTRIBUTION_WINDOW}
    near.discard(None)
    return next(iter(near)) if len(near) == 1 else None


def by_account(samples=None, pastes=None, statusline=None, now=None,
               live=None, archive=None, copies=None, observations=None, statusline_path=None):
    """The meter per account, for the Board (P-0001-T55). Both accounts side by
    side, never averaged and never summed: two accounts are two meters.

    status() judges the desktop file for the most recently seen account only,
    which is right for `reckon status` on the machine in front of you and wrong
    for a screen that has to show both. Here every account the desktop file or a
    paste names gets its own column, and each figure shows the NEWEST reading
    that still describes a live window, with the others listed under it by
    source and age -- so a desktop sample from before a weekly reset cannot sit
    on top of a paste taken after it.

    A status-line reading names no account, so it goes under `unassigned`
    rather than being guessed into one. Not a bill; nothing is converted."""
    now = _now(now)
    if samples is None:
        samples = plan_usage.merge(*[s["samples"] for s in _desktop_sources(live, archive, copies)])
    if pastes is None:
        pastes = _read_jsonl(observations or usage_paste.DEFAULT_OBSERVATIONS)
    if statusline is None:
        import statusline as sl
        statusline = _read_jsonl(statusline_path or sl.DEFAULT_READINGS)

    labels = plan_usage.account_labels(samples or [])
    readings = {}   # account -> figure -> [entries]

    def put(account, figure, entry):
        if entry:
            readings.setdefault(account, {f: [] for f in WINDOWS})[figure].append(entry)

    for key, label in labels.items():
        mine = sorted((x for x in samples if x.get("account_key") == key), key=lambda x: x["t"])
        for figure in WINDOWS:
            points = [{"at": _parse(x["at"]), "percent": x[f"{figure}_percent"], "resets_at": None}
                      for x in mine if isinstance(x.get(f"{figure}_percent"), (int, float))]
            put(label, figure, judge(figure, SOURCE_DESKTOP, points, now, label))

    by_paste_account = {}
    for r in pastes or []:
        by_paste_account.setdefault(r.get("account"), []).append(r)
    for account, group in by_paste_account.items():
        series = paste_series(group)
        for figure in WINDOWS:
            put(account, figure, judge(figure, SOURCE_PASTE, series[figure], now, account))

    # A reading that names its account by key goes in that account's column;
    # one that does not stays unassigned rather than being guessed into one.
    by_status_account = {}
    for r in statusline or []:
        account = labels.get(r.get("account_key"))
        if account is None:
            # A READING WRITTEN BEFORE THE KEY EXISTED. Attributed the way a Run
            # with no account line already is: by what the desktop app's own
            # meter was sampling at that moment, and only when the samples
            # around it name ONE account. Evidence, not a guess -- where two
            # accounts are sampled either side of it, it stays unassigned.
            account = _account_around(r.get("taken_at"), samples, labels)
        by_status_account.setdefault(account, []).append(r)
    for account, group in by_status_account.items():
        line = statusline_series(group)
        for figure in WINDOWS:
            put(account, figure, judge(figure, SOURCE_STATUSLINE, line[figure], now, account))

    def column(account, figures):
        out = {"account": account, "figures": {}, "warnings": []}
        for figure in WINDOWS:
            entries = sorted(figures[figure], key=lambda e: e["taken_at"], reverse=True)
            live_entries = [e for e in entries if e["percent"] is not None]
            current = live_entries[0] if live_entries else None
            out["figures"][figure] = {
                "name": NAMES[figure],
                "current": current,
                # Only readings taken close to the current one: two sources that
                # disagree NOW are worth seeing; a reading from before a reset is
                # not a disagreement, it is history, and it read as "100%" on the
                # first draw of this panel on 17 September.
                "others": [e for e in entries if e is not current and (
                    current is None or
                    (_parse(current["taken_at"]) - _parse(e["taken_at"])) <= OTHERS_WITHIN)],
                "at_or_over_warning": bool(current and current["percent"] >= WARN_AT),
            }
            if current and current["warning"]:
                out["warnings"].append(current["warning"])
        return out

    accounts = [column(a, readings[a]) for a in sorted(k for k in readings if k)]
    return {
        "generated_at": _stamp(now),
        "warn_at_percent": WARN_AT,
        "accounts": accounts,
        "unassigned": column(None, readings[None]) if None in readings else None,
        "notes": [
            "Each account's own meter, as the desktop app, a pasted usage page or the Claude "
            "Code status line recorded it. Two accounts are two meters: nothing is averaged "
            "or added up.",
            "The meter counts everything the account did, on every device. It is not a bill "
            "and nothing here is converted into money.",
        ],
    }


def period(start, end, samples=None, pastes=None, statusline=None,
           live=None, archive=None, copies=None, observations=None, statusline_path=None):
    """The meter over one period, for the report (R8): per account from the desktop
    file, and from the status line and pastes, whose account is not always known.

    For each figure: how many readings fell in the period, the highest, and the
    first and last. Coverage is the share of the period's quarter-hours that
    hold a desktop sample, so a period the app was closed for is not read as a
    quiet one. A weekly series spanning 13 September says so.
    """
    if samples is None:
        samples = plan_usage.merge(*[s["samples"] for s in _desktop_sources(live, archive, copies)])
    if pastes is None:
        pastes = _read_jsonl(observations or usage_paste.DEFAULT_OBSERVATIONS)
    if statusline is None:
        import statusline as sl
        statusline = _read_jsonl(statusline_path or sl.DEFAULT_READINGS)

    def inside(points):
        return [p for p in points if start <= p["at"] <= end]

    def summarise(points):
        points = inside(points)
        if not points:
            return None
        return {"readings": len(points), "highest": max(p["percent"] for p in points),
                "first": points[0]["percent"], "first_at": _stamp(points[0]["at"]),
                "last": points[-1]["percent"], "last_at": _stamp(points[-1]["at"])}

    rows = []
    labels = plan_usage.account_labels(samples)
    for key, label in sorted(labels.items(), key=lambda kv: kv[1]):
        mine = sorted((s for s in samples if s.get("account_key") == key), key=lambda s: s["t"])
        series = {f: [{"at": _parse(s["at"]), "percent": s[f"{f}_percent"]} for s in mine
                      if isinstance(s.get(f"{f}_percent"), (int, float))] for f in WINDOWS}
        quarters = int((end - start).total_seconds() // 900) or 1
        held = {int((_parse(s["at"]) - start).total_seconds() // 900) for s in mine
                if start <= _parse(s["at"]) <= end}
        figures = {f: summarise(series[f]) for f in WINDOWS}
        if any(figures.values()):
            rows.append({"source": SOURCE_DESKTOP, "account": label, "figures": figures,
                         "coverage_percent": round(min(len(held), quarters) / quarters * 100)})
    for source, series in ((SOURCE_STATUSLINE, statusline_series(statusline)),
                           (SOURCE_PASTE, paste_series(pastes))):
        figures = {f: summarise(series[f]) for f in WINDOWS}
        if any(figures.values()):
            rows.append({"source": source, "account": None, "figures": figures,
                         "coverage_percent": None})
    return {
        "start": _stamp(start), "end": _stamp(end), "sources": rows,
        "spans_weekly_break": _stamp(start)[:10] < WEEKLY_SCALE_BREAK <= _stamp(end)[:10],
    }


def _desktop_sources(live=None, archive=None, copies=None):
    cfg_live, cfg_archive, cfg_copies = plan_usage.load_config()
    paths = [Path(live) if live else cfg_live, Path(archive) if archive else cfg_archive]
    copies = Path(copies) if copies else cfg_copies
    if copies and copies.is_dir():
        paths += sorted(copies.glob("*.json"))
    return [plan_usage.read_source(p) for p in paths]


def statusline_called_line(note):
    """Never-ran and ran-without-a-meter are different findings (P-0001-T79)."""
    if not note or not note.get("called_at"):
        return ("\nStatus line: has never run on this machine, so no reading carries a reset "
                "time. Claude Code in a terminal runs it; the desktop app does not.")
    when = note["called_at"][:16].replace("T", " ")
    if note.get("had_meter"):
        return f"\nStatus line: last ran {when} UTC, with a reading."
    return (f"\nStatus line: last ran {when} UTC with no meter in its input "
            f"(Claude Code gives one only to subscribers, after the first reply).")


def lines(result):
    out = []
    for w in result["warnings"]:
        out.append(w)
    if result["warnings"]:
        out.append("")
    for figure in WINDOWS:
        out.append(f"{NAMES[figure].capitalize()} limit")
        entries = result["figures"][figure]
        if not entries:
            out.append("  no reading from any source")
        for e in entries:
            who = f", {e['account']}" if e.get("account") else ""
            age = (f"{round(e['age_hours'] * 60)} min ago" if e["age_hours"] < 1
                   else f"{e['age_hours']}h ago")
            taken = f"taken {e['taken_at'][:16].replace('T', ' ')} UTC, {age}"
            if e["percent"] is None:
                out.append(f"  --    {e['source']}{who}: {taken}; {e['stale']}")
                continue
            reset = ""
            if e["resets_at"]:
                reset = f", resets {e['resets_at'][:16].replace('T', ' ')} UTC"
            elif e.get("resets_at_text"):
                reset = f", resets {e['resets_at_text']} (as the page put it)"
            elif e["source"] == SOURCE_DESKTOP:
                reset = ", reset time not in this source"
            out.append(f"  {e['percent']:>3}%  {e['source']}{who}: {taken}{reset}")
    split = result["product_split"]
    if split:
        parts = ", ".join(f"{k} {v}%" for k, v in split["percent"].items())
        out.append(f"\nThis week by product (paste of {split['taken_at'][:10]}): {parts}")
    out += credit_lines(result.get("credits"))
    check = result["cross_check"]
    if check["available"] and check["percent_of_observed_ceiling"] is not None:
        out.append(f"\nCross-check: {check['percent_of_observed_ceiling']}% of the observed "
                   f"{NAMES.get(check['window'], check['window'])} ceiling, from "
                   f"{check['refusals']} refusal(s), computed {check['computed_at'][:16]} -- "
                   f"{check['note']}.")
    else:
        out.append(f"\nCross-check: {check['note']}.")
    if "statusline_called" in result:
        out.append(statusline_called_line(result["statusline_called"]))
    out.append("")
    out += [f"* {n}" for n in result["notes"]]
    return out


def credit_lines(credits):
    """The credits block, in words. Every figure is the page's own text.

    Shown however old it is, with its date, because a spend limit and a balance
    are standing arrangements rather than gauges -- see `credits_seen`. Nothing
    here is converted into money this register has calculated, and nothing is
    set beside the register's own estimates: the estimate is a floor on what an
    account loses, never a prediction of what a limit will read.
    """
    if not credits:
        return []
    who = f", {credits['account']}" if credits.get("account") else ""
    taken = (credits.get("taken_at") or "")[:16].replace("T", " ")
    out = [f"\nUsage credits (paste of the usage page{who}, taken {taken} UTC)"]
    if credits.get("credit_spend_limit_text"):
        share = ("" if credits.get("credit_spend_limit_percent_used") is None
                 else f", {credits['credit_spend_limit_percent_used']}% used")
        resets = ("" if not credits.get("credit_spend_limit_resets_text")
                  else f", resets {credits['credit_spend_limit_resets_text']} "
                       f"(as the page put it)")
        out.append(f"  monthly spend limit  {credits['credit_spend_limit_text']}"
                   f"{share}{resets}")
    spent = credits.get("credit_spend_this_month_text")
    if spent:
        out.append(f"  spent this month     {spent}")
    elif credits.get("usage_credits_text"):
        out.append(f"  usage credits        {credits['usage_credits_text']} "
                   f"(the page did not say whether this is a balance or a spend)")
    if credits.get("credit_balance_text"):
        reload_state = ("" if not credits.get("auto_reload")
                        else f", auto-reload {credits['auto_reload']}")
        out.append(f"  current balance      {credits['credit_balance_text']}{reload_state}")
    elif credits.get("auto_reload"):
        out.append(f"  auto-reload          {credits['auto_reload']}")
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="Where the account's usage limits stand now.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--source", help="the desktop usage file (read-only)")
    parser.add_argument("--archive-path", dest="archive_path")
    parser.add_argument("--copies")
    parser.add_argument("--observations", help="pasted readings (usage_paste)")
    parser.add_argument("--statusline", help="status-line readings (statusline)")
    parser.add_argument("--limits", help="the refusal-based estimate (limits.py)")
    args = parser.parse_args(argv)
    result = status(live=args.source, archive=args.archive_path, copies=args.copies,
                    observations=args.observations, statusline_path=args.statusline,
                    limits_path=args.limits)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("\n".join(lines(result)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
