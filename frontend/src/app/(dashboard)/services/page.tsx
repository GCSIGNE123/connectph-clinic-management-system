"use client";

import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { MasterDataPage } from "@/features/clinic-config/components/MasterDataPage";
import type { ClinicServiceItem } from "@/features/clinic-config/types";
import { Role } from "@/types";

const MANAGE_ROLES = new Set<Role>([Role.Owner, Role.Administrator]);

export default function ServicesPage() {
  const { data: currentUser } = useCurrentUser();
  const canManage = Boolean(currentUser && MANAGE_ROLES.has(currentUser.role));

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
        { header: "Code", render: (s) => s.service_code },
        { header: "Name", render: (s) => s.service_name },
        { header: "Price", render: (s) => s.default_price },
        { header: "Duration (min)", render: (s) => s.duration_minutes ?? "-" },
        { header: "Status", render: (s) => s.status },
      ]}
      fields={[
        { name: "service_code", label: "Code", type: "text", required: true },
        { name: "service_name", label: "Name", type: "text", required: true },
        { name: "description", label: "Description", type: "textarea" },
        { name: "default_price", label: "Default price", type: "number", required: true },
        { name: "duration_minutes", label: "Duration (minutes)", type: "number" },
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
        headers: ["service_code", "service_name", "description", "default_price", "duration_minutes", "status"],
        toRow: (s) => [s.service_code, s.service_name, s.description ?? "", s.default_price, s.duration_minutes ?? "", s.status],
        matchKey: "service_code",
        fromRow: (row) => {
          if (!row.service_code?.trim()) throw new Error("service_code is required.");
          if (!row.service_name?.trim()) throw new Error("service_name is required.");
          const price = Number(row.default_price);
          if (row.default_price?.trim() && Number.isNaN(price)) {
            throw new Error(`default_price "${row.default_price}" is not a number.`);
          }
          const duration = row.duration_minutes?.trim() ? Number(row.duration_minutes) : null;
          if (duration !== null && Number.isNaN(duration)) {
            throw new Error(`duration_minutes "${row.duration_minutes}" is not a number.`);
          }
          const status = row.status?.trim() || "Active";
          if (status !== "Active" && status !== "Inactive") {
            throw new Error(`status "${row.status}" must be "Active" or "Inactive".`);
          }
          return {
            service_code: row.service_code.trim(),
            service_name: row.service_name.trim(),
            description: row.description?.trim() || undefined,
            default_price: row.default_price?.trim() || "0",
            duration_minutes: duration,
            status,
          } as Partial<ClinicServiceItem>;
        },
      }}
    />
  );
}
