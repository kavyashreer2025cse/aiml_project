"""Repair consent table for databases that recorded the old empty revision.

Revision ID: 4f8d1a02c671
Revises: 366924c60adc
"""
from alembic import op
import sqlalchemy as sa

revision = "4f8d1a02c671"
down_revision = "366924c60adc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "medical_records" not in inspector.get_table_names():
        op.create_table(
            "medical_records",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("patient_id", sa.Integer(), nullable=False),
            sa.Column("blood_group", sa.String(length=10), nullable=True),
            sa.Column("allergies", sa.Text(), nullable=True),
            sa.Column("medical_conditions", sa.Text(), nullable=True),
            sa.Column("current_medications", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_medical_records_id", "medical_records", ["id"])
        op.create_index("ix_medical_records_patient_id", "medical_records", ["patient_id"])
        inspector = sa.inspect(op.get_bind())
    if "medication_references" not in inspector.get_table_names():
        op.create_table(
            "medication_references",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("rxcui", sa.String(length=50), nullable=False),
            sa.Column("name", sa.String(length=500), nullable=False),
            sa.Column("synonym", sa.String(length=500), nullable=True),
            sa.Column("term_type", sa.String(length=20), nullable=True),
            sa.Column("source", sa.String(length=100), nullable=True),
            sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("rxcui"),
        )
        op.create_index("ix_medication_references_id", "medication_references", ["id"])
        op.create_index("ix_medication_references_rxcui", "medication_references", ["rxcui"])
    if "consent_requests" in inspector.get_table_names():
        return
    op.create_table(
        "consent_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["doctor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_consent_requests_id", "consent_requests", ["id"])
    op.create_index("ix_consent_requests_doctor_id", "consent_requests", ["doctor_id"])
    op.create_index("ix_consent_requests_patient_id", "consent_requests", ["patient_id"])


def downgrade() -> None:
    # This repair is conditional and may have adopted existing tables.
    # Preserve repaired tables and data on downgrade.
    pass
