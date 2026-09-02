"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { useEligibleMedTechs, useReleaseResults } from "@/features/laboratory/hooks/use-laboratory";
import { usePathologists } from "@/features/pathologists/hooks/use-pathologists";

/**
 * Round 6 (Laboratory Report Signatories): Pathologist selection happens
 * HERE, as part of the release workflow - never at print time (see the
 * feature's implementation report, section F). The selector only ever
 * lists ACTIVE pathologists (`usePathologists(true)`); selection is
 * optional (matching the existing "release doesn't require a pathologist"
 * business rule) - printing later shows a blank Pathologist block when
 * none was selected here, never a fabricated one.
 *
 * Client requirement (countersigning MedTech): a second, MANUALLY-signing
 * Med Technologist is also selected here, at release time, following the
 * identical optional/snapshot-at-release pattern as the Pathologist above
 * - only their name/license are captured (`useEligibleMedTechs` never
 * exposes a signature field at all), since this person always signs the
 * printed page by hand. The list is scoped to active Laboratory-role
 * Users only - the same role/authorization the backend endpoint enforces,
 * so a Pathologist/Doctor/Receptionist/etc. can never be selected. */
export function ReleaseResultsDialog({
  laboratoryOrderId,
  open,
  onOpenChange,
}: {
  laboratoryOrderId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [pathologistId, setPathologistId] = useState<string>("");
  const [countersigningMedTechId, setCountersigningMedTechId] = useState<string>("");
  const pathologistsQuery = usePathologists(true, { enabled: open });
  const medTechsQuery = useEligibleMedTechs({ enabled: open });
  const release = useReleaseResults();

  function handleClose(next: boolean) {
    if (!next) {
      setPathologistId("");
      setCountersigningMedTechId("");
    }
    onOpenChange(next);
  }

  function handleConfirm() {
    if (!laboratoryOrderId) return;
    release.mutate(
      { id: laboratoryOrderId, pathologistId: pathologistId || null, countersigningMedTechId: countersigningMedTechId || null },
      { onSuccess: () => handleClose(false) }
    );
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Release Results</DialogTitle>
        </DialogHeader>

        <div className="space-y-2 py-2">
          <label htmlFor="release-pathologist" className="text-sm font-medium">
            Pathologist (optional)
          </label>
          <Select
            id="release-pathologist"
            value={pathologistId}
            onChange={(e) => setPathologistId(e.target.value)}
            disabled={pathologistsQuery.isLoading}
          >
            <option value="">None selected</option>
            {(pathologistsQuery.data ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
          <p className="text-xs text-muted-foreground">
            The Med Tech In Charge is recorded automatically as you (the releasing user).
          </p>
        </div>

        <div className="space-y-2 py-2">
          <label htmlFor="release-countersigning-med-tech" className="text-sm font-medium">
            Countersigning Med Technologist (optional)
          </label>
          <Select
            id="release-countersigning-med-tech"
            value={countersigningMedTechId}
            onChange={(e) => setCountersigningMedTechId(e.target.value)}
            disabled={medTechsQuery.isLoading}
          >
            <option value="">None selected</option>
            {(medTechsQuery.data ?? []).map((mt) => (
              <option key={mt.id} value={mt.id}>
                {mt.fullName}
              </option>
            ))}
          </Select>
          <p className="text-xs text-muted-foreground">
            Both Med Technologists sign the printed report by hand - no e-signature is captured for either.
          </p>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => handleClose(false)} disabled={release.isPending}>
            Cancel
          </Button>
          <Button type="button" onClick={handleConfirm} isLoading={release.isPending}>
            Release
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
