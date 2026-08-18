"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { MasterDataPage } from "@/features/clinic-config/components/MasterDataPage";
import type { Doctor } from "@/features/clinic-config/types";
import { Role } from "@/types";

const MANAGE_ROLES = new Set<Role>([Role.Owner, Role.Administrator]);

/**
 * Doctor master-data list. `doctor_code` is server-generated (see
 * `DoctorCodeGenerator`) so it is shown read-only and excluded from the
 * create/edit form. Doctor weekly availability (`doctor_schedules`) is
 * managed via `GET/POST/PUT/DELETE /doctors/{id}/schedules` on the backend;
 * a dedicated schedule editor UI is a documented follow-up (see
 * docs/ROADMAP.md) - this page covers the doctor profile CRUD critical path.
 */
export default function DoctorsPage() {
  const { data: currentUser } = useCurrentUser();
  const canManage = Boolean(currentUser && MANAGE_ROLES.has(currentUser.role));

  return (
    <MasterDataPage<Doctor>
      title="Doctors"
      description="Doctor profiles: license numbers, specialization, department/branch assignment, and consultation fee."
      resourceKey="doctors"
      resourcePath="/doctors"
      canManage={canManage}
      searchPlaceholder="Search doctors"
      rowLabel={(d) => `Dr. ${d.first_name} ${d.last_name}`}
      renderRowActions={(d) => (
        <Button type="button" variant="ghost" size="sm" asChild>
          <Link href={`/doctors/${d.id}`}>E-Signature</Link>
        </Button>
      )}
      columns={[
        { header: "Code", render: (d) => d.doctor_code },
        { header: "Name", render: (d) => `${d.first_name} ${d.last_name}` },
        { header: "Specialization", render: (d) => d.specialization ?? "-" },
        { header: "Fee", render: (d) => d.consultation_fee ?? "-" },
        { header: "Status", render: (d) => d.status },
      ]}
      fields={[
        { name: "first_name", label: "First name", type: "text", required: true },
        { name: "middle_name", label: "Middle name", type: "text" },
        { name: "last_name", label: "Last name", type: "text", required: true },
        { name: "suffix", label: "Suffix", type: "text" },
        { name: "prc_license", label: "PRC license", type: "text" },
        { name: "ptr_number", label: "PTR number", type: "text" },
        { name: "specialization", label: "Specialization", type: "text" },
        { name: "contact_number", label: "Contact number", type: "text" },
        { name: "email", label: "Email", type: "text" },
        { name: "consultation_fee", label: "Consultation fee", type: "number" },
        {
          name: "status",
          label: "Status",
          type: "select",
          options: [
            { value: "Active", label: "Active" },
            { value: "Inactive", label: "Inactive" },
            { value: "On Leave", label: "On Leave" },
          ],
        },
      ]}
    />
  );
}
