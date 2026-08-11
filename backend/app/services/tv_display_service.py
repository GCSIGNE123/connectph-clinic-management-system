"""TV Display service (Phase 13): config/announcement CRUD and the
Now-Serving/Next-Waiting snapshot used by both the public and the
authenticated-preview display endpoints.

Reuses `QueueRepository`'s existing query building blocks (via a direct,
Queue-model `select` scoped by `ACTIVE_QUEUE_STATUSES`, the same active-set
constant `QueueService`/`QueueRepository` already use) rather than
duplicating queue-list logic - no separate "queue status" concept is
introduced here.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.clinic import Clinic
from app.models.queue import ACTIVE_QUEUE_STATUSES, Queue, QueueStatus
from app.models.queue_setting import QueueSetting
from app.models.tv_announcement import TvAnnouncement
from app.models.tv_display_config import TvDisplayConfig, generate_public_slug
from app.models.tv_info_content import TvInfoContent
from app.repositories.queue_setting_repository import QueueSettingRepository
from app.repositories.tv_display_repository import (
    TvAnnouncementRepository,
    TvDisplayConfigRepository,
    TvInfoContentRepository,
)
from app.schemas.tv_display import (
    TvAnnouncementCreate,
    TvAnnouncementRead,
    TvAnnouncementUpdate,
    TvDisplayConfigCreate,
    TvDisplayConfigUpdate,
    TvDisplayData,
    TvDisplayNowServing,
    TvDisplayWaitingEntry,
    TvInfoContentCreate,
    TvInfoContentRead,
    TvInfoContentUpdate,
)
from app.services.audit_service import AuditService


def _resolve_room_label(
    settings: list[QueueSetting], *, branch_id: UUID | None, department_id: UUID | None, doctor_id: UUID | None
) -> str | None:
    """Post-RC1 (room-based TV announcements): in-memory re-implementation of
    `QueueSettingRepository.get_effective_for_doctor`'s exact "narrowest
    scope wins" resolution (doctor override -> department override ->
    branch/clinic default), operating over an already-fetched settings list
    instead of issuing a query per ticket. The winning row's `room_label` is
    used as-is (including `None` if that specific row never had one
    configured) - deliberately NOT cascading further up the chain looking
    for an ancestor row's room_label, since prefix and room are configured
    together on the same override row in the admin UI; a row that exists
    for prefix purposes but leaves room blank means "no room for this
    destination", not "inherit the parent's room"."""

    def find(b: UUID | None, d: UUID | None, doc: UUID | None) -> QueueSetting | None:
        for s in settings:
            if s.branch_id == b and s.department_id == d and s.doctor_id == doc:
                return s
        return None

    if doctor_id is not None:
        row = find(branch_id, department_id, doctor_id)
        if row is not None:
            return row.room_label
    if department_id is not None:
        row = find(branch_id, department_id, None)
        if row is not None:
            return row.room_label
    row = find(branch_id, None, None)
    return row.room_label if row is not None else None


def _initials(first_name: str, last_name: str) -> str:
    """Derives privacy-safe initials from a patient's name, server-side, so
    the full name is never sent to (or renderable by) the public display -
    see Phase 13 spec's explicit "patient initials only, never full name"
    requirement. e.g. "Juan" "Dela Cruz" -> "JD"."""
    f = first_name.strip()[:1].upper() if first_name and first_name.strip() else ""
    l = last_name.strip()[:1].upper() if last_name and last_name.strip() else ""
    return (f + l) or "??"


class TvDisplayService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.config_repo = TvDisplayConfigRepository(session)
        self.announcement_repo = TvAnnouncementRepository(session)
        self.info_content_repo = TvInfoContentRepository(session)
        self.queue_setting_repo = QueueSettingRepository(session)
        self.audit = AuditService(session)

    # ---- Config CRUD -----------------------------------------------------

    async def create_config(
        self, clinic_id: UUID, data: TvDisplayConfigCreate, actor_id: UUID
    ) -> TvDisplayConfig:
        public_slug = None
        if data.is_public:
            public_slug = generate_public_slug()
            # Astronomically unlikely to collide (192-bit token), but loop
            # defensively rather than trust chance.
            while await self.config_repo.slug_exists(public_slug):
                public_slug = generate_public_slug()

        config = await self.config_repo.create(
            clinic_id=clinic_id,
            branch_id=data.branch_id,
            department_id=data.department_id,
            doctor_id=data.doctor_id,
            display_name=data.display_name,
            is_public=data.is_public,
            public_slug=public_slug,
            theme=data.theme,
            font_size=data.font_size,
            animation_speed=data.animation_speed,
            queue_size=data.queue_size,
            refresh_interval_seconds=data.refresh_interval_seconds,
            logo_url=data.logo_url,
            primary_color=data.primary_color,
            secondary_color=data.secondary_color,
            tts_enabled=data.tts_enabled,
            tts_template=data.tts_template,
            is_active=data.is_active,
            created_by=actor_id,
        )
        await self.audit.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="tv_display.config_created",
            entity_type="tv_display_config", entity_id=str(config.id),
            metadata={"display_name": config.display_name, "is_public": config.is_public},
        )
        await self.session.commit()
        return config

    async def list_configs(self, clinic_id: UUID) -> list[TvDisplayConfig]:
        return await self.config_repo.list_by_clinic(clinic_id)

    async def get_config(self, clinic_id: UUID, config_id: UUID) -> TvDisplayConfig:
        config = await self.config_repo.get_by_id_and_clinic(config_id, clinic_id)
        if config is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TV display not found")
        return config

    async def update_config(
        self, clinic_id: UUID, config_id: UUID, data: TvDisplayConfigUpdate, actor_id: UUID
    ) -> TvDisplayConfig:
        config = await self.get_config(clinic_id, config_id)
        updates = data.model_dump(exclude_unset=True)

        # Toggling is_public on: mint a slug if one doesn't already exist.
        if updates.get("is_public") is True and not config.public_slug:
            new_slug = generate_public_slug()
            while await self.config_repo.slug_exists(new_slug):
                new_slug = generate_public_slug()
            updates["public_slug"] = new_slug
        # Toggling is_public off: keep the slug on file (so re-enabling
        # doesn't change the URL clinics may have printed/posted) but it
        # stops resolving publicly - `get_by_public_slug` filters on
        # `is_public.is_(True)`.

        config = await self.config_repo.update(config, **updates)
        await self.audit.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="tv_display.config_updated",
            entity_type="tv_display_config", entity_id=str(config.id), metadata={"fields": list(updates.keys())},
        )
        await self.session.commit()
        return config

    async def delete_config(self, clinic_id: UUID, config_id: UUID, actor_id: UUID) -> None:
        config = await self.get_config(clinic_id, config_id)
        await self.config_repo.delete(config, soft=True)
        await self.audit.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="tv_display.config_deleted",
            entity_type="tv_display_config", entity_id=str(config.id),
        )
        await self.session.commit()

    # ---- Announcement CRUD ------------------------------------------------

    async def create_announcement(
        self, clinic_id: UUID, config_id: UUID | None, data: TvAnnouncementCreate, actor_id: UUID
    ) -> TvAnnouncement:
        if data.tv_display_config_id is not None:
            await self.get_config(clinic_id, data.tv_display_config_id)  # 404s if not found/cross-tenant
        announcement = await self.announcement_repo.create(
            clinic_id=clinic_id,
            tv_display_config_id=data.tv_display_config_id,
            message=data.message,
            announcement_type=data.announcement_type,
            display_order=data.display_order,
            is_active=data.is_active,
            starts_at=data.starts_at,
            ends_at=data.ends_at,
            created_by=actor_id,
        )
        await self.audit.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="tv_display.announcement_created",
            entity_type="tv_announcement", entity_id=str(announcement.id),
            metadata={"announcement_type": announcement.announcement_type.value},
        )
        await self.session.commit()
        return announcement

    async def list_announcements(self, clinic_id: UUID, config_id: UUID) -> list[TvAnnouncement]:
        await self.get_config(clinic_id, config_id)
        return await self.announcement_repo.list_for_config(clinic_id, config_id)

    async def update_announcement(
        self, clinic_id: UUID, announcement_id: UUID, data: TvAnnouncementUpdate, actor_id: UUID
    ) -> TvAnnouncement:
        announcement = await self.announcement_repo.get_by_id_and_clinic(announcement_id, clinic_id)
        if announcement is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Announcement not found")
        updates = data.model_dump(exclude_unset=True)
        announcement = await self.announcement_repo.update(announcement, **updates)
        await self.audit.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="tv_display.announcement_updated",
            entity_type="tv_announcement", entity_id=str(announcement.id), metadata={"fields": list(updates.keys())},
        )
        await self.session.commit()
        return announcement

    async def delete_announcement(self, clinic_id: UUID, announcement_id: UUID, actor_id: UUID) -> None:
        announcement = await self.announcement_repo.get_by_id_and_clinic(announcement_id, clinic_id)
        if announcement is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Announcement not found")
        await self.announcement_repo.delete(announcement, soft=True)
        await self.audit.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="tv_display.announcement_deleted",
            entity_type="tv_announcement", entity_id=str(announcement.id),
        )
        await self.session.commit()

    # ---- Info Content CRUD (Post-RC1: 50/50 Information/Advertisement Panel) --

    async def create_info_content(
        self, clinic_id: UUID, data: TvInfoContentCreate, actor_id: UUID
    ) -> TvInfoContent:
        content = await self.info_content_repo.create(
            clinic_id=clinic_id,
            title=data.title,
            body=data.body,
            content_type=data.content_type,
            duration_seconds=data.duration_seconds,
            display_order=data.display_order,
            is_active=data.is_active,
            image_url=data.image_url,
            created_by=actor_id,
        )
        await self.audit.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="tv_display.info_content_created",
            entity_type="tv_info_content", entity_id=str(content.id),
            metadata={"content_type": content.content_type.value},
        )
        await self.session.commit()
        return content

    async def list_info_content(self, clinic_id: UUID) -> list[TvInfoContent]:
        return await self.info_content_repo.list_for_clinic(clinic_id)

    async def get_info_content_or_404(self, clinic_id: UUID, content_id: UUID) -> TvInfoContent:
        content = await self.info_content_repo.get_by_id_and_clinic(content_id, clinic_id)
        if content is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Information content not found")
        return content

    async def update_info_content(
        self, clinic_id: UUID, content_id: UUID, data: TvInfoContentUpdate, actor_id: UUID
    ) -> TvInfoContent:
        content = await self.info_content_repo.get_by_id_and_clinic(content_id, clinic_id)
        if content is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Information content not found")
        updates = data.model_dump(exclude_unset=True)
        content = await self.info_content_repo.update(content, **updates)
        await self.audit.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="tv_display.info_content_updated",
            entity_type="tv_info_content", entity_id=str(content.id), metadata={"fields": list(updates.keys())},
        )
        await self.session.commit()
        return content

    async def set_info_content_image(
        self, clinic_id: UUID, content_id: UUID, image_url: str | None, actor_id: UUID
    ) -> TvInfoContent:
        content = await self.info_content_repo.get_by_id_and_clinic(content_id, clinic_id)
        if content is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Information content not found")
        content = await self.info_content_repo.update(content, image_url=image_url)
        await self.audit.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="tv_display.info_content_image_updated",
            entity_type="tv_info_content", entity_id=str(content.id),
        )
        await self.session.commit()
        return content

    async def delete_info_content(self, clinic_id: UUID, content_id: UUID, actor_id: UUID) -> None:
        content = await self.info_content_repo.get_by_id_and_clinic(content_id, clinic_id)
        if content is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Information content not found")
        await self.info_content_repo.delete(content, soft=True)
        await self.audit.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="tv_display.info_content_deleted",
            entity_type="tv_info_content", entity_id=str(content.id),
        )
        await self.session.commit()

    # ---- Display data snapshot --------------------------------------------

    async def _build_display_data(self, config: TvDisplayConfig) -> TvDisplayData:
        clinic = (
            await self.session.execute(select(Clinic).where(Clinic.id == config.clinic_id))
        ).scalar_one_or_none()

        today = datetime.now(UTC).date()
        filters = [
            Queue.clinic_id == config.clinic_id,
            Queue.is_deleted.is_(False),
            Queue.status.in_(ACTIVE_QUEUE_STATUSES),
            Queue.queue_date == today,
        ]
        if config.branch_id is not None:
            filters.append(Queue.branch_id == config.branch_id)
        if config.department_id is not None:
            filters.append(Queue.department_id == config.department_id)
        if config.doctor_id is not None:
            filters.append(Queue.doctor_id == config.doctor_id)

        stmt = (
            select(Queue)
            .where(*filters)
            .options(
                selectinload(Queue.patient),
                selectinload(Queue.doctor),
                selectinload(Queue.branch),
                selectinload(Queue.department),
            )
            .order_by(Queue.called_at.asc().nulls_last(), Queue.created_at.asc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()

        now_serving_rows = [q for q in rows if q.status in (QueueStatus.CALLED, QueueStatus.SERVING)]
        waiting_rows = [q for q in rows if q.status == QueueStatus.WAITING]

        def doctor_name(q: Queue) -> str | None:
            if q.doctor is None:
                return None
            parts = [q.doctor.first_name, q.doctor.last_name]
            return " ".join(p for p in parts if p)

        # Post-RC1 (room-based TV announcements): fetched once per snapshot
        # build (not per ticket) and resolved in-memory - see
        # `_resolve_room_label`'s docstring. `ConsultationRoom` (Phase 4
        # master data) still has no FK link from Queue/Visit - this is a
        # deliberately separate, simpler "room label" carried on the same
        # QueueSetting override row already used for prefixes, not a new
        # link to that table.
        all_queue_settings = await self.queue_setting_repo.list_for_clinic(config.clinic_id)

        def room_name(q: Queue) -> str | None:
            return _resolve_room_label(
                all_queue_settings, branch_id=q.branch_id, department_id=q.department_id, doctor_id=q.doctor_id
            )

        now_serving = [
            TvDisplayNowServing(
                queue_id=q.id,
                queue_number=q.queue_number,
                patient_initials=_initials(q.patient.first_name, q.patient.last_name) if q.patient else "??",
                doctor_name=doctor_name(q),
                department_id=q.department_id,
                department_name=q.department.name if q.department else None,
                room_name=room_name(q),
                status=q.status.value,
                called_at=q.called_at,
            )
            for q in now_serving_rows
        ]
        next_waiting = [
            TvDisplayWaitingEntry(
                queue_id=q.id,
                queue_number=q.queue_number,
                patient_initials=_initials(q.patient.first_name, q.patient.last_name) if q.patient else "??",
                doctor_name=doctor_name(q),
                department_id=q.department_id,
                department_name=q.department.name if q.department else None,
                priority=q.priority.value,
            )
            for q in waiting_rows[: config.queue_size]
        ]

        announcements = await self.announcement_repo.list_active_for_display(
            config.clinic_id, config.id, today
        )
        info_content = await self.info_content_repo.list_active_for_clinic(config.clinic_id)

        branch_name = None
        if config.branch_id is not None:
            from app.models.branch import Branch

            branch = (
                await self.session.execute(select(Branch).where(Branch.id == config.branch_id))
            ).scalar_one_or_none()
            branch_name = branch.name if branch else None

        return TvDisplayData(
            display_name=config.display_name,
            clinic_name=clinic.name if clinic else "",
            branch_name=branch_name,
            theme=config.theme,
            font_size=config.font_size,
            animation_speed=config.animation_speed,
            queue_size=config.queue_size,
            refresh_interval_seconds=config.refresh_interval_seconds,
            logo_url=config.logo_url,
            primary_color=config.primary_color,
            secondary_color=config.secondary_color,
            now_serving=now_serving,
            next_waiting=next_waiting,
            announcements=[TvAnnouncementRead.model_validate(a) for a in announcements],
            info_content=[TvInfoContentRead.model_validate(c) for c in info_content],
            server_time=datetime.now(UTC),
            ws_channel_clinic_id=config.clinic_id,
            ws_auth_slug=config.public_slug if config.is_public else None,
        )

    async def get_public_display_data(self, public_slug: str) -> TvDisplayData:
        """No-auth-required. `TvDisplayConfigRepository.get_by_public_slug`
        already filters to `is_public=True, is_active=True, is_deleted=False`
        so an unknown/disabled/private slug returns 404 here, never a 500 or
        another clinic's data - the slug itself resolves exactly one clinic's
        scope, there is no way to widen it from the request."""
        config = await self.config_repo.get_by_public_slug(public_slug)
        if config is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TV display not found")
        return await self._build_display_data(config)

    async def get_display_data_for_authenticated_user(self, clinic_id: UUID, config_id: UUID) -> TvDisplayData:
        config = await self.get_config(clinic_id, config_id)
        return await self._build_display_data(config)
