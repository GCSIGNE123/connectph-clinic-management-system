"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { MasterDataPage } from "@/features/clinic-config/components/MasterDataPage";
import type { Pathologist } from "@/features/pathologists/types";
import { Role } from "@/types";

const MANAGE_ROLES = new Set<Role>([Role.Owner, Role.Administrator]);

/**
 * Pathologist master-data list (Round 6: Laboratory Report Signatories).
 * Mirrors the Doctors page's shape exactly - same shared `MasterDataPage`,
 * same "E-Signature" per-row link to a dedicated detail page - since a
 * Pathologist is configured the same way a Doctor is: name/license number/
 * active state here, signature on its own detail page.
 */
export default function PathologistsPage() {
  const { data: currentUser } = useCurrentUser();
  const canManage = Boolean(currentUser && MANAGE_ROLES.has(currentUser.role));

  return (
    <MasterDataPage<Pathologist>
      title="Pathologists"
      description="Pathologists selectable as a Laboratory Report signatory at result release time."
      resourceKey="pathologists"
      resourcePath="/pathologists"
      canManage={canManage}
      searchPlaceholder="Search pathologists"
      rowLabel={(p) => p.name}
      renderRowActions={(p) => (
        <Button type="button" variant="ghost" size="sm" asChild>
          <Link href={`/pathologists/${p.id}`}>E-Signature</Link>
        </Button>
      )}
      columns={[
        { header: "Name", render: (p) => p.name },
        { header: "License No.", render: (p) => p.license_number ?? "-" },
        { header: "Active", render: (p) => (p.is_active ? "Yes" : "No") },
      ]}
      fields={[
        { name: "name", label: "Name", type: "text", required: true },
        { name: "license_number", label: "License number", type: "text" },
        { name: "is_active", label: "Active", type: "checkbox" },
      ]}
    />
  );
}
