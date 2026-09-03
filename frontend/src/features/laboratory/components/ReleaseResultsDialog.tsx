"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { useEligibleMedTechs, useReleaseResults } from "@/features/laboratory/hooks/use-laboratory";
import { usePathologists } from "@/features/pathologists/hooks/use-pathologists";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";

/**
 * Round 6 (Laboratory Report Signatories): Pathologist selection happens
 * HERE, as part of the release workflow - never at print time. Product
 * decision update: Pathologist selection is now MANDATORY - a Laboratory
 * result must not be finalized without one on record (superseding the
 * original "deliberately optional" Round 6 decision, section F). The
 * selector only ever lists ACTIVE pathologists (`usePathologists(true)`);
 * an empty selection blocks release client-side (see `formError` below)
 * AND is rejected server-side regardless (`LaboratoryReleaseRequest.
 * pathologist_id` is a required field - see `release_results()`), so a
 * request bypassing this dialog entirely still cannot omit it. No default/
 * first-available pathologist is ever auto-selected - the user must
 * actively choose one.
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
  const [formError, setFormError] = useState<string | null>(null);
  const pathologistsQuery = usePathologists(true, { enabled: open });
  const medTechsQuery = useEligibleMedTechs({ enabled: open });
  const currentUserQuery = useCurrentUser();
  const release = useReleaseResults();

  // Client requirement: the Countersigning MedTech must never be the same
  // person as the Med Tech In Charge - who IS the releasing user (see the
  // "recorded automatically as you" copy below; there's no separate
  // selector for who they are). Excluded by ID, never by displayed name,
  // so two Laboratory users who happen to share a name are never confused
  // with each other. The backend enforces this same rule independently in
  // `release_results()` - this is a UX convenience, not the source of
  // truth, since a request bypassing this dialog entirely must still be
  // rejected server-side.
  const currentUserId = currentUserQuery.data?.id;
  const eligibleCountersigners = (medTechsQuery.data ?? []).filter((mt) => mt.id !== currentUserId);

  function handleClose(next: boolean) {
    if (!next) {
      setPathologistId("");
      setCountersigningMedTechId("");
      setFormError(null);
    }
    onOpenChange(next);
  }

  function handleConfirm() {
    if (!laboratoryOrderId) return;
    // Pathologist is mandatory - block the request client-side with the
    // same inline-error pattern used elsewhere in this codebase for a
    // plain (non-react-hook-form) dialog's required-field validation (see
    // e.g. `NewAppointmentDialog`'s `formError`). Not merely a UX nicety:
    // the backend independently rejects a request missing this field
    // regardless (`LaboratoryReleaseRequest.pathologist_id` is required),
    // so this only prevents a doomed round-trip, never substitutes for it.
    if (!pathologistId) {
      setFormError("Select a Pathologist before releasing results.");
      return;
    }
    setFormError(null);
    release.mutate(
      { id: laboratoryOrderId, pathologistId, countersigningMedTechId: countersigningMedTechId || null },
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
            Pathologist (required)
          </label>
          <Select
            id="release-pathologist"
            value={pathologistId}
            onChange={(e) => {
              setPathologistId(e.target.value);
              if (e.target.value) setFormError(null);
            }}
            disabled={pathologistsQuery.isLoading}
            invalid={Boolean(formError)}
          >
            {/* "None selected" stays the pre-selected default - never the
                first real pathologist in the list - so nothing is ever
                auto-assigned; the user must actively pick one. */}
            <option value="">None selected</option>
            {(pathologistsQuery.data ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
          {formError ? <p className="text-xs text-destructive">{formError}</p> : null}
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
            disabled={medTechsQuery.isLoading || eligibleCountersigners.length === 0}
          >
            <option value="">None selected</option>
            {eligibleCountersigners.map((mt) => (
              <option key={mt.id} value={mt.id}>
                {mt.fullName}
              </option>
            ))}
          </Select>
          <p className="text-xs text-muted-foreground">
            Both Med Technologists sign the printed report by hand - no e-signature is captured for either.
          </p>
          {/* The Med Tech In Charge (you) is never offered here - they
              can't countersign their own release. When they're also the
              only eligible Laboratory user, that leaves nothing else to
              select from, so say so explicitly rather than showing an
              empty-looking dropdown with no explanation. */}
          {!medTechsQuery.isLoading && eligibleCountersigners.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              No other eligible Med Technologist is available to countersign.
            </p>
          ) : null}
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
