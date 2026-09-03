"use client";

import { useQuery } from "@tanstack/react-query";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { MasterDataPage } from "@/features/clinic-config/components/MasterDataPage";
import { createCrudApi } from "@/features/clinic-config/api/crud-factory";
import type { ClinicServiceItem, Department } from "@/features/clinic-config/types";
import { parseCsvNumber } from "@/lib/csv";
import { Role } from "@/types";

const MANAGE_ROLES = new Set<Role>([Role.Owner, Role.Administrator]);

const departmentsApi = createCrudApi<Department>("/departments");

// Reused by both the CSV export/import and the admin table's Department
// column - matches CSV rows and existing services to a department by NAME
// rather than raw id, per the "reuse existing department identifiers/names"
// requirement (department_code would also work, but name is what a clinic
// admin actually recognizes on an export).
const UNASSIGNED_LABEL = "Unassigned";

export default function ServicesPage() {
  const { data: currentUser } = useCurrentUser();
  const canManage = Boolean(currentUser && MANAGE_ROLES.has(currentUser.role));

  // Departments are fetched here (not baked into a static `fields` array)
  // so the Department selector's options reflect the clinic's real,
  // currently-active department list - no hard-coded mapping, no schema
  // change, just a dynamic `options` array on an existing `select` field.
  const departments = useQuery({
    queryKey: ["services-page", "departments"],
    queryFn: () => departmentsApi.list({ status: "Active", limit: 100 }),
  });
  const departmentItems = departments.data?.items ?? [];

  function departmentName(departmentId: string | null | undefined): string {
    if (!departmentId) return UNASSIGNED_LABEL;
    return departmentItems.find((d) => d.id === departmentId)?.name ?? "Unknown department";
  }

  function departmentIdByName(name: string | undefined): string | null {
    const trimmed = name?.trim();
    if (!trimmed || trimmed.toLowerCase() === UNASSIGNED_LABEL.toLowerCase()) return null;
    const match = departmentItems.find((d) => d.name.toLowerCase() === trimmed.toLowerCase());
    if (!match) throw new Error(`Department "${trimmed}" was not found.`);
    return match.id;
  }

  return (
    <MasterDataPage<ClinicServiceItem>
      title="Services"
      description="The billable/consultable service catalog consumed by future Billing, Queue, and Appointments modules."
      resourceKey="services"
      resourcePath="/services"
      canManage={canManage}
      searchPlaceholder="Search services"
      rowLabel={(s) => s.service_name}
      columns={[
        { header: "Code", render: (s) => s.service_code, sortable: true },
        { header: "Name", render: (s) => s.service_name, sortable: true },
        { header: "Price", render: (s) => s.default_price, sortable: true, sortValue: (s) => Number(s.default_price) },
        { header: "Duration (min)", render: (s) => s.duration_minutes ?? "-" },
        // Unassigned services (the current state of all 442 existing Canora
        // services - see the investigation this feature was approved from)
        // must clearly read as "Unassigned", not a blank cell.
        { header: "Department", render: (s) => departmentName(s.department_id), sortable: true },
        { header: "Status", render: (s) => s.status, sortable: true },
      ]}
      fields={[
        { name: "service_code", label: "Code", type: "text", required: true },
        { name: "service_name", label: "Name", type: "text", required: true },
        { name: "description", label: "Description", type: "textarea" },
        { name: "default_price", label: "Default price", type: "number", required: true },
        { name: "duration_minutes", label: "Duration (minutes)", type: "number" },
        {
          name: "department_id",
          label: "Department",
          type: "select",
          // No default is invented here - "" (unassigned/NULL) is always the
          // first, pre-selected option, matching every existing service's
          // current (unset) state. `nullable` makes editing a previously-
          // assigned service back to "" actually clear it on the backend
          // (see `FieldConfig.nullable`'s doc comment).
          nullable: true,
          options: [
            { value: "", label: UNASSIGNED_LABEL },
            ...departmentItems.map((d) => ({ value: d.id, label: d.name })),
          ],
        },
        {
          name: "status",
          label: "Status",
          type: "select",
          options: [
            { value: "Active", label: "Active" },
            { value: "Inactive", label: "Inactive" },
          ],
        },
      ]}
      csv={{
        filename: "services.csv",
        headers: ["service_code", "service_name", "description", "default_price", "duration_minutes", "department", "status"],
        toRow: (s) => [
          s.service_code,
          s.service_name,
          s.description ?? "",
          s.default_price,
          s.duration_minutes ?? "",
          departmentName(s.department_id),
          s.status,
        ],
        matchKey: "service_code",
        fromRow: (row) => {
          if (!row.service_code?.trim()) throw new Error("service_code is required.");
          if (!row.service_name?.trim()) throw new Error("service_name is required.");
          // parseCsvNumber tolerates thousands-separator commas/currency
          // symbols (e.g. "1,200.00", "₱ 300") - a common real-world Excel
          // export format that plain Number() rejects outright.
          const price = parseCsvNumber(row.default_price);
          if (row.default_price?.trim() && Number.isNaN(price)) {
            throw new Error(`default_price "${row.default_price}" is not a number.`);
          }
          const duration = parseCsvNumber(row.duration_minutes);
          if (Number.isNaN(duration)) {
            throw new Error(`duration_minutes "${row.duration_minutes}" is not a number.`);
          }
          const status = row.status?.trim() || "Active";
          if (status !== "Active" && status !== "Inactive") {
            throw new Error(`status "${row.status}" must be "Active" or "Inactive".`);
          }
          // "department" column is optional and backward-compatible - a CSV
          // exported before this feature existed simply won't have the
          // column, `row.department` is then undefined, and the row is
          // treated as unassigned (department_id: null), same as any
          // existing service today.
          const departmentId = departmentIdByName(row.department);
          return {
            service_code: row.service_code.trim(),
            service_name: row.service_name.trim(),
            description: row.description?.trim() || undefined,
            default_price: String(price ?? 0),
            duration_minutes: duration,
            department_id: departmentId,
            status,
          } as Partial<ClinicServiceItem>;
        },
      }}
    />
  );
}
