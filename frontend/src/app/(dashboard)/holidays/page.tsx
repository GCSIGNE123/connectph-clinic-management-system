"use client";

import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { MasterDataPage } from "@/features/clinic-config/components/MasterDataPage";
import type { Holiday } from "@/features/clinic-config/types";
import { Role } from "@/types";

const MANAGE_ROLES = new Set<Role>([Role.Owner, Role.Administrator]);

export default function HolidaysPage() {
  const { data: currentUser } = useCurrentUser();
  const canManage = Boolean(currentUser && MANAGE_ROLES.has(currentUser.role));

  return (
    <MasterDataPage<Holiday>
      title="Holiday Calendar"
      description="Clinic-wide or branch-specific closures and half-days. `branch_id` left blank applies clinic-wide."
      resourceKey="holidays"
      resourcePath="/holidays"
      canManage={canManage}
      searchPlaceholder="Search holidays"
      rowLabel={(h) => h.holiday_name}
      columns={[
        { header: "Name", render: (h) => h.holiday_name },
        { header: "Date", render: (h) => h.date },
        { header: "Recurring", render: (h) => (h.is_recurring ? "Yes" : "No") },
        { header: "Closed", render: (h) => (h.is_closed ? "Yes" : "No") },
        { header: "Half day", render: (h) => (h.is_half_day ? "Yes" : "No") },
      ]}
      fields={[
        { name: "holiday_name", label: "Holiday name", type: "text", required: true },
        { name: "date", label: "Date", type: "date", required: true },
        { name: "is_recurring", label: "Recurs yearly", type: "checkbox" },
        { name: "is_closed", label: "Clinic closed", type: "checkbox" },
        { name: "is_half_day", label: "Half day", type: "checkbox" },
      ]}
    />
  );
}
