# SPDX-License-Identifier: Apache-2.0
"""reckon usage: the account's own meter -- R1, R2 and R4 of RECKON-1.2-SPEC.md.

No calculation is copied here (RECKON-1.1-SPEC.md decision 4, carried forward):
this builds argv for ledger/plan_usage.py and ledger/usage_paste.py and calls
their main(), exactly as `reckon record` does for the recorder.

Three ways in, in the spec's stated order: the desktop app's file where it
exists, the status line while a session runs (R3, not this command's), and a
paste when the newest reading is stale. `reckon usage` is the first; `reckon
usage --paste` is the third.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def _ledger(name):
    import importlib
    path = str(ROOT / "ledger")
    if path not in sys.path:
        sys.path.insert(0, path)
    return importlib.import_module(name)


def run_file(as_json=False, source=None, archive=None, copies=None, gap_minutes=None):
    plan_usage = _ledger("plan_usage")
    argv = []
    if as_json:
        argv.append("--json")
    if source:
        argv += ["--source", source]
    if archive:
        argv += ["--archive-path", archive]
    if copies:
        argv += ["--copies", copies]
    if gap_minutes:
        argv += ["--gap-minutes", str(gap_minutes)]
    return plan_usage.main(argv)


def run_archive(dry_run=False, source=None, archive=None):
    plan_usage = _ledger("plan_usage")
    argv = ["--archive"]
    if dry_run:
        argv.append("--dry-run")
    if source:
        argv += ["--source", source]
    if archive:
        argv += ["--archive-path", archive]
    return plan_usage.main(argv)


def run_paste(text=None, file=None, taken_at=None, account=None, observations=None,
              assume_yes=False, as_json=False):
    usage_paste = _ledger("usage_paste")
    argv = []
    if file:
        argv += ["--file", file]
    elif text:
        argv.append(text)
    if taken_at:
        argv += ["--taken-at", taken_at]
    if account:
        argv += ["--account", account]
    if observations:
        argv += ["--observations", observations]
    if assume_yes:
        argv.append("--yes")
    if as_json:
        argv.append("--json")
    return usage_paste.main(argv)
