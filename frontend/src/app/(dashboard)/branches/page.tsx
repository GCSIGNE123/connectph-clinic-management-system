"use client";

import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { MasterDataPage } from "@/features/clinic-config/components/MasterDataPage";
import type { Branch } from "@/features/clinic-config/types";
import { Role } from "@/types";

const MANAGE_ROLES = new Set<Role>([Role.Owner, Role.Administrator]);

export default function BranchesPage() {
  const { data: currentUser } = useCurrentUser();
  const canManage = Boolean(currentUser && MANAGE_ROLES.has(currentUser.role));

  return (
    <MasterDataPage<Branch>
      title="Branches"
      description="Physical clinic locations. Each branch can have its own manager, operating hours, and queue settings."
      resourceKey="branches"
      resourcePath="/branches"
      canManage={canManage}
      searchPlaceholder="Search branches"
      rowLabel={(b) => b.name}
      columns={[
        { header: "Name", render: (b) => b.name },
        { header: "Code", render: (b) => b.code ?? "-" },
        { header: "Contact", render: (b) => b.contact_number ?? b.phone ?? "-" },
        { header: "Status", render: (b) => b.status },
      ]}
      fields={[
        { name: "name", label: "Branch name", type: "text", required: true },
        { name: "code", label: "Code", type: "text" },
        { name: "address", label: "Address", type: "textarea" },
        { name: "contact_number", label: "Contact number", type: "text" },
        { name: "email", label: "Email", type: "text" },
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
