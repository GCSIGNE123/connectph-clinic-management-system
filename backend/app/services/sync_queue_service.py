"""Sync Queue Service - Post-RC1 Phase 2 Milestone 2: Cloud Backup (One-Way Sync).

`enqueue(...)` is the single shared entry point every clinic-entity service
(Patient, Visit, SOAP note, Queue ticket, Prescription, Laboratory order/
result, Payment, Shift) calls at the end of its own successful mutation to
record "this record needs to be uploaded to the cloud".

Deliberately uses its OWN, separate DB session/transaction (not the caller's
session) rather than piggy-backing on the caller's in-flight transaction:
1. It is called AFTER the caller's own `session.commit()` has already
   succeeded, so the primary clinic record is durably saved regardless of
   anything that happens here.
2. If this insert itself fails (DB hiccup, serialization error, whatever),
   catching it here can't leave the caller's *own* session/transaction in an
   aborted state - the caller's transaction is already closed out.

This is strictly best-effort and additive: `enqueue()` NEVER raises. Any
exception is caught and logged; sync queuing failing/lagging must never
fail, roll back, or slow the primary clinic operation that called it.
"""

import logging
from typing import Any
from uuid import UUID

from app.db.session import AsyncSessionLocal
from app.models.sync_job import SyncJob, SyncJobOperation

logger = logging.getLogger("app.sync")


async def enqueue(
    *,
    entity_type: str,
    record_id: UUID,
    operation: SyncJobOperation | str,
    payload: dict[str, Any],
    clinic_id: UUID,
) -> None:
    """Best-effort: queue a sync job. Never raises - any failure is logged
    and swallowed so the caller's already-committed clinic operation is
    completely unaffected."""
    try:
        op_value = operation.value if isinstance(operation, SyncJobOperation) else str(operation)
        async with AsyncSessionLocal() as session:
            session.add(
                SyncJob(
                    clinic_id=clinic_id,
                    entity_type=entity_type,
                    record_id=record_id,
                    operation=op_value,
                    payload=payload,
                )
            )
            await session.commit()
        logger.info(
            "Sync job enqueued",
            extra={"entity_type": entity_type, "record_id": str(record_id), "operation": op_value},
        )
    except Exception:
        # Best-effort/additive per the milestone spec: sync queuing must
        # never propagate and fail the caller's primary clinic operation.
        logger.exception(
            "Failed to enqueue sync job (non-fatal, clinic operation unaffected)",
            extra={"entity_type": entity_type, "record_id": str(record_id)},
        )
