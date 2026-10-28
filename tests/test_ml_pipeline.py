import json
import unittest

from app.services.ml_service import ARTIFACT_DIR, build_features, predict_review_signal


class MLReviewTests(unittest.TestCase):
    def test_training_artifacts_contain_measured_model_comparison(self):
        metrics = json.loads((ARTIFACT_DIR / "metrics.json").read_text(encoding="utf-8"))
        self.assertEqual(metrics["sample_count"], 5000)
        self.assertEqual(set(metrics["metrics"]), {"logistic_regression", "random_forest"})
        for score in metrics["metrics"].values():
            self.assertTrue({"accuracy", "precision", "recall", "f1", "roc_auc"}.issubset(score))
            self.assertTrue(all(0 <= score[key] <= 1 for key in ("accuracy", "precision", "recall", "f1", "roc_auc")))

    def test_prediction_and_explanation_for_interaction_context(self):
        features = build_features(
            allergies=[], conditions=[{"condition_name": "Hypertension"}],
            current_medications=[{"medication_name": "Amlodipine", "status": "Active"}],
            prescription_items=[{"medication_name": "Simvastatin", "dose": "40 mg", "frequency": "Once daily"}],
        )
        self.assertEqual(features["simvastatin_amlodipine"], 1)
        self.assertEqual(features["simvastatin_over_20mg"], 1)
        prediction = predict_review_signal(features)
        self.assertTrue(prediction["available"])
        self.assertIn(prediction["review_recommended"], (0, 1))
        self.assertGreaterEqual(prediction["probability"], 0)
        self.assertLessEqual(prediction["probability"], 1)
        self.assertTrue(prediction["explanation"])
        self.assertIn("synthetic", prediction["explanation"])


if __name__ == "__main__":
    unittest.main()
