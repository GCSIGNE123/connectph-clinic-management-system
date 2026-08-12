"""Cross-tenant clinic (tenant) management for the Platform Administration Portal.

This is the "separate, explicitly cross-tenant service layer" called for by
the phase spec: it queries `Clinic`/`User`/`Subscription` WITHOUT a
`clinic_id` filter (deliberately - that's its entire purpose), and is only
ever reachable via `get_current_platform_admin`. It never touches
`TenantMixin`-scoped repositories used by clinic-scoped endpoints, and no
clinic-scoped endpoint imports this service.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.clinic import Clinic
from app.models.consultation_attachment import ConsultationAttachment
from app.models.laboratory_attachment import LaboratoryAttachment
from app.models.refresh_token import RefreshToken
from app.models.role import Role, RoleName
from app.models.subscription import Subscription
from app.models.user import User
from app.services.platform_audit_service import PlatformAuditService


class TenantManagementService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = PlatformAuditService(session)

    async def list_tenants(
        self, *, search: str | None = None, status_filter: str | None = None, page: int = 1, page_size: int = 20
    ) -> tuple[list[Clinic], int]:
        stmt = select(Clinic).where(Clinic.is_deleted.is_(False))
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(Clinic.name.ilike(like), Clinic.email.ilike(like), Clinic.slug.ilike(like)))
        if status_filter:
            stmt = stmt.where(Clinic.status == status_filter)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(Clinic.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows), total

    async def get_tenant(self, clinic_id: UUID) -> Clinic | None:
        result = await self.session.execute(select(Clinic).where(Clinic.id == clinic_id))
        return result.scalar_one_or_none()

    async def get_tenant_stats(self, clinic_id: UUID) -> dict:
        """Real aggregation, not cached/duplicated columns (Phase 12 principle)."""
        user_count = (
            await self.session.execute(
                select(func.count()).select_from(User).where(User.clinic_id == clinic_id, User.is_deleted.is_(False))
            )
        ).scalar_one()

        branch_count = (
            await self.session.execute(
                select(func.count()).select_from(Clinic).where(Clinic.id == clinic_id)
            )
        ).scalar_one()

        # Storage usage: sum real attachment file sizes across the phases that
        # have file uploads (consultation + laboratory attachments).
        consult_bytes = (
            await self.session.execute(
                select(func.coalesce(func.sum(ConsultationAttachment.file_size_bytes), 0)).where(
                    ConsultationAttachment.clinic_id == clinic_id
                )
            )
        ).scalar_one()
        lab_bytes = (
            await self.session.execute(
                select(func.coalesce(func.sum(LaboratoryAttachment.file_size_bytes), 0)).where(
                    LaboratoryAttachment.clinic_id == clinic_id
                )
            )
        ).scalar_one()

        subscription = (
            await self.session.execute(
                select(Subscription)
                .where(Subscription.clinic_id == clinic_id, Subscription.is_deleted.is_(False))
                .order_by(Subscription.created_at.desc())
            )
        ).scalars().first()

        return {
            "user_count": user_count,
            "storage_used_bytes": int(consult_bytes) + int(lab_bytes),
            "subscription": subscription,
        }

    async def create_tenant(
        self,
        *,
        actor_id: UUID,
        name: str,
        slug: str,
        email: str | None,
        owner_email: str,
        owner_username: str,
        owner_password: str,
        owner_first_name: str,
        owner_last_name: str,
    ) -> Clinic:
        owner_role = (await self.session.execute(select(Role).where(Role.name == RoleName.OWNER.value))).scalar_one_or_none()
        if owner_role is None:
            # Foundation seed data (app/models/seed.py) guarantees this role
            # exists in any correctly-migrated database - a missing Owner
            # role means the deployment itself is broken, not a client error.
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Owner role is not seeded in this database - cannot create a clinic without it.",
            )

        clinic = Clinic(name=name, slug=slug, email=email, status="Active")
        self.session.add(clinic)
        await self.session.flush()

        owner = User(
            clinic_id=clinic.id,
            email=owner_email,
            username=owner_username,
            hashed_password=hash_password(owner_password),
            first_name=owner_first_name,
            last_name=owner_last_name,
            role_id=owner_role.id,
            is_active=True,
            is_email_verified=True,
        )
        self.session.add(owner)
        await self.session.flush()

        await self.audit.log(
            actor_id=actor_id, action="tenant.create", entity_type="clinic", entity_id=str(clinic.id),
            clinic_id=clinic.id, metadata={"name": name, "slug": slug, "owner_email": owner_email},
        )
        await self.session.commit()
        return clinic

    async def update_tenant(
        self, *, actor_id: UUID, clinic_id: UUID, name: str | None = None, slug: str | None = None,
        email: str | None = None,
    ) -> Clinic:
        clinic = await self.get_tenant(clinic_id)
        if clinic is None:
            raise ValueError("Tenant not found")

        if slug is not None and slug != clinic.slug:
            existing = await self.session.execute(
                select(Clinic).where(Clinic.slug == slug, Clinic.id != clinic_id, Clinic.is_deleted.is_(False))
            )
            if existing.scalar_one_or_none() is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already in use")
            clinic.slug = slug

        if name is not None:
            clinic.name = name
        if email is not None:
            clinic.email = email

        await self.audit.log(
            actor_id=actor_id, action="tenant.update", entity_type="clinic", entity_id=str(clinic_id),
            clinic_id=clinic_id,
            metadata={"fields": [k for k, v in {"name": name, "slug": slug, "email": email}.items() if v is not None]},
        )
        await self.session.commit()
        await self.session.refresh(clinic)
        return clinic

    async def delete_tenant(self, *, actor_id: UUID, clinic_id: UUID) -> None:
        clinic = await self.get_tenant(clinic_id)
        if clinic is None:
            raise ValueError("Tenant not found")
        # Only reachable from the terminal "Archived" lifecycle state - an
        # explicit two-step (Archive, then Delete) safety rail against
        # accidentally soft-deleting a live clinic's data (patients, visits,
        # billing, etc. all still hang off this clinic_id and are never
        # cascade-removed by this - see `SoftDeleteMixin`, matching every
        # other delete in this codebase).
        if clinic.status != "Archived":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tenant must be archived before it can be deleted.",
            )
        clinic.is_deleted = True
        await self.audit.log(
            actor_id=actor_id, action="tenant.delete", entity_type="clinic", entity_id=str(clinic_id), clinic_id=clinic_id
        )
        await self.session.commit()

    async def suspend_tenant(self, *, actor_id: UUID, clinic_id: UUID, reason: str | None) -> Clinic:
        clinic = await self.get_tenant(clinic_id)
        if clinic is None:
            raise ValueError("Tenant not found")
        clinic.status = "Suspended"
        clinic.suspended_at = datetime.now(UTC)
        clinic.suspended_reason = reason
        # Force-logout every user in this tenant on suspend: revoke all their
        # refresh tokens so existing sessions cannot continue, and login is
        # blocked going forward by AuthService checking clinic.status
        # (see app/services/auth_service.py login() - Phase 15 addition).
        await self.session.execute(
            RefreshToken.__table__.update()
            .where(RefreshToken.user_id.in_(select(User.id).where(User.clinic_id == clinic_id)))
            .values(revoked_at=datetime.now(UTC))
        )
        await self.audit.log(
            actor_id=actor_id, action="tenant.suspend", entity_type="clinic", entity_id=str(clinic_id),
            clinic_id=clinic_id, metadata={"reason": reason},
        )
        await self.session.commit()
        await self.session.refresh(clinic)
        return clinic

    async def reactivate_tenant(self, *, actor_id: UUID, clinic_id: UUID) -> Clinic:
        clinic = await self.get_tenant(clinic_id)
        if clinic is None:
            raise ValueError("Tenant not found")
        clinic.status = "Active"
        clinic.suspended_at = None
        clinic.suspended_reason = None
        await self.audit.log(
            actor_id=actor_id, action="tenant.reactivate", entity_type="clinic", entity_id=str(clinic_id), clinic_id=clinic_id
        )
        await self.session.commit()
        await self.session.refresh(clinic)
        return clinic

    async def archive_tenant(self, *, actor_id: UUID, clinic_id: UUID) -> Clinic:
        clinic = await self.get_tenant(clinic_id)
        if clinic is None:
            raise ValueError("Tenant not found")
        clinic.status = "Archived"
        clinic.archived_at = datetime.now(UTC)
        await self.audit.log(
            actor_id=actor_id, action="tenant.archive", entity_type="clinic", entity_id=str(clinic_id), clinic_id=clinic_id
        )
        await self.session.commit()
        await self.session.refresh(clinic)
        return clinic
