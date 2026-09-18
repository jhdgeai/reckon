# SPDX-License-Identifier: Apache-2.0
"""Tests for reckon/cli.py: each subcommand reaches the right module with the
right arguments (RECKON-1.1-SPEC.md R1's acceptance test), reckon --help
lists every subcommand, and the install check gates all of them.

`usage` joined them in 1.2.0 (R1, R2 and R4)."""

import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from reckon import cli, install_check  # noqa: E402


class TestHelpListsEverySubcommand(unittest.TestCase):
    def test_help_names_estimate_gate_record_report_usage_and_status(self):
        text = cli.build_parser().format_help()
        for name in ("estimate", "gate", "record", "report", "usage", "status"):
            self.assertIn(name, text)


class TestRecordHelpNamesTheRealDefault(unittest.TestCase):
    def test_record_help_names_claude_projects_not_an_undefined_archive(self):
        """RECKON-USER-SPEC.md R3: on a fresh machine the default source is
        ~/.claude/projects, and "the archive" is defined nowhere a newcomer reads."""
        parser = cli.build_parser()
        record = parser._subparsers._group_actions[0].choices["record"]
        text = " ".join(record.format_help().split())
        self.assertIn("~/.claude/projects", text)
        self.assertNotIn("default the archive", text)


class TestDispatch(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(install_check, "require_linked_install",
                                    return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_estimate_passes_a_positional_proposal_through(self):
        fake = mock.Mock()
        fake.main.return_value = 0
        with mock.patch.object(cli, "_module", return_value=fake) as module_lookup:
            rc = cli.main(["estimate", "Build a thing", "--json"])
        self.assertEqual(rc, 0)
        module_lookup.assert_called_once_with("estimate", "estimator")
        fake.main.assert_called_once_with(["--proposal", "Build a thing", "--json"])

    def test_estimate_file_is_used_instead_of_a_positional_proposal(self):
        fake = mock.Mock()
        fake.main.return_value = 0
        with mock.patch.object(cli, "_module", return_value=fake):
            cli.main(["estimate", "--file", "p.txt"])
        fake.main.assert_called_once_with(["--file", "p.txt"])

    def test_gate_passes_the_task_file_and_execute_through_unchanged(self):
        fake = mock.Mock()
        fake.main.return_value = 0
        with mock.patch.object(cli, "_module", return_value=fake) as module_lookup:
            rc = cli.main(["gate", "tasks/P-0001-T61.md", "--execute"])
        self.assertEqual(rc, 0)
        module_lookup.assert_called_once_with("launch", "wrapper")
        fake.main.assert_called_once_with(["tasks/P-0001-T61.md", "--execute"])

    def test_gate_defaults_to_dry_run_by_passing_no_execute_flag(self):
        fake = mock.Mock()
        fake.main.return_value = 0
        with mock.patch.object(cli, "_module", return_value=fake):
            cli.main(["gate", "tasks/P-0001-T61.md"])
        fake.main.assert_called_once_with(["tasks/P-0001-T61.md"])

    def test_record_calls_the_record_module_with_source_and_session(self):
        with mock.patch.object(cli.record_mod, "run", return_value=0) as record_run:
            rc = cli.main(["record", "--source", "/tmp/x", "--session", "abc"])
        self.assertEqual(rc, 0)
        record_run.assert_called_once_with(source="/tmp/x", session="abc")

    def test_report_calls_the_report_module_with_sample(self):
        with mock.patch.object(cli.report_mod, "run", return_value=0) as report_run:
            rc = cli.main(["report", "--sample"])
        self.assertEqual(rc, 0)
        report_run.assert_called_once_with(sample=True)

    def test_usage_reads_the_desktop_file_by_default(self):
        with mock.patch.object(cli.usage_mod, "run_file", return_value=0) as run_file:
            rc = cli.main(["usage", "--json"])
        self.assertEqual(rc, 0)
        run_file.assert_called_once_with(as_json=True, source=None, archive=None,
                                         copies=None, gap_minutes=None)

    def test_usage_paste_goes_to_the_paste_reader(self):
        """R4 of RECKON-1.2-SPEC.md. The whole panel, from a file, so the
        permission dialog shows one short line rather than a wall of pasted
        text -- CLAUDE.md's rule about an ask he cannot read."""
        with mock.patch.object(cli.usage_mod, "run_paste", return_value=0) as run_paste:
            rc = cli.main(["usage", "--paste", "--file", "panel.txt",
                           "--taken-at", "2026-09-16T05:20:00Z", "--yes"])
        self.assertEqual(rc, 0)
        run_paste.assert_called_once_with(file="panel.txt",
                                          taken_at="2026-09-16T05:20:00Z",
                                          account=None, observations=None,
                                          assume_yes=True, as_json=False)

    def test_usage_archive_goes_to_the_archiver(self):
        with mock.patch.object(cli.usage_mod, "run_archive", return_value=0) as run_archive:
            rc = cli.main(["usage", "--archive", "--dry-run"])
        self.assertEqual(rc, 0)
        run_archive.assert_called_once_with(dry_run=True, source=None, archive=None)

    def test_status_goes_to_the_status_reader(self):
        """R5 and R6 of RECKON-1.2-SPEC.md."""
        with mock.patch.object(cli.usage_mod, "run_status", return_value=0) as run_status:
            rc = cli.main(["status", "--json"])
        self.assertEqual(rc, 0)
        run_status.assert_called_once_with(as_json=True, source=None, archive=None,
                                           copies=None, observations=None, statusline=None)

    def test_status_runs_end_to_end_on_empty_sources(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp, \
                contextlib.redirect_stdout(io.StringIO()) as printed:
            missing = str(Path(tmp) / "absent")
            rc = cli.main(["status", "--source", missing, "--archive-path", missing,
                           "--copies", missing, "--observations", missing, "--statusline", missing])
        self.assertEqual(rc, 0)
        self.assertIn("no reading from any source", printed.getvalue())

    def test_no_command_prints_help_and_returns_nonzero(self):
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            rc = cli.main([])
        self.assertEqual(rc, 1)
        self.assertIn("usage: reckon", printed.getvalue())


class TestInstallCheckGatesEveryCommand(unittest.TestCase):
    def test_a_refused_install_stops_before_any_module_runs(self):
        with mock.patch.object(install_check, "require_linked_install",
                               side_effect=install_check.NotLinkedInstall("nope")):
            with mock.patch.object(cli, "_module") as module_lookup, \
                    contextlib.redirect_stderr(io.StringIO()) as printed:
                rc = cli.main(["estimate", "text"])
        self.assertEqual(rc, 2)
        self.assertIn("ERROR: nope", printed.getvalue())
        module_lookup.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class TestTheVersionIsOneNumber(unittest.TestCase):
    """P-0001-T77, 17 September 2026: reckon/__init__.py said 1.1.0 while the
    package was published as 1.2.1. Two copies of a version drift; this holds
    them together until there is one."""

    def test_the_module_and_the_package_say_the_same_version(self):
        import re
        from pathlib import Path
        import reckon
        root = Path(__file__).resolve().parents[2]
        declared = re.search(r'^version\s*=\s*"([^"]+)"',
                             (root / "pyproject.toml").read_text(encoding="utf-8"), re.M)
        self.assertIsNotNone(declared)
        self.assertEqual(reckon.__version__, declared.group(1))
