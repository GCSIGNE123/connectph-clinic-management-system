"use client";

import { MoreHorizontal } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Avatar } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SkeletonList } from "@/components/layout/LoadingSkeletons";
import { EmptyState } from "@/components/layout/EmptyState";
import { PatientStatus } from "@/features/patients/types";
import type { PatientListItem } from "@/features/patients/types";
import { formatDate } from "@/lib/utils";

export interface PatientsTableProps {
  patients: PatientListItem[];
  isLoading?: boolean;
  onView: (patient: PatientListItem) => void;
  onEdit: (patient: PatientListItem) => void;
  onArchive: (patient: PatientListItem) => void;
  onRestore: (patient: PatientListItem) => void;
  canManage: boolean;
  canArchive: boolean;
  emptyMessage?: string;
}

const STATUS_BADGE: Record<PatientStatus, { label: string; variant: "success" | "secondary" }> = {
  [PatientStatus.Active]: { label: "Active", variant: "success" },
  [PatientStatus.Archived]: { label: "Archived", variant: "secondary" },
};

/** Computes age in whole years from an ISO birth-date string. */
export function computeAge(birthDate: string): number {
  const dob = new Date(birthDate);
  const today = new Date();
  let age = today.getFullYear() - dob.getFullYear();
  const monthDiff = today.getMonth() - dob.getMonth();
  if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < dob.getDate())) {
    age -= 1;
  }
  return age;
}

function fullName(p: PatientListItem): string {
  return [p.firstName, p.middleName, p.lastName, p.suffix].filter(Boolean).join(" ");
}

/**
 * Paginated patient directory table with row actions (view/edit/archive/
 * restore). Search, filters, sorting, and pagination controls live in the
 * parent page.
 */
export function PatientsTable({
  patients,
  isLoading,
  onView,
  onEdit,
  onArchive,
  onRestore,
  canManage,
  canArchive,
  emptyMessage,
}: PatientsTableProps) {
  if (isLoading) {
    return <SkeletonList rows={6} />;
  }

  if (patients.length === 0) {
    return (
      <EmptyState
        title="No patients found"
        description={emptyMessage ?? "Try adjusting your search or filters, or add a new patient."}
      />
    );
  }

  return (
    <div className="rounded-lg border border-border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-12">Photo</TableHead>
            <TableHead>Patient Number</TableHead>
            <TableHead>Name</TableHead>
            <TableHead>Age</TableHead>
            <TableHead>Gender</TableHead>
            <TableHead>Mobile</TableHead>
            <TableHead>Last Visit</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {patients.map((patient) => {
            const status = STATUS_BADGE[patient.status];
            const name = fullName(patient);

            return (
              <TableRow key={patient.id} className="cursor-pointer" onClick={() => onView(patient)}>
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <Avatar name={name} src={patient.photoUrl} size="sm" />
                </TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">
                  {patient.patientNumber}
                </TableCell>
                <TableCell className="font-medium text-foreground">{name}</TableCell>
                <TableCell className="text-muted-foreground">{computeAge(patient.birthDate)}</TableCell>
                <TableCell className="text-muted-foreground">{patient.gender}</TableCell>
                <TableCell className="text-muted-foreground">{patient.mobileNumber}</TableCell>
                <TableCell className="text-muted-foreground">
                  {patient.lastVisit ? formatDate(patient.lastVisit) : "—"}
                </TableCell>
                <TableCell>
                  <Badge variant={status.variant}>{status.label}</Badge>
                </TableCell>
                <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                  <DropdownMenu>
                    <DropdownMenuTrigger>
                      <Button type="button" variant="ghost" size="icon" aria-label="Row actions">
                        <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent>
                      <DropdownMenuItem onClick={() => onView(patient)}>View profile</DropdownMenuItem>
                      {canManage ? (
                        <DropdownMenuItem onClick={() => onEdit(patient)}>Edit</DropdownMenuItem>
                      ) : null}
                      {canArchive ? (
                        patient.status === PatientStatus.Active ? (
                          <DropdownMenuItem destructive onClick={() => onArchive(patient)}>
                            Archive
                          </DropdownMenuItem>
                        ) : (
                          <DropdownMenuItem onClick={() => onRestore(patient)}>Restore</DropdownMenuItem>
                        )
                      ) : null}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
