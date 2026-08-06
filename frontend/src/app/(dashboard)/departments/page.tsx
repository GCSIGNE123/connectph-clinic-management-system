"use client";

import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { MasterDataPage } from "@/features/clinic-config/components/MasterDataPage";
import type { Department } from "@/features/clinic-config/types";
import { Role } from "@/types";

const MANAGE_ROLES = new Set<Role>([Role.Owner, Role.Administrator]);

export default function DepartmentsPage() {
  const { data: currentUser } = useCurrentUser();
  const canManage = Boolean(currentUser && MANAGE_ROLES.has(currentUser.role));

  return (
    <MasterDataPage<Department>
      title="Departments"
      description="Clinical sections used to organize doctors, rooms, and services (e.g. Pediatrics, Dental, Laboratory)."
      resourceKey="departments"
      resourcePath="/departments"
      canManage={canManage}
      searchPlaceholder="Search departments"
      rowLabel={(d) => d.name}
      columns={[
        { header: "Code", render: (d) => d.department_code },
        { header: "Name", render: (d) => d.name },
        { header: "Status", render: (d) => d.status },
      ]}
      fields={[
        { name: "department_code", label: "Code", type: "text", required: true },
        { name: "name", label: "Name", type: "text", required: true },
        { name: "description", label: "Description", type: "textarea" },
        { name: "color", label: "Color (hex)", type: "color" },
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
