"""FastAPI dependency-injection providers: DB session, current user, tenant context."""

from collections.abc import AsyncGenerator
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.patient_security import PatientTokenType, decode_patient_token
from app.core.platform_admin_security import PlatformTokenType, decode_platform_token
from app.core.security import TokenPayloadError, TokenType, decode_token
from app.db.session import get_session
from app.models.patient import Patient
from app.models.patient_account import PatientAccount
from app.models.platform_admin_user import PlatformAdminRole, PlatformAdminUser
from app.models.user import User
from app.repositories.patient_account_repository import PatientAccountRepository
from app.repositories.platform_admin_repository import PlatformAdminUserRepository
from app.repositories.user_repository import UserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

# Phase 15: a completely separate bearer scheme for the Platform Administration
# Portal. This is intentionally NOT the same `oauth2_scheme` instance as the
# clinic portal's - the two auth flows never share a dependency.
platform_admin_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/platform-admin/auth/login", auto_error=False
)

# Phase 18: a third, completely separate bearer scheme for the Patient Portal.
patient_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/patient-portal/auth/login", auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a request-scoped async DB session."""
    async for session in get_session():
        yield session


def _decode_access_token(token: str) -> dict:
    try:
        return decode_token(token, expected_type=TokenType.ACCESS)
    except TokenPayloadError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the authenticated user from the bearer access token."""
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = _decode_access_token(token)
    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    repo = UserRepository(db)
    user = await repo.get_by_id(UUID(user_id))
    if user is None or user.is_deleted:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")
    return user


async def get_current_clinic_id(
    token: str | None = Depends(oauth2_scheme),
) -> UUID | None:
    """Extract the tenant (clinic) id from the JWT claims, used for tenant scoping."""
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = _decode_access_token(token)
    clinic_id = payload.get("clinic_id")
    if clinic_id is None:
        return None
    return UUID(clinic_id)


async def require_clinic_context(
    clinic_id: UUID | None = Depends(get_current_clinic_id),
) -> UUID:
    """Like `get_current_clinic_id` but fails if no tenant context is present."""
    if clinic_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No clinic (tenant) context associated with this token",
        )
    return clinic_id


# Roles permitted to manage other users (create/edit/disable/enable/reset password).
USER_MANAGEMENT_ROLES = {"Owner", "Administrator"}


def require_roles(*allowed_role_names: str):
    """Dependency factory: 403s unless the current user's role is in `allowed_role_names`."""

    async def _check(current_user: User = Depends(get_current_user)) -> User:
        role_name = current_user.role.name if current_user.role is not None else None
        if role_name not in allowed_role_names:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return _check


require_user_management_role = require_roles(*USER_MANAGEMENT_ROLES)

# Patient management roles.
# View: every authenticated clinic role can look up patient records (needed
# by front-desk, clinical, billing, lab, and pharmacy workflows alike).
PATIENT_VIEW_ROLES = {
    "Owner", "Administrator", "Receptionist", "Doctor", "Nurse",
    "Cashier", "Laboratory", "Pharmacy", "Viewer",
}
# Add/edit: roles that actually capture or correct patient demographic data.
PATIENT_MANAGE_ROLES = {"Owner", "Administrator", "Receptionist", "Doctor", "Nurse"}
# Archive/restore: a more sensitive action, restricted to front-desk/admin roles.
PATIENT_ARCHIVE_ROLES = {"Owner", "Administrator", "Receptionist"}

require_patient_view_role = require_roles(*PATIENT_VIEW_ROLES)
require_patient_manage_role = require_roles(*PATIENT_MANAGE_ROLES)
require_patient_archive_role = require_roles(*PATIENT_ARCHIVE_ROLES)

# Phase 4: Clinic Configuration & Master Data.
# View: broad - operational roles need to see doctors/services/rooms for
# their daily work (booking, billing, lab routing, etc. in future modules).
CONFIG_VIEW_ROLES = {
    "Owner", "Administrator", "Receptionist", "Doctor", "Nurse",
    "Cashier", "Laboratory", "Pharmacy", "Viewer",
}
# Write: configuration changes are restricted to Owner/Administrator.
CONFIG_MANAGE_ROLES = {"Owner", "Administrator"}

require_config_view_role = require_roles(*CONFIG_VIEW_ROLES)
require_config_manage_role = require_roles(*CONFIG_MANAGE_ROLES)

# TV Displays / TV Info Panel: Receptionist has full operational control
# here (create/update/delete displays, announcements, info content, and
# uploaded images) - front-desk staff own operating and maintaining the
# waiting-room screens, deliberately kept off Doctors, unlike other
# config-manage endpoints which stay Owner/Administrator only.
TV_DISPLAY_MANAGE_ROLES = {"Owner", "Administrator", "Receptionist"}
require_tv_display_manage_role = require_roles(*TV_DISPLAY_MANAGE_ROLES)

# Phase 5: Reception & Queue Management.
# Manage (create/cancel/reassign): front-desk + admin roles that own the
# daily walk-in workflow.
QUEUE_MANAGE_ROLES = {"Owner", "Administrator", "Receptionist"}
# Transition (call/serve/complete/skip/no-show): also clinical roles who
# actually pull patients from the queue.
QUEUE_TRANSITION_ROLES = {"Owner", "Administrator", "Receptionist", "Doctor", "Nurse"}
# View: broad, read-only for everyone else (e.g. Viewer, Cashier).
QUEUE_VIEW_ROLES = {
    "Owner", "Administrator", "Receptionist", "Doctor", "Nurse",
    "Cashier", "Laboratory", "Pharmacy", "Viewer",
}

require_queue_manage_role = require_roles(*QUEUE_MANAGE_ROLES)
require_queue_transition_role = require_roles(*QUEUE_TRANSITION_ROLES)
require_queue_view_role = require_roles(*QUEUE_VIEW_ROLES)

# Phase 6: Visit (Encounter) Management.
# Visits are primarily created via the Queue flow, but the same role
# matrix as Queue applies for View/Create/Modify actions; "Close" (final
# status transitions like Completed/Cancelled) is intentionally the same as
# the transition roles since clinical roles need to close out consultations.
VISIT_VIEW_ROLES = QUEUE_VIEW_ROLES
VISIT_CREATE_ROLES = QUEUE_MANAGE_ROLES
VISIT_MODIFY_ROLES = QUEUE_MANAGE_ROLES
VISIT_CLOSE_ROLES = QUEUE_TRANSITION_ROLES

require_visit_view_role = require_roles(*VISIT_VIEW_ROLES)
require_visit_create_role = require_roles(*VISIT_CREATE_ROLES)
require_visit_modify_role = require_roles(*VISIT_MODIFY_ROLES)
require_visit_close_role = require_roles(*VISIT_CLOSE_ROLES)

# Phase 7: Doctor Workspace.
# View: Doctor (own visits only, enforced in the service layer),
# Administrator/Owner (all visits), and Receptionist (read-only per spec -
# "Reception cannot modify doctor actions", but reception still needs to
# see the doctor's queue for coordination).
DOCTOR_WORKSPACE_VIEW_ROLES = {"Owner", "Administrator", "Doctor", "Receptionist"}
# Act (call/recall/start/complete/no-show/cancel/open/release-lock): Doctor
# (own visits only) and Administrator/Owner (any visit). Receptionist is
# intentionally excluded - view-only on this module.
DOCTOR_WORKSPACE_ACT_ROLES = {"Owner", "Administrator", "Doctor"}
# Roles that may act on/view *any* doctor's visits, not just their own.
DOCTOR_WORKSPACE_PRIVILEGED_ROLES = {"Owner", "Administrator"}

require_doctor_workspace_view_role = require_roles(*DOCTOR_WORKSPACE_VIEW_ROLES)
require_doctor_workspace_act_role = require_roles(*DOCTOR_WORKSPACE_ACT_ROLES)

# Doctor E-Signature: Owner/Administrator may manage ANY doctor's signature
# (same as `CONFIG_MANAGE_ROLES`); a Doctor-role user is additionally let
# through this role gate but ONLY to manage their OWN signature - that
# ownership check is NOT expressible as a role set and is enforced
# separately in `DoctorService` (see `_require_signature_permission`),
# never trusted from this dependency alone. Receptionist/Cashier are
# deliberately excluded entirely, per product decision.
DOCTOR_SIGNATURE_MANAGE_ROLES = {"Owner", "Administrator", "Doctor"}
require_doctor_signature_manage_role = require_roles(*DOCTOR_SIGNATURE_MANAGE_ROLES)

# Phase 8: Clinical Consultation / SOAP.
# Stricter than Phase 7: "Administrators may view" (not edit) and
# "Reception cannot view or edit SOAP notes" per spec - Receptionist is
# excluded entirely (403 on both view and edit), unlike Phase 7 where
# Receptionist got read-only access to the doctor's queue.
CONSULTATION_VIEW_ROLES = {"Owner", "Administrator", "Doctor"}
# Edit: enforced further in the service layer to "only the visit's assigned
# doctor" - Owner/Administrator pass this role gate but are then denied
# write access in `ConsultationService` (view-only, per spec), so they are
# intentionally included here (for the view-capable open/read endpoints)
# but never granted `can_edit=True`.
CONSULTATION_EDIT_ROLES = {"Owner", "Administrator", "Doctor"}
CONSULTATION_PRIVILEGED_ROLES = {"Owner", "Administrator"}

require_consultation_view_role = require_roles(*CONSULTATION_VIEW_ROLES)
require_consultation_edit_role = require_roles(*CONSULTATION_EDIT_ROLES)

# Phase 20 (Client Acceptance Revisions, items 3-5): a deliberate, narrow
# reversal of the "Reception cannot view or edit SOAP notes" rule above -
# the client explicitly wants Receptionist (performing Nurse-type duties,
# item 3) to be able to enter ONLY the Subjective and Objective/vitals
# portions of a visit's SOAP note. This does NOT grant Receptionist general
# consultation view/edit access (`CONSULTATION_VIEW_ROLES`/`_EDIT_ROLES` are
# unchanged) - it only gates the new, field-restricted
# `/consultations/{id}/soap/subjective-objective` GET/PUT endpoints and the
# matching `/visits/{id}/consultation/open-for-reception` endpoint in
# `api/v1/consultations.py`. Nurse is included per item 3 even though no
# Nurse-specific endpoints exist yet elsewhere, so a real Nurse-role user
# gets the same capability as Receptionist for this one narrow purpose.
# Assessment/Plan and consultation open(full)/complete/sign remain
# Doctor/Owner/Administrator-only via the roles above, unchanged.
SOAP_SUBJECTIVE_OBJECTIVE_ROLES = {"Owner", "Administrator", "Doctor", "Receptionist", "Nurse"}
require_soap_subjective_objective_role = require_roles(*SOAP_SUBJECTIVE_OBJECTIVE_ROLES)

# Phase 9: Billing & Cashier.
# View: broad - Cashier/Owner/Administrator/Doctor(view-only)/Receptionist
# (read-only per spec's explicit "Reception: Read-only" wording - distinct
# from Phase 8's Receptionist-excluded-entirely rule for SOAP notes; billing
# amounts/status are visible to reception, just not editable by them).
BILLING_VIEW_ROLES = {"Owner", "Administrator", "Cashier", "Doctor", "Receptionist"}
# Create/edit invoice items + discounts, record/void payments: Cashier plus
# Owner/Administrator (who can do anything a Cashier can, per the general
# admin-override pattern already used for Patients/Queue/Visits).
BILLING_MANAGE_ROLES = {"Owner", "Administrator", "Cashier"}
# Phase 20 (Client Acceptance Revisions, item 1/2/11): the client explicitly
# asked for Receptionist to be able to apply discounts and record payments
# (previously Cashier-only per the original Billing spec's "Reception:
# Read-only" wording). Voiding a payment and refund approval remain
# stricter/unchanged - Receptionist is intentionally NOT added to those, so
# it still cannot undo a recorded payment or approve a refund.
#
# Client Acceptance Revisions - Round 2 (item 2/3): the client reversed the
# discount-authority decision specifically. Discount apply/remove is now a
# separation-of-duties control: the Doctor authorizes the discount, the
# Cashier/Receptionist just execute/record payment without being able to
# alter pricing. Receptionist loses discount access; Doctor gains it.
# Cashier was never in this set per the original Phase 10 design and stays
# out. Payment recording (BILLING_PAYMENT_RECORD_ROLES) is unaffected -
# that stays Receptionist-inclusive per Phase 20, unchanged here.
#
# Client Acceptance Revisions - Round 3 (item 10): the client reversed this
# decision AGAIN. Exact requirement text: "Permissions: Receptionist,
# Cashier, Admin [should be able to apply Senior Citizen/PWD/Custom
# discounts]." This round does NOT say Doctor loses access - only that
# Receptionist/Cashier/Admin gain (regain) it - so Doctor is kept rather
# than removed (removing something nobody asked to remove would itself be
# an unrequested regression). Owner is kept too, consistent with every
# other permission set in this codebase treating Owner as a superset of
# Administrator. Final decision: Owner, Administrator, Doctor, Cashier,
# Receptionist. This is the THIRD time this permission has changed hands
# (Phase 20 Round 1: +Receptionist: Round 2: -Receptionist, +Doctor;
# Round 3 (this change): +Receptionist, +Cashier, Doctor/Owner/Admin kept).
# See docs/TESTING.md "Round 3" section for the full history table.
BILLING_DISCOUNT_ROLES = {"Owner", "Administrator", "Doctor", "Cashier", "Receptionist"}
BILLING_PAYMENT_RECORD_ROLES = {"Owner", "Administrator", "Cashier", "Receptionist"}
# Void: unchanged from the original Cashier/Owner/Administrator-only gate.
BILLING_VOID_ROLES = {"Owner", "Administrator", "Cashier"}
# Refund approval: Administrator (and Owner) only - stricter than payment
# recording, per spec ("Administrator-only refund").
BILLING_REFUND_ROLES = {"Owner", "Administrator"}

require_billing_view_role = require_roles(*BILLING_VIEW_ROLES)
require_billing_manage_role = require_roles(*BILLING_MANAGE_ROLES)
require_billing_discount_role = require_roles(*BILLING_DISCOUNT_ROLES)
require_billing_payment_record_role = require_roles(*BILLING_PAYMENT_RECORD_ROLES)
require_billing_void_role = require_roles(*BILLING_VOID_ROLES)
require_billing_refund_role = require_roles(*BILLING_REFUND_ROLES)

# Phase 9: Clinical Orders & Prescriptions.
# View: same shape as Consultation (Owner/Administrator view-only,
# Doctor - enforced further to "assigned doctor may edit" in the service/
# API layer, same as Phase 8's SOAP/Diagnosis pattern) PLUS Receptionist,
# who per this phase's spec gets explicit "Reception: Read-only" (distinct
# from Phase 8, where Receptionist was excluded entirely from Consultation).
CLINICAL_ORDERS_VIEW_ROLES = {"Owner", "Administrator", "Doctor", "Receptionist"}
# Edit (create orders/procedures/referrals/prescriptions, update order
# status): enforced further in the service layer to "only the visit's
# assigned doctor"; Owner/Administrator pass this gate for the view-capable
# endpoints but are never granted `can_edit=True` (view-only, mirrors Phase 8).
CLINICAL_ORDERS_EDIT_ROLES = {"Owner", "Administrator", "Doctor"}
CLINICAL_ORDERS_PRIVILEGED_ROLES = {"Owner", "Administrator"}
# Laboratory role: read-only view of Laboratory-category orders only (no
# access to Radiology/Procedure/Referral/Vaccination orders or to
# Prescriptions) - enforced in `api/v1/clinical_orders.py`'s Laboratory
# order-list endpoint.
CLINICAL_ORDERS_LAB_VIEW_ROLES = {"Owner", "Administrator", "Laboratory"}

require_clinical_orders_view_role = require_roles(*CLINICAL_ORDERS_VIEW_ROLES)
require_clinical_orders_edit_role = require_roles(*CLINICAL_ORDERS_EDIT_ROLES)
require_clinical_orders_lab_view_role = require_roles(*CLINICAL_ORDERS_LAB_VIEW_ROLES)

# Medical Certificates.
# View/print: broader than Clinical Orders' own view set - product decision
# explicitly adds Cashier (alongside Receptionist) so front-desk staff can
# reprint an already-issued certificate for a returning patient, without
# granting either role any create/edit/issue/cancel capability.
MEDICAL_CERTIFICATE_VIEW_ROLES = {"Owner", "Administrator", "Doctor", "Receptionist", "Cashier"}
# Edit (create draft/update draft/issue/cancel/reissue): enforced further in
# the service layer to "only the visit's assigned doctor" - Owner/
# Administrator pass this gate for the view-capable endpoints but are never
# granted `can_edit=True` (product decision v1: Owner/Administrator must NOT
# issue on a doctor's behalf), mirroring the Consultation/Clinical Orders
# pattern exactly.
MEDICAL_CERTIFICATE_EDIT_ROLES = {"Owner", "Administrator", "Doctor"}
MEDICAL_CERTIFICATE_PRIVILEGED_ROLES = {"Owner", "Administrator"}

require_medical_certificate_view_role = require_roles(*MEDICAL_CERTIFICATE_VIEW_ROLES)
require_medical_certificate_edit_role = require_roles(*MEDICAL_CERTIFICATE_EDIT_ROLES)

# Post-RC1: Vaccination administration. A doctor ORDERS a vaccination via the
# normal Clinical Orders flow above (CLINICAL_ORDERS_EDIT_ROLES); actually
# ADMINISTERING it (recording lot/site/route/dose and marking it given) is a
# deliberately separate, broader permission - unlike other order categories,
# not restricted to "the assigned doctor": any Nurse or Receptionist in the
# clinic may administer, in addition to the ordering Doctor and Owner/
# Administrator, matching real clinic staffing where front-desk/nursing
# staff routinely give injections a doctor has ordered.
VACCINATION_ADMINISTER_ROLES = {"Owner", "Administrator", "Doctor", "Nurse", "Receptionist"}
VACCINATION_VIEW_ROLES = VACCINATION_ADMINISTER_ROLES

require_vaccination_administer_role = require_roles(*VACCINATION_ADMINISTER_ROLES)
require_vaccination_view_role = require_roles(*VACCINATION_VIEW_ROLES)

# Phase 10: Laboratory Management.
# View: broad, same shape as the other clinical modules - Doctor/Receptionist
# are read-only ("Reception: view-only" per spec), Laboratory/Owner/
# Administrator get full visibility.
LAB_VIEW_ROLES = {"Owner", "Administrator", "Laboratory", "Doctor", "Receptionist"}
# Manage (collect/process/enter-results/release/cancel/attachments): the
# Laboratory role (plus Owner/Administrator per the general admin-override
# pattern used across every other module). Doctor is explicitly excluded -
# per spec, Doctor only *creates* orders (unchanged Phase 9 endpoint);
# Laboratory personnel own the collection->release workflow.
LAB_MANAGE_ROLES = {"Owner", "Administrator", "Laboratory"}
# Template administration: Administrator-only mutation per spec
# ("Administrator configures tests without code changes"); read is broad
# (LAB_VIEW_ROLES) since the doctor-facing order-creation UI and the Lab
# Dashboard both need to read the template catalog.
LAB_TEMPLATE_MANAGE_ROLES = {"Owner", "Administrator"}

require_lab_view_role = require_roles(*LAB_VIEW_ROLES)
require_lab_manage_role = require_roles(*LAB_MANAGE_ROLES)
require_lab_template_manage_role = require_roles(*LAB_TEMPLATE_MANAGE_ROLES)

# Phase 11: Appointment Management.
# View: broad - everyone who touches the appointment lifecycle needs to see it.
APPOINTMENT_VIEW_ROLES = {"Owner", "Administrator", "Receptionist", "Doctor", "Cashier", "Laboratory"}
# Create/edit/reschedule/cancel/check-in: Reception (plus Owner/Administrator
# per the general admin-override pattern used across every other module).
APPOINTMENT_MANAGE_ROLES = {"Owner", "Administrator", "Receptionist"}
# Complete/no-show: Doctor-actionable (plus Owner/Administrator).
APPOINTMENT_COMPLETE_ROLES = {"Owner", "Administrator", "Doctor"}
# Doctor schedule (working hours/blocks) administration: Administrator-only
# mutation, matching LAB_TEMPLATE_MANAGE_ROLES's rationale.
APPOINTMENT_SCHEDULE_MANAGE_ROLES = {"Owner", "Administrator"}

require_appointment_view_role = require_roles(*APPOINTMENT_VIEW_ROLES)
require_appointment_manage_role = require_roles(*APPOINTMENT_MANAGE_ROLES)
require_appointment_complete_role = require_roles(*APPOINTMENT_COMPLETE_ROLES)
require_appointment_schedule_manage_role = require_roles(*APPOINTMENT_SCHEDULE_MANAGE_ROLES)

# Phase 12: Owner Dashboard & Reports.
# The strictest, simplest gate in the project - every analytics endpoint
# (dashboard, activity feed, every report, alerts, exports) is Owner and
# Administrator ONLY. No other role (including Doctor/Cashier/Laboratory,
# who each have their own scoped dashboards from earlier phases) gets any
# access here, per the spec's explicit "Owner/Administrator only" scoping.
ANALYTICS_ROLES = {"Owner", "Administrator"}

require_analytics_role = require_roles(*ANALYTICS_ROLES)

# Post-RC1 Phase 2 Milestone 1: Cloud Readiness - System Status panel.
# Owner and Administrator ONLY, same strictest gate/rationale as the
# Analytics module above - reused verbatim (`ANALYTICS_ROLES`) rather than
# defining a new permission, per the milestone spec's explicit instruction
# to match the existing admin-settings role-gating convention.
require_system_status_role = require_roles(*ANALYTICS_ROLES)

# Phase 14: Legacy Migration Wizard.
# Owner and Administrator ONLY, per spec - the same strictest gate as
# Phase 12's analytics module, reused verbatim: bulk-importing/overwriting
# real clinical entity data is not something any operational role should
# be able to trigger.
MIGRATION_ROLES = {"Owner", "Administrator"}

require_migration_role = require_roles(*MIGRATION_ROLES)


# =============================================================================
# Phase 15: SaaS Administration Portal - a SEPARATE, PARALLEL auth path.
#
# Everything below is completely independent of `get_current_user`/
# `require_roles` above. A platform-admin token will 401 if presented to any
# `get_current_user`-gated clinic endpoint (wrong `type` claim, no `user_id`
# claim), and a clinic-user token will 401 if presented to
# `get_current_platform_admin` (wrong `type` claim, no `platform_admin_id`
# claim). Neither dependency chain calls into the other.
# =============================================================================


async def get_current_platform_admin(
    token: str | None = Depends(platform_admin_oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> PlatformAdminUser:
    """Resolve the authenticated platform admin from a platform-admin bearer token.

    Rejects (401) any token that is not a valid, unexpired
    `platform_admin_access` token - including a perfectly valid clinic-user
    access token, since that token lacks the `platform_admin_id` claim and has
    `type == "access"` rather than `type == "platform_admin_access"`.
    """
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated (platform admin token required)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_platform_token(token, expected_type=PlatformTokenType.ACCESS)
    except TokenPayloadError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    platform_admin_id = payload.get("platform_admin_id")
    if platform_admin_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    repo = PlatformAdminUserRepository(db)
    admin = await repo.get_by_id(UUID(platform_admin_id))
    if admin is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Platform admin not found")
    if not admin.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform admin account is inactive")
    return admin


def require_platform_admin_roles(*allowed_roles: PlatformAdminRole):
    """Dependency factory: 403s unless the platform admin's role is in `allowed_roles`."""

    async def _check(current: PlatformAdminUser = Depends(get_current_platform_admin)) -> PlatformAdminUser:
        if current.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return current

    return _check


# Role/permission matrix for the Platform Administration Portal (documented in
# docs/ARCHITECTURE.md):
#   - Auditor: READ-ONLY across the entire platform-admin surface.
#   - SupportEngineer: can manage tenant users (reset password/lock/unlock/
#     force-logout) and view everything, but cannot change subscriptions,
#     feature flags, or platform config.
#   - ImplementationTeam: can manage tenants/subscriptions/feature flags
#     (onboarding work) but not platform users/config/backups.
#   - PlatformAdministrator: full access to everything.
PLATFORM_ADMIN_ALL_ROLES = {
    PlatformAdminRole.PLATFORM_ADMINISTRATOR,
    PlatformAdminRole.SUPPORT_ENGINEER,
    PlatformAdminRole.IMPLEMENTATION_TEAM,
    PlatformAdminRole.AUDITOR,
}
PLATFORM_ADMIN_TENANT_MANAGE_ROLES = {PlatformAdminRole.PLATFORM_ADMINISTRATOR, PlatformAdminRole.IMPLEMENTATION_TEAM}
PLATFORM_ADMIN_USER_MANAGE_ROLES = {PlatformAdminRole.PLATFORM_ADMINISTRATOR, PlatformAdminRole.SUPPORT_ENGINEER}
PLATFORM_ADMIN_FULL_ONLY_ROLES = {PlatformAdminRole.PLATFORM_ADMINISTRATOR}

require_platform_admin_view = require_platform_admin_roles(*PLATFORM_ADMIN_ALL_ROLES)
require_platform_admin_tenant_manage = require_platform_admin_roles(*PLATFORM_ADMIN_TENANT_MANAGE_ROLES)
require_platform_admin_user_manage = require_platform_admin_roles(*PLATFORM_ADMIN_USER_MANAGE_ROLES)
require_platform_admin_full = require_platform_admin_roles(*PLATFORM_ADMIN_FULL_ONLY_ROLES)


# =============================================================================
# Phase 18: Patient Portal - a THIRD, completely independent auth path.
#
# A patient token will 401 on `get_current_user` (wrong `type`, no `user_id`
# claim) and on `get_current_platform_admin` (wrong `type`, no
# `platform_admin_id` claim). Conversely, `get_current_patient` 401s on
# either a clinic-staff or a platform-admin token for the same reason.
# =============================================================================


class CurrentPatient:
    """Resolved patient-portal principal: the `PatientAccount` (credentials)
    plus the linked `Patient` (clinical/demographic record) it authenticates.
    Every patient-portal endpoint MUST scope all queries by
    `current.patient.id` and `current.patient.clinic_id` taken from THIS
    object (derived from the verified JWT), never from a request body/query
    param - this is what proves patient-to-patient and patient-to-clinic
    isolation."""

    def __init__(self, *, account: PatientAccount, patient: Patient) -> None:
        self.account = account
        self.patient = patient

    @property
    def id(self) -> UUID:
        return self.patient.id

    @property
    def clinic_id(self) -> UUID:
        return self.patient.clinic_id


async def get_current_patient(
    token: str | None = Depends(patient_oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentPatient:
    """Resolve the authenticated patient from a patient-portal bearer token.

    Rejects (401) any token that is not a valid, unexpired `patient_access`
    token - including a perfectly valid clinic-user or platform-admin access
    token, since those lack the `patient_account_id`/`patient_id` claims and
    have the wrong `type` value (see `app/core/patient_security.py`).
    """
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated (patient token required)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_patient_token(token, expected_type=PatientTokenType.ACCESS)
    except TokenPayloadError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc), headers={"WWW-Authenticate": "Bearer"}
        ) from exc

    patient_account_id = payload.get("patient_account_id")
    if patient_account_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    repo = PatientAccountRepository(db)
    found = await repo.get_with_patient(UUID(patient_account_id))
    if found is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Patient account not found")
    account, patient = found
    if not account.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Patient account is inactive")
    if patient.is_deleted:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Patient record not found")
    return CurrentPatient(account=account, patient=patient)


# Phase 21: Receptionist Shift Management.
# Start/view-own/close: Receptionist (plus Owner/Administrator, per the
# general admin-override pattern used throughout this codebase). Reopening
# a closed shift is a stricter, Owner/Administrator-only action - a
# Receptionist should not be able to un-close their own shift after the
# fact, that would defeat the point of the cash-accountability control.
SHIFT_MANAGE_ROLES = {"Owner", "Administrator", "Receptionist"}
SHIFT_REOPEN_ROLES = {"Owner", "Administrator"}

require_shift_manage_role = require_roles(*SHIFT_MANAGE_ROLES)
require_shift_reopen_role = require_roles(*SHIFT_REOPEN_ROLES)

# Medicine Inventory Phase 1 (Medicine catalog + MedicineBatch).
# View: Receptionist/Doctor/Nurse per the client's explicit request (Doctor
# is view-only - can check availability/expiry but never edit), plus Owner/
# Administrator. Deliberately narrower than CONFIG_VIEW_ROLES/PATIENT_VIEW_
# ROLES (no Cashier/Laboratory/Pharmacy/Viewer) - the client's spec named
# exactly Owner/Administrator/Receptionist/Doctor/Nurse and explicitly said
# not to invent a Pharmacy role for this feature.
INVENTORY_VIEW_ROLES = {"Owner", "Administrator", "Receptionist", "Doctor", "Nurse"}
# Manage (create/edit medicine catalog, receive/add batches, edit batch
# quantities): Receptionist owns day-to-day stock receiving per the client's
# spec, plus Owner/Administrator per the general admin-override pattern used
# throughout this codebase. Doctor is intentionally excluded - view only.
INVENTORY_MANAGE_ROLES = {"Owner", "Administrator", "Receptionist"}

require_inventory_view_role = require_roles(*INVENTORY_VIEW_ROLES)
require_inventory_manage_role = require_roles(*INVENTORY_MANAGE_ROLES)
