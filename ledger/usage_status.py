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
           live=None, archive=None, copies=None, observations=None, statusline_path=None):
    now = _now(now)
    if samples is None:
        samples = plan_usage.merge(*[s["samples"] for s in _desktop_sources(live, archive, copies)])
    if pastes is None:
        pastes = _read_jsonl(observations or usage_paste.DEFAULT_OBSERVATIONS)
    if statusline is None:
        import statusline as sl
        statusline = _read_jsonl(statusline_path or sl.DEFAULT_READINGS)

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
    return {
        "generated_at": _stamp(now),
        "figures": figures,
        "warnings": warnings,
        "product_split": split,
        "cross_check": cross_check(limits_path, now),
        "notes": [
            "The account's own meter, from every source that has a reading. Where two sources "
            "disagree both are shown; nothing is averaged.",
            "Not a bill, and nothing here is converted into money.",
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
    check = result["cross_check"]
    if check["available"] and check["percent_of_observed_ceiling"] is not None:
        out.append(f"\nCross-check: {check['percent_of_observed_ceiling']}% of the observed "
                   f"{NAMES.get(check['window'], check['window'])} ceiling, from "
                   f"{check['refusals']} refusal(s), computed {check['computed_at'][:16]} -- "
                   f"{check['note']}.")
    else:
        out.append(f"\nCross-check: {check['note']}.")
    out.append("")
    out += [f"* {n}" for n in result["notes"]]
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
