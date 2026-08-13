"""Generic repository providing common CRUD + tenant-scoped query helpers."""

from __future__ import annotations

from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Generic async repository. Concrete repositories set `model`."""

    model: type[ModelType]

    def __init__(self, session: AsyncSession, model: type[ModelType] | None = None) -> None:
        self.session = session
        if model is not None:
            self.model = model

    async def get_by_id(self, id_: UUID) -> ModelType | None:
        result = await self.session.execute(select(self.model).where(self.model.id == id_))
        return result.scalar_one_or_none()

    async def get(self, **filters: Any) -> ModelType | None:
        stmt = select(self.model).filter_by(**filters)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(self, *, limit: int = 100, offset: int = 0, **filters: Any) -> list[ModelType]:
        stmt = select(self.model).filter_by(**filters).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, **kwargs: Any) -> ModelType:
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, instance: ModelType, **kwargs: Any) -> ModelType:
        for key, value in kwargs.items():
            setattr(instance, key, value)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: ModelType, *, soft: bool = True) -> None:
        if soft and hasattr(instance, "is_deleted"):
            instance.is_deleted = True
            from datetime import UTC, datetime

            if hasattr(instance, "deleted_at"):
                instance.deleted_at = datetime.now(UTC)
            await self.session.flush()
        else:
            await self.session.delete(instance)
            await self.session.flush()

    # --- Tenant-scoped helpers ---

    async def list_by_clinic(
        self, clinic_id: UUID, *, limit: int = 100, offset: int = 0, **filters: Any
    ) -> list[ModelType]:
        if not hasattr(self.model, "clinic_id"):
            raise AttributeError(f"{self.model.__name__} is not tenant-scoped (no clinic_id column)")
        stmt = (
            select(self.model)
            .filter_by(clinic_id=clinic_id, **filters)
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_and_clinic(self, id_: UUID, clinic_id: UUID) -> ModelType | None:
        if not hasattr(self.model, "clinic_id"):
            raise AttributeError(f"{self.model.__name__} is not tenant-scoped (no clinic_id column)")
        stmt = select(self.model).where(self.model.id == id_, self.model.clinic_id == clinic_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
