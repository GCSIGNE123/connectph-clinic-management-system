"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { MasterDataPage } from "@/features/clinic-config/components/MasterDataPage";
import type { Medicine } from "@/features/clinic-config/types";
import { Role } from "@/types";

const MANAGE_ROLES = new Set<Role>([Role.Owner, Role.Administrator, Role.Receptionist]);

/**
 * Medicine Inventory Phase 1: catalog list. Batch/lot tracking (quantities,
 * expiry, status) lives on the dedicated `/medicines/{id}` detail page - a
 * one-to-many batch list doesn't fit this generic single-section modal, same
 * reasoning as the Doctor E-Signature detail page. No stock movement ledger
 * or dispensing UI yet (Phase 2/3+).
 */
export default function MedicinesPage() {
  const { data: currentUser } = useCurrentUser();
  const canManage = Boolean(currentUser && MANAGE_ROLES.has(currentUser.role));

  return (
    <MasterDataPage<Medicine>
      title="Medicines"
      description="Medicine catalog. Open a medicine to manage its stocked batches, quantities, and expiry dates."
      resourceKey="medicines"
      resourcePath="/medicines"
      canManage={canManage}
      searchPlaceholder="Search medicines"
      rowLabel={(m) => m.generic_name}
      renderRowActions={(m) => (
        <Button type="button" variant="ghost" size="sm" asChild>
          <Link href={`/medicines/${m.id}`}>Batches</Link>
        </Button>
      )}
      columns={[
        { header: "Generic Name", render: (m) => m.generic_name, sortable: true },
        { header: "Brand Name", render: (m) => m.brand_name ?? "-" },
        { header: "Strength", render: (m) => m.strength ?? "-" },
        { header: "Dosage Form", render: (m) => m.dosage_form ?? "-" },
        { header: "Unit", render: (m) => m.unit ?? "-" },
        { header: "Reorder Level", render: (m) => m.reorder_level ?? "-" },
        { header: "Status", render: (m) => (m.is_active ? "Active" : "Inactive") },
      ]}
      fields={[
        { name: "generic_name", label: "Generic name", type: "text", required: true },
        { name: "brand_name", label: "Brand name", type: "text" },
        { name: "strength", label: "Strength", type: "text", placeholder: "e.g. 500mg" },
        { name: "dosage_form", label: "Dosage form", type: "text", placeholder: "e.g. Tablet" },
        { name: "unit", label: "Unit", type: "text", placeholder: "e.g. tablet" },
        { name: "reorder_level", label: "Reorder level", type: "number" },
        { name: "is_active", label: "Active", type: "checkbox" },
      ]}
    />
  );
}
