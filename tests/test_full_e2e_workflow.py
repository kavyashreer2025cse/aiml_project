import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import hash_password
from app.database import Base, get_db
from app.main import app
from app.models import User
from app.models.medical_record import MedicalRecord


class FullMedShieldWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for index in list(User.__table__.indexes):
            if index.name == "ix_users_single_admin":
                User.__table__.indexes.remove(index)

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

        def override_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)

        with self.Session() as db:
            self.patient = User(
                email="patient01@medshield.test",
                password_hash=hash_password("DemoPass!2026"),
                role="Patient",
                status="Active",
                is_active=True,
                unique_user_id="MS-P-00001",
            )
            self.doctor = User(
                email="doctor01@medshield.test",
                password_hash=hash_password("DemoPass!2026"),
                role="Doctor",
                status="Active",
                is_active=True,
                unique_user_id="MS-D-00001",
            )
            db.add_all([self.patient, self.doctor])
            db.commit()
            db.refresh(self.patient)
            db.refresh(self.doctor)
            self.patient_id = self.patient.id
            self.doctor_id = self.doctor.id

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_complete_medshield_e2e_workflow(self):
        # 1. Verify Health Endpoints (with and without /api)
        res_h1 = self.client.get("/health")
        self.assertEqual(res_h1.status_code, 200)
        self.assertEqual(res_h1.json().get("status"), "healthy")

        res_h2 = self.client.get("/api/health")
        self.assertEqual(res_h2.status_code, 200)
        self.assertEqual(res_h2.json().get("status"), "healthy")

        # 2. Patient Login
        login_res = self.client.post(
            "/api/auth/login",
            json={"email": "patient01@medshield.test", "password": "DemoPass!2026"},
        )
        self.assertEqual(login_res.status_code, 200)
        patient_token = login_res.json()["access_token"]
        self.assertEqual(login_res.json()["role"], "Patient")
        p_headers = {"Authorization": f"Bearer {patient_token}"}

        # 3. Patient Updates Medical Record and Health Profile
        mr_update = self.client.post(
            "/api/patient/medical-record",
            headers=p_headers,
            json={"blood_group": "A+", "allergies": "Penicillin"},
        )
        self.assertEqual(mr_update.status_code, 200)
        self.assertEqual(mr_update.json()["blood_group"], "A+")

        # Add structured allergy
        al_res = self.client.post(
            "/api/patient/health/allergies",
            headers=p_headers,
            json={"allergen": "Aspirin", "reaction": "Hives", "severity": "High"},
        )
        self.assertEqual(al_res.status_code, 200)

        # Add structured condition
        cond_res = self.client.post(
            "/api/patient/health/conditions",
            headers=p_headers,
            json={"condition_name": "Hypertension", "status": "Active"},
        )
        self.assertEqual(cond_res.status_code, 200)

        # Add existing medication
        med_res = self.client.post(
            "/api/patient/health/medications",
            headers=p_headers,
            json={"medication_name": "Lisinopril", "dose": "10mg", "frequency": "Daily"},
        )
        self.assertEqual(med_res.status_code, 200)

        # Verify synthesized /patient/medical-record includes structured items
        mr_get = self.client.get("/api/patient/medical-record", headers=p_headers)
        self.assertEqual(mr_get.status_code, 200)
        data = mr_get.json()
        self.assertEqual(data["blood_group"], "A+")
        self.assertIn("Aspirin", data["allergies"])
        self.assertIn("Hypertension", data["medical_conditions"])
        self.assertIn("Lisinopril", data["current_medications"])

        # 4. Doctor Login
        doc_login = self.client.post(
            "/api/auth/login",
            json={"email": "doctor01@medshield.test", "password": "DemoPass!2026"},
        )
        self.assertEqual(doc_login.status_code, 200)
        doctor_token = doc_login.json()["access_token"]
        self.assertEqual(doc_login.json()["role"], "Doctor")
        d_headers = {"Authorization": f"Bearer {doctor_token}"}

        # Doctor cannot view patient context before consent
        pre_ctx = self.client.get(
            f"/api/doctor/patient/{self.patient_id}/safety-profile",
            headers=d_headers,
        )
        self.assertEqual(pre_ctx.status_code, 403)

        # 5. Doctor Requests Consent
        consent_req = self.client.post(
            "/api/doctor/consent-requests",
            headers=d_headers,
            json={"patient_unique_id": "MS-P-00001"},
        )
        self.assertEqual(consent_req.status_code, 200)
        consent_id = consent_req.json()["id"]
        self.assertEqual(consent_req.json()["status"], "Pending")

        # 6. Patient Approves Consent
        approve_res = self.client.post(
            f"/api/patient/consent-requests/{consent_id}/approve",
            headers=p_headers,
        )
        self.assertEqual(approve_res.status_code, 200)
        self.assertEqual(approve_res.json()["status"], "Active")

        # 7. Doctor Reads Authorized Patient Context
        post_ctx = self.client.get(
            f"/api/doctor/patient/{self.patient_id}/safety-profile",
            headers=d_headers,
        )
        self.assertEqual(post_ctx.status_code, 200)
        ctx_data = post_ctx.json()
        self.assertEqual(ctx_data["blood_group"], "A+")
        self.assertTrue(any(a["allergen"] == "Aspirin" for a in ctx_data["allergies"]))

        # 8. Doctor Records Consultation
        consult_res = self.client.post(
            f"/api/doctor/patient/{self.patient_id}/consultations",
            headers=d_headers,
            json={
                "reason_for_visit": "Persistent headache and fever",
                "notes": "Patient reports severe symptoms for 3 days.",
                "assessment": "Acute tension headache with mild febrile episode.",
            },
        )
        self.assertEqual(consult_res.status_code, 200)
        consultation_id = consult_res.json()["id"]

        # 9. Doctor Proposes Prescription
        rx_res = self.client.post(
            f"/api/doctor/patient/{self.patient_id}/prescriptions",
            headers=d_headers,
            json={
                "consultation_id": consultation_id,
                "doctor_notes": "Prescribing Amoxicillin 500mg TDS for 5 days.",
                "items": [
                    {
                        "medication_name": "Amoxicillin",
                        "dose": "500mg",
                        "frequency": "Three times daily",
                        "duration": "5 days",
                        "instructions": "Take with meals",
                    }
                ],
            },
        )
        self.assertEqual(rx_res.status_code, 200)
        prescription_id = rx_res.json()["id"]
        self.assertEqual(rx_res.json()["status"], "Proposed")

        # 10. Doctor Runs Safety Check
        safety_res = self.client.post(
            f"/api/doctor/patient/{self.patient_id}/safety-check",
            headers=d_headers,
            json={"prescription_id": prescription_id},
        )
        self.assertEqual(safety_res.status_code, 200)
        safety_data = safety_res.json()
        safety_check_id = safety_data["safety_check_id"]
        self.assertIn("findings", safety_data)
        # Check ML review signal
        self.assertIn("ml_review", safety_data)
        self.assertIsNotNone(safety_data["ml_review"])
        self.assertTrue(safety_data["ml_review"]["available"])
        self.assertIn("probability", safety_data["ml_review"])
        self.assertIn("explanation", safety_data["ml_review"])

        # 11. Doctor Reviews Safety Check (Approved)
        review_res = self.client.post(
            f"/api/doctor/safety-check/{safety_check_id}/review",
            headers=d_headers,
            json={
                "doctor_decision": "Approved",
                "doctor_decision_notes": "Benefits outweigh minor risk. Monitored for rash.",
            },
        )
        self.assertEqual(review_res.status_code, 200)
        self.assertEqual(review_res.json()["doctor_decision"], "Approved")

        # 12. Doctor Finalizes Prescription
        finalize_res = self.client.post(
            f"/api/doctor/prescriptions/{prescription_id}/finalize",
            headers=d_headers,
        )
        self.assertEqual(finalize_res.status_code, 200)
        self.assertEqual(finalize_res.json()["status"], "Finalized")

        # 13. Patient Views Finalized Prescription
        patient_rx_res = self.client.get(
            "/api/patient/prescriptions",
            headers=p_headers,
        )
        self.assertEqual(patient_rx_res.status_code, 200)
        patient_rxs = patient_rx_res.json()
        self.assertTrue(any(rx["id"] == prescription_id for rx in patient_rxs))


if __name__ == "__main__":
    unittest.main()
