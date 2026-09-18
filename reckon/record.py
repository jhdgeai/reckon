# SPDX-License-Identifier: Apache-2.0
"""reckon record: ledger/recorder.py, then the store's run intake.

No calculation is copied here (RECKON-1.1-SPEC.md decision 4's "no logic"
carries to R1 as a whole): recorder.build() writes ledger/runs.json exactly as
`python3 ledger/recorder.py` does, and ingest_runs() is store.py's own
function -- the same one `store.py --ingest-runs` calls.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def _recorder():
    import importlib
    sys.path.insert(0, str(ROOT / "ledger"))
    return importlib.import_module("recorder")


def _store():
    import importlib
    sys.path.insert(0, str(ROOT / "store"))
    return importlib.import_module("store")


def run(source=None, session=None, root=None, out=None):
    """Returns an exit code. Mirrors `python3 ledger/recorder.py` followed by
    `store.py --ingest-runs`, because that is what this command is."""
    out = out or sys.stdout
    root = Path(root) if root else ROOT
    recorder = _recorder()

    argv = []
    if source:
        argv += ["--source", source]
    if session:
        argv += ["--session", session]
    rc = recorder.main(argv)

    if session:
        print("\n(--session prints one run only; nothing is intaken into the store. "
              "Run `reckon record` without --session to update it.)", file=out)
        return rc
    if rc != 0:
        return rc

    store = _store()
    register = store.RefRegister.load(root / "store" / "refs.json")
    existing = store.load_store(root)["runs"]
    ledger_path = root / "ledger" / "runs.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger_runs = ledger["runs"] if isinstance(ledger, dict) else ledger
    decisions = store.read_decisions(root / "decisions")
    observed = store.observe_preferences(decisions)
    if observed:
        store.append_decisions(observed, root / "decisions")
        decisions = list(decisions) + list(observed)
        print(f"preferences {len(observed)} fingerprint(s) recorded (changed since the last)",
              file=out)
    # The desktop app's own record of the same session (P-0001-T52). It is read
    # from `ledger/app_sessions.py`, which the shareable package does not ship:
    # it reads the Claude desktop app's files on THIS Mac. Where it is not
    # there, recording carries on without it and every new Run says so in its
    # own `why` -- the same sentence a session the app has no record of gets.
    # Before 17 September this raised FileNotFoundError out of `reckon record`,
    # which is how the package's own suite found it.
    app_sessions_mod = None
    try:
        from ledger import app_sessions as app_sessions_mod
    except ImportError:                      # pragma: no cover - layout fallback
        import importlib.util
        module_path = root / "ledger" / "app_sessions.py"
        if module_path.exists():
            spec = importlib.util.spec_from_file_location("app_sessions", module_path)
            app_sessions_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(app_sessions_mod)
    seen_sessions = app_sessions_mod.by_cli_session() if app_sessions_mod else {}
    records, report = store.ingest_runs(ledger_runs, register, existing,
                                        preferences=decisions,
                                        app_sessions=seen_sessions)

    print(file=out)
    for record in report["new"]:
        print(f"new        {record['ref']}  {record['session'][:8]}  "
              f"${record['cost_usd']:.2f}", file=out)
    for record in report["superseded"]:
        print(f"corrected  {record['ref']}  ${record['from_cost_usd']:.2f} -> "
              f"${record['to_cost_usd']:.2f}  ({', '.join(record['changed'])})", file=out)
    if report.get("backfilled"):
        print(f"backfilled {len(report['backfilled'])}  (session records added to runs "
              f"written before they existed; new records, nothing edited)", file=out)
    if report.get("held"):
        print(f"held       {len(report['held'])}  (still moving: no later session has "
              f"started, so nothing permanent is written for it yet)", file=out)
    print(f"unchanged  {len(report['unchanged'])}", file=out)

    by_file = {}
    for record in records:
        by_file.setdefault(store.runs_path(record["started_at"], root / "runs"), []
                           ).append(record)
    for path, group in by_file.items():
        store.append_runs(path, group)
        print(f"-> appended {len(group)} to {path}", file=out)
    register.save()
    return 0
