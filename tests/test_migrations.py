from uuid import uuid4
import unittest
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from app.database import settings


class MigrationSmokeTests(unittest.TestCase):
    def test_all_migrations_build_a_fresh_schema(self):
        database = Path(__file__).resolve().parents[1] / f".migration-smoke-{uuid4().hex}.sqlite"
        previous = settings.database_url
        engine = None
        try:
            settings.database_url = f"sqlite:///{database.as_posix()}"
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            command.upgrade(config, "head")
            engine = create_engine(settings.database_url)
            tables = set(inspect(engine).get_table_names())
            engine.dispose()
            engine = None
            command.downgrade(config, "base")
        finally:
            if engine is not None:
                engine.dispose()
            settings.database_url = previous
            if database.exists():
                database.unlink()
        self.assertTrue({"users", "consent_requests", "medical_records", "consultations",
                         "prescriptions", "prescription_items", "medication_references",
                         "allergies", "medical_conditions", "patient_medications",
                         "safety_checks", "safety_findings", "audit_logs"}.issubset(tables))


if __name__ == "__main__":
    unittest.main()
