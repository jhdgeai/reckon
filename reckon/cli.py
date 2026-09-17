# SPDX-License-Identifier: Apache-2.0
"""reckon: one command over the estimator, the gate, the recorder and the
store -- estimate, gate, record, report, usage and status. Each subcommand is a thin wrapper:
it builds argv for the module that already does the work and calls its
main(), or calls its functions directly for report. No calculation is copied
here (RECKON-1.1-SPEC.md decision 4). See docs/METHOD.md.
"""

import argparse
import sys
from pathlib import Path

from . import install_check, record as record_mod, report as report_mod, usage as usage_mod

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def _module(name, subdir):
    import importlib
    path = str(ROOT / subdir)
    if path not in sys.path:
        sys.path.insert(0, path)
    return importlib.import_module(name)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="reckon",
        description="Preflight, gate, record and report the cost of a Claude Code task, "
                    "from the register's own estimator, gate, recorder and store.")
    sub = parser.add_subparsers(dest="command")

    p_estimate = sub.add_parser("estimate", help="price a proposal before it runs")
    p_estimate.add_argument("proposal", nargs="?", help="the proposal, in words")
    p_estimate.add_argument("--file", help="read the proposal from a file")
    p_estimate.add_argument("--json", action="store_true", help="machine-readable output")

    p_gate = sub.add_parser("gate", help="preview (and, with --execute, run) a task file")
    p_gate.add_argument("task", help="path to the task's markdown file")
    p_gate.add_argument("--execute", action="store_true",
                        help="actually run it. Costs real tokens. Default is dry-run.")
    p_gate.add_argument("--allowedTools", dest="allowed_tools", default=None)
    p_gate.add_argument("--permission-mode", dest="permission_mode", default=None)
    p_gate.add_argument("--scheduled", action="store_true")
    p_gate.add_argument("--gate-config", default=None)

    p_record = sub.add_parser(
        "record", help="turn Claude Code transcripts into Run records, then into the store")
    p_record.add_argument("--source", default=None, help="folder of Claude Code transcripts; default ~/.claude/projects, "
                               "or the archive ledger/archive-config.json names if that "
                               "file exists")
    p_record.add_argument("--session", default=None,
                          help="print one run only; nothing is intaken this way")

    p_report = sub.add_parser(
        "report", help="a read-only summary, including which tasks ran over estimate")
    p_report.add_argument("--sample", action="store_true",
                          help="read the sample shipped with the package instead of your store")

    p_usage = sub.add_parser(
        "usage", help="the account's own usage meter, per account, with its gaps")
    p_usage.add_argument("--paste", action="store_true",
                         help="read a pasted copy of the usage page in Claude's settings, "
                              "for when the desktop app's newest sample is stale. Paste the "
                              "whole panel; it is never a field at a time")
    p_usage.add_argument("--file", help="with --paste, read the paste from a file")
    p_usage.add_argument("--taken-at", dest="taken_at",
                         help="with --paste, when the page was read (ISO 8601). The page "
                              "gives clock times with no dates, so a paste needs this")
    p_usage.add_argument("--account", help="with --paste, account-1 / account-2 where known")
    p_usage.add_argument("--observations", help="with --paste, where observations are appended")
    p_usage.add_argument("--yes", action="store_true",
                         help="with --paste, save without asking. Without it, what was read "
                              "is shown and a yes is waited for")
    p_usage.add_argument("--archive", action="store_true",
                         help="copy the desktop app's newest samples into Reckon's own "
                              "archive, which keeps them after the app drops them (it keeps "
                              "about thirty days). Nothing runs this on a schedule unless "
                              "you set one up")
    p_usage.add_argument("--dry-run", action="store_true",
                         help="with --archive, report and write nothing")
    p_usage.add_argument("--source", help="the desktop usage file (read-only)")
    p_usage.add_argument("--archive-path", dest="archive_path",
                         help="Reckon's own archive of the meter")
    p_usage.add_argument("--copies", help="folder of hand-taken copies to merge in")
    p_usage.add_argument("--gap-minutes", dest="gap_minutes", type=int,
                         help="report gaps longer than this (default 60)")
    p_usage.add_argument("--json", action="store_true", help="machine-readable output")

    p_status = sub.add_parser(
        "status", help="where both usage limits stand now, from every source, with a "
                       "warning at 80 per cent")
    p_status.add_argument("--source", help="the desktop usage file (read-only)")
    p_status.add_argument("--archive-path", dest="archive_path",
                          help="Reckon's own archive of the meter")
    p_status.add_argument("--copies", help="folder of hand-taken copies to merge in")
    p_status.add_argument("--observations", help="pasted readings of the usage page")
    p_status.add_argument("--statusline", help="readings kept by the status line")
    p_status.add_argument("--json", action="store_true", help="machine-readable output")

    return parser


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    try:
        install_check.require_linked_install()
    except install_check.NotLinkedInstall as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.command == "estimate":
        estimate = _module("estimate", "estimator")
        sub_argv = []
        if args.file:
            sub_argv += ["--file", args.file]
        elif args.proposal:
            sub_argv += ["--proposal", args.proposal]
        if args.json:
            sub_argv += ["--json"]
        return estimate.main(sub_argv)

    if args.command == "gate":
        launch = _module("launch", "wrapper")
        sub_argv = [args.task]
        if args.execute:
            sub_argv.append("--execute")
        if args.allowed_tools:
            sub_argv += ["--allowedTools", args.allowed_tools]
        if args.permission_mode:
            sub_argv += ["--permission-mode", args.permission_mode]
        if args.scheduled:
            sub_argv.append("--scheduled")
        if args.gate_config:
            sub_argv += ["--gate-config", args.gate_config]
        return launch.main(sub_argv)

    if args.command == "record":
        return record_mod.run(source=args.source, session=args.session)

    if args.command == "report":
        return report_mod.run(sample=args.sample)

    if args.command == "usage":
        if args.paste:
            return usage_mod.run_paste(
                file=args.file, taken_at=args.taken_at, account=args.account,
                observations=args.observations, assume_yes=args.yes, as_json=args.json)
        if args.archive:
            return usage_mod.run_archive(dry_run=args.dry_run, source=args.source,
                                         archive=args.archive_path)
        return usage_mod.run_file(as_json=args.json, source=args.source,
                                  archive=args.archive_path, copies=args.copies,
                                  gap_minutes=args.gap_minutes)

    if args.command == "status":
        return usage_mod.run_status(as_json=args.json, source=args.source,
                                    archive=args.archive_path, copies=args.copies,
                                    observations=args.observations,
                                    statusline=args.statusline)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
