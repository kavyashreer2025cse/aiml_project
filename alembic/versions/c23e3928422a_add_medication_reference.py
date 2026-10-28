"""add medication reference

Revision ID: c23e3928422a
Revises: 87ff74ce77e9
Create Date: 2026-09-23 23:19:03.789316

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c23e3928422a"
down_revision: Union[str, Sequence[str], None] = "87ff74ce77e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
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

    op.create_index(
        op.f("ix_medication_references_id"),
        "medication_references",
        ["id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_medication_references_rxcui"),
        "medication_references",
        ["rxcui"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_medication_references_rxcui"), table_name="medication_references")
    op.drop_index(op.f("ix_medication_references_id"), table_name="medication_references")
    op.drop_table("medication_references")
