"""导出门槛回归使用临时目录和模拟验收，不调用求解器。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.q4 import result_writer as writer


class SubmissionGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "outputs/model_validation/q4_reference_acceptance.json"
        self.path.parent.mkdir(parents=True)
        self.acceptance = dict(passed=True, team_confirmed=True, alpha=.85,
                               source=writer.REFERENCE_SOURCE, label="Q4-3 fixed-parameter final candidate",
                               parameter_adoption=writer.ADOPTION, days=334, slots=48096,
                               max_constraint_violation=1e-7, cross_day_soc_max_difference=0.)
        self.acceptance["lambda"] = .25
        for key in ("plan_cost_yuan","adjustment_cost_yuan","emergency_purchase_kwh","emergency_cost_yuan",
                    "total_actual_cost_yuan","emergency_slot_count","emergency_day_count","simultaneous_slots"):
            self.acceptance[key] = 0.
        for key in ("initial_soc_kwh","final_soc_kwh","minimum_soc_kwh","maximum_soc_kwh"):
            self.acceptance[key] = 1200.
        self.save()
        self.metrics = dict(self.acceptance, formal=True, variant=3, run_label="Q4-3 REFERENCE")
        self.metrics.update(total_plan_cost_real_yuan=0.,total_adjustment_cost_real_yuan=0.,
                            total_emergency_purchase_kwh=0.,total_emergency_cost_yuan=0.)

    def save(self):
        self.path.write_text(json.dumps(self.acceptance), encoding="utf-8")

    def test_reference_source_without_search(self):
        self.assertEqual(writer.resolve_submission_source(self.root,3),self.root/writer.REFERENCE_SOURCE)
        self.assertFalse((self.root/"outputs/q4/search").exists())

    def test_reject_invalid_confirmation(self):
        for key,value in dict(team_confirmed=False, passed=False, alpha=.9, source="outputs/q4/final",
                              label="REFERENCE", parameter_adoption="未确认", **{"lambda":.5}).items():
            with self.subTest(key=key):
                original = self.acceptance[key]
                self.acceptance[key] = value
                self.save()
                with self.assertRaises(ValueError):
                    writer.resolve_submission_source(self.root,3)
                self.acceptance[key] = original
                self.save()

    def test_reject_invalid_metrics(self):
        for key,value in dict(formal=False, variant=2, run_label="SMOKE", alpha=.9, **{"lambda":.5}).items():
            with self.subTest(key=key), patch.object(writer,"validate_outputs") as validate:
                with self.assertRaises(ValueError):
                    writer.validate_submission_source(self.root,3,{},dict(self.metrics,**{key:value}))
                validate.assert_not_called()

    def test_reference_enters_formal_validation_and_sha(self):
        with patch.object(writer,"validate_outputs",return_value=self.acceptance) as validate, patch.object(writer,"check_protected") as sha:
            writer.validate_submission_source(self.root,3,{},self.metrics)
            validate.assert_called_once_with({},3,formal=True)
            sha.assert_called_once_with(self.root,self.metrics)

    def test_reject_acceptance_numerical_conflict(self):
        with patch.object(writer,"validate_outputs",return_value=self.acceptance), patch.object(writer,"check_protected"):
            for change in ({"days":333},{"max_constraint_violation":2e-6},{"final_soc_kwh":6000.}):
                self.acceptance["final_soc_kwh"] = 1200.
                self.save()
                with self.subTest(change=change), self.assertRaises(ValueError):
                    writer.validate_submission_source(self.root,3,{},dict(self.metrics,**change))

    def test_variant_two_unchanged(self):
        self.assertEqual(writer.resolve_submission_source(self.root,2),self.root/"outputs/q4/q4_2")
        for label in ("REFERENCE","SMOKE"):
            with self.subTest(label=label), self.assertRaises(ValueError):
                writer.validate_submission_source(self.root,2,{},dict(formal=True,variant=2,run_label=label))

    def test_existing_destination_rejected_before_loading(self):
        destination = self.root/"outputs/submissions/result4-3.xlsx"
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"existing")
        with patch.object(writer,"load_outputs") as load, self.assertRaises(FileExistsError):
            writer.write_submission(self.root,3,human_approved=True)
        load.assert_not_called()
        self.assertEqual(destination.read_bytes(),b"existing")

    def test_human_approval_required(self):
        with self.assertRaises(ValueError):
            writer.write_submission(self.root,3)

    def test_protected_sha_still_rejects(self):
        with self.assertRaises(ValueError):
            writer.check_protected(self.root,{"protected_sha256":{"missing.csv":"a"}})


if __name__ == "__main__":
    unittest.main()
