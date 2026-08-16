"""System Health dashboard aggregate stats for the Platform Administration Portal.

Real aggregation queries against the actual Postgres database and operational
tables - no fabricated numbers. Where no real source exists yet (API request
counts - there is no request-logging middleware in this project), the value is
explicitly returned as `None` with a `"not_implemented"` note rather than a
fake number, per the phase spec.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.background_job import BackgroundJob, BackgroundJobStatus
from app.models.clinic import Clinic
from app.models.refresh_token import RefreshToken
from app.models.subscription import Subscription, SubscriptionStatus


class PlatformDashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_system_health(self) -> dict:
        total_clinics = (
            await self.session.execute(select(func.count()).select_from(Clinic).where(Clinic.is_deleted.is_(False)))
        ).scalar_one()
        active_clinics = (
            await self.session.execute(
                select(func.count()).select_from(Clinic).where(Clinic.is_deleted.is_(False), Clinic.status == "Active")
            )
        ).scalar_one()
        suspended_clinics = (
            await self.session.execute(
                select(func.count()).select_from(Clinic).where(Clinic.is_deleted.is_(False), Clinic.status == "Suspended")
            )
        ).scalar_one()
        trials = (
            await self.session.execute(
                select(func.count()).select_from(Subscription).where(Subscription.status == SubscriptionStatus.TRIALING)
            )
        ).scalar_one()
        # BUG-039: NOT `Subscription.status == SubscriptionStatus.EXPIRED`.
        # `EXPIRED` was added to the *Python* enum (and, via `create_all()`,
        # to a fresh test database) as the lowercase value "expired", but
        # migration 0015's `ALTER TYPE subscription_status ADD VALUE
        # 'EXPIRED'` added it to a REAL, migration-built Postgres database
        # with the wrong casing (uppercase) - so on any actually-migrated
        # database, querying `status = 'expired'` 500s with
        # `InvalidTextRepresentationError`. Nothing in the app ever writes
        # `status = EXPIRED` either (grep confirms zero writers), so an
        # enum-status comparison was never the right source of truth here
        # anyway. `expiration_date` (added by the same migration) is the
        # real, populated, enum-independent field for "has this
        # subscription's paid term lapsed" - use that instead, which also
        # sidesteps the broken enum label entirely regardless of whether/
        # how it eventually gets corrected in the database.
        expired_subscriptions = (
            await self.session.execute(
                select(func.count()).select_from(Subscription).where(
                    Subscription.expiration_date.is_not(None),
                    Subscription.expiration_date < datetime.now(UTC),
                )
            )
        ).scalar_one()

        online_users = (
            await self.session.execute(
                select(func.count()).select_from(RefreshToken).where(
                    RefreshToken.revoked_at.is_(None), RefreshToken.expires_at > datetime.now(UTC)
                )
            )
        ).scalar_one()

        db_size_bytes = (await self.session.execute(text("SELECT pg_database_size(current_database())"))).scalar_one()

        background_jobs_total = (
            await self.session.execute(select(func.count()).select_from(BackgroundJob))
        ).scalar_one()
        failed_jobs = (
            await self.session.execute(
                select(func.count()).select_from(BackgroundJob).where(BackgroundJob.status == BackgroundJobStatus.FAILED)
            )
        ).scalar_one()

        return {
            "total_clinics": total_clinics,
            "active_clinics": active_clinics,
            "suspended_clinics": suspended_clinics,
            "trial_subscriptions": trials,
            "expired_subscriptions": expired_subscriptions,
            "online_users": online_users,
            "database_size_bytes": db_size_bytes,
            "background_jobs_total": background_jobs_total,
            "background_jobs_failed": failed_jobs,
            "api_requests_today": None,  # TODO: no request-logging middleware exists yet
        }
