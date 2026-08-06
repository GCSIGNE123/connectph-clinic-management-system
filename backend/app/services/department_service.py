"""Department management service: CRUD + soft-delete/restore + optional default seeding."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import DEFAULT_DEPARTMENTS, Department
from app.models.user import User
from app.repositories.department_repository import DepartmentRepository
from app.schemas.department import DepartmentCreate, DepartmentSearchParams, DepartmentUpdate
from app.services.audit_service import AuditService


class DepartmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = DepartmentRepository(session)
        self.audit_service = AuditService(session)

    async def search(self, clinic_id: UUID, params: DepartmentSearchParams) -> tuple[list[Department], int]:
        return await self.repo.search(clinic_id, params)

    async def get(self, department_id: UUID, clinic_id: UUID) -> Department:
        department = await self.repo.get_by_id_and_clinic(department_id, clinic_id)
        if department is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
        return department

    async def create(self, payload: DepartmentCreate, *, clinic_id: UUID, actor: User) -> Department:
        existing = await self.repo.get_by_code(payload.department_code, clinic_id)
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Department code already in use")

        department = await self.repo.create(clinic_id=clinic_id, **payload.model_dump())
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="department.created",
            entity_type="department", entity_id=str(department.id),
        )
        await self.session.commit()
        return await self.get(department.id, clinic_id)

    async def update(self, department_id: UUID, payload: DepartmentUpdate, *, clinic_id: UUID, actor: User) -> Department:
        department = await self.get(department_id, clinic_id)
        updates = payload.model_dump(exclude_unset=True)
        if "department_code" in updates:
            existing = await self.repo.get_by_code(updates["department_code"], clinic_id)
            if existing is not None and existing.id != department_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Department code already in use")

        department = await self.repo.update(department, **updates)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="department.updated",
            entity_type="department", entity_id=str(department_id), metadata={"fields": list(updates.keys())},
        )
        await self.session.commit()
        return await self.get(department.id, clinic_id)

    async def delete(self, department_id: UUID, *, clinic_id: UUID, actor: User) -> None:
        department = await self.get(department_id, clinic_id)
        await self.repo.delete(department, soft=True)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="department.deleted",
            entity_type="department", entity_id=str(department_id),
        )
        await self.session.commit()

    async def restore(self, department_id: UUID, *, clinic_id: UUID, actor: User) -> Department:
        department = await self.repo.get_by_id_and_clinic(department_id, clinic_id)
        if department is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
        department.is_deleted = False
        department.deleted_at = None
        await self.session.flush()
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="department.restored",
            entity_type="department", entity_id=str(department_id),
        )
        await self.session.commit()
        return await self.get(department.id, clinic_id)

    async def seed_defaults(self, clinic_id: UUID, *, actor: User) -> list[Department]:
        """Optional convenience: populate the standard department set for a
        brand-new clinic. Skips codes that already exist. Documented in
        docs/FEATURES.md."""
        existing_count = await self.repo.count_active(clinic_id)
        if existing_count > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Clinic already has departments; default seeding is only for brand-new clinics.",
            )
        created = []
        for entry in DEFAULT_DEPARTMENTS:
            department = await self.repo.create(clinic_id=clinic_id, status="Active", description=None, **entry)
            created.append(department)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="department.defaults_seeded",
            entity_type="department", metadata={"count": len(created)},
        )
        await self.session.commit()
        return created
