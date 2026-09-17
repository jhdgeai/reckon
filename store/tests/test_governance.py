#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Classification, and the consent an export needs before it is written.

Presentation mode is the register's own half and is not shipped; see
store/governance.py in this package for why.

Usage: python3 -m unittest discover -s store/tests

Own fixtures in a temp dir. Nothing here reads ~/.claude, the archive, the real
store or the network, and nothing here can reach a binary.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "store"))

import store            # noqa: E402
import governance       # noqa: E402


class Temp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        for name in ("projects", "tasks", "runs", "store", "ledger", "decisions"):
            (self.root / name).mkdir()
        self.refs = self.root / "store" / "refs.json"

    def tearDown(self):
        self.dir.cleanup()

    def register(self):
        return store.RefRegister.load(self.refs)

    def project(self, ref, **fields):
        record = {"ref": ref, "name": f"name-of-{ref}", "one_liner": "a one liner",
                  "stage": "captured"}
        record.update(fields)
        store.write_record(self.root / "projects" / f"{ref}.md", record, "")
        return record


class TestProviderNotDeployer(Temp):
    """§10 query 2, added to classification_queries() in an earlier session rather than
    built as a second classification reader somewhere else."""

    def test_provider_and_both_are_reported_separately(self):
        self.project("P-0001", my_role="provider")
        self.project("P-0002", my_role="both")
        self.project("P-0003", my_role="deployer")
        self.project("P-0004", my_role="n/a")
        loaded = store.load_store(self.root)
        result = governance.classification_queries(loaded)["provider_not_deployer"]
        self.assertEqual(result["provider"], ["P-0001"])
        self.assertEqual(result["both"], ["P-0002"])
        self.assertEqual(result["deployer"], ["P-0003"])
        self.assertEqual(result["not_applicable"], ["P-0004"])

    def test_a_project_with_no_role_is_unclassified_not_a_deployer(self):
        """Absent is not a value. Reading a blank as 'deployer' would be the
        register answering a governance question nobody answered."""
        self.project("P-0005")
        loaded = store.load_store(self.root)
        result = governance.classification_queries(loaded)["provider_not_deployer"]
        self.assertEqual(result["unclassified"], ["P-0005"])
        self.assertEqual(result["deployer"], [])

    def test_a_value_outside_the_vocabulary_is_not_silently_bucketed(self):
        self.project("P-0006", my_role="vendor")
        loaded = store.load_store(self.root)
        queries = governance.classification_queries(loaded)
        self.assertIn("P-0006", queries["provider_not_deployer"]["unclassified"])
        self.assertIn("my_role", queries["invalid_values"]["P-0006"])


# ----------------------------------------------------------- classification

class TestClassification(Temp):

    def test_is_ai_system_is_three_valued_and_never_a_bool(self):
        """§2.1: yes | no | contested. Two thirds of it is not the whole field,
        and `contested` is the honest answer for the interesting cases."""
        self.assertEqual(store.CLASSIFICATION_VOCABULARY["is_ai_system"],
                         ["yes", "no", "contested"])
        for value in ("yes", "no", "contested"):
            result = store.classify({"ref": "P-0009", "is_ai_system": value})
            self.assertEqual(result["fields"]["is_ai_system"]["value"], value)
            self.assertNotIsInstance(result["fields"]["is_ai_system"]["value"], bool)
            self.assertEqual(result["fields"]["is_ai_system"]["state"], "set")

    def test_the_parser_does_not_collapse_yes_and_no(self):
        fields, _ = store.parse_record("---\nref: P-0009\nis_ai_system: no\n---\n")
        self.assertEqual(fields["is_ai_system"], "no")
        self.assertNotIsInstance(fields["is_ai_system"], bool)

    def test_a_value_outside_the_vocabulary_is_invalid(self):
        result = store.classify({"ref": "P-0009", "act_tier": "medium"})
        self.assertEqual(result["fields"]["act_tier"]["state"], "invalid")
        self.assertIn("act_tier", result["invalid"])
        self.assertFalse(result["complete"])

    def test_a_captured_project_owes_no_classification_yet(self):
        """§3.1's principle from the classification side: fields become
        mandatory as a project advances, never at creation."""
        result = store.classify({"ref": "P-0009", "stage": "captured"})
        self.assertEqual(result["missing_and_owed"], [])
        self.assertTrue(result["unclassified"])
        self.assertFalse(result["fields"]["act_tier"]["owed_now"])

    def test_the_same_project_at_scoped_owes_three_of_the_four(self):
        result = store.classify({"ref": "P-0009", "stage": "scoped"})
        self.assertEqual(sorted(result["missing_and_owed"]),
                         ["act_tier", "is_ai_system", "my_role"])
        self.assertFalse(result["fields"]["third_party_output"]["owed_now"])

    def test_third_party_output_is_owed_from_validated(self):
        result = store.classify({"ref": "P-0009", "stage": "validated"})
        self.assertIn("third_party_output", result["missing_and_owed"])

    def test_which_stage_owes_what_is_read_from_the_one_table(self):
        """Not restated in the classification code. A second list is a second
        place to be wrong."""
        for field in store.CLASSIFICATION_FIELDS:
            stage = store.classification_owed_from(field)
            self.assertIn(field, store.STAGE_REQUIREMENTS[stage]["fields"])

    def test_check_calls_an_invalid_value_a_problem_not_an_advisory(self):
        """Advisory about debts is not advisory about the vocabulary -- the same
        rule an unknown stage has always had."""
        self.project("P-0009", stage="scoped", is_ai_system="maybe",
                     my_role="deployer", act_tier="minimal", directory="~/x")
        reg = self.register()
        reg.adopt("P-0009", "x", "project")
        result = store.check(store.load_store(self.root), reg)
        self.assertTrue(any("is_ai_system is 'maybe'" in line
                            for line in result["problems"]))
        self.assertTrue(any("yes | no | contested" in line
                            for line in result["problems"]))

    def test_check_calls_a_missing_classification_a_debt(self):
        self.project("P-0009", stage="scoped")
        reg = self.register()
        reg.adopt("P-0009", "x", "project")
        result = store.check(store.load_store(self.root), reg)
        self.assertEqual(result["problems"], [])
        self.assertTrue(any("owes 'act_tier'" in line for line in result["advisories"]))


class TestClassificationQueries(Temp):

    def setUp(self):
        super().setUp()
        self.project("P-0001", stage="production", is_ai_system="yes",
                     my_role="deployer", act_tier="high", third_party_output="client",
                     directory="~/a", output_location="~/a", value_estimate="3h",
                     context="business", type="code", value_basis="hours_saved",
                     next_review="2026-12-01")
        self.project("P-0002", stage="scoped", is_ai_system="contested",
                     my_role="provider", act_tier="transparency", directory="~/b")
        self.project("P-0003", stage="captured")
        self.project("P-0004", stage="validated", is_ai_system="no", my_role="n/a",
                     act_tier="minimal", directory="~/d")
        self.queries = governance.classification_queries(store.load_store(self.root))

    def test_missing_at_a_stage_that_owes_it(self):
        self.assertEqual(self.queries["missing_at_a_stage_that_owes_it"],
                         {"P-0004": ["third_party_output"]})

    def test_never_classified_is_a_different_answer_from_missing(self):
        """A captured shower thought owes nothing yet. Collapsing the two would
        be the flat thirty-field form §3.1 rejects."""
        self.assertEqual(self.queries["never_classified"], ["P-0003"])
        self.assertNotIn("P-0003", self.queries["missing_at_a_stage_that_owes_it"])

    def test_contested_gets_a_list_of_its_own(self):
        self.assertEqual(self.queries["contested"], ["P-0002"])
        self.assertEqual(self.queries["ai_systems"], ["P-0001"])

    def test_by_act_tier(self):
        self.assertEqual(self.queries["by_act_tier"]["high"], ["P-0001"])
        self.assertEqual(self.queries["by_act_tier"]["unclassified"], ["P-0003"])

    def test_output_reaching_a_third_party(self):
        self.assertEqual(self.queries["output_reaches_a_third_party"], ["P-0001"])

    def test_a_query_returns_refs_and_never_names(self):
        """A query result that carries names cannot be shown in presentation
        mode, which would make the two features contradict each other."""
        text = json.dumps(self.queries)
        for ref in ("P-0001", "P-0002", "P-0003", "P-0004"):
            self.assertNotIn(f"name-of-{ref}", text)


class TestTheGovernanceCLI(Temp):

    def run_cli(self, *argv):
        import io
        out = io.StringIO()
        code = governance.main(["--root", str(self.root), *argv], out=out)
        return code, out.getvalue()

    def setUp(self):
        super().setUp()
        self.project("P-0009", stage="scoped", name="secret-client-thing",
                     is_ai_system="contested", my_role="provider", directory="~/x")
        reg = self.register()
        reg.adopt("P-0009", "secret-client-thing", "project")
        reg.save()

    def test_the_default_view_names_what_is_owed(self):
        code, text = self.run_cli()
        self.assertEqual(code, 0)
        self.assertIn("is_ai_system=contested", text)
        self.assertIn("act_tier", text)

    def test_show_marks_missing_and_not_yet_owed_differently(self):
        code, text = self.run_cli("--show", "P-0009")
        self.assertEqual(code, 0)
        self.assertIn("owed from scoped", text)
        self.assertIn("not owed until validated", text)


# --------------------------------------------------------------------- row 8
# Export consent (§8.5). An earlier session. The serialiser shipped in an earlier session and the
# redactor in an earlier session; what row 8 owes is the DEMAND being recorded.
# --------------------------------------------------------------------------

class TestExportConsent(Temp):

    def payload(self):
        self.project("P-0001", name="secret-client-thing",
                     directory="/Users/someone/Clients/Acme")
        return store.export(store.load_store(self.root), self.register())

    def test_a_manifest_counts_the_disclosive_values_by_field(self):
        manifest = store.export_manifest(self.payload())
        self.assertGreaterEqual(manifest["disclosive_values"]["name"], 1)
        self.assertGreaterEqual(manifest["disclosive_values"]["directory"], 1)
        self.assertFalse(manifest["presentation_mode"])
        self.assertTrue(manifest["warnings"])

    def test_a_manifest_counts_the_natural_keys_in_the_allocation_register(self):
        """The leak an earlier session's audit found. A manifest that counted the record
        and not the register would understate what the export carries."""
        payload = self.payload()
        payload["refs"] = {"bindings": {
            "P-0001": {"kind": "project", "natural_key": "acme-thing"},
            "R-0001": {"kind": "run", "natural_key": "5b2f-a-uuid"}}}
        inventory = store.disclosive_inventory(payload)
        self.assertEqual(inventory["natural_key"], 1)      # the run's is not one

    def test_a_failed_audit_becomes_a_warning_on_the_manifest(self):
        manifest = store.export_manifest(
            self.payload(), presentation_mode=True,
            audit={"clean": False, "leaked": ["secret-client-thing"], "checked": 1})
        self.assertTrue(any("FAILED ITS OWN AUDIT" in w for w in manifest["warnings"]))

    def test_consent_needs_a_name_and_a_reason(self):
        manifest = store.export_manifest(self.payload())
        with self.assertRaises(store.ConsentNotRecorded):
            store.consent_record(manifest, by=None, reason="because")
        with self.assertRaises(store.ConsentNotRecorded):
            store.consent_record(manifest, by="ada", reason="   ")

    def test_consent_is_appended_to_the_append_only_decisions_log(self):
        manifest = store.export_manifest(self.payload(), destination="/tmp/x.json")
        record = store.record_export_consent(
            manifest, "ada", "sending to a client", root=self.root)
        self.assertEqual(record["kind"], "ExportConsent")
        loaded = store.load_store(self.root)
        self.assertEqual(len(store.export_consents(loaded)), 1)
        self.assertEqual(store.export_consents(loaded)[0]["by"], "ada")

    def test_a_consent_records_how_much_shipped_in_the_clear(self):
        manifest = store.export_manifest(self.payload())
        record = store.consent_record(manifest, "ada", "why")
        self.assertGreater(record["disclosive_values_in_the_clear"], 0)

    def test_nothing_is_written_when_consent_is_refused(self):
        manifest = store.export_manifest(self.payload())
        with self.assertRaises(store.ConsentNotRecorded):
            store.record_export_consent(manifest, "ada", None, root=self.root)
        self.assertEqual(list((self.root / "decisions").glob("*.jsonl")), [])



class TestTheExportCLIGate(Temp):

    def run_cli(self, *argv):
        import io
        out = io.StringIO()
        code = store.main(["--root", str(self.root), *argv], out=out)
        return code, out.getvalue()

    def setUp(self):
        super().setUp()
        self.project("P-0001", name="secret-client-thing")

    def test_stdout_is_not_gated_because_nothing_is_written(self):
        code, text = self.run_cli("--export")
        self.assertEqual(code, 0)
        self.assertIn("export manifest", text)
        self.assertIn("WARNING", text)                    # in the clear, and it says so

    def test_writing_a_file_without_a_name_is_refused(self):
        target = self.root / "export.json"
        code, text = self.run_cli("--export", "--out", str(target))
        self.assertEqual(code, 1)
        self.assertIn("REFUSED", text)
        self.assertFalse(target.exists())

    def test_writing_a_file_with_consent_records_it(self):
        target = self.root / "export.json"
        code, text = self.run_cli("--export", "--out", str(target),
                                  "--consent-by", "ada",
                                  "--consent-reason", "a client asked")
        self.assertEqual(code, 0)
        self.assertTrue(target.exists())
        code, log = self.run_cli("--consent-log")
        self.assertIn("ada", log)
        self.assertIn("a client asked", log)
        self.assertIn("IN THE CLEAR", log)
