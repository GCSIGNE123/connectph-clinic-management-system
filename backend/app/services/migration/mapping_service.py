"""Field mapping: known destination fields per entity type, fuzzy
suggestion of source->destination mappings, and CRUD over
`migration_field_mappings`.

Only `Patients` and `Doctors` are fully wired to real destination
entities in this phase (see `import_service.py` docstring for the scope
decision); the other 15 entity types in `MIGRATION_ENTITY_ORDER` still
get schema analysis + mapping-suggestion support (useful for a future
phase), but `import_service` skips them with a clear log message.
"""

import re
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.migration_batch import MigrationEntityType, MigrationFieldMapping

# Known destination fields per entity, used both for mapping suggestions
# and for the frontend's "destination fields" dropdown.
DESTINATION_FIELDS: dict[MigrationEntityType, list[str]] = {
    MigrationEntityType.PATIENTS: [
        "first_name", "middle_name", "last_name", "suffix", "birth_date", "gender",
        "civil_status", "nationality", "address_line", "barangay", "city", "province",
        "zip_code", "mobile_number", "telephone_number", "email", "occupation",
        "employer", "blood_type", "allergies", "medical_notes", "remarks",
        "emergency_contact_name", "emergency_contact_phone",
    ],
    MigrationEntityType.DOCTORS: [
        "first_name", "middle_name", "last_name", "suffix", "prc_license", "ptr_number",
        "specialization", "contact_number", "email", "consultation_fee", "status",
    ],
}

# Cheap normalization-based synonym table for the fuzzy matcher.
_SYNONYMS: dict[str, list[str]] = {
    "first_name": ["fname", "firstname", "first", "givenname"],
    "middle_name": ["mname", "middlename", "middle"],
    "last_name": ["lname", "lastname", "surname", "familyname"],
    "birth_date": ["dob", "dateofbirth", "birthdate", "bday"],
    "mobile_number": ["mobile", "cellphone", "cell", "mobileno", "contactnumber", "phone"],
    "telephone_number": ["telephone", "landline", "tel"],
    "email": ["emailaddress", "emailaddr"],
    "gender": ["sex"],
    "prc_license": ["prc", "prclicense", "prcno", "license"],
    "ptr_number": ["ptr", "ptrno", "ptrnumber"],
    "specialization": ["specialty", "speciality"],
    "contact_number": ["mobile", "phone", "contact"],
    "civil_status": ["maritalstatus", "civilstatus"],
    "address_line": ["address", "streetaddress", "addr"],
}


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def suggest_mappings(
    entity_type: MigrationEntityType, source_fields: list[str]
) -> list[dict]:
    """Exact/synonym/normalized name matching between source columns and
    known destination fields - a real, useful default the admin adjusts,
    not an empty form."""
    destinations = DESTINATION_FIELDS.get(entity_type, [])
    normalized_destinations = {_normalize(d): d for d in destinations}
    # Build reverse synonym lookup: normalized synonym -> destination field.
    synonym_lookup: dict[str, str] = {}
    for dest, synonyms in _SYNONYMS.items():
        if dest not in destinations:
            continue
        for syn in synonyms:
            synonym_lookup[_normalize(syn)] = dest

    suggestions = []
    used_destinations: set[str] = set()
    for source_field in source_fields:
        norm = _normalize(source_field)
        destination = None
        if norm in normalized_destinations and normalized_destinations[norm] not in used_destinations:
            destination = normalized_destinations[norm]
        elif norm in synonym_lookup and synonym_lookup[norm] not in used_destinations:
            destination = synonym_lookup[norm]
        if destination:
            used_destinations.add(destination)
        suggestions.append({"source_field": source_field, "destination_field": destination, "is_ignored": destination is None})
    return suggestions


class MappingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_mappings(self, batch_id: UUID, clinic_id: UUID) -> list[MigrationFieldMapping]:
        stmt = select(MigrationFieldMapping).where(
            MigrationFieldMapping.migration_batch_id == batch_id,
            MigrationFieldMapping.clinic_id == clinic_id,
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def replace_mappings(
        self, batch_id: UUID, clinic_id: UUID, mappings: list[dict]
    ) -> list[MigrationFieldMapping]:
        await self.session.execute(
            delete(MigrationFieldMapping).where(
                MigrationFieldMapping.migration_batch_id == batch_id,
                MigrationFieldMapping.clinic_id == clinic_id,
            )
        )
        rows = []
        for m in mappings:
            row = MigrationFieldMapping(
                clinic_id=clinic_id,
                migration_batch_id=batch_id,
                entity_type=m["entity_type"],
                source_field=m["source_field"],
                destination_field=m.get("destination_field"),
                transform_type=m.get("transform_type", "None"),
                transform_config=m.get("transform_config"),
                is_ignored=m.get("is_ignored", False),
            )
            self.session.add(row)
            rows.append(row)
        await self.session.flush()
        return rows
