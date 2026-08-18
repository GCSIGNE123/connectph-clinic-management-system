"""Aggregates all v1 API routers."""

from fastapi import APIRouter

from app.api.v1.patient_portal.router import router as patient_portal_router
from app.api.v1.platform_admin.router import router as platform_admin_router
from app.api.v1 import (
    analytics,
    appointments,
    auth,
    backup,
    billing,
    branches,
    clinic_settings,
    clinical_orders,
    consultation_rooms,
    consultations,
    departments,
    doctor_workspace,
    doctors,
    health,
    holidays,
    internal_messages,
    laboratory,
    medical_certificates,
    migration,
    operating_hours,
    patients,
    queue_settings,
    queues,
    roles,
    services,
    shifts,
    system_status,
    tv_display,
    users,
    vaccinations,
    visits,
    ws_queues,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(roles.router)
api_router.include_router(patients.router)

# Phase 4: Clinic Configuration & Master Data
api_router.include_router(clinic_settings.router)
api_router.include_router(branches.router)
api_router.include_router(departments.router)
api_router.include_router(doctors.router)
api_router.include_router(consultation_rooms.router)
api_router.include_router(services.router)
api_router.include_router(queue_settings.router)
api_router.include_router(operating_hours.router)
api_router.include_router(holidays.router)

# Phase 20: Internal staff messaging (item 14)
api_router.include_router(internal_messages.router)

# Phase 21: Receptionist Shift Management
api_router.include_router(shifts.router)

# Phase 5: Reception & Queue Management
api_router.include_router(queues.router)
api_router.include_router(ws_queues.router)

# Phase 6: Visit (Encounter) Management
api_router.include_router(visits.router)

# Phase 7: Doctor Workspace
api_router.include_router(doctor_workspace.router)

# Phase 8: Clinical Consultation / SOAP
api_router.include_router(consultations.router)

# Phase 9: Clinical Orders & Prescriptions
api_router.include_router(clinical_orders.router)

# Medical Certificates
api_router.include_router(medical_certificates.router)

# Phase 12: Billing & Cashier (renumbered - developed before Laboratory and
# before Appointments, but placed at 12 in the final sequence to make room
# for Phase 10 Laboratory and Phase 11 Appointments per explicit user instruction)
api_router.include_router(billing.router)

# Phase 10: Laboratory Management
api_router.include_router(laboratory.router)
api_router.include_router(laboratory.visit_router)

# Post-RC1: Vaccination Administration
api_router.include_router(vaccinations.router)

# Phase 11: Appointment Management
api_router.include_router(appointments.router)
api_router.include_router(appointments.doctors_router)
api_router.include_router(appointments.patients_router)

# Phase 12: Owner Dashboard & Reports
api_router.include_router(analytics.router)

# Phase 13: Live TV Queue Display
api_router.include_router(tv_display.router)
api_router.include_router(tv_display.announcements_router)
api_router.include_router(tv_display.info_content_router)
api_router.include_router(tv_display.public_router)

# Phase 14: Legacy Migration Wizard
api_router.include_router(migration.router)

# Phase 15: SaaS Administration Portal - genuinely separate router, gated by
# get_current_platform_admin (never get_current_user/require_roles).
api_router.include_router(platform_admin_router)

# Phase 18: Patient Portal - a THIRD, genuinely separate router, gated by
# get_current_patient (never get_current_user/require_roles or
# get_current_platform_admin).
api_router.include_router(patient_portal_router)

# Post-RC1 Phase 2 Milestone 1: Cloud Readiness - System Status panel.
api_router.include_router(system_status.router)

# Post-RC1 Phase 2 Milestone 2: Cloud Backup (One-Way Sync) - the API a
# cloud-hosted instance of this codebase exposes to a clinic's local sync
# worker. Gated by X-Sync-Api-Key, not any JWT dependency - see
# app/api/v1/backup.py.
api_router.include_router(backup.router)
