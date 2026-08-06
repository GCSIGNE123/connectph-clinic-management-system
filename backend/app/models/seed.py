"""Static seed data for foundation lookup tables (roles, permissions, mappings).

Used by the initial Alembic migration's data-seeding step and can also be
imported by application bootstrap scripts.
"""

from app.models.role import RoleName

# Role name -> human readable description.
ROLE_SEED_DATA: list[dict[str, str]] = [
    {"name": RoleName.OWNER.value, "description": "Clinic owner with full administrative control."},
    {"name": RoleName.ADMINISTRATOR.value, "description": "Manages clinic operations, staff, and settings."},
    {"name": RoleName.RECEPTIONIST.value, "description": "Front-desk scheduling and patient check-in."},
    {"name": RoleName.DOCTOR.value, "description": "Licensed physician providing clinical care."},
    {"name": RoleName.NURSE.value, "description": "Provides nursing and clinical support."},
    {"name": RoleName.CASHIER.value, "description": "Handles billing and payment collection."},
    {"name": RoleName.LABORATORY.value, "description": "Manages laboratory orders and results."},
    {"name": RoleName.PHARMACY.value, "description": "Manages pharmacy inventory and dispensing."},
    {"name": RoleName.VIEWER.value, "description": "Read-only access for reporting/audit purposes."},
]

# A reasonable starter set of permission codes, grouped by domain.
PERMISSION_SEED_DATA: list[dict[str, str]] = [
    {"code": "clinic:manage", "description": "Manage clinic profile and branches."},
    {"code": "users:manage", "description": "Create, update, and deactivate staff users."},
    {"code": "users:view", "description": "View staff user directory."},
    {"code": "patients:manage", "description": "Create and update patient records."},
    {"code": "patients:view", "description": "View patient records."},
    {"code": "appointments:manage", "description": "Create and update appointments/schedules."},
    {"code": "appointments:view", "description": "View appointments/schedules."},
    {"code": "billing:manage", "description": "Create invoices and process payments."},
    {"code": "billing:view", "description": "View billing and payment history."},
    {"code": "lab:manage", "description": "Manage laboratory orders and results."},
    {"code": "lab:view", "description": "View laboratory orders and results."},
    {"code": "pharmacy:manage", "description": "Manage pharmacy inventory and dispensing."},
    {"code": "pharmacy:view", "description": "View pharmacy inventory."},
    {"code": "reports:view", "description": "View operational and financial reports."},
    {"code": "settings:manage", "description": "Manage system settings."},
]

# Mapping of role name -> list of permission codes granted to that role by default.
ROLE_PERMISSION_SEED_DATA: dict[str, list[str]] = {
    RoleName.OWNER.value: [p["code"] for p in PERMISSION_SEED_DATA],
    RoleName.ADMINISTRATOR.value: [
        "clinic:manage",
        "users:manage",
        "users:view",
        "patients:manage",
        "patients:view",
        "appointments:manage",
        "appointments:view",
        "billing:manage",
        "billing:view",
        "reports:view",
        "settings:manage",
    ],
    RoleName.RECEPTIONIST.value: [
        "patients:manage",
        "patients:view",
        "appointments:manage",
        "appointments:view",
        "billing:view",
    ],
    RoleName.DOCTOR.value: [
        "patients:manage",
        "patients:view",
        "appointments:view",
        "lab:view",
        "pharmacy:view",
    ],
    RoleName.NURSE.value: [
        "patients:view",
        "appointments:view",
        "lab:view",
    ],
    RoleName.CASHIER.value: [
        "billing:manage",
        "billing:view",
        "patients:view",
    ],
    RoleName.LABORATORY.value: [
        "lab:manage",
        "lab:view",
        "patients:view",
    ],
    RoleName.PHARMACY.value: [
        "pharmacy:manage",
        "pharmacy:view",
        "patients:view",
    ],
    RoleName.VIEWER.value: [
        "patients:view",
        "appointments:view",
        "billing:view",
        "reports:view",
    ],
}
