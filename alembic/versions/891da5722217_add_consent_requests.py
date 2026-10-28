"""add consent requests

Revision ID: 891da5722217
Revises: bc38b9a02bb3
Create Date: 2026-09-20 22:15:46.858239

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '891da5722217'
down_revision: Union[str, Sequence[str], None] = 'bc38b9a02bb3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
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
    """Downgrade schema."""
    op.drop_index("ix_consent_requests_patient_id", table_name="consent_requests")
    op.drop_index("ix_consent_requests_doctor_id", table_name="consent_requests")
    op.drop_index("ix_consent_requests_id", table_name="consent_requests")
    op.drop_table("consent_requests")
