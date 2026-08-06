"""Branch management service: CRUD + soft-delete/restore, tenant-scoped, audited."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.branch import Branch
from app.models.user import User
from app.repositories.branch_repository import BranchRepository
from app.schemas.branch import BranchCreate, BranchSearchParams, BranchUpdate
from app.services.audit_service import AuditService


class BranchService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = BranchRepository(session)
        self.audit_service = AuditService(session)

    async def search(self, clinic_id: UUID, params: BranchSearchParams) -> tuple[list[Branch], int]:
        return await self.repo.search(clinic_id, params)

    async def get(self, branch_id: UUID, clinic_id: UUID) -> Branch:
        branch = await self.repo.get_by_id_and_clinic(branch_id, clinic_id)
        if branch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
        return branch

    async def create(self, payload: BranchCreate, *, clinic_id: UUID, actor: User) -> Branch:
        if payload.code:
            existing = await self.repo.get_by_code(payload.code, clinic_id)
            if existing is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Branch code already in use")

        branch = await self.repo.create(clinic_id=clinic_id, **payload.model_dump())
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="branch.created",
            entity_type="branch", entity_id=str(branch.id),
        )
        await self.session.commit()
        return await self.get(branch.id, clinic_id)

    async def update(self, branch_id: UUID, payload: BranchUpdate, *, clinic_id: UUID, actor: User) -> Branch:
        branch = await self.get(branch_id, clinic_id)
        updates = payload.model_dump(exclude_unset=True)
        if "code" in updates and updates["code"]:
            existing = await self.repo.get_by_code(updates["code"], clinic_id)
            if existing is not None and existing.id != branch_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Branch code already in use")

        branch = await self.repo.update(branch, **updates)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="branch.updated",
            entity_type="branch", entity_id=str(branch_id), metadata={"fields": list(updates.keys())},
        )
        await self.session.commit()
        return await self.get(branch.id, clinic_id)

    async def delete(self, branch_id: UUID, *, clinic_id: UUID, actor: User) -> None:
        branch = await self.get(branch_id, clinic_id)
        await self.repo.delete(branch, soft=True)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="branch.deleted",
            entity_type="branch", entity_id=str(branch_id),
        )
        await self.session.commit()

    async def restore(self, branch_id: UUID, *, clinic_id: UUID, actor: User) -> Branch:
        branch = await self.repo.get_by_id_and_clinic(branch_id, clinic_id)
        if branch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
        branch.is_deleted = False
        branch.deleted_at = None
        await self.session.flush()
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="branch.restored",
            entity_type="branch", entity_id=str(branch_id),
        )
        await self.session.commit()
        return await self.get(branch.id, clinic_id)
