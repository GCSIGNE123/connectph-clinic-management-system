"""Shared expiry-severity computation - the single source of truth used by
both `MedicineExpiryService` (Phase 3 daily notification job) and
`MedicineService` (medicine-level stats/filters), so the two never drift
into different definitions of "near expiry"/"expired". Mirrors
`medicine_service._compute_status`'s "one function, called everywhere"
convention.
"""

from datetime import date

from app.models.medicine import (
    EXPIRY_TIER_1,
    EXPIRY_TIER_2,
    EXPIRY_TIER_3,
    EXPIRY_TIER_4,
    EXPIRY_TIER_EXPIRED,
    EXPIRY_TIER_NONE,
    MedicineBatch,
    MedicineBatchStatus,
)


class ExpiryThresholds:
    """Immutable snapshot of a clinic's four configured warning-day
    thresholds, always descending (tier1 > tier2 > tier3 > tier4) -
    enforced at the API/service layer that constructs this, never here."""

    __slots__ = ("tier1", "tier2", "tier3", "tier4")

    def __init__(self, tier1: int, tier2: int, tier3: int, tier4: int) -> None:
        self.tier1 = tier1
        self.tier2 = tier2
        self.tier3 = tier3
        self.tier4 = tier4


def compute_expiry_tier(batch: MedicineBatch, thresholds: ExpiryThresholds, *, today: date | None = None) -> int:
    """Returns one of the `EXPIRY_TIER_*` constants for this batch right
    now. A Recalled or Depleted (quantity_remaining <= 0) batch never
    generates an alert - "Depleted batches should not generate expiry
    alerts" and a Recalled batch is already a resolved/handled state, not
    an expiry concern - matching `MedicineBatch.status`'s own semantics
    (never silently overwritten here either)."""
    if batch.status == MedicineBatchStatus.RECALLED:
        return EXPIRY_TIER_NONE
    if batch.quantity_remaining <= 0:
        return EXPIRY_TIER_NONE

    reference_date = today or date.today()
    days_remaining = (batch.expiry_date - reference_date).days
    if days_remaining < 0:
        return EXPIRY_TIER_EXPIRED
    if days_remaining <= thresholds.tier4:
        return EXPIRY_TIER_4
    if days_remaining <= thresholds.tier3:
        return EXPIRY_TIER_3
    if days_remaining <= thresholds.tier2:
        return EXPIRY_TIER_2
    if days_remaining <= thresholds.tier1:
        return EXPIRY_TIER_1
    return EXPIRY_TIER_NONE


def is_expired(batch: MedicineBatch, *, today: date | None = None) -> bool:
    """"Expired" per the medicine-inventory filter/stat definition: past its
    expiry date AND still has remaining quantity (a Depleted or Recalled
    batch is not counted as "expired" for filter/dashboard purposes, even
    if its date has also passed)."""
    if batch.status == MedicineBatchStatus.RECALLED:
        return False
    if batch.quantity_remaining <= 0:
        return False
    reference_date = today or date.today()
    return batch.expiry_date < reference_date


def is_near_expiry(batch: MedicineBatch, thresholds: ExpiryThresholds, *, today: date | None = None) -> bool:
    tier = compute_expiry_tier(batch, thresholds, today=today)
    return tier in (EXPIRY_TIER_1, EXPIRY_TIER_2, EXPIRY_TIER_3, EXPIRY_TIER_4)
