"""Add soap_phrase_favorites (Doctor-specific "My Phrases" for SOAP suggestions)

Task #2 enhancement: a Doctor can save a short, reusable phrase for a specific
SOAP / diagnosis field and see it first in that field's suggestion list.

Purely additive: one new table, no change to any existing table or row, no
backfill, and no seed data. Each row is scoped to (clinic, doctor, field) and
holds only the short phrase text - no patient / consultation / visit reference.
Un-favoriting hard-deletes the row (it is a personal preference, not clinical
data). Uniqueness on (clinic_id, doctor_id, field, phrase_key) makes a duplicate
save idempotent.

Revision ID: 0046_soap_phrase_favorites
Revises: 0045_prescription_item_dosage_form
Create Date: 2026-09-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0046_soap_phrase_favorites"
down_revision: str | None = "0045_prescription_item_dosage_form"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "soap_phrase_favorites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field", sa.String(length=40), nullable=False),
        sa.Column("phrase", sa.String(length=80), nullable=False),
        sa.Column("phrase_key", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("clinic_id", "doctor_id", "field", "phrase_key", name="uq_soap_phrase_favorite"),
    )
    op.create_index("ix_soap_phrase_favorites_clinic_id", "soap_phrase_favorites", ["clinic_id"])
    op.create_index(
        "ix_soap_phrase_favorites_clinic_doctor_field", "soap_phrase_favorites", ["clinic_id", "doctor_id", "field"]
    )


def downgrade() -> None:
    op.drop_index("ix_soap_phrase_favorites_clinic_doctor_field", table_name="soap_phrase_favorites")
    op.drop_index("ix_soap_phrase_favorites_clinic_id", table_name="soap_phrase_favorites")
    op.drop_table("soap_phrase_favorites")
