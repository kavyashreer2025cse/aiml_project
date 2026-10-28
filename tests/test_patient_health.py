import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token, hash_password
from app.database import Base, get_db
from app.main import app
from app.models import User
from app.models.medical_record import MedicalRecord


class PatientHealthEndpointsTests(unittest.TestCase):
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
            self.patient1 = User(
                email="patient1@example.com",
                password_hash=hash_password("pass123"),
                role="Patient",
                status="Active",
                is_active=True,
                unique_user_id="MS-P-00001",
            )
            self.patient2 = User(
                email="patient2@example.com",
                password_hash=hash_password("pass123"),
                role="Patient",
                status="Active",
                is_active=True,
                unique_user_id="MS-P-00002",
            )
            db.add_all([self.patient1, self.patient2])
            db.commit()
            self.p1_id = self.patient1.id
            self.p2_id = self.patient2.id

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def headers(self, user_id, role="Patient"):
        return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}

    def test_allergy_crud_and_isolation(self):
        # 1. Add allergy for Patient 1
        res = self.client.post(
            "/patient/health/allergies",
            headers=self.headers(self.p1_id),
            json={"allergen": "Penicillin", "reaction": "Rash", "severity": "High"},
        )
        self.assertEqual(res.status_code, 200)
        allergy_id = res.json()["id"]
        self.assertEqual(res.json()["allergen"], "Penicillin")

        # 2. Patient 1 lists allergies
        list_res = self.client.get("/patient/health/allergies", headers=self.headers(self.p1_id))
        self.assertEqual(list_res.status_code, 200)
        self.assertEqual(len(list_res.json()), 1)

        # 3. Patient 2 cannot see Patient 1's allergy
        p2_list = self.client.get("/patient/health/allergies", headers=self.headers(self.p2_id))
        self.assertEqual(len(p2_list.json()), 0)

        # 4. Patient 2 cannot delete Patient 1's allergy
        del_attempt = self.client.delete(
            f"/patient/health/allergies/{allergy_id}",
            headers=self.headers(self.p2_id),
        )
        self.assertEqual(del_attempt.status_code, 404)

        # 5. Patient 1 deletes own allergy
        del_res = self.client.delete(
            f"/patient/health/allergies/{allergy_id}",
            headers=self.headers(self.p1_id),
        )
        self.assertEqual(del_res.status_code, 200)

        # Verify deletion
        list_after = self.client.get("/patient/health/allergies", headers=self.headers(self.p1_id))
        self.assertEqual(len(list_after.json()), 0)

    def test_condition_crud_and_isolation(self):
        # 1. Add condition for Patient 1
        res = self.client.post(
            "/patient/health/conditions",
            headers=self.headers(self.p1_id),
            json={"condition_name": "Hypertension", "notes": "Managed by diet"},
        )
        self.assertEqual(res.status_code, 200)
        cond_id = res.json()["id"]

        # 2. Patient 2 cannot delete Patient 1's condition
        del_attempt = self.client.delete(
            f"/patient/health/conditions/{cond_id}",
            headers=self.headers(self.p2_id),
        )
        self.assertEqual(del_attempt.status_code, 404)

        # 3. Patient 1 deletes own condition
        del_res = self.client.delete(
            f"/patient/health/conditions/{cond_id}",
            headers=self.headers(self.p1_id),
        )
        self.assertEqual(del_res.status_code, 200)

    def test_medication_crud_stop_and_isolation(self):
        # 1. Add medication for Patient 1
        res = self.client.post(
            "/patient/health/medications",
            headers=self.headers(self.p1_id),
            json={"medication_name": "Amlodipine", "dose": "5 mg", "frequency": "Once daily"},
        )
        self.assertEqual(res.status_code, 200)
        med_id = res.json()["id"]
        self.assertEqual(res.json()["status"], "Active")

        # 2. Patient 2 cannot stop Patient 1's medication
        stop_attempt = self.client.post(
            f"/patient/health/medications/{med_id}/stop",
            headers=self.headers(self.p2_id),
        )
        self.assertEqual(stop_attempt.status_code, 404)

        # 3. Patient 1 stops own medication
        stop_res = self.client.post(
            f"/patient/health/medications/{med_id}/stop",
            headers=self.headers(self.p1_id),
        )
        self.assertEqual(stop_res.status_code, 200)
        self.assertEqual(stop_res.json()["status"], "Stopped")
        self.assertIsNotNone(stop_res.json()["stopped_at"])

        # 4. Patient 1 deletes own medication
        del_res = self.client.delete(
            f"/patient/health/medications/{med_id}",
            headers=self.headers(self.p1_id),
        )
        self.assertEqual(del_res.status_code, 200)

    def test_update_blood_group(self):
        res = self.client.post(
            "/patient/medical-record",
            headers=self.headers(self.p1_id),
            json={"blood_group": "AB+"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["blood_group"], "AB+")

        # Fetch record
        get_res = self.client.get("/patient/medical-record", headers=self.headers(self.p1_id))
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.json()["blood_group"], "AB+")


if __name__ == "__main__":
    unittest.main()
