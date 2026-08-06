"""Phase 20: Internal staff messaging (item 14)

Adds `internal_messages` - a minimal Receptionist <-> Doctor message list
(no threads, no attachments, no group recipients). `read_at` is the only
read-tracking (null until read, set once on first read).

Revision ID: 0019_internal_messaging
Revises: 0018_patient_appointment_booking
Create Date: 2026-07-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0019_internal_messaging"
down_revision: Union[str, None] = "0018_patient_appointment_booking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "internal_messages",
        sa.Column("sender_id", sa.UUID(), nullable=False),
        sa.Column("recipient_id", sa.UUID(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_internal_messages_sender_id"), "internal_messages", ["sender_id"], unique=False)
    op.create_index(op.f("ix_internal_messages_recipient_id"), "internal_messages", ["recipient_id"], unique=False)
    op.create_index(op.f("ix_internal_messages_clinic_id"), "internal_messages", ["clinic_id"], unique=False)
    # Common query: "my conversation with this other user, newest first".
    op.create_index(
        "ix_internal_messages_recipient_sender_created",
        "internal_messages",
        ["recipient_id", "sender_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_internal_messages_recipient_sender_created", table_name="internal_messages")
    op.drop_index(op.f("ix_internal_messages_clinic_id"), table_name="internal_messages")
    op.drop_index(op.f("ix_internal_messages_recipient_id"), table_name="internal_messages")
    op.drop_index(op.f("ix_internal_messages_sender_id"), table_name="internal_messages")
    op.drop_table("internal_messages")
