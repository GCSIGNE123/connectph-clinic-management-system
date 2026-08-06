"use client";

import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { MasterDataPage } from "@/features/clinic-config/components/MasterDataPage";
import type { ConsultationRoom } from "@/features/clinic-config/types";
import { Role } from "@/types";

const MANAGE_ROLES = new Set<Role>([Role.Owner, Role.Administrator]);

export default function ConsultationRoomsPage() {
  const { data: currentUser } = useCurrentUser();
  const canManage = Boolean(currentUser && MANAGE_ROLES.has(currentUser.role));

  return (
    <MasterDataPage<ConsultationRoom>
      title="Consultation Rooms"
      description="Physical rooms used for consultations, assignable to a department and branch."
      resourceKey="consultation-rooms"
      resourcePath="/consultation-rooms"
      canManage={canManage}
      searchPlaceholder="Search rooms"
      rowLabel={(r) => r.room_name}
      columns={[
        { header: "Room", render: (r) => r.room_name },
        { header: "Number", render: (r) => r.room_number ?? "-" },
        { header: "Status", render: (r) => r.status },
      ]}
      fields={[
        { name: "room_name", label: "Room name", type: "text", required: true },
        { name: "room_number", label: "Room number", type: "text" },
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
