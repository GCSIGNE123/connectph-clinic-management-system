"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/layout/EmptyState";
import { SkeletonList } from "@/components/layout/LoadingSkeletons";
import { apiClient } from "@/lib/api-client";
import { useCreatePrescription, usePrescriptionsForConsultation } from "@/features/clinical-orders/hooks/use-clinical-orders";
import { COMMON_MEDICINES, validatePrescriptionItems, type Prescription, type PrescriptionItemInput } from "@/features/clinical-orders/types";
import { PrintableDocumentDialog } from "@/features/clinical-orders/components/PrintableDocumentDialog";
import type { ClinicSettings } from "@/features/clinic-config/types";

function emptyItem(): PrescriptionItemInput {
  return { medicine: "", dosage: "", frequency: "", duration: "", quantity: "", route: "", instructions: "", substitutionAllowed: true };
}

export function PrescriptionTab({
  consultationId,
  visitId,
  patientId,
  canEdit,
  patientName,
  patientAge,
  doctorName,
  visitNumber,
}: {
  consultationId: string;
  visitId: string;
  patientId?: string | null;
  canEdit: boolean;
  patientName?: string | null;
  patientAge?: number | null;
  doctorName?: string | null;
  visitNumber?: string | null;
}) {
  const prescriptionsQuery = usePrescriptionsForConsultation(consultationId);
  const createPrescription = useCreatePrescription(consultationId, visitId, patientId);
  // Item 8 (Round 3): clinic name/logo/address for the prescription-pad
  // header. Reuses the existing GET /clinic-settings (Phase 4) - view is
  // available to any authenticated clinic role, so a Doctor can load this
  // without new permissions. No new upload infra: the "template" is this
  // formatted layout using existing Clinic.name/logo_url/address fields.
  const clinicQuery = useQuery({
    queryKey: ["clinic-settings"],
    queryFn: () => apiClient.get<ClinicSettings>("/clinic-settings"),
    staleTime: 5 * 60 * 1000,
  });
  const clinic = clinicQuery.data;

  const [items, setItems] = useState<PrescriptionItemInput[]>([emptyItem()]);
  const [activeSuggestionRow, setActiveSuggestionRow] = useState<number | null>(null);
  const [printRx, setPrintRx] = useState<Prescription | null>(null);

  const liveWarnings = useMemo(() => validatePrescriptionItems(items.filter((i) => i.medicine.trim())), [items]);

  if (prescriptionsQuery.isLoading) return <SkeletonList rows={4} />;

  const updateItem = (index: number, patch: Partial<PrescriptionItemInput>) => {
    setItems((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  };

  const addRow = () => setItems((rows) => [...rows, emptyItem()]);
  const removeRow = (index: number) => setItems((rows) => rows.filter((_, i) => i !== index));

  const submit = () => {
    const validItems = items.filter((i) => i.medicine.trim());
    if (validItems.length === 0) return;
    createPrescription.mutate(validItems, { onSuccess: () => setItems([emptyItem()]) });
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader><CardTitle>Prescriptions</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          {prescriptionsQuery.data && prescriptionsQuery.data.length > 0 ? (
            <ul className="space-y-3">
              {prescriptionsQuery.data.map((rx) => (
                <li key={rx.id} className="rounded-md border border-border p-3 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-muted-foreground">{rx.prescriptionNumber}</span>
                    <Badge variant={rx.status === "Finalized" ? "success" : "secondary"}>{rx.status}</Badge>
                    <Button type="button" variant="outline" size="sm" className="ml-auto h-7 text-xs" onClick={() => setPrintRx(rx)}>
                      Print
                    </Button>
                  </div>
                  <ul className="mt-2 space-y-1">
                    {rx.items.map((item) => (
                      <li key={item.id} className="text-muted-foreground">
                        <span className="font-medium text-foreground">{item.medicine}</span>
                        {item.strength ? ` ${item.strength}` : ""}
                        {item.dosage ? ` — ${item.dosage}` : ""}
                        {item.frequency ? ` ${item.frequency}` : ""}
                        {item.duration ? ` for ${item.duration}` : ""}
                        {item.quantity ? ` (Qty: ${item.quantity})` : ""}
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No prescriptions yet" description="Add medicine items below to write a prescription." />
          )}

          {canEdit ? (
            <div className="space-y-4 border-t border-border pt-4">
              {items.map((item, index) => (
                <div key={index} className="space-y-2 rounded-md border border-border p-3">
                  <div className="grid gap-2 sm:grid-cols-4">
                    <div className="relative sm:col-span-2">
                      <label className="text-xs font-medium text-muted-foreground">Medicine</label>
                      <Input
                        value={item.medicine}
                        onChange={(e) => updateItem(index, { medicine: e.target.value })}
                        onFocus={() => setActiveSuggestionRow(index)}
                        onBlur={() => setTimeout(() => setActiveSuggestionRow(null), 150)}
                        placeholder="Type medicine name…"
                      />
                      {activeSuggestionRow === index && item.medicine.trim() ? (
                        <MedicationSuggestions
                          query={item.medicine}
                          onSelect={(name) => updateItem(index, { medicine: name })}
                        />
                      ) : null}
                    </div>
                    <div>
                      <label className="text-xs font-medium text-muted-foreground">Strength</label>
                      <Input value={item.strength ?? ""} onChange={(e) => updateItem(index, { strength: e.target.value })} placeholder="e.g. 500mg" />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-muted-foreground">Route</label>
                      <Input value={item.route ?? ""} onChange={(e) => updateItem(index, { route: e.target.value })} placeholder="Oral / IV / Topical" />
                    </div>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-4">
                    <div>
                      <label className="text-xs font-medium text-muted-foreground">Dosage</label>
                      <Input value={item.dosage ?? ""} onChange={(e) => updateItem(index, { dosage: e.target.value })} />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-muted-foreground">Frequency</label>
                      <Input value={item.frequency ?? ""} onChange={(e) => updateItem(index, { frequency: e.target.value })} placeholder="e.g. TID" />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-muted-foreground">Duration</label>
                      <Input value={item.duration ?? ""} onChange={(e) => updateItem(index, { duration: e.target.value })} placeholder="e.g. 7 days" />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-muted-foreground">Quantity</label>
                      <Input value={item.quantity ?? ""} onChange={(e) => updateItem(index, { quantity: e.target.value })} placeholder="e.g. 21 tabs" />
                    </div>
                  </div>
                  <div className="flex items-center justify-between">
                    <label className="flex items-center gap-2 text-xs text-muted-foreground">
                      <input
                        type="checkbox"
                        checked={item.substitutionAllowed}
                        onChange={(e) => updateItem(index, { substitutionAllowed: e.target.checked })}
                      />
                      Generic substitution allowed
                    </label>
                    {items.length > 1 ? (
                      <Button type="button" variant="ghost" size="sm" onClick={() => removeRow(index)}>
                        Remove
                      </Button>
                    ) : null}
                  </div>
                </div>
              ))}

              <Button type="button" variant="secondary" onClick={addRow}>
                + Add another medicine
              </Button>

              {liveWarnings.length > 0 ? (
                <div className="rounded-md border border-amber-400/50 bg-amber-50 p-3 text-xs text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
                  <p className="font-medium">Review before saving (will not block saving):</p>
                  <ul className="mt-1 list-disc pl-4">
                    {liveWarnings.map((w, i) => <li key={i}>{w}</li>)}
                  </ul>
                </div>
              ) : null}

              <div className="flex justify-end">
                <Button type="button" onClick={submit} disabled={createPrescription.isPending || items.every((i) => !i.medicine.trim())}>
                  Save Prescription
                </Button>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <PrintableDocumentDialog
        open={printRx !== null}
        onOpenChange={(open) => !open && setPrintRx(null)}
        title="Prescription"
        printableId="prescription-printable"
      >
        {printRx ? (
          <>
            {/* Clinic header - name/logo/address from existing Clinic
                branding + settings fields (Phase 4), not new upload infra. */}
            <div className="flex items-center gap-3 border-b-2 border-foreground pb-2">
              {clinic?.logo_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={clinic.logo_url} alt="" className="h-12 w-12 object-contain" />
              ) : null}
              <div className="flex-1 text-center">
                <p className="text-base font-bold uppercase tracking-wide">{clinic?.name ?? "Clinic"}</p>
                <p className="text-xs text-muted-foreground">
                  {[clinic?.address, clinic?.city, clinic?.province].filter(Boolean).join(", ")}
                </p>
                <p className="text-xs text-muted-foreground">
                  {[clinic?.telephone ?? clinic?.mobile, clinic?.email].filter(Boolean).join(" · ")}
                </p>
              </div>
            </div>

            <div className="text-center">
              <p className="font-semibold uppercase tracking-wide">Prescription</p>
              <p className="text-xs text-muted-foreground">{printRx.prescriptionNumber}</p>
            </div>

            <div className="border-t border-dashed pt-2 space-y-1">
              <div className="flex justify-between"><span className="text-muted-foreground">Doctor</span><span>{doctorName ? `Dr. ${doctorName}` : "-"}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Date</span><span>{new Date(printRx.createdAt).toLocaleDateString()}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Visit #</span><span>{visitNumber ?? "-"}</span></div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Patient</span>
                <span>
                  {patientName ?? "-"}
                  {typeof patientAge === "number" ? ` (${patientAge} y/o)` : ""}
                </span>
              </div>
            </div>

            {/* Rx symbol + medication list - all items of this prescription
                render into this one document (see Item 9 fix note in
                PrescriptionTab: there is a single window.print() call for
                the whole list, not one per item). */}
            <div className="border-t-2 border-foreground pt-2 space-y-3">
              <p className="text-2xl font-serif italic leading-none">℞</p>
              {printRx.items.map((item, i) => (
                <div key={item.id} className="pl-4">
                  <p className="font-medium">
                    {i + 1}. {item.medicine}
                    {item.strength ? ` ${item.strength}` : ""}
                  </p>
                  <p className="text-muted-foreground">
                    {[item.dosage, item.route, item.frequency, item.duration ? `for ${item.duration}` : null, item.quantity ? `Qty: ${item.quantity}` : null]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                  {item.instructions ? <p className="text-muted-foreground">Sig: {item.instructions}</p> : null}
                  {!item.substitutionAllowed ? <p className="text-xs italic text-muted-foreground">No generic substitution</p> : null}
                </div>
              ))}
            </div>

            {/* Signature line - a physically-signable area at the bottom of
                the printed sheet. */}
            <div className="pt-10 flex flex-col items-end">
              <div className="w-56 border-t border-foreground text-center text-xs pt-1">
                {doctorName ? `Dr. ${doctorName}` : "Prescribing Physician"}
                {clinic?.license_number ? <><br />License No. {clinic.license_number}</> : null}
              </div>
            </div>
          </>
        ) : null}
      </PrintableDocumentDialog>
    </div>
  );
}

function MedicationSuggestions({ query, onSelect }: { query: string; onSelect: (name: string) => void }) {
  const matches = COMMON_MEDICINES.filter((m) => m.toLowerCase().includes(query.trim().toLowerCase())).slice(0, 6);
  if (matches.length === 0) return null;
  return (
    <ul className="absolute z-10 mt-1 w-full rounded-md border border-border bg-popover shadow-md">
      {matches.map((m) => (
        <li key={m}>
          <button
            type="button"
            className="block w-full px-3 py-1.5 text-left text-sm hover:bg-accent"
            onMouseDown={(e) => {
              e.preventDefault();
              onSelect(m);
            }}
          >
            {m}
          </button>
        </li>
      ))}
    </ul>
  );
}
