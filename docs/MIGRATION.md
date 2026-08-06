# Legacy Migration Wizard — Operator Guide (Phase 14)

This guide is for the person running a real cutover from a legacy desktop
clinic system into CONNECT.PH. It covers what this build can and cannot
do today, how to prepare a source file, how to run the wizard end to
end, and how to interpret the results.

## What's actually implemented

- **CSV** and **Excel** source adapters are fully working (stdlib `csv`,
  `openpyxl`). This covers "export from virtually any legacy desktop
  system" without committing to one specific client's database engine.
- **SQLite / Microsoft Access / SQL Server / MySQL / PostgreSQL** sources
  have a real `SourceAdapter` interface (`connect()` / `analyze_schema()`
  / `read_table()` / `close()`) and a registry, but the concrete adapters
  raise `NotImplementedError` — export to CSV/Excel and use that path
  instead until a specific client's database technology is prioritized.
- **Patients** and **Doctors** are the only entity types that write to a
  real destination table in this build. The other 15 entity types in the
  17-step import order (Clinic, Branches, Departments, Users, Services,
  Visits, QueueHistory, Consultations, Diagnoses, Prescriptions,
  Laboratory, Billing, Payments, Attachments, AuditLogs) go through
  schema-analysis and field-mapping the same way, but the import step
  marks them `Skipped` with a log entry explaining why. Extending a
  skipped entity to a real import is a matter of adding a branch to
  `services/migration/migration_service.py::_import_one()` using that
  entity's existing service/repository create path — the
  progress/mapping/validation architecture already supports it.

## Preparing a CSV/Excel export

For CSV: export **one file per entity type** you want to import, named
so the wizard can guess the entity from the filename (e.g.
`patients.csv`, `doctors.csv` — case-insensitive, singular/plural both
match). Each file's first row must be a header row; every other row is
one record.

For Excel: export **one workbook**, one **sheet per entity type**, sheet
name matching the entity type (`Patients`, `Doctors`). First row of each
sheet is the header row.

### Expected columns (destination fields you can map to)

**Patients** — `first_name`, `middle_name`, `last_name`, `suffix`,
`birth_date`, `gender` (`Male`/`Female`/`Other`), `civil_status`
(`Single`/`Married`/`Widowed`/`Separated`/`Divorced`), `nationality`,
`address_line`, `barangay`, `city`, `province`, `zip_code`,
`mobile_number`, `telephone_number`, `email`, `occupation`, `employer`,
`blood_type`, `allergies`, `medical_notes`, `remarks`,
`emergency_contact_name`, `emergency_contact_phone`.
Required: `first_name`, `last_name`, `birth_date`, `gender`,
`civil_status`, `mobile_number`.

**Doctors** — `first_name`, `middle_name`, `last_name`, `suffix`,
`prc_license`, `ptr_number`, `specialization`, `contact_number`,
`email`, `consultation_fee`, `status`.
Required: `first_name`, `last_name`.

Your source column names don't need to match these exactly — the
mapping engine's `suggest_mappings()` does exact/synonym/normalized
matching (e.g. `FName`/`fname`/`First Name` → `first_name`, `DOB` →
`birth_date`, `Mobile` → `mobile_number`) and pre-fills a best guess you
then adjust.

## Running the wizard end to end

1. **Choose Source** — pick CSV or Excel, give it a description (e.g.
   the legacy system's name or the export filename).
2. **Connect** — upload the file(s).
3. **Analyze** — detects entity types (from filename/sheet name) and
   their columns.
4. **Map Fields** — per entity, review the suggested source→destination
   mapping; adjust or ignore columns; add a transform where needed:
   - `DateFormat` — parses the source date string (`transform_config:
     {"source_format": "%Y-%m-%d"}` or similar strptime pattern; falls
     back to a few common formats automatically).
   - `PhoneFormat` — strips non-digit/`+` characters; converts a
     Philippine `09XXXXXXXXX` trunk number to `+63XXXXXXXXXX`.
   - `Trim` — strips leading/trailing whitespace.
5. **Preview** — shows rows-to-import / rows-to-skip / warnings / errors
   per entity, computed without writing anything.
6. **Validate & Resolve Issues** — runs the full check list (required
   fields, duplicate patient by name+DOB or mobile, duplicate doctor by
   name, invalid date/phone/email, broken relationships) and lists every
   flagged row. Resolve each with **Skip** (row is not imported),
   **Merge/Overwrite/CreateNew** (architecture recorded on the issue;
   current import behavior for all non-Skip resolutions is CreateNew —
   see note below), or leave **Unresolved** (Error-severity rows still
   `Unresolved` at import time are automatically skipped; Warning-severity
   rows are always imported regardless of resolution). **Phase 17 fix**:
   earlier builds ignored `resolution` entirely and force-skipped every
   Error-severity row even after it was resolved to `CreateNew`/`Merge`/
   `Overwrite` — see `docs/BUGS.md` BUG-001. Resolving an issue now
   actually lets that row through on the next `preview`/`import`/
   `retry-batch` call.
7. **Import** — starts a background job (FastAPI `BackgroundTasks`, no
   new job-queue dependency) processing entities in the mandated
   17-step order, 500 rows per DB transaction, each batch's failure
   rolling back cleanly (no partial rows). The Migration Dashboard polls
   `GET /migration/batches/{id}/status` every 2 seconds while the batch
   is `Importing` and shows Status/Source/Records Found/Imported/
   Duplicates/Warnings/Errors/Elapsed Time/Estimated Time Remaining, plus
   a per-entity progress table.
8. **Verify** — `GET /migration/batches/{id}/verify` compares expected
   vs. imported counts per entity and reports `overall_ok`.

## Resume and retry

Every entity's progress is tracked independently
(`migration_entity_progress.last_processed_offset`). If an import is
interrupted (server restart, crash), calling
`POST /migration/batches/{id}/resume` re-runs the same entity loop —
entities already `Completed` are skipped instantly (offset already at
the end), and an `InProgress`/`Pending` entity continues from its last
processed offset. `POST /migration/batches/{id}/retry-batch?entity_type=X`
resets one entity's progress to `Pending`/offset 0 and re-imports it —
safe to do because of the idempotency check below, even though it forces
a full re-scan of that entity's rows.

## Idempotency

Every entity table already has `legacy_id` (the source row's ID) and
`migration_batch_id` from `LegacyMixin`. Before creating a new row, the
import engine looks up
`WHERE clinic_id = ? AND legacy_id = ? AND migration_batch_id = ?` on the
destination table — if a match exists, the row is counted as already
imported (skipped) rather than re-inserted. No separate `sync_hash`
column was added; this pair is sufficient. This was proven directly: an
identical CSV sample was imported, the batch was re-run in full (twice —
once via the normal resume path, once with the offset forcibly reset to
0 to force a complete re-scan), and `patients`/`doctors` row counts were
identical before and after both re-runs.

## Interpreting the Verification Report

For each entity type: `expected` (records found in the source minus
records that failed) vs. `imported` (records actually written), and a
`matches` boolean. `relationship_issues` lists any spot-checked broken
foreign keys (e.g. an imported Visit whose `doctor_id` doesn't resolve).
`overall_ok` is true only if every entity matches.

## Known limitations of this build

- Only Patients and Doctors import for real; every other entity type is
  mapping/validation-ready but skipped on import (see above).
- `Merge`/`Overwrite` resolutions are recorded on the validation issue
  but the import engine currently treats every non-Skip resolution as
  CreateNew (i.e., it still creates a new row rather than updating an
  existing one) — a straightforward follow-up once a specific client's
  merge semantics are defined.
- No production deployment tooling — this is the import engine only.

## Phase 17: real hands-on verification

Run against the running dev backend (not just unit tests) with a realistic
5-row `patients.csv` + 2-row `doctors.csv` sample (Filipino names, mixed
column shapes, `civil_status` intentionally omitted to mirror a common
legacy-export gap): Choose Source → Connect (real multipart upload) →
Analyze → suggested mappings applied → Validate (5 Patients rows flagged
Error for missing `civil_status`, 0 Doctors issues) → each issue resolved
to `CreateNew` → Preview (`rows_to_import: 5`) → Import → Verify. Final
verify report: `Patients expected=5/imported=5`, `Doctors expected=2/
imported=2`, `overall_ok: true`, confirmed independently via `GET
/patients` returning all 5 imported patients. This run is what surfaced
and confirmed the fix for BUG-001.
