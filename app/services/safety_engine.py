import re
from dataclasses import dataclass


@dataclass
class SafetyFinding:
    category: str
    severity: str
    title: str
    explanation: str
    source: str


def _extract_mg_dose(dose: str) -> float | None:
    """
    Extract a numeric mg dose only when the dose contains
    an explicit numeric value followed by mg.
    """
    if not dose:
        return None

    match = re.search(
        r"(\d+(?:\.\d+)?)\s*mg\b",
        dose.strip().lower(),
    )

    if match is None:
        return None

    return float(match.group(1))


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


def run_safety_engine(
    allergies: list[dict],
    conditions: list[dict],
    current_medications: list[dict],
    prescription_items: list[dict],
) -> list[SafetyFinding]:
    findings: list[SafetyFinding] = []

    # ---------------------------------------------------------
    # Rule 1: Recorded allergy vs prescribed medication
    # ---------------------------------------------------------
    for prescribed in prescription_items:
        medication_name = prescribed.get("medication_name", "")

        for allergy in allergies:
            allergen = allergy.get("allergen", "")

            if allergen and _allergy_matches(allergen, medication_name):
                findings.append(
                    SafetyFinding(
                        category="Allergy",
                        severity="High",
                        title="Potential allergy-related safety concern",
                        explanation=(
                            f"The prescribed medication ({medication_name}) "
                            f"matches a recorded patient allergen ({allergen}). "
                            "Professional review is required."
                        ),
                        source="Patient allergy record",
                    )
                )

    # ---------------------------------------------------------
    # Rule 2: Amlodipine + Simvastatin interaction
    # ---------------------------------------------------------
    active_current = [
        m for m in current_medications
        if str(m.get("status", "Active")).strip().capitalize() == "Active"
    ]

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

    if has_interaction:
        simva_sources = prescribed_simva if prescribed_simva else current_simva
        parsed_doses = [
            _extract_mg_dose(str(s.get("dose", "")))
            for s in simva_sources
        ]
        valid_doses = [d for d in parsed_doses if d is not None]

        if valid_doses:
            dose_mg = max(valid_doses)
            if dose_mg > 20:
                severity = "High"
                explanation = (
                    f"Simvastatin dose ({dose_mg:g} mg) exceeds the 20 mg daily ceiling "
                    "recommended when co-administered with amlodipine due to increased "
                    "risk of myopathy and rhabdomyolysis. Current prescribing guidelines "
                    "limit simvastatin to 20 mg daily with amlodipine."
                )
            else:
                severity = "Moderate"
                explanation = (
                    f"Co-administration of amlodipine and simvastatin ({dose_mg:g} mg) "
                    "increases simvastatin exposure. Dose is within the 20 mg daily ceiling, "
                    "but clinical review is recommended."
                )
        else:
            severity = "Moderate"
            explanation = (
                "Simvastatin and amlodipine are co-administered. The simvastatin dose could "
                "not be reliably verified from the recorded dose format. Simvastatin should "
                "not exceed 20 mg daily when taken with amlodipine."
            )

        findings.append(
            SafetyFinding(
                category="Drug-Drug Interaction",
                severity=severity,
                title="Potential drug-drug interaction",
                explanation=explanation,
                source="FDA amlodipine prescribing information",
            )
        )

    return findings