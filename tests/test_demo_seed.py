import unittest

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

import seed_demo
from app.database import Base
from app.models import User
from app.models.consent import ConsentRequest
from app.models.health import Allergy, PatientMedication
from app.models.medical_record import MedicalRecord


class DemoSeedTests(unittest.TestCase):
    def test_seed_is_repeatable_and_contains_required_demo_scenarios(self):
        for index in list(User.__table__.indexes):
            if index.name == "ix_users_single_admin":
                User.__table__.indexes.remove(index)
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        original = seed_demo.SessionLocal
        seed_demo.SessionLocal = sessions
        try:
            seed_demo.main()
            seed_demo.main()
            with sessions() as db:
                self.assertEqual(db.scalar(select(func.count(User.id)).where(User.role == "Patient")), 10)
                self.assertEqual(db.scalar(select(func.count(User.id)).where(User.role == "Doctor")), 10)
                self.assertEqual(db.scalar(select(func.count(User.id)).where(User.role == "Admin")), 1)
                self.assertEqual(db.scalar(select(func.count(MedicalRecord.id))), 10)
                self.assertTrue(db.scalar(select(Allergy).where(Allergy.allergen == "Penicillin")))
                self.assertTrue(db.scalar(select(PatientMedication).where(PatientMedication.medication_name == "Amlodipine")))
                self.assertEqual(db.scalar(select(func.count(ConsentRequest.id))), 2)
        finally:
            seed_demo.SessionLocal = original
            Base.metadata.drop_all(engine)
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
