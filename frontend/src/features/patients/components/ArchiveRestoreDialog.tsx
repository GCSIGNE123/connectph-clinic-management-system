"use client";

import { AlertDialog } from "@/components/ui/alert-dialog";
import { useArchivePatient, useRestorePatient } from "@/features/patients/hooks/use-patient-mutations";
import type { PatientListItem } from "@/features/patients/types";

export interface ArchiveRestoreDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  patient: PatientListItem | null;
  action: "archive" | "restore" | null;
}

/** Confirms the archive/restore actions before they're sent to the API. */
export function ArchiveRestoreDialog({ open, onOpenChange, patient, action }: ArchiveRestoreDialogProps) {
  const archivePatient = useArchivePatient();
  const restorePatient = useRestorePatient();

  if (!patient || !action) return null;

  const isArchive = action === "archive";
  const mutation = isArchive ? archivePatient : restorePatient;
  const fullName = [patient.firstName, patient.middleName, patient.lastName].filter(Boolean).join(" ");

  return (
    <AlertDialog
      open={open}
      onOpenChange={onOpenChange}
      title={isArchive ? "Archive this patient?" : "Restore this patient?"}
      description={
        isArchive
          ? `${fullName} will be moved out of the active patient list. This does not delete their record.`
          : `${fullName} will reappear in the active patient list.`
      }
      confirmLabel={isArchive ? "Archive" : "Restore"}
      confirmVariant={isArchive ? "destructive" : "default"}
      isConfirming={mutation.isPending}
      onConfirm={() => {
        mutation.mutate(patient.id, { onSuccess: () => onOpenChange(false) });
      }}
    />
  );
}
