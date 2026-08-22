"""Import all ORM models so `Base.metadata` is fully populated for Alembic autogenerate."""

from app.models.appointment import (
    Appointment,
    AppointmentCounter,
    AppointmentHistory,
    AppointmentHistoryAction,
    AppointmentReminder,
    AppointmentReminderChannel,
    AppointmentReminderStatus,
    AppointmentNote,
    AppointmentStatus,
    AppointmentType,
    APPOINTMENT_STATUS_TRANSITIONS,
    DoctorScheduleBlock,
    DoctorScheduleBlockType,
    NON_BLOCKING_APPOINTMENT_STATUSES,
    WaitlistEntry,
    WaitlistStatus,
)
from app.models.audit_log import AuditLog
from app.models.branch import Branch
from app.models.clinic import Clinic
from app.models.clinic_service import ClinicService
from app.models.consultation import Consultation, ConsultationStatus, CONSULTATION_STATUS_TRANSITIONS
from app.models.consultation_attachment import AttachmentType, ConsultationAttachment
from app.models.consultation_room import ConsultationRoom
from app.models.consultation_session import ConsultationSession, ConsultationSessionStatus
from app.models.department import Department
from app.models.diagnosis import Diagnosis, DiagnosisStatus, DiagnosisType
from app.models.discount import Discount, DiscountCalculationType, DiscountType
from app.models.doctor import Doctor, DoctorSchedule, DoctorStatus
from app.models.doctor_activity import DoctorActivity, DoctorActivityType
from app.models.email_verification_token import EmailVerificationToken
from app.models.holiday import Holiday
from app.models.internal_message import InternalMessage
from app.models.invoice import Invoice, InvoiceStatus, INVOICE_STATUS_TRANSITIONS
from app.models.invoice_counter import InvoiceCounter
from app.models.invoice_item import InvoiceItem, InvoiceItemType
from app.models.laboratory_attachment import LaboratoryAttachment, LaboratoryAttachmentType
from app.models.laboratory_order import LaboratoryOrder, LaboratoryOrderStatus, LABORATORY_ORDER_STATUS_TRANSITIONS
from app.models.laboratory_reference_range import LaboratoryReferenceRange
from app.models.laboratory_result import LaboratoryInterpretation, LaboratoryResult, LaboratoryResultType
from app.models.laboratory_template import LaboratoryTemplate, LaboratoryTemplateParameter
from app.models.medicine import (
    Medicine,
    MedicineBatch,
    MedicineBatchStatus,
    MedicineStockMovement,
    MedicineStockMovementType,
)
from app.models.migration_batch import (
    MigrationBatch,
    MigrationBatchStatus,
    MigrationEntityProgress,
    MigrationEntityProgressStatus,
    MigrationEntityType,
    MigrationFieldMapping,
    MigrationIssueResolution,
    MigrationIssueSeverity,
    MigrationIssueType,
    MigrationLog,
    MigrationLogLevel,
    MigrationSourceType,
    MigrationTransformType,
    MigrationValidationIssue,
)
from app.models.notification import Notification, NotificationRecipient, NotificationType
from app.models.operating_hours import OperatingHours
from app.models.api_key import ApiKey, OAuthClient, WebhookSecret
from app.models.backup import Backup, BackupStatus
from app.models.background_job import BackgroundJob, BackgroundJobStatus
from app.models.platform_admin_user import PlatformAdminRole, PlatformAdminUser
from app.models.platform_audit_log import PlatformAuditLog
from app.models.platform_config import PlatformConfig
from app.models.platform_session import PlatformSession
from app.models.tenant_feature_flag import TenantFeatureFlag, KNOWN_FEATURE_KEYS
from app.models.order import Order, OrderCategory, OrderItem, OrderPriority, OrderStatus, ORDER_STATUS_TRANSITIONS
from app.models.password_reset_token import PasswordResetToken
from app.models.patient import BloodType, CivilStatus, Gender, Patient, PatientStatus
from app.models.patient_account import (
    NotificationChannel,
    PatientAccount,
    PatientNotification,
    PatientNotificationPreference,
    PatientNotificationType,
    PatientPasswordResetToken,
)
from app.models.pathologist import Pathologist
from app.models.payment import Payment, PaymentMethod, PaymentStatus, Refund
from app.models.permission import Permission
from app.models.prescription import Prescription, PrescriptionItem, PrescriptionStatus
from app.models.procedure import Procedure
from app.models.queue import Queue, QueueCounter, QueuePriority, QueueStatus, QueueStatusHistory, VisitClassification
from app.models.doctor_session import DoctorSession
from app.models.queue_setting import PriorityType, QueueSetting
from app.models.referral import Referral
from app.models.refresh_token import RefreshToken
from app.models.role import Role, RoleName
from app.models.role_permission import RolePermission
from app.models.shift import Shift, ShiftStatus
from app.models.soap_note import SoapNote
from app.models.subscription import Subscription, SubscriptionPlan, SubscriptionStatus
from app.models.sync_job import SyncJob, SyncJobOperation, SyncJobStatus
from app.models.synced_record import SyncedRecord
from app.models.system_setting import SystemSetting
from app.models.tv_announcement import TvAnnouncement, TvAnnouncementType
from app.models.tv_display_config import (
    TvDisplayAnimationSpeed,
    TvDisplayConfig,
    TvDisplayFontSize,
    TvDisplayTheme,
)
from app.models.tv_info_content import DEFAULT_DURATION_SECONDS, TvInfoContent, TvInfoContentType
from app.models.user import User, UserStatus
from app.models.vaccination_administration import (
    VaccinationAdministration,
    VaccinationStatus,
    VACCINATION_STATUS_TRANSITIONS,
)
from app.models.visit import (
    Visit,
    VisitPriority,
    VisitStatus,
    VisitTimelineEvent,
    VisitTimelineEventType,
    VisitType,
)
from app.models.visit_counter import VisitCounter
from app.models.visit_lock import VisitLock

__all__ = [
    "Appointment",
    "AppointmentCounter",
    "AppointmentHistory",
    "AppointmentHistoryAction",
    "AppointmentReminder",
    "AppointmentReminderChannel",
    "AppointmentReminderStatus",
    "AppointmentNote",
    "AppointmentStatus",
    "AppointmentType",
    "APPOINTMENT_STATUS_TRANSITIONS",
    "DoctorScheduleBlock",
    "DoctorScheduleBlockType",
    "NON_BLOCKING_APPOINTMENT_STATUSES",
    "WaitlistEntry",
    "WaitlistStatus",
    "AttachmentType",
    "AuditLog",
    "BloodType",
    "Branch",
    "CivilStatus",
    "Clinic",
    "ClinicService",
    "Consultation",
    "ConsultationAttachment",
    "ConsultationRoom",
    "ConsultationSession",
    "ConsultationSessionStatus",
    "ConsultationStatus",
    "CONSULTATION_STATUS_TRANSITIONS",
    "Department",
    "Diagnosis",
    "DiagnosisStatus",
    "DiagnosisType",
    "Doctor",
    "DoctorActivity",
    "DoctorActivityType",
    "DoctorSchedule",
    "DoctorStatus",
    "EmailVerificationToken",
    "Gender",
    "Holiday",
    "OperatingHours",
    "ApiKey",
    "OAuthClient",
    "WebhookSecret",
    "Backup",
    "BackupStatus",
    "BackgroundJob",
    "BackgroundJobStatus",
    "PlatformAdminRole",
    "PlatformAdminUser",
    "PlatformAuditLog",
    "PlatformConfig",
    "PlatformSession",
    "TenantFeatureFlag",
    "KNOWN_FEATURE_KEYS",
    "Order",
    "OrderCategory",
    "OrderItem",
    "OrderPriority",
    "OrderStatus",
    "ORDER_STATUS_TRANSITIONS",
    "Pathologist",
    "Patient",
    "PatientStatus",
    "NotificationChannel",
    "PatientAccount",
    "PatientNotification",
    "PatientNotificationPreference",
    "PatientNotificationType",
    "PatientPasswordResetToken",
    "Permission",
    "PasswordResetToken",
    "Prescription",
    "PrescriptionItem",
    "PrescriptionStatus",
    "Procedure",
    "PriorityType",
    "Queue",
    "QueueCounter",
    "QueuePriority",
    "InternalMessage",
    "Medicine",
    "MedicineBatch",
    "MedicineBatchStatus",
    "MedicineStockMovement",
    "MedicineStockMovementType",
    "Notification",
    "NotificationRecipient",
    "NotificationType",
    "QueueSetting",
    "QueueStatus",
    "QueueStatusHistory",
    "VisitClassification",
    "Referral",
    "RefreshToken",
    "Role",
    "RoleName",
    "RolePermission",
    "Shift",
    "ShiftStatus",
    "SoapNote",
    "Subscription",
    "SubscriptionPlan",
    "SubscriptionStatus",
    "SyncJob",
    "SyncJobOperation",
    "SyncJobStatus",
    "SyncedRecord",
    "SystemSetting",
    "TvAnnouncement",
    "TvAnnouncementType",
    "TvDisplayAnimationSpeed",
    "TvDisplayConfig",
    "TvDisplayFontSize",
    "TvDisplayTheme",
    "TvInfoContent",
    "TvInfoContentType",
    "DEFAULT_DURATION_SECONDS",
    "User",
    "UserStatus",
    "VaccinationAdministration",
    "VaccinationStatus",
    "VACCINATION_STATUS_TRANSITIONS",
    "Visit",
    "VisitCounter",
    "VisitLock",
    "VisitPriority",
    "VisitStatus",
    "VisitTimelineEvent",
    "VisitTimelineEventType",
    "VisitType",
]
