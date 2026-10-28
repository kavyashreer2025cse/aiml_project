from datetime import datetime, timedelta, timezone
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool
from jose import jwt
from sqlalchemy.orm import sessionmaker

from app.auth import ALGORITHM, SECRET_KEY, create_access_token, hash_password, verify_password
from app.database import Base, get_db
from app.main import app
from app.models import User
from app.models.audit import AuditLog
from app.models.consent import ConsentRequest
from app.models.health import Allergy, PatientMedication
from app.models.medical_record import MedicalRecord


class MedShieldFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The model's partial unique Admin index is PostgreSQL-specific.
        for index in list(User.__table__.indexes):
            if index.name == "ix_users_single_admin":
                User.__table__.indexes.remove(index)

    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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
            self.patient = self._user(db, "patient@example.com", "Patient", "MS-P-00001")
            self.doctor = self._user(db, "doctor@example.com", "Doctor", "MS-D-00001")
            self.admin = self._user(db, "admin@example.com", "Admin", None)
            db.add(MedicalRecord(patient_id=self.patient.id, blood_group="O+"))
            db.commit()
            self.patient_id, self.doctor_id, self.admin_id = self.patient.id, self.doctor.id, self.admin.id

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    @staticmethod
    def _user(db, email, role, public_id):
        user = User(email=email, password_hash=hash_password("correct horse battery"),
                    role=role, status="Active", is_active=True, unique_user_id=public_id)
        db.add(user)
        db.flush()
        return user

    def headers(self, user_id, role):
        return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}

    def test_password_hash_and_invalid_token(self):
        hashed = hash_password("correct horse battery")
        self.assertTrue(verify_password("correct horse battery", hashed))
        self.assertFalse(verify_password("wrong", hashed))
        response = self.client.get("/patient/consent-requests", headers={"Authorization": "Bearer bad"})
        self.assertEqual(response.status_code, 401)
        expired = jwt.encode({"sub": str(self.patient_id), "role": "Patient", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)}, SECRET_KEY, algorithm=ALGORITHM)
        self.assertEqual(self.client.get("/patient/consent-requests", headers={"Authorization": f"Bearer {expired}"}).status_code, 401)

    def test_inactive_account_and_private_status_route(self):
        with self.Session() as db:
            patient = db.get(User, self.patient_id)
            patient.is_active = False
            patient.status = "Deactivated"
            db.commit()
        self.assertEqual(self.client.get("/auth/me", headers=self.headers(self.patient_id, "Patient")).status_code, 403)
        self.assertEqual(self.client.get("/auth/account-status", params={"email": "patient@example.com"}).status_code, 401)

    def test_registration_requires_approval_and_role_is_server_controlled(self):
        response = self.client.post("/auth/register", json={"email": "new@example.com", "password": "secure-pass-123", "role": "Admin"})
        self.assertEqual(response.status_code, 400)
        response = self.client.post("/auth/register", json={"email": "new@example.com", "password": "secure-pass-123", "role": "Patient"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "Pending Approval")
        denied = self.client.post("/auth/login", json={"email": "new@example.com", "password": "secure-pass-123"})
        self.assertEqual(denied.status_code, 401)

    def test_admin_approval_and_admin_authorization(self):
        self.assertEqual(self.client.get("/admin/users", headers=self.headers(self.patient_id, "Patient")).status_code, 403)
        self.client.post("/auth/register", json={"email": "approve@example.com", "password": "secure-pass-123", "role": "Patient"})
        with self.Session() as db:
            user = db.scalar(select(User).where(User.email == "approve@example.com"))
            user_id = user.id
        response = self.client.post(f"/admin/users/{user_id}/approve", headers=self.headers(self.admin_id, "Admin"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["unique_user_id"], "MS-P-00002")
        self.assertEqual(self.client.post(f"/admin/users/{user_id}/activation", headers=self.headers(self.admin_id, "Admin"), json={"is_active": False}).json()["status"], "Deactivated")
        self.assertEqual(self.client.post(f"/admin/users/{user_id}/activation", headers=self.headers(self.admin_id, "Admin"), json={"is_active": True}).json()["status"], "Active")

        rejected_response = self.client.post("/auth/register", json={"email": "reject@example.com", "password": "secure-pass-123", "role": "Patient"})
        self.assertEqual(rejected_response.status_code, 200)
        with self.Session() as db:
            rejected_user = db.scalar(select(User).where(User.email == "reject@example.com"))
            rejected_id = rejected_user.id
        rejected = self.client.post(f"/admin/users/{rejected_id}/reject", headers=self.headers(self.admin_id, "Admin"))
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.json()["status"], "Rejected")
        self.assertFalse(rejected.json()["is_active"])

    def test_consent_gate_approve_expire_and_revoke(self):
        with self.Session() as db:
            other_patient = self._user(db, "other-patient@example.com", "Patient", "MS-P-00002")
            other_patient_id = other_patient.id
            db.commit()
        path = f"/doctor/patient/{self.patient_id}/medical-record"
        self.assertEqual(self.client.get(path, headers=self.headers(self.doctor_id, "Doctor")).status_code, 403)
        self.assertEqual(self.client.post("/doctor/consent-requests", headers=self.headers(self.doctor_id, "Doctor"), json={"patient_unique_id": "MS-P-99999"}).status_code, 404)
        request = self.client.post("/doctor/consent-requests", headers=self.headers(self.doctor_id, "Doctor"), json={"patient_unique_id": "MS-P-00001"})
        self.assertEqual(request.status_code, 200)
        consent_id = request.json()["id"]
        self.assertEqual(self.client.post(f"/patient/consent-requests/{consent_id}/approve", headers=self.headers(other_patient_id, "Patient")).status_code, 404)
        self.assertEqual(self.client.post(f"/patient/consent-requests/{consent_id}/approve", headers=self.headers(self.patient_id, "Patient")).status_code, 200)
        self.assertEqual(self.client.get(path, headers=self.headers(self.doctor_id, "Doctor")).status_code, 200)
        self.assertEqual(self.client.post(f"/patient/consent-requests/{consent_id}/revoke", headers=self.headers(self.patient_id, "Patient")).status_code, 200)
        self.assertEqual(self.client.get(path, headers=self.headers(self.doctor_id, "Doctor")).status_code, 403)
        self.assertEqual(self.client.post(f"/patient/consent-requests/{consent_id}/approve", headers=self.headers(self.admin_id, "Admin")).status_code, 403)

    def test_consent_expiry_and_audit(self):
        with self.Session() as db:
            consent = ConsentRequest(doctor_id=self.doctor_id, patient_id=self.patient_id, status="Active",
                requested_at=datetime.now(timezone.utc) - timedelta(hours=2),
                expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
            db.add(consent)
            db.commit()
            consent_id = consent.id
        response = self.client.get(f"/doctor/patient/{self.patient_id}/medical-record", headers=self.headers(self.doctor_id, "Doctor"))
        self.assertEqual(response.status_code, 403)
        with self.Session() as db:
            self.assertEqual(db.get(ConsentRequest, consent_id).status, "Expired")
            self.assertTrue(db.scalar(select(AuditLog).where(AuditLog.action == "CONSENT_EXPIRED")))

    def test_consultation_safety_review_and_finalization(self):
        with self.Session() as db:
            other_doctor = self._user(db, "other-doctor@example.com", "Doctor", "MS-D-00002")
            other_doctor_id = other_doctor.id
            db.add(Allergy(patient_id=self.patient_id, allergen="Simvastatin", severity="High"))
            db.add(PatientMedication(patient_id=self.patient_id, medication_name="Amlodipine", status="Active"))
            db.commit()
        doctor_login = self.client.post("/auth/login", json={"email": "doctor@example.com", "password": "correct horse battery"})
        patient_login = self.client.post("/auth/login", json={"email": "patient@example.com", "password": "correct horse battery"})
        self.assertEqual(doctor_login.status_code, 200)
        self.assertEqual(patient_login.status_code, 200)
        headers = {"Authorization": f"Bearer {doctor_login.json()['access_token']}"}
        patient_headers = {"Authorization": f"Bearer {patient_login.json()['access_token']}"}
        other_doctor_headers = self.headers(other_doctor_id, "Doctor")
        self.assertEqual(self.client.get(f"/doctor/patient/{self.patient_id}/safety-profile", headers=other_doctor_headers).status_code, 403)
        self.assertEqual(self.client.post(f"/doctor/patient/{self.patient_id}/consultations", headers=headers, json={"patient_id": self.patient_id, "reason_for_visit": "No consent"}).status_code, 403)
        consent = self.client.post("/doctor/consent-requests", headers=headers, json={"patient_unique_id": "MS-P-00001"})
        self.assertEqual(consent.status_code, 200, consent.text)
        consent_id = consent.json()["id"]
        self.assertEqual(self.client.post(f"/patient/consent-requests/{consent_id}/approve", headers=patient_headers).status_code, 200)
        refreshed = self.client.get("/doctor/consent-requests", headers=headers)
        self.assertEqual(refreshed.json()[0]["status"], "Active")
        self.assertEqual(self.client.get(f"/doctor/patient/{self.patient_id}/medical-record", headers=headers).status_code, 200)
        consultation = self.client.post(f"/doctor/patient/{self.patient_id}/consultations", headers=headers,
            json={"patient_id": self.patient_id, "reason_for_visit": "Medication review", "clinical_notes": "Synthetic test", "assessment": "Review proposed therapy"})
        self.assertEqual(consultation.status_code, 200, consultation.text)
        consult_id = consultation.json()["id"]
        proposed = self.client.post(f"/doctor/patient/{self.patient_id}/prescriptions", headers=headers,
            json={"consultation_id": consult_id, "patient_id": self.patient_id, "items": [{"medication_name": "Simvastatin", "dose": "40 mg", "frequency": "Once daily", "duration": "30 days"}]})
        self.assertEqual(proposed.status_code, 200, proposed.text)
        prescription_id = proposed.json()["id"]
        finalize_path = f"/doctor/prescriptions/{prescription_id}/finalize"
        self.assertEqual(self.client.post(finalize_path, headers=other_doctor_headers).status_code, 403)
        self.assertEqual(self.client.post(finalize_path, headers=headers).status_code, 400)
        check = self.client.post(f"/doctor/patient/{self.patient_id}/safety-check", headers=headers, json={"prescription_id": prescription_id})
        self.assertEqual(check.status_code, 200, check.text)
        self.assertTrue(check.json()["findings"])
        self.assertTrue(check.json()["ml_review"]["available"])
        self.assertEqual(self.client.post(f"/doctor/safety-check/{check.json()['safety_check_id']}/review", headers=other_doctor_headers, json={"doctor_decision": "Approved"}).status_code, 403)
        review = self.client.post(f"/doctor/safety-check/{check.json()['safety_check_id']}/review", headers=headers, json={"doctor_decision": "Approved", "doctor_decision_notes": "Reviewed synthetic case"})
        self.assertEqual(review.status_code, 200, review.text)
        self.assertEqual(self.client.post(finalize_path, headers=headers).status_code, 200)
        patient_prescriptions = self.client.get("/patient/prescriptions", headers=patient_headers)
        self.assertEqual(patient_prescriptions.status_code, 200)
        self.assertEqual(patient_prescriptions.json()[0]["status"], "Finalized")
        admin_logs = self.client.get("/admin/audit-logs", headers=self.headers(self.admin_id, "Admin"))
        self.assertEqual(admin_logs.status_code, 200)
        with self.Session() as db:
            actions = set(db.scalars(select(AuditLog.action)).all())
        self.assertTrue({"CONSULTATION_CREATED", "PRESCRIPTION_PROPOSED", "SAFETY_CHECK_PERFORMED", "SAFETY_CHECK_REVIEWED", "PRESCRIPTION_FINALIZED"}.issubset(actions))


if __name__ == "__main__":
    unittest.main()
