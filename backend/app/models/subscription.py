"""Subscription model - the clinic's commercial SaaS plan/billing state."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class SubscriptionPlan(str, enum.Enum):
    TRIAL = "trial"
    BASIC = "basic"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    TRIALING = "trialing"
    EXPIRED = "expired"  # Phase 15: added for platform-admin license management


class Subscription(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, Base):
    """The commercial subscription/billing plan a clinic tenant is on."""

    __tablename__ = "subscriptions"

    plan: Mapped[SubscriptionPlan] = mapped_column(
        Enum(
            SubscriptionPlan,
            name="subscription_plan",
            values_callable=lambda enum_class: [e.value for e in enum_class],
        ),
        nullable=False,
        default=SubscriptionPlan.TRIAL,
    )

    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(
            SubscriptionStatus,
            name="subscription_status",
            values_callable=lambda enum_class: [e.value for e in enum_class],
        ),
        nullable=False,
        default=SubscriptionStatus.TRIALING,
    )
    price_per_month: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="PHP", nullable=False)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Phase 15: SaaS Administration (License Management) ---
    # `plan` (Trial/Basic/Professional/Enterprise, already existed) is reused
    # as-is; "Basic" stands in for the spec's "Starter" tier name.
    # License limit fields are kept directly on `subscriptions` (tied 1:1 to
    # the plan a clinic is on) rather than a separate `license_limits` lookup
    # table - there is exactly one active subscription row per clinic, so a
    # lookup table would add a join for no normalization benefit. Documented
    # in docs/DATABASE.md.
    trial_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trial_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    subscription_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    renewal_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expiration_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_branches: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_limit_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    api_rate_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)

    clinic: Mapped["Clinic"] = relationship(back_populates="subscriptions")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Subscription id={self.id} plan={self.plan!r} status={self.status!r}>"
