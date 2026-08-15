"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useAdministerVaccination } from "@/features/vaccinations/hooks/use-vaccinations";
import type { VaccinationAdministration } from "@/features/vaccinations/types";

export function AdministerVaccinationDialog({
  open,
  onOpenChange,
  vaccination,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  vaccination: VaccinationAdministration | null;
}) {
  const [vaccineName, setVaccineName] = useState("");
  const [dose, setDose] = useState("");
  const [lotNumber, setLotNumber] = useState("");
  const [site, setSite] = useState("");
  const [route, setRoute] = useState("");
  const [notes, setNotes] = useState("");
  const administer = useAdministerVaccination();

  function reset() {
    setVaccineName("");
    setDose("");
    setLotNumber("");
    setSite("");
    setRoute("");
    setNotes("");
  }

  async function handleSubmit() {
    if (!vaccination) return;
    await administer.mutateAsync({
      id: vaccination.id,
      payload: { vaccineName: vaccineName || undefined, dose, lotNumber, site, route, notes },
    });
    reset();
    onOpenChange(false);
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Administer vaccination</DialogTitle>
        </DialogHeader>

        {vaccination ? (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Patient: <span className="font-medium text-foreground">{vaccination.patientName ?? "-"}</span>
            </p>
            <p className="text-sm text-muted-foreground">
              Ordered: <span className="font-medium text-foreground">{vaccination.vaccineName}</span>
            </p>

            <div>
              <Label>Vaccine given (leave blank to confirm as ordered)</Label>
              <Input value={vaccineName} onChange={(e) => setVaccineName(e.target.value)} placeholder={vaccination.vaccineName} />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Dose</Label>
                <Input value={dose} onChange={(e) => setDose(e.target.value)} placeholder="e.g. 0.5 mL" />
              </div>
              <div>
                <Label>Lot number</Label>
                <Input value={lotNumber} onChange={(e) => setLotNumber(e.target.value)} />
              </div>
              <div>
                <Label>Site</Label>
                <Input value={site} onChange={(e) => setSite(e.target.value)} placeholder="e.g. Left Deltoid" />
              </div>
              <div>
                <Label>Route</Label>
                <Input value={route} onChange={(e) => setRoute(e.target.value)} placeholder="e.g. Intramuscular" />
              </div>
            </div>

            <div>
              <Label>Notes</Label>
              <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Any observations (e.g. adverse reaction)" />
            </div>
          </div>
        ) : null}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" onClick={handleSubmit} disabled={administer.isPending}>
            {administer.isPending ? "Recording..." : "Mark as administered"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
