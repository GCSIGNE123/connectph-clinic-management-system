"""Phase 15: SaaS Administration Portal (platform-admin cross-tenant layer)

Adds a genuinely separate platform-administration data model alongside the
existing tenant-scoped schema: platform_admin_users (no clinic_id - these
users exist outside the tenant model), tenant_feature_flags, platform_audit_logs,
platform_sessions, background_jobs (monitoring the real Phase 14 migration
imports), platform_config, api_keys/oauth_clients/webhook_secrets, backups.
Also extends clinics (suspend/archive lifecycle) and subscriptions (trial/
renewal/license-limit fields) - both tables already existed since Phase 1/4.

Deliberately hand-curated (not the raw `alembic revision --autogenerate`
output) to isolate Phase 15's changes from unrelated schema drift already
present on disk from earlier phases.

Revision ID: 0015_saas_administration
Revises: 0014_legacy_migration_wizard
Create Date: 2026-07-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0015_saas_administration"
down_revision: Union[str, None] = "0014_legacy_migration_wizard"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_admin_users",
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column(
            "role",
            sa.Enum("PlatformAdministrator", "SupportEngineer", "ImplementationTeam", "Auditor", name="platform_admin_role"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_platform_admin_users_email"), "platform_admin_users", ["email"], unique=True)
    op.create_index(op.f("ix_platform_admin_users_username"), "platform_admin_users", ["username"], unique=True)

    op.create_table(
        "api_keys",
        sa.Column("clinic_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("key_hash", sa.String(length=128), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rate_limit_per_minute", sa.Integer(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_api_keys_clinic_id"), "api_keys", ["clinic_id"], unique=False)
    op.create_index(op.f("ix_api_keys_key_hash"), "api_keys", ["key_hash"], unique=True)

    op.create_table(
        "background_jobs",
        sa.Column("job_type", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.Enum("Scheduled", "Running", "Completed", "Failed", "Retrying", name="background_job_status"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("clinic_id", sa.UUID(), nullable=True),
        sa.Column("reference_id", sa.String(length=64), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_background_jobs_clinic_id"), "background_jobs", ["clinic_id"], unique=False)

    op.create_table(
        "backups",
        sa.Column("backup_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.Enum("Pending", "Completed", "Failed", name="backup_status"), nullable=False),
        sa.Column("triggered_by", sa.UUID(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("storage_location", sa.String(length=500), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(["triggered_by"], ["platform_admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "oauth_clients",
        sa.Column("clinic_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("client_secret_hash", sa.String(length=128), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_oauth_clients_client_id"), "oauth_clients", ["client_id"], unique=True)
    op.create_index(op.f("ix_oauth_clients_clinic_id"), "oauth_clients", ["clinic_id"], unique=False)

    op.create_table(
        "platform_audit_logs",
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=150), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column("clinic_id", sa.UUID(), nullable=True),
        sa.Column("log_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["platform_admin_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_platform_audit_logs_actor_id"), "platform_audit_logs", ["actor_id"], unique=False)
    op.create_index(op.f("ix_platform_audit_logs_clinic_id"), "platform_audit_logs", ["clinic_id"], unique=False)

    op.create_table(
        "platform_config",
        sa.Column("config_key", sa.String(length=100), nullable=False),
        sa.Column("config_value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["platform_admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_platform_config_config_key"), "platform_config", ["config_key"], unique=True)

    op.create_table(
        "platform_sessions",
        sa.Column("platform_admin_user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("device_label", sa.String(length=100), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminated_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["platform_admin_user_id"], ["platform_admin_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["terminated_by"], ["platform_admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_platform_sessions_platform_admin_user_id"), "platform_sessions", ["platform_admin_user_id"], unique=False
    )
    op.create_index(op.f("ix_platform_sessions_token_hash"), "platform_sessions", ["token_hash"], unique=True)

    op.create_table(
        "tenant_feature_flags",
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("feature_key", sa.String(length=64), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["platform_admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clinic_id", "feature_key", name="uq_tenant_feature_flag"),
    )
    op.create_index(op.f("ix_tenant_feature_flags_clinic_id"), "tenant_feature_flags", ["clinic_id"], unique=False)

    op.create_table(
        "webhook_secrets",
        sa.Column("clinic_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("secret_hash", sa.String(length=128), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_webhook_secrets_clinic_id"), "webhook_secrets", ["clinic_id"], unique=False)

    # --- Extend clinics (Phase 1/4 table) ---
    op.add_column("clinics", sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("clinics", sa.Column("suspended_reason", sa.String(length=500), nullable=True))
    op.add_column("clinics", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))

    # --- Extend subscriptions (Phase 1 table) ---
    op.add_column("subscriptions", sa.Column("trial_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("subscriptions", sa.Column("trial_end", sa.DateTime(timezone=True), nullable=True))
    op.add_column("subscriptions", sa.Column("subscription_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("subscriptions", sa.Column("renewal_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("subscriptions", sa.Column("expiration_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("subscriptions", sa.Column("max_users", sa.Integer(), nullable=True))
    op.add_column("subscriptions", sa.Column("max_branches", sa.Integer(), nullable=True))
    op.add_column("subscriptions", sa.Column("storage_limit_mb", sa.Integer(), nullable=True))
    op.add_column("subscriptions", sa.Column("api_rate_limit", sa.Integer(), nullable=True))

    # Add EXPIRED to subscription_status enum (native PG enum, added via ALTER TYPE)
    # NOTE: this native enum stores Python enum *names* (ACTIVE/PAST_DUE/...),
    # not `.value` strings, matching the pre-existing column's (no
    # `values_callable`) behavior - so the new member must be added as 'EXPIRED'.
    op.execute("ALTER TYPE subscription_status ADD VALUE IF NOT EXISTS 'EXPIRED'")


def downgrade() -> None:
    op.drop_column("subscriptions", "api_rate_limit")
    op.drop_column("subscriptions", "storage_limit_mb")
    op.drop_column("subscriptions", "max_branches")
    op.drop_column("subscriptions", "max_users")
    op.drop_column("subscriptions", "expiration_date")
    op.drop_column("subscriptions", "renewal_date")
    op.drop_column("subscriptions", "subscription_start")
    op.drop_column("subscriptions", "trial_end")
    op.drop_column("subscriptions", "trial_start")

    op.drop_column("clinics", "archived_at")
    op.drop_column("clinics", "suspended_reason")
    op.drop_column("clinics", "suspended_at")

    op.drop_index(op.f("ix_webhook_secrets_clinic_id"), table_name="webhook_secrets")
    op.drop_table("webhook_secrets")
    op.drop_index(op.f("ix_tenant_feature_flags_clinic_id"), table_name="tenant_feature_flags")
    op.drop_table("tenant_feature_flags")
    op.drop_index(op.f("ix_platform_sessions_token_hash"), table_name="platform_sessions")
    op.drop_index(op.f("ix_platform_sessions_platform_admin_user_id"), table_name="platform_sessions")
    op.drop_table("platform_sessions")
    op.drop_index(op.f("ix_platform_config_config_key"), table_name="platform_config")
    op.drop_table("platform_config")
    op.drop_index(op.f("ix_platform_audit_logs_clinic_id"), table_name="platform_audit_logs")
    op.drop_index(op.f("ix_platform_audit_logs_actor_id"), table_name="platform_audit_logs")
    op.drop_table("platform_audit_logs")
    op.drop_index(op.f("ix_oauth_clients_clinic_id"), table_name="oauth_clients")
    op.drop_index(op.f("ix_oauth_clients_client_id"), table_name="oauth_clients")
    op.drop_table("oauth_clients")
    op.drop_table("backups")
    op.drop_index(op.f("ix_background_jobs_clinic_id"), table_name="background_jobs")
    op.drop_table("background_jobs")
    op.drop_index(op.f("ix_api_keys_key_hash"), table_name="api_keys")
    op.drop_index(op.f("ix_api_keys_clinic_id"), table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_index(op.f("ix_platform_admin_users_username"), table_name="platform_admin_users")
    op.drop_index(op.f("ix_platform_admin_users_email"), table_name="platform_admin_users")
    op.drop_table("platform_admin_users")
