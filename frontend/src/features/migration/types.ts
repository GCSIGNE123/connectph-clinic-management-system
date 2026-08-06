export type MigrationSourceType = "SQLite" | "Access" | "SQLServer" | "MySQL" | "PostgreSQL" | "CSV" | "Excel";

export type MigrationBatchStatus =
  | "Draft" | "Connected" | "Analyzed" | "Previewed" | "Validated" | "Importing"
  | "Completed" | "Failed" | "PartiallyCompleted" | "Cancelled";

export type MigrationEntityType =
  | "Clinic" | "Branches" | "Departments" | "Doctors" | "Users" | "Patients" | "Services"
  | "Visits" | "QueueHistory" | "Consultations" | "Diagnoses" | "Prescriptions" | "Laboratory"
  | "Billing" | "Payments" | "Attachments" | "AuditLogs";

export const IMPLEMENTED_ENTITY_TYPES: MigrationEntityType[] = ["Patients", "Doctors"];

export interface MigrationBatch {
  id: string;
  clinic_id: string;
  source_type: MigrationSourceType;
  source_description: string | null;
  status: MigrationBatchStatus;
  started_at: string | null;
  completed_at: string | null;
  total_records_found: number | null;
  total_records_imported: number;
  total_duplicates: number;
  total_warnings: number;
  total_errors: number;
  current_entity: MigrationEntityType | null;
  created_at: string;
}

export interface MigrationEntityProgress {
  entity_type: MigrationEntityType;
  status: "Pending" | "InProgress" | "Completed" | "Failed" | "Skipped";
  records_found: number;
  records_imported: number;
  records_skipped: number;
  records_failed: number;
  last_processed_offset: number;
}

export interface MigrationStatusResponse {
  batch: MigrationBatch;
  entities: MigrationEntityProgress[];
  elapsed_seconds: number | null;
  estimated_seconds_remaining: number | null;
}

export interface MigrationFieldMapping {
  id: string;
  entity_type: MigrationEntityType;
  source_field: string;
  destination_field: string | null;
  transform_type: "None" | "Rename" | "DateFormat" | "PhoneFormat" | "Trim" | "Custom";
  transform_config: Record<string, unknown> | null;
  is_ignored: boolean;
}

export interface MigrationMappingSuggestion {
  source_field: string;
  destination_field: string | null;
  is_ignored: boolean;
}

export interface MigrationValidationIssue {
  id: string;
  entity_type: MigrationEntityType;
  source_row_identifier: string;
  issue_type: string;
  severity: "Warning" | "Error";
  message: string;
  resolution: "Unresolved" | "Skip" | "Merge" | "Overwrite" | "CreateNew" | null;
}

export interface MigrationPreview {
  entity_type: MigrationEntityType;
  rows_to_import: number;
  rows_to_skip: number;
  warnings: number;
  errors: number;
}

export interface MigrationVerificationReport {
  batch_id: string;
  generated_at: string;
  entities: { entity_type: MigrationEntityType; expected: number; imported: number; matches: boolean }[];
  relationship_issues: string[];
  overall_ok: boolean;
}

export interface MigrationLogEntry {
  log_level: "Info" | "Warning" | "Error";
  entity_type: MigrationEntityType | null;
  message: string;
  details: Record<string, unknown> | null;
  logged_at: string;
}
