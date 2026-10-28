"""Doctor-facing review signal from a model trained on labelled synthetic data."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
import pandas as pd


ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "ml_artifacts"
MODEL_PATH = ARTIFACT_DIR / "review_model.joblib"
METRICS_PATH = ARTIFACT_DIR / "metrics.json"
BACKGROUND_PATH = ARTIFACT_DIR / "shap_background.joblib"
FEATURES = ["current_medication_count", "condition_count", "allergy_match", "simvastatin_amlodipine", "simvastatin_over_20mg", "daily_frequency"]


def _normalize_text(s: str) -> str:
    s = re.sub(r"[^\w\s]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _allergy_matches(allergen: str, medication_name: str) -> bool:
    norm_a = _normalize_text(allergen)
    norm_m = _normalize_text(medication_name)
    if not norm_a or not norm_m:
        return False
    if norm_a == norm_m:
        return True
    pattern = r"\b" + re.escape(norm_a) + r"\b"
    if re.search(pattern, norm_m):
        return True
    if norm_a.endswith("s") and len(norm_a) > 3:
        singular = norm_a[:-1]
        if re.search(r"\b" + re.escape(singular) + r"\b", norm_m):
            return True
    return False


def _is_med(name: str, target: str) -> bool:
    norm = _normalize_text(name)
    return bool(re.search(r"\b" + re.escape(target) + r"\b", norm))


def _extract_mg_dose(dose: str) -> float | None:
    if not dose:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*mg\b", str(dose).strip().lower())
    return float(match.group(1)) if match else None


def build_features(allergies: list[dict], conditions: list[dict], current_medications: list[dict], prescription_items: list[dict]) -> dict:
    active_current = [
        x for x in current_medications
        if str(x.get("status", "Active")).strip().capitalize() == "Active"
    ]
    allergy_match = any(
        _allergy_matches(str(a.get("allergen", "")), str(p.get("medication_name", "")))
        for a in allergies for p in prescription_items if a.get("allergen")
    )
    prescribed_simva = [
        p for p in prescription_items
        if _is_med(str(p.get("medication_name", "")), "simvastatin")
    ]
    prescribed_amlo = [
        p for p in prescription_items
        if _is_med(str(p.get("medication_name", "")), "amlodipine")
    ]
    current_simva = [
        m for m in active_current
        if _is_med(str(m.get("medication_name", "")), "simvastatin")
    ]
    current_amlo = [
        m for m in active_current
        if _is_med(str(m.get("medication_name", "")), "amlodipine")
    ]

    has_interaction = (
        (bool(prescribed_simva) and (bool(current_amlo) or bool(prescribed_amlo)))
        or (bool(prescribed_amlo) and bool(current_simva))
    )

    all_simva = prescribed_simva if prescribed_simva else current_simva
    doses = [_extract_mg_dose(str(s.get("dose", ""))) for s in all_simva]
    valid_doses = [d for d in doses if d is not None]

    return {
        "current_medication_count": len(active_current),
        "condition_count": len(conditions),
        "allergy_match": int(allergy_match),
        "simvastatin_amlodipine": int(has_interaction),
        "simvastatin_over_20mg": int(has_interaction and any(d > 20 for d in valid_doses)),
        "daily_frequency": int(any("daily" in str(p.get("frequency", "")).casefold() for p in prescription_items)),
    }


_cached_model = None


def _load():
    global _cached_model
    if _cached_model is not None:
        return _cached_model
    import joblib
    if not MODEL_PATH.exists() or not METRICS_PATH.exists():
        try:
            import importlib
            train_ml = importlib.import_module("train_ml")
            train_ml.main()
        except Exception as err:
            # Fallback path if train_ml is located in parent
            try:
                import sys
                backend_dir = str(Path(__file__).resolve().parents[2])
                if backend_dir not in sys.path:
                    sys.path.insert(0, backend_dir)
                import train_ml
                train_ml.main()
            except Exception as train_err:
                print(f"[ML Service] Automatic model training failed: {train_err}")
                return None
    if not MODEL_PATH.exists() or not METRICS_PATH.exists():
        return None
    try:
        with MODEL_PATH.open("rb") as f:
            model = joblib.load(f)
        metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
        background = joblib.load(BACKGROUND_PATH) if BACKGROUND_PATH.exists() else None
        _cached_model = (model, metrics, background)
        return _cached_model
    except Exception as exc:
        print(f"[ML Service] Error loading model artifacts: {exc}")
        return None


def predict_review_signal(features: dict) -> dict:
    loaded = _load()
    if loaded is None:
        return {"available": False, "review_recommended": None, "probability": None,
                "explanation": "The synthetic-data model has not been trained yet.", "model_version": None}
    model, metadata, background = loaded
    row = pd.DataFrame([{key: features[key] for key in FEATURES}], columns=FEATURES)
    probability = float(model.predict_proba(row)[0][1])
    signal = int(probability >= 0.5)
    explanations = []
    try:
        import shap
        estimator = model.named_steps["classifier"]
        matrix = model.named_steps["preprocessor"].transform(row)
        if hasattr(estimator, "estimators_"):
            values = shap.TreeExplainer(estimator)(matrix).values
            scores = values[0, :, 1] if values.ndim == 3 else values[0]
        elif background is not None:
            values = shap.LinearExplainer(estimator, background)(matrix).values
            scores = values[0]
        else:
            scores = []
        if len(scores):
            names = model.named_steps["preprocessor"].get_feature_names_out()
            explanations = [
                f"{str(names[i]).replace('numeric__', '').replace('binary__', '')} ({'raised' if scores[i] > 0 else 'lowered'} the model signal)"
                for i in sorted(range(len(scores)), key=lambda j: abs(scores[j]), reverse=True)[:3]
                if abs(scores[i]) > 1e-6
            ]
    except Exception:
        explanations = []
    if not explanations:
        explanations = [name for name in FEATURES if features[name]]
    if not explanations:
        explanations = ["No strong contributing feature was identified"]
    return {"available": True, "review_recommended": signal,
            "probability": round(probability, 4),
            "explanation": "Review signal reflects: " + ", ".join(explanations) + ". Trained and evaluated on synthetic demonstration data; not clinical evidence.",
            "model_name": metadata["selected_model"],
            "model_version": metadata.get("model_version", "1.0.0"),
            "dataset": metadata["dataset"]}
