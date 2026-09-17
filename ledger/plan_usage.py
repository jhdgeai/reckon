#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The desktop app's own usage meter, read -- R1 and R2 of package/RECKON-1.2-SPEC.md.

Usage: python3 plan_usage.py [--json] [--archive] [--dry-run]

WHAT THIS READS. The Claude desktop app keeps a rolling history of the account's
plan usage at

    ~/Library/Application Support/Claude/plan-usage-history.json

format version 2, undocumented. A sample is `{t, org, u}`: a timestamp in
milliseconds, an account identifier, and inside `u` the five-hour limit percent
`fh` and the seven-day limit percent `sd`, both whole numbers 0 to 100. The app
writes one about every fifteen minutes AND ONLY WHILE IT IS RUNNING, so the file
is full of holes: a quiet stretch and a closed laptop look identical. Coverage
below is therefore not decoration. A percentage read without its gaps is a
number that flatters a machine that was switched off.

THREE THINGS THIS FILE WILL NOT TELL YOU, said here so no caller assumes them:

  * No reset times. A percentage with no reset clock cannot say how long it has
    to last; the reset times come from a paste (R4) or the status line (R3).
  * No unit for the spend figure. `xu` appears on a minority of samples and
    spec-core.md 4.1 describes it as a percent AND as pounds. It FELL between
    two samples, which no running total of spend does. It is carried here as
    `spend_figure`, unitless, and MUST NOT be printed in a currency until its
    unit is confirmed against something the owner can see. Same rule that keeps
    `cost_to_date_gbp` null.
  * No absolute claim about the weekly scale. The summer promotion ended on
    13 September 2026 and the weekly limit rose about 25%, so a seven-day
    percentage from before that date and one from after are not two readings of
    the same thing. WEEKLY_SCALE_BREAK carries the date and the report says so.

ACCOUNTS, NOT MACHINES. A reading belongs to an account. The identifiers in the
file are disclosive and they are NEVER written out: not into the report, not
into the archive, not into a log line, not into a test fixture. They are hashed
on the way in (`account_key`) and shown as `account-1`, `account-2`, numbered by
first appearance in time -- exactly the rule ledger/sessions.py already uses for
transcript owner accounts, so the two readers label the same account the same
way. See ledger/rails.json `_second_account_note`.

THE ARCHIVE (R2). The app keeps about thirty days and drops a day off the back
each day, so the register keeps its own copy. `--archive` merges the live file
into a durable archive, deduplicated by (sample time, account), append-only:
a sample once archived stays archived after the app has forgotten it. This runs
from ledger/archive.py, so the LaunchAgent that already keeps the transcripts
alive keeps the meter alive too, on the same ten-minute beat.

WHERE THE ARCHIVE LIVES, AND WHY IT IS NOT IN THE REPOSITORY. Two reasons, both
mechanical. (1) launchd cannot read or write ~/Documents without Full Disk
Access -- the same reason ledger/archive-config.json gives for the transcript
archive -- and an archive that needs a human to authorise it is not automation.
(2) Even hashed, an account key is a per-account identifier and the repository
is the one place a disclosive value can never be taken back from. So the archive
sits beside the transcript archive in ~/Library/Application Support/claude-ledger
and the reader merges it with the live file and any hand-taken copies in
ledger/plan-usage/.

No third-party dependencies, no network. Every source is opened read-only.
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "archive-config.json"

DEFAULT_LIVE = (Path.home() / "Library" / "Application Support" / "Claude"
                / "plan-usage-history.json")
DEFAULT_ARCHIVE = (Path.home() / "Library" / "Application Support" / "claude-ledger"
                   / "plan-usage" / "plan-usage-history.json")
DEFAULT_COPIES = HERE / "plan-usage"

ARCHIVE_FORMAT = "p2p-register plan-usage archive v1"

#: A gap longer than this is reported. The app samples every ~15 minutes.
GAP_MINUTES = 60
#: The spec's own finding counts gaps over three hours separately.
LONG_GAP_HOURS = 3

#: The day the weekly denominator changed. A seven-day series that spans it is
#: two scales, not one, and nothing may be projected across it.
WEEKLY_SCALE_BREAK = "2026-09-13"

SPEND_FIELD = "xu"
SPEND_UNIT_NOTE = (
    "the file states no unit for this figure and it FELL between two samples, so it is "
    "carried unitless and is never printed in a currency (RECKON-1.2-SPEC.md decision 4)")

#: Hashing keeps a stable key for the same account across merges without ever
#: holding the identifier itself. The prefix stops the digest matching a hash of
#: the same identifier taken anywhere else.
_KEY_PREFIX = b"p2p-register plan-usage account\n"
ACCOUNT_KEY_LENGTH = 16


class PlanUsageError(Exception):
    """A source that cannot be read at all. A source that is merely absent is
    not one of these -- absence is reported and is not fatal."""


# --------------------------------------------------------------------------
# reading


def account_key(identifier):
    """A stable, non-reversible key for an account identifier.

    The identifier goes in and never comes out. Nothing in this module stores,
    prints or returns the value passed here.
    """
    digest = hashlib.sha256(_KEY_PREFIX + str(identifier).encode("utf-8")).hexdigest()
    return digest[:ACCOUNT_KEY_LENGTH]


def load_config():
    """(live, archive, copies) from archive-config.json, falling back to the
    defaults. The config file is shared with archive.py on purpose: one place
    says where this machine keeps things."""
    live, archive, copies = DEFAULT_LIVE, DEFAULT_ARCHIVE, DEFAULT_COPIES
    if CONFIG_PATH.exists():
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return live, archive, copies
        if raw.get("plan_usage_source"):
            live = Path(raw["plan_usage_source"]).expanduser()
        if raw.get("plan_usage_archive"):
            archive = Path(raw["plan_usage_archive"]).expanduser()
        if raw.get("plan_usage_copies"):
            copies = Path(raw["plan_usage_copies"]).expanduser()
    return live, archive, copies


def _stamp(millis):
    return datetime.fromtimestamp(millis / 1000, tz=timezone.utc).isoformat().replace(
        "+00:00", "Z")


def normalise(sample):
    """One raw sample -> the shape this module works in, or None.

    Accepts the desktop app's own `{t, org, u}` and this module's archive form
    `{t, account_key, u}`, so a merge never cares which it is holding.

    `spend_figure` is None where the sample carries no `xu`. A SAMPLE WITH NO
    SPEND FIGURE IS NOT A SAMPLE WITH ZERO SPEND, and the difference is the
    whole reason this function does not use `.get(SPEND_FIELD, 0)`.
    """
    if not isinstance(sample, dict):
        return None
    millis = sample.get("t")
    if not isinstance(millis, (int, float)):
        return None
    usage = sample.get("u")
    usage = usage if isinstance(usage, dict) else {}

    key = sample.get("account_key")
    if not key and sample.get("org") is not None:
        key = account_key(sample["org"])

    known = {"fh", "sd", SPEND_FIELD}
    return {
        "t": int(millis),
        "at": _stamp(millis),
        "account_key": key,
        "five_hour_percent": usage.get("fh"),
        "seven_day_percent": usage.get("sd"),
        "spend_figure": usage.get(SPEND_FIELD),
        "other_fields": sorted(k for k in usage if k not in known),
    }


def read_source(path):
    """Read one file. Returns a dict describing the source, never raising for a
    file that simply is not there -- R1: a missing file is reported, not fatal."""
    path = Path(path)
    source = {"path": str(path), "exists": path.exists(), "samples": [],
              "sample_count": 0, "format": None, "problem": None}
    if not path.exists():
        source["problem"] = "no file here"
        return source
    try:
        raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError) as exc:
        source["problem"] = f"could not be read: {exc}"
        return source

    if isinstance(raw, list):
        samples, version = raw, None
    elif isinstance(raw, dict):
        samples = raw.get("samples")
        version = raw.get("version") or raw.get("format")
    else:
        source["problem"] = "not a usage-history file: no samples in it"
        return source

    if not isinstance(samples, list):
        source["problem"] = "not a usage-history file: no samples in it"
        return source

    source["format"] = version
    read = [normalise(s) for s in samples]
    good = [s for s in read if s]
    source["samples"] = good
    source["sample_count"] = len(good)
    if len(good) != len(read):
        source["problem"] = (f"{len(read) - len(good)} of {len(read)} samples had no usable "
                             f"timestamp and were left out")
    return source


def merge(*groups):
    """One series from many, deduplicated by (sample time, account).

    Overlapping copies of the same file are the normal case: the live file and
    an archive share thousands of samples. Deduplication is by time AND account
    because a time alone is not unique across two accounts.
    """
    seen = {}
    for group in groups:
        for sample in group or ():
            if not sample:
                continue
            key = (sample["t"], sample.get("account_key"))
            if key not in seen:
                seen[key] = sample
    return sorted(seen.values(), key=lambda s: (s["t"], s.get("account_key") or ""))


def account_labels(samples):
    """{account_key: 'account-N'}, numbered by first appearance in time.

    The same rule as ledger/sessions.py account_labels, so a Run's account-2 and
    a meter reading's account-2 mean the same account.
    """
    first = {}
    for sample in samples:
        key = sample.get("account_key")
        if key is None:
            continue
        if key not in first or sample["t"] < first[key]:
            first[key] = sample["t"]
    return {key: f"account-{i + 1}" for i, key in enumerate(sorted(first, key=first.get))}


# --------------------------------------------------------------------------
# coverage


def gaps(samples, gap_minutes=GAP_MINUTES):
    """Every stretch longer than `gap_minutes` with no sample in it.

    The app writes only while it runs, so these are the hours this series says
    NOTHING about. They are not low usage.
    """
    ordered = sorted(samples, key=lambda s: s["t"])
    found = []
    for before, after in zip(ordered, ordered[1:]):
        minutes = (after["t"] - before["t"]) / 60000.0
        if minutes > gap_minutes:
            found.append({"from": before["at"], "to": after["at"],
                          "minutes": round(minutes, 1),
                          "hours": round(minutes / 60, 1)})
    return found


def coverage(samples, gap_minutes=GAP_MINUTES):
    """First sample, last sample, and what the series does not cover."""
    ordered = sorted(samples, key=lambda s: s["t"])
    if not ordered:
        return {"sample_count": 0, "first_sample_at": None, "last_sample_at": None,
                "gap_minutes": gap_minutes, "gaps": [], "gap_count": 0,
                "longest_gap_hours": None, "gaps_over_three_hours": 0,
                "covered_fraction": None}

    found = gaps(ordered, gap_minutes)
    span = (ordered[-1]["t"] - ordered[0]["t"]) / 60000.0
    missing = sum(g["minutes"] for g in found)
    return {
        "sample_count": len(ordered),
        "first_sample_at": ordered[0]["at"],
        "last_sample_at": ordered[-1]["at"],
        "span_hours": round(span / 60, 1),
        "gap_minutes": gap_minutes,
        "gaps": found,
        "gap_count": len(found),
        "longest_gap_hours": max((g["hours"] for g in found), default=0.0),
        "gaps_over_three_hours": sum(1 for g in found if g["hours"] > LONG_GAP_HOURS),
        "covered_fraction": round((span - missing) / span, 3) if span else None,
    }


def spend_figures(samples):
    """What the file says about `xu`, without saying what it means.

    Samples with no `xu` are counted as having none, never as zero -- R1's
    acceptance test.
    """
    present = [s["spend_figure"] for s in samples
               if isinstance(s.get("spend_figure"), (int, float))]
    return {
        "field": SPEND_FIELD,
        "samples_with_a_figure": len(present),
        "samples_without_one": len(samples) - len(present),
        "lowest": min(present) if present else None,
        "highest": max(present) if present else None,
        "fell_at_some_point": any(b < a for a, b in zip(present, present[1:])),
        "unit": "not stated by the file",
        "note": SPEND_UNIT_NOTE,
    }


def newest(samples):
    """The newest sample, with the two percentages as whole numbers."""
    if not samples:
        return None
    last = max(samples, key=lambda s: s["t"])
    return {
        "at": last["at"],
        "five_hour_percent": last["five_hour_percent"],
        "seven_day_percent": last["seven_day_percent"],
        "age_hours": round(
            (datetime.now(timezone.utc).timestamp() - last["t"] / 1000) / 3600, 1),
    }


def spans_the_weekly_break(cover):
    first, last = cover.get("first_sample_at"), cover.get("last_sample_at")
    if not first or not last:
        return False
    return first[:10] < WEEKLY_SCALE_BREAK <= last[:10]


# --------------------------------------------------------------------------
# the report


def report(sources=None, live=None, archive=None, copies=None, gap_minutes=GAP_MINUTES):
    """Everything R1 asks for, per account, from every source that exists."""
    if sources is None:
        cfg_live, cfg_archive, cfg_copies = load_config()
        live = Path(live) if live else cfg_live
        archive = Path(archive) if archive else cfg_archive
        copies = Path(copies) if copies else cfg_copies
        sources = [live, archive]
        if copies and Path(copies).is_dir():
            sources += sorted(Path(copies).glob("*.json"))

    read = [read_source(p) for p in sources]
    samples = merge(*[s["samples"] for s in read])
    labels = account_labels(samples)

    accounts = []
    for key, label in sorted(labels.items(), key=lambda kv: kv[1]):
        mine = [s for s in samples if s.get("account_key") == key]
        cover = coverage(mine, gap_minutes)
        accounts.append({
            "account": label,
            "newest": newest(mine),
            "coverage": cover,
            "spend_figure": spend_figures(mine),
            "weekly_series_spans_the_scale_break": spans_the_weekly_break(cover),
        })

    unlabelled = [s for s in samples if s.get("account_key") is None]
    notes = [
        "Every figure here is the account's own meter as the desktop app recorded it. "
        "It is not a bill and it is not this register's cost estimate.",
        "The app writes only while it is running, so a gap is an hour this file says "
        "nothing about -- never an hour of low usage.",
        f"The weekly limit changed on {WEEKLY_SCALE_BREAK}; seven-day percentages either "
        f"side of that date are not one series, and nothing is projected across it.",
        "Accounts are numbered by first appearance. The identifiers are disclosive and "
        "are never written down here.",
    ]
    if unlabelled:
        notes.append(f"{len(unlabelled)} sample(s) name no account and are counted in no "
                     f"account's series.")
    missing = [s for s in read if not s["exists"]]
    if missing and len(missing) == len(read):
        notes.append("NO SOURCE EXISTS. There is nothing to read, which is reported and is "
                     "not an error -- see the sources listed above.")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "sources": [{k: v for k, v in s.items() if k != "samples"} for s in read],
        "sample_count": len(samples),
        "account_count": len(labels),
        "accounts": accounts,
        "unlabelled_samples": len(unlabelled),
        "overall_coverage": coverage(samples, gap_minutes),
        "notes": notes,
    }


# --------------------------------------------------------------------------
# the archive (R2)


def archive_samples(samples):
    """The archive's own record for a sample: no identifier, only its key."""
    return [{"t": s["t"], "account_key": s["account_key"],
             "u": {k: v for k, v in (("fh", s["five_hour_percent"]),
                                     ("sd", s["seven_day_percent"]),
                                     (SPEND_FIELD, s["spend_figure"]))
                   if v is not None}}
            for s in sorted(samples, key=lambda s: (s["t"], s.get("account_key") or ""))]


def archive_run(live=None, archive=None, dry_run=False):
    """Merge the live file into the archive. Append-only and idempotent.

    Returns (added, kept, problem). A live file that is not there is a problem
    reported, not an exception: the desktop app may simply never have run.
    """
    cfg_live, cfg_archive, _ = load_config()
    live = Path(live) if live else cfg_live
    archive = Path(archive) if archive else cfg_archive

    source = read_source(live)
    held = read_source(archive)
    if not source["exists"]:
        return 0, held["sample_count"], f"no desktop usage file at {live}"
    if source["problem"] and not source["samples"]:
        return 0, held["sample_count"], source["problem"]

    before = {(s["t"], s.get("account_key")) for s in held["samples"]}
    merged = merge(held["samples"], source["samples"])
    added = sum(1 for s in merged if (s["t"], s.get("account_key")) not in before)

    if added and not dry_run:
        payload = {
            "format": ARCHIVE_FORMAT,
            "_note": ("The desktop app's plan-usage history, kept because the app itself "
                      "keeps about thirty days and drops a day off the back each day. "
                      "Append-only: a sample archived here stays here. Accounts are held "
                      "as a one-way key, never as the identifier the app writes."),
            "_source": str(live),
            "_last_run": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "samples": archive_samples(merged),
        }
        archive.parent.mkdir(parents=True, exist_ok=True)
        tmp = archive.with_suffix(archive.suffix + ".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(archive)          # atomic: a crash never leaves a half file
    return added, len(before), None


# --------------------------------------------------------------------------
# command line


def _lines(data):
    out = []
    out.append(f"{data['sample_count']:,} sample(s) across {data['account_count']} account(s).")
    for source in data["sources"]:
        if source["exists"]:
            out.append(f"  read {source['sample_count']:,} from {source['path']}")
        else:
            out.append(f"  absent, and that is not an error: {source['path']}")
        if source["problem"] and source["exists"]:
            out.append(f"    {source['problem']}")

    for account in data["accounts"]:
        cover, new = account["coverage"], account["newest"]
        out.append("")
        out.append(f"{account['account']}")
        if new:
            out.append(f"  newest reading {new['at']} ({new['age_hours']}h old): "
                       f"five-hour {new['five_hour_percent']}%, "
                       f"seven-day {new['seven_day_percent']}%")
        out.append(f"  {cover['sample_count']:,} samples, {cover['first_sample_at']} to "
                   f"{cover['last_sample_at']}")
        out.append(f"  {cover['gap_count']} gap(s) over {cover['gap_minutes']} minutes; "
                   f"{cover['gaps_over_three_hours']} over {LONG_GAP_HOURS} hours; "
                   f"longest {cover['longest_gap_hours']}h")
        if cover["covered_fraction"] is not None:
            out.append(f"  covers {cover['covered_fraction'] * 100:.1f}% of its own span -- "
                       f"the rest is hours this file says nothing about")
        spend = account["spend_figure"]
        if spend["samples_with_a_figure"]:
            out.append(f"  spend figure `{spend['field']}` on "
                       f"{spend['samples_with_a_figure']} of {cover['sample_count']} samples, "
                       f"{spend['lowest']} to {spend['highest']}, unit not stated -- "
                       f"never shown in a currency")
        if account["weekly_series_spans_the_scale_break"]:
            out.append(f"  this account's seven-day series spans {WEEKLY_SCALE_BREAK}, when "
                       f"the weekly limit changed: it is two scales, not one")
    out.append("")
    out += [f"* {note}" for note in data["notes"]]
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--archive", action="store_true",
                        help="merge the live file into the register's own archive")
    parser.add_argument("--dry-run", action="store_true",
                        help="with --archive, report and write nothing")
    parser.add_argument("--source", help="the desktop usage file (read-only)")
    parser.add_argument("--archive-path", help="the register's own archive")
    parser.add_argument("--copies", help="folder of hand-taken copies")
    parser.add_argument("--gap-minutes", type=int, default=GAP_MINUTES,
                        help=f"report gaps longer than this (default {GAP_MINUTES})")
    args = parser.parse_args(argv)

    if args.archive:
        added, kept, problem = archive_run(args.source, args.archive_path, args.dry_run)
        if problem:
            print(f"plan usage: {problem}")
            return 0
        verb = "would add" if args.dry_run else "added"
        print(f"plan usage: {verb} {added:,} new sample(s); archive held {kept:,}.")
        return 0

    data = report(live=args.source, archive=args.archive_path, copies=args.copies,
                  gap_minutes=args.gap_minutes)
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print("\n".join(_lines(data)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
