"""add safety check and findings

Revision ID: 81740585058c
Revises: ee0b584ca0cb
Create Date: 2026-09-24 09:49:05.789064

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "81740585058c"
down_revision: Union[str, Sequence[str], None] = "ee0b584ca0cb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "safety_checks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("consultation_id", sa.Integer(), nullable=False),
        sa.Column("prescription_id", sa.Integer(), nullable=True),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
        ),
        sa.Column(
            "doctor_decision",
            sa.String(length=50),
            nullable=True,
        ),
        sa.Column(
            "doctor_decision_notes",
            sa.Text(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["consultation_id"],
            ["consultations.id"],
        ),
        sa.ForeignKeyConstraint(
            ["prescription_id"],
            ["prescriptions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["doctor_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_safety_checks_id",
        "safety_checks",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_safety_checks_consultation_id",
        "safety_checks",
        ["consultation_id"],
        unique=False,
    )
    op.create_index(
        "ix_safety_checks_prescription_id",
        "safety_checks",
        ["prescription_id"],
        unique=False,
    )
    op.create_index(
        "ix_safety_checks_doctor_id",
        "safety_checks",
        ["doctor_id"],
        unique=False,
    )
    op.create_index(
        "ix_safety_checks_patient_id",
        "safety_checks",
        ["patient_id"],
        unique=False,
    )

    op.create_table(
        "safety_findings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("safety_check_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=500), nullable=False),
        sa.ForeignKeyConstraint(
            ["safety_check_id"],
            ["safety_checks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_safety_findings_id",
        "safety_findings",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_safety_findings_safety_check_id",
        "safety_findings",
        ["safety_check_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_safety_findings_safety_check_id",
        table_name="safety_findings",
    )
    op.drop_index(
        "ix_safety_findings_id",
        table_name="safety_findings",
    )
    op.drop_table("safety_findings")

    op.drop_index(
        "ix_safety_checks_patient_id",
        table_name="safety_checks",
    )
    op.drop_index(
        "ix_safety_checks_doctor_id",
        table_name="safety_checks",
    )
    op.drop_index(
        "ix_safety_checks_prescription_id",
        table_name="safety_checks",
    )
    op.drop_index(
        "ix_safety_checks_consultation_id",
        table_name="safety_checks",
    )
    op.drop_index(
        "ix_safety_checks_id",
        table_name="safety_checks",
    )
    op.drop_table("safety_checks")