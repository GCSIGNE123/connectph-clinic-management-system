"""Short human-typeable alias for TV Display public URLs (Post-RC1).

Adds nullable, unique `tv_display_configs.short_code` - an admin-chosen
short string (e.g. "canora") that resolves to the same row as the existing
`public_slug`. Purely additive: `public_slug` and its resolution behavior
are completely untouched, so every existing long-URL TV display keeps
working unchanged. See `app/models/tv_display_config.py`'s docstring for
the security-tradeoff rationale.

Revision ID: 0028_tv_display_short_code
Revises: 0027_tv_info_content
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_tv_display_short_code"
down_revision: str | None = "0027_tv_info_content"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tv_display_configs", sa.Column("short_code", sa.String(length=32), nullable=True))
    op.create_index(
        "ix_tv_display_configs_short_code", "tv_display_configs", ["short_code"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_tv_display_configs_short_code", table_name="tv_display_configs")
    op.drop_column("tv_display_configs", "short_code")
