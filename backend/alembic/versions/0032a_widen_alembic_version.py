"""Widen alembic_version.version_num to VARCHAR(255).

Alembic's built-in `alembic_version` bookkeeping table defaults to
`version_num VARCHAR(32)` when no `version_table_column`/`version_table_args`
override is configured (this project's `alembic/env.py` never overrides
it). This project's convention is to use the full descriptive filename
stem as each migration's `revision` id - which has already twice before
required manually SHORTENING a revision id to fit under 32 characters
(see the comments in `0016_production_hardening_indexes.py` and
`0031_lab_structured_results.py`). `0033_invoice_one_active_per_visit`
(33 characters) is the first revision id that was never shortened, and
it silently exceeds the limit: `alembic upgrade head` fails with
`StringDataRightTruncationError` on the automatic post-migration
`UPDATE alembic_version SET version_num = '0033_invoice_one_active_per_visit'`
statement, on every database still using Alembic's default column width
(confirmed against a real production database still at revision 0030).

A widening statement already exists in
`0034_laboratory_order_id_nullable.py`, but it runs too late to help -
Alembic stamps each migration's own revision id in the same transaction
immediately after that migration's `upgrade()` completes, so `0033` must
already have a wide-enough column by the time ITS OWN stamp write
happens, not `0034`'s. Inserted here, between `0032` and `0033`, so the
column is widened before `0033`'s stamp write is ever attempted.
`0034`'s own (now redundant) widening statement is left completely
unchanged - `ALTER COLUMN ... TYPE VARCHAR(255)` on a column already
`VARCHAR(255)` is a harmless no-op in Postgres, and leaving it preserves
that already-released migration exactly as shipped.

This migration touches ONLY Alembic's own bookkeeping column - no
application table or data is read, created, or modified.

Revision ID: 0032a_widen_alembic_version
Revises: 0032_lab_template_section
Create Date: 2026-08-19
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032a_widen_alembic_version"
down_revision: str | None = "0032_lab_template_section"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("alembic_version", "version_num", type_=postgresql.VARCHAR(255))


def downgrade() -> None:
    # NOT SAFE to narrow back to VARCHAR(32) once any later revision has
    # actually been applied and stamped: 0033_invoice_one_active_per_visit
    # (33 chars) and 0034_laboratory_order_id_nullable (33 chars) are both
    # longer than 32 characters, so narrowing the column back while either
    # of those (or any later revision) is the current stamped value would
    # either fail outright (Postgres refuses to narrow a varchar column
    # when an existing value doesn't fit) or - far worse - silently
    # truncate `alembic_version.version_num` into a value that no longer
    # matches any real revision id, corrupting Alembic's own bookkeeping
    # and leaving the database's migration state unrecoverable without
    # manual intervention. There is no safe general downgrade for this
    # migration once the chain has advanced past it, so this deliberately
    # does nothing rather than risk silent corruption - matching the same
    # accepted-irreversibility precedent already used elsewhere in this
    # migration chain (e.g. 0034's own downgrade() for walk-in lab orders,
    # 0033's own PRODUCTION SAFETY NOTE about resolving data before
    # upgrading). If a downgrade below this revision is ever genuinely
    # required, narrow the column back manually ONLY after confirming
    # (`SELECT version_num FROM alembic_version`) that the current stamped
    # value is 32 characters or fewer.
    pass
