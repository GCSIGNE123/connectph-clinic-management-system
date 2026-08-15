"use client";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import type { DuplicateCandidate } from "@/features/patients/types";
import { formatDate } from "@/lib/utils";

export interface DuplicateWarningDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  duplicates: DuplicateCandidate[];
  /** Whether the current user is allowed to bypass the warning (Owner/Administrator only). */
  canOverride: boolean;
  isSaving?: boolean;
  onConfirmAnyway: () => void;
}

/**
 * Shown when the backend flags likely duplicate patients on create/edit.
 * Lists the conflicting record(s) and, for Owner/Administrator users only,
 * offers an "Add anyway" override that resubmits with `override=true`.
 */
export function DuplicateWarningDialog({
  open,
  onOpenChange,
  duplicates,
  canOverride,
  isSaving,
  onConfirmAnyway,
}: DuplicateWarningDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" onClose={() => onOpenChange(false)}>
        <DialogHeader>
          <DialogTitle>Possible duplicate patient</DialogTitle>
          <DialogDescription>
            We found existing patient record(s) that closely match the details you entered.
          </DialogDescription>
        </DialogHeader>

        <ul className="space-y-2">
          {duplicates.map((dup) => (
            <li key={dup.id} className="rounded-md border border-border p-3 text-sm">
              <p className="font-medium text-foreground">
                {dup.fullName}{" "}
                <span className="font-mono text-xs text-muted-foreground">({dup.patientNumber})</span>
              </p>
              <p className="text-muted-foreground">
                DOB: {formatDate(dup.birthDate)} · Mobile: {dup.mobileNumber}
              </p>
              <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">{dup.matchReason}</p>
            </li>
          ))}
        </ul>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          {canOverride ? (
            <Button type="button" variant="destructive" isLoading={isSaving} onClick={onConfirmAnyway}>
              Add anyway
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
