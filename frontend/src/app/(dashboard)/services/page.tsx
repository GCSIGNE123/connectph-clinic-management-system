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
    />
  );
}
