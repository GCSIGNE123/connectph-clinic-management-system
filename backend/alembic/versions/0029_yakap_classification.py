"""YAKAP Patient Classification (Phase 2.7).

Adds two additive columns:
- `patients.is_yakap_beneficiary` (boolean, default False) - the patient's
  STANDING PhilHealth YAKAP beneficiary status, set on the patient profile.
- `queues.visit_classification` (new `visit_classification` enum: Yakap /
  Regular, default Regular) - the PER-ENCOUNTER classification of a
  specific queue ticket, set at ticket-creation time (pre-filled from the
  patient's beneficiary flag but independently editable).

Deliberately NOT a queue prefix - existing A/B/L/R queue numbering,
`queue_number`/`queue_prefix` generation, and the queue-counter table are
completely untouched. Every existing `patients`/`queues` row gets the safe
default (`false` / `Regular`) via `server_default`, so no backfill/rewrite
of historical data is needed.

Revision ID: 0029_yakap_classification
Revises: 0028_tv_display_short_code
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_yakap_classification"
down_revision: str | None = "0028_tv_display_short_code"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_VISIT_CLASSIFICATION_ENUM = sa.Enum("Yakap", "Regular", name="visit_classification")


def upgrade() -> None:
    op.add_column(
        "patients",
        sa.Column("is_yakap_beneficiary", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    _VISIT_CLASSIFICATION_ENUM.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "queues",
        sa.Column(
            "visit_classification",
            _VISIT_CLASSIFICATION_ENUM,
            nullable=False,
            server_default="Regular",
        ),
    )
    op.create_index("ix_queues_visit_classification", "queues", ["visit_classification"])


def downgrade() -> None:
    op.drop_index("ix_queues_visit_classification", table_name="queues")
    op.drop_column("queues", "visit_classification")
    _VISIT_CLASSIFICATION_ENUM.drop(op.get_bind(), checkfirst=True)

    op.drop_column("patients", "is_yakap_beneficiary")
