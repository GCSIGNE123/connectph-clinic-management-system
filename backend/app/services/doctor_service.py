"""Doctor + doctor-schedule management service: CRUD, code generation, audit."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.doctor import Doctor, DoctorSchedule
from app.models.user import User
from app.repositories.doctor_repository import DoctorRepository, DoctorScheduleRepository
from app.schemas.doctor import (
    DoctorCreate,
    DoctorScheduleCreate,
    DoctorScheduleUpdate,
    DoctorSearchParams,
    DoctorUpdate,
)
from app.services.audit_service import AuditService
from app.services.doctor_code_generator import DoctorCodeGenerator


class DoctorService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = DoctorRepository(session)
        self.schedule_repo = DoctorScheduleRepository(session)
        self.code_generator = DoctorCodeGenerator(session)
        self.audit_service = AuditService(session)

    async def search(self, clinic_id: UUID, params: DoctorSearchParams) -> tuple[list[Doctor], int]:
        return await self.repo.search(clinic_id, params)

    async def get(self, doctor_id: UUID, clinic_id: UUID) -> Doctor:
        doctor = await self.repo.get_by_id_and_clinic(doctor_id, clinic_id)
        if doctor is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
        return doctor

    async def create(self, payload: DoctorCreate, *, clinic_id: UUID, actor: User) -> Doctor:
        doctor_code = await self.code_generator.next_code(clinic_id)
        doctor = await self.repo.create(clinic_id=clinic_id, doctor_code=doctor_code, **payload.model_dump())
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="doctor.created",
            entity_type="doctor", entity_id=str(doctor.id), metadata={"doctor_code": doctor_code},
        )
        await self.session.commit()
        return await self.get(doctor.id, clinic_id)

    async def update(self, doctor_id: UUID, payload: DoctorUpdate, *, clinic_id: UUID, actor: User) -> Doctor:
        doctor = await self.get(doctor_id, clinic_id)
        updates = payload.model_dump(exclude_unset=True)
        doctor = await self.repo.update(doctor, **updates)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="doctor.updated",
            entity_type="doctor", entity_id=str(doctor_id), metadata={"fields": list(updates.keys())},
        )
        await self.session.commit()
        return await self.get(doctor.id, clinic_id)

    async def delete(self, doctor_id: UUID, *, clinic_id: UUID, actor: User) -> None:
        doctor = await self.get(doctor_id, clinic_id)
        await self.repo.delete(doctor, soft=True)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="doctor.deleted",
            entity_type="doctor", entity_id=str(doctor_id),
        )
        await self.session.commit()

    async def restore(self, doctor_id: UUID, *, clinic_id: UUID, actor: User) -> Doctor:
        doctor = await self.repo.get_by_id_and_clinic(doctor_id, clinic_id)
        if doctor is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
        doctor.is_deleted = False
        doctor.deleted_at = None
        await self.session.flush()
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="doctor.restored",
            entity_type="doctor", entity_id=str(doctor_id),
        )
        await self.session.commit()
        return await self.get(doctor.id, clinic_id)

    async def request_photo_upload_url(self, doctor_id: UUID, *, clinic_id: UUID) -> dict:
        import secrets

        doctor = await self.get(doctor_id, clinic_id)
        token = secrets.token_urlsafe(24)
        object_path = f"clinics/{clinic_id}/doctors/{doctor.id}/photo-{token}.jpg"
        return {
            "upload_url": f"https://stub.supabase.local/storage/v1/upload/{object_path}",
            "public_url": f"https://stub.supabase.local/storage/v1/object/public/{object_path}",
            "expires_in": 600,
        }

    # --- Doctor E-Signature ---

    def require_signature_manage_permission(self, doctor_id: UUID, *, current_user: User) -> None:
        """Service-layer ownership check (defense in depth - never trust the
        API-layer role gate alone, same convention as
        `ConsultationService`'s can-edit checks). Owner/Administrator may
        manage ANY doctor's signature; a Doctor-role user may manage ONLY
        the signature on their OWN linked `Doctor` record
        (`User.doctor_id`)."""
        role_name = current_user.role.name if current_user.role is not None else None
        if role_name in {"Owner", "Administrator"}:
            return
        if role_name == "Doctor" and current_user.doctor_id is not None and current_user.doctor_id == doctor_id:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage this doctor's signature.",
        )

    async def set_signature(
        self, doctor_id: UUID, *, clinic_id: UUID, actor: User, stored_filename: str, replaced: bool
    ) -> Doctor:
        doctor = await self.get(doctor_id, clinic_id)
        doctor = await self.repo.update(doctor, signature_url=stored_filename)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id,
            action="doctor_signature.replaced" if replaced else "doctor_signature.added",
            entity_type="doctor", entity_id=str(doctor_id), metadata={"stored_filename": stored_filename},
        )
        await self.session.commit()
        return await self.get(doctor.id, clinic_id)

    async def remove_signature(self, doctor_id: UUID, *, clinic_id: UUID, actor: User) -> Doctor:
        doctor = await self.get(doctor_id, clinic_id)
        previous = doctor.signature_url
        doctor = await self.repo.update(doctor, signature_url=None)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="doctor_signature.removed",
            entity_type="doctor", entity_id=str(doctor_id), metadata={"stored_filename": previous},
        )
        await self.session.commit()
        return await self.get(doctor.id, clinic_id)

    # --- Doctor schedules ---

    async def list_schedules(self, doctor_id: UUID, *, clinic_id: UUID) -> list[DoctorSchedule]:
        await self.get(doctor_id, clinic_id)
        return await self.schedule_repo.list_for_doctor(doctor_id, clinic_id)

    async def add_schedule(
        self, doctor_id: UUID, payload: DoctorScheduleCreate, *, clinic_id: UUID, actor: User
    ) -> DoctorSchedule:
        await self.get(doctor_id, clinic_id)
        if payload.end_time <= payload.start_time:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="end_time must be after start_time")
        schedule = await self.schedule_repo.create(clinic_id=clinic_id, doctor_id=doctor_id, **payload.model_dump())
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="doctor_schedule.created",
            entity_type="doctor_schedule", entity_id=str(schedule.id), metadata={"doctor_id": str(doctor_id)},
        )
        await self.session.commit()
        return schedule

    async def update_schedule(
        self, doctor_id: UUID, schedule_id: UUID, payload: DoctorScheduleUpdate, *, clinic_id: UUID, actor: User
    ) -> DoctorSchedule:
        schedule = await self.schedule_repo.get_by_id_and_clinic(schedule_id, clinic_id)
        if schedule is None or schedule.doctor_id != doctor_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor schedule not found")
        updates = payload.model_dump(exclude_unset=True)
        schedule = await self.schedule_repo.update(schedule, **updates)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="doctor_schedule.updated",
            entity_type="doctor_schedule", entity_id=str(schedule_id),
        )
        await self.session.commit()
        return schedule

    async def delete_schedule(self, doctor_id: UUID, schedule_id: UUID, *, clinic_id: UUID, actor: User) -> None:
        schedule = await self.schedule_repo.get_by_id_and_clinic(schedule_id, clinic_id)
        if schedule is None or schedule.doctor_id != doctor_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor schedule not found")
        await self.schedule_repo.delete(schedule, soft=True)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="doctor_schedule.deleted",
            entity_type="doctor_schedule", entity_id=str(schedule_id),
        )
        await self.session.commit()
