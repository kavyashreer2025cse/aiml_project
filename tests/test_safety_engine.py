import unittest

from app.services.safety_engine import run_safety_engine
from app.services.ml_service import build_features


class SafetyEngineTests(unittest.TestCase):
    def test_rule_a_exact_allergy_match(self):
        findings = run_safety_engine(
            allergies=[{"allergen": "Penicillin"}],
            conditions=[],
            current_medications=[],
            prescription_items=[{"medication_name": "Penicillin", "dose": "500 mg"}],
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, "Allergy")
        self.assertEqual(findings[0].severity, "High")
        self.assertEqual(findings[0].title, "Potential allergy-related safety concern")
        self.assertEqual(findings[0].source, "Patient allergy record")

    def test_rule_a_normalized_allergy_match(self):
        # Patient allergic to Penicillin, doctor prescribes Penicillin V Potassium
        findings = run_safety_engine(
            allergies=[{"allergen": "Penicillin"}],
            conditions=[],
            current_medications=[],
            prescription_items=[{"medication_name": "Penicillin V Potassium", "dose": "250 mg"}],
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, "Allergy")
        self.assertEqual(findings[0].severity, "High")

    def test_rule_a_plural_allergy_match(self):
        # Patient allergic to Penicillins, prescribed Penicillin
        findings = run_safety_engine(
            allergies=[{"allergen": "Penicillins"}],
            conditions=[],
            current_medications=[],
            prescription_items=[{"medication_name": "Penicillin", "dose": "500 mg"}],
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "High")

    def test_rule_a_no_false_positive_substring(self):
        # Patient allergic to Sulfa, prescribed Morphine Sulfate -> Sulfa should not match Sulfate
        findings = run_safety_engine(
            allergies=[{"allergen": "Sulfa"}],
            conditions=[],
            current_medications=[],
            prescription_items=[{"medication_name": "Morphine Sulfate", "dose": "10 mg"}],
        )
        self.assertEqual(len(findings), 0)

    def test_rule_b_prescribed_simvastatin_over_20mg_with_current_amlodipine(self):
        findings = run_safety_engine(
            allergies=[],
            conditions=[],
            current_medications=[{"medication_name": "Amlodipine", "status": "Active"}],
            prescription_items=[{"medication_name": "Simvastatin", "dose": "40 mg"}],
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, "Drug-Drug Interaction")
        self.assertEqual(findings[0].severity, "High")
        self.assertEqual(findings[0].title, "Potential drug-drug interaction")
        self.assertEqual(findings[0].source, "FDA amlodipine prescribing information")
        self.assertIn("exceeds the 20 mg daily ceiling", findings[0].explanation)

    def test_rule_b_prescribed_simvastatin_under_or_equal_20mg_with_current_amlodipine(self):
        findings = run_safety_engine(
            allergies=[],
            conditions=[],
            current_medications=[{"medication_name": "Amlodipine", "status": "Active"}],
            prescription_items=[{"medication_name": "Simvastatin", "dose": "20 mg"}],
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, "Drug-Drug Interaction")
        self.assertEqual(findings[0].severity, "Moderate")
        self.assertIn("within the 20 mg daily ceiling", findings[0].explanation)

    def test_rule_b_unparseable_simvastatin_dose_with_current_amlodipine(self):
        findings = run_safety_engine(
            allergies=[],
            conditions=[],
            current_medications=[{"medication_name": "Amlodipine", "status": "Active"}],
            prescription_items=[{"medication_name": "Simvastatin", "dose": "one tablet daily"}],
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, "Drug-Drug Interaction")
        self.assertEqual(findings[0].severity, "Moderate")
        self.assertIn("could not be reliably verified", findings[0].explanation)

    def test_rule_b_prescribed_amlodipine_with_current_simvastatin(self):
        findings = run_safety_engine(
            allergies=[],
            conditions=[],
            current_medications=[{"medication_name": "Simvastatin", "dose": "40 mg", "status": "Active"}],
            prescription_items=[{"medication_name": "Amlodipine", "dose": "5 mg"}],
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, "Drug-Drug Interaction")
        self.assertEqual(findings[0].severity, "High")

    def test_rule_b_both_prescribed_together(self):
        findings = run_safety_engine(
            allergies=[],
            conditions=[],
            current_medications=[],
            prescription_items=[
                {"medication_name": "Simvastatin", "dose": "40 mg"},
                {"medication_name": "Amlodipine", "dose": "5 mg"},
            ],
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, "Drug-Drug Interaction")
        self.assertEqual(findings[0].severity, "High")

    def test_rule_b_stopped_current_medication_does_not_trigger(self):
        # Amlodipine is Stopped in medication history -> no interaction
        findings = run_safety_engine(
            allergies=[],
            conditions=[],
            current_medications=[{"medication_name": "Amlodipine", "status": "Stopped"}],
            prescription_items=[{"medication_name": "Simvastatin", "dose": "40 mg"}],
        )
        self.assertEqual(len(findings), 0)

    def test_ml_feature_builder_alignment(self):
        features = build_features(
            allergies=[{"allergen": "Penicillin"}],
            conditions=[{"condition_name": "Hypertension"}],
            current_medications=[{"medication_name": "Amlodipine", "status": "Active"}],
            prescription_items=[
                {"medication_name": "Penicillin V Potassium", "dose": "250 mg", "frequency": "Once daily"},
                {"medication_name": "Simvastatin", "dose": "40 mg", "frequency": "Once daily"},
            ],
        )
        self.assertEqual(features["allergy_match"], 1)
        self.assertEqual(features["simvastatin_amlodipine"], 1)
        self.assertEqual(features["simvastatin_over_20mg"], 1)
        self.assertEqual(features["daily_frequency"], 1)
        self.assertEqual(features["current_medication_count"], 1)
        self.assertEqual(features["condition_count"], 1)


if __name__ == "__main__":
    unittest.main()
