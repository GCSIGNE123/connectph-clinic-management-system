"""Room label for queue settings (Post-RC1: room-based TV announcements)

Adds nullable `queue_settings.room_label`. Purely additive - no existing
column/table touched, no data migration needed (NULL for every existing row
means "no room configured", which falls back to the pre-existing doctor/
department-name announcement behavior unchanged).

Revision ID: 0026_queue_setting_room_label
Revises: 0025_queue_setting_doctor_prefix
Create Date: 2026-08-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0026_queue_setting_room_label"
down_revision: Union[str, None] = "0025_queue_setting_doctor_prefix"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("queue_settings", sa.Column("room_label", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("queue_settings", "room_label")
