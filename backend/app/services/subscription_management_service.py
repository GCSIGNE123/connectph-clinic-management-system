"""Plan/trial/renewal/expiration CRUD per tenant, for the Platform Administration Portal."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import Subscription, SubscriptionPlan, SubscriptionStatus
from app.services.platform_audit_service import PlatformAuditService


class SubscriptionManagementService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = PlatformAuditService(session)

    async def get_for_tenant(self, clinic_id: UUID) -> Subscription | None:
        result = await self.session.execute(
            select(Subscription)
            .where(Subscription.clinic_id == clinic_id, Subscription.is_deleted.is_(False))
            .order_by(Subscription.created_at.desc())
        )
        return result.scalars().first()

    async def upsert(
        self,
        *,
        actor_id: UUID,
        clinic_id: UUID,
        plan: SubscriptionPlan | None = None,
        status: SubscriptionStatus | None = None,
        trial_start=None,
        trial_end=None,
        subscription_start=None,
        renewal_date=None,
        expiration_date=None,
        max_users: int | None = None,
        max_branches: int | None = None,
        storage_limit_mb: int | None = None,
        api_rate_limit: int | None = None,
    ) -> Subscription:
        sub = await self.get_for_tenant(clinic_id)
        if sub is None:
            sub = Subscription(clinic_id=clinic_id, plan=plan or SubscriptionPlan.TRIAL, status=status or SubscriptionStatus.TRIALING)
            self.session.add(sub)

        for field, value in (
            ("plan", plan), ("status", status), ("trial_start", trial_start), ("trial_end", trial_end),
            ("subscription_start", subscription_start), ("renewal_date", renewal_date),
            ("expiration_date", expiration_date), ("max_users", max_users), ("max_branches", max_branches),
            ("storage_limit_mb", storage_limit_mb), ("api_rate_limit", api_rate_limit),
        ):
            if value is not None:
                setattr(sub, field, value)

        await self.session.flush()
        await self.audit.log(
            actor_id=actor_id, action="subscription.update", entity_type="subscription",
            entity_id=str(sub.id), clinic_id=clinic_id,
        )
        await self.session.commit()
        await self.session.refresh(sub)
        return sub
