# SPDX-License-Identifier: Apache-2.0
"""reckon report: a read-only summary of the store, or of the sample shipped
with the package. Decision 7, RECKON-1.1-SPEC.md: lists any task whose
sessions cost more than 10% over its estimate, with the estimate-not-a-bill
wording on its face. A store with no tasks says so, with the runs it holds,
rather than reading like a store where nothing ran over (RECKON-USER-SPEC.md
R4). Prints only; writes nothing, so no consent is needed
(store.py's export consent gate is about writing an export, not this).
"""

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SAMPLE_PATH = ROOT / "sample" / "register-sample.json"

NOT_A_BILL = (
    "Every figure here is a client-side estimate at list rates, from the task's own "
    "record and its sessions' own transcripts. The estimate is a range, not a point; "
    "the recorded cost is a floor on what a task drew, not a bill for it."
)

OVER_THRESHOLD = 0.10
PERIOD_DAYS = 7

FLOOR = (
    "This register sees Claude Code only. Chat in the desktop app, on the web and on a phone "
    "draws on the same limits and leaves no transcript here, so the measured cost is a floor "
    "on what the account used; the meter is the whole account, and it is not a bill."
)


def _store():
    import importlib
    sys.path.insert(0, str(ROOT / "store"))
    return importlib.import_module("store")


def _ledger(name):
    import importlib
    path = str(ROOT / "ledger")
    if path not in sys.path:
        sys.path.insert(0, path)
    return importlib.import_module(name)


def _load_live(root):
    store = _store()
    data = store.load_store(root)
    runs = list(store.current_runs(data["runs"]).values())
    return data["tasks"], runs


def _load_sample(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return payload.get("tasks", {}), payload.get("runs", [])


def cost_by_task(runs):
    totals = {}
    for run in runs:
        ref = run.get("task_ref")
        if not ref:
            continue
        totals[ref] = totals.get(ref, 0.0) + (run.get("cost_usd") or 0.0)
    return totals


def _as_float(value):
    """Front matter is flat text, so a real store's est_p95_usd arrives as a
    string ('14.0'), never a number -- unlike this module's own tests, which
    is exactly how the walkthrough (RECKON-1.1-SPEC.md R3) caught this."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def overruns(tasks, totals, threshold=OVER_THRESHOLD):
    """Tasks whose recorded cost is more than `threshold` over est_p95_usd.
    Decision 7's comparison; the whole point is this list, not the totals."""
    rows = []
    for ref, task in tasks.items():
        fields = task.get("fields", task)
        estimate = _as_float(fields.get("est_p95_usd"))
        spent = totals.get(ref)
        if not estimate or spent is None:
            continue
        ratio = (spent - estimate) / estimate
        if ratio > threshold:
            rows.append({"ref": ref, "estimate_usd": estimate, "spent_usd": spent,
                        "over_pct": ratio * 100})
    rows.sort(key=lambda r: -r["over_pct"])
    return rows


def run(sample=False, root=None, out=None, now=None, meter=None, days=PERIOD_DAYS):
    out = out or sys.stdout
    root = Path(root) if root else ROOT

    if sample:
        tasks, runs = _load_sample(SAMPLE_PATH)
        source_label = f"the sample shipped with the package ({SAMPLE_PATH.name})"
    else:
        tasks, runs = _load_live(root)
        source_label = "the reader's own store"

    print(f"reckon report -- {source_label}", file=out)
    print(NOT_A_BILL, file=out)
    print(file=out)

    _overruns_section(tasks, runs, out)
    print(file=out)
    _meter_section(runs, out, sample=sample, now=now, meter=meter, days=days)
    return 0


def _overruns_section(tasks, runs, out):
    if not tasks:
        print("No tasks in this store yet, so there is no estimate to compare a recorded "
              "cost with.", file=out)
        if runs:
            total = sum(run.get("cost_usd") or 0.0 for run in runs)
            print(f"Runs recorded: {len(runs)}, ${total:.2f} at list rates.", file=out)
        else:
            print("Runs recorded: none yet. `reckon record` reads your Claude Code "
                  "transcripts into this store.", file=out)
        return

    rows = overruns(tasks, cost_by_task(runs))
    if not rows:
        print(f"No task's recorded cost is more than {OVER_THRESHOLD*100:.0f}% "
              f"over its estimate.", file=out)
        return

    print(f"Tasks more than {OVER_THRESHOLD*100:.0f}% over their estimate:", file=out)
    for row in rows:
        print(f"  {row['ref']:<14} estimate ${row['estimate_usd']:.2f}   "
              f"recorded ${row['spent_usd']:.2f}   (+{row['over_pct']:.0f}%)", file=out)


def _parse(value):
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    # Python 3.9's fromisoformat takes a fraction of exactly 3 or 6 digits.
    text = re.sub(r"\.(\d{1,6})(?=[+-]|$)", lambda m: "." + m.group(1).ljust(6, "0"), text)
    try:
        when = datetime.fromisoformat(text)
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def measured_in(runs, start, end):
    """Claude Code's measured cost for runs that started in the period."""
    inside = [r for r in runs
              if _parse(r.get("started_at")) and start <= _parse(r["started_at"]) <= end]
    return len(inside), sum(r.get("cost_usd") or 0.0 for r in inside)


def _meter_section(runs, out, sample=False, now=None, meter=None, days=PERIOD_DAYS):
    """R8 of RECKON-1.2-SPEC.md: the account meter beside measured cost, same period."""
    end = now or datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    count, cost = measured_in(runs, start, end)
    print(f"The last {days} days, {start:%d %B} to {end:%d %B %Y}:", file=out)
    print(f"  Claude Code, measured: {count} session(s), ${cost:.2f} at list rates.", file=out)
    if sample:
        print("  The account meter: the sample carries no meter readings.", file=out)
        print(f"  {FLOOR}", file=out)
        return
    if meter is None:
        try:
            meter = _ledger("usage_status").period(start, end)
        except Exception as exc:                          # noqa: BLE001 -- the list above stands
            print(f"  The account meter: not read ({exc.__class__.__name__}: {exc}).", file=out)
            print(f"  {FLOOR}", file=out)
            return
    if not meter["sources"]:
        print("  The account meter: no readings for this period, from any source.", file=out)
    for row in meter["sources"]:
        who = f", {row['account']}" if row.get("account") else ""
        cover = (f", covering {row['coverage_percent']}% of the period"
                 if row.get("coverage_percent") is not None else "")
        print(f"  The account meter, {row['source']}{who}{cover}:", file=out)
        for figure, name in (("five_hour", "five-hour"), ("seven_day", "seven-day")):
            f = row["figures"].get(figure)
            if not f:
                continue
            print(f"    {name:<10} highest {f['highest']:g}%, from {f['first']:g}% to "
                  f"{f['last']:g}% across {f['readings']} reading(s)", file=out)
    if meter.get("spans_weekly_break"):
        print("  The weekly limit changed on 13 September 2026; seven-day percentages either "
              "side of it are of two different limits.", file=out)
    print(f"  {FLOOR}", file=out)
