"use client";

import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useEnterResults, useLaboratoryAttachments, useUploadLaboratoryAttachment } from "@/features/laboratory/hooks/use-laboratory";
import { interpretResult } from "@/features/laboratory/types";
import type { LaboratoryOrder, LaboratoryResultInput } from "@/features/laboratory/types";
import { InterpretationBadge } from "@/features/laboratory/components/InterpretationBadge";
import { LaboratoryAttachmentList } from "@/features/laboratory/components/LaboratoryAttachmentList";

interface ResultEntryDialogProps {
  order: LaboratoryOrder | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Row state extends the submit payload with a local-only flag: once the
 * lab tech explicitly picks an interpretation from the dropdown, live
 * recomputation (while typing the value) must stop overwriting it - the
 * manual choice always wins, per spec. Stripped before submit. */
type RowState = LaboratoryResultInput & { manualOverride: boolean };

function emptyRow(): RowState {
  return {
    parameterName: "", resultType: "Numeric", numericValue: null, textValue: null,
    normalRange: "", units: "", interpretation: null, remarks: "",
    rangeLow: null, rangeHigh: null, expectedNormalText: null, manualOverride: false,
  };
}

/** Pre-populates one row per already-entered result (editing an existing
 * submission); otherwise, if the order has a linked template, one row per
 * template parameter (name/unit/reference range pre-filled, value left
 * blank for the lab tech to fill in - never inventing a range); otherwise
 * starts with a single blank row. */
function initialRows(order: LaboratoryOrder | null): RowState[] {
  if (!order) return [emptyRow()];
  if (order.results.length > 0) {
    return order.results.map((r) => ({
      parameterName: r.parameterName,
      resultType: r.resultType,
      numericValue: r.numericValue,
      textValue: r.textValue,
      normalRange: r.normalRange ?? "",
      units: r.units ?? "",
      interpretation: r.interpretation,
      remarks: r.remarks ?? "",
      rangeLow: r.rangeLow,
      rangeHigh: r.rangeHigh,
      expectedNormalText: null,
      manualOverride: r.interpretation !== null,
    }));
  }
  if (order.template && order.template.parameters.length > 0) {
    return order.template.parameters.map((p) => ({
      parameterName: p.parameterName,
      resultType: p.resultType,
      numericValue: null,
      textValue: null,
      normalRange: p.normalRange ?? "",
      units: p.unit ?? "",
      interpretation: null,
      remarks: "",
      rangeLow: p.rangeLow ?? null,
      rangeHigh: p.rangeHigh ?? null,
      expectedNormalText: p.expectedNormalText ?? null,
      manualOverride: false,
    }));
  }
  return [emptyRow()];
}

export function ResultEntryDialog({ order, open, onOpenChange }: ResultEntryDialogProps) {
  const [rows, setRows] = useState<RowState[]>(() => initialRows(order));
  const mutation = useEnterResults();
  const attachmentsQuery = useLaboratoryAttachments(order?.id);
  const uploadAttachment = useUploadLaboratoryAttachment(order?.id);

  useEffect(() => {
    if (open) setRows(initialRows(order));
  }, [open, order]);

  if (!order) return null;

  function updateRow(index: number, patch: Partial<RowState>) {
    setRows((prev) =>
      prev.map((r, i) => {
        if (i !== index) return r;
        const next = { ...r, ...patch };
        // Live-recompute the suggestion into the Interpretation dropdown as
        // the lab tech types the value - but never once they've manually
        // overridden it themselves.
        if (!next.manualOverride) {
          next.interpretation = interpretResult({
            resultType: next.resultType,
            numericValue: next.numericValue,
            textValue: next.textValue,
            rangeLow: next.rangeLow,
            rangeHigh: next.rangeHigh,
            expectedNormalText: next.expectedNormalText,
          });
        }
        return next;
      }),
    );
  }

  function addRow() {
    setRows((prev) => [...prev, emptyRow()]);
  }

  function removeRow(index: number) {
    setRows((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleSubmit() {
    const cleaned = rows
      .filter((r) => r.parameterName.trim().length > 0)
      .map(({ manualOverride: _manualOverride, ...r }) => ({
        ...r,
        numericValue: r.resultType === "Numeric" ? (r.numericValue === null || Number.isNaN(r.numericValue) ? null : r.numericValue) : null,
        textValue: r.resultType === "Text" ? r.textValue || null : null,
      }));
    if (cleaned.length === 0) return;
    try {
      await mutation.mutateAsync({ id: order!.id, results: cleaned });
      onOpenChange(false);
    } catch {
      // toast handled in the mutation's onError
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Enter Results - {order.testType}</DialogTitle>
        </DialogHeader>

        <div className="max-h-[60vh] space-y-4 overflow-y-auto pr-1">
          {rows.map((row, index) => (
            <div key={index} className="grid grid-cols-12 gap-2 rounded-md border border-border p-3">
              <div className="col-span-12 sm:col-span-3">
                <label className="text-xs text-muted-foreground">Parameter</label>
                <Input value={row.parameterName} onChange={(e) => updateRow(index, { parameterName: e.target.value })} placeholder="e.g. Hemoglobin" />
              </div>
              <div className="col-span-6 sm:col-span-2">
                <label className="text-xs text-muted-foreground">Type</label>
                <Select value={row.resultType} onChange={(e) => updateRow(index, { resultType: e.target.value as "Numeric" | "Text" })}>
                  <option value="Numeric">Numeric</option>
                  <option value="Text">Text</option>
                </Select>
              </div>
              {row.resultType === "Numeric" ? (
                <div className="col-span-6 sm:col-span-2">
                  <label className="text-xs text-muted-foreground">Value</label>
                  <Input
                    type="number" step="any"
                    value={row.numericValue ?? ""}
                    onChange={(e) => updateRow(index, { numericValue: e.target.value === "" ? null : Number(e.target.value) })}
                  />
                </div>
              ) : (
                <div className="col-span-12 sm:col-span-4">
                  <label className="text-xs text-muted-foreground">Value</label>
                  <Textarea value={row.textValue ?? ""} onChange={(e) => updateRow(index, { textValue: e.target.value })} rows={1} />
                </div>
              )}
              <div className="col-span-4 sm:col-span-2">
                <label className="text-xs text-muted-foreground">Units</label>
                <Input value={row.units ?? ""} onChange={(e) => updateRow(index, { units: e.target.value })} />
              </div>
              <div className="col-span-4 sm:col-span-2">
                <label className="text-xs text-muted-foreground">Normal Range</label>
                <Input value={row.normalRange ?? ""} onChange={(e) => updateRow(index, { normalRange: e.target.value })} />
              </div>
              <div className="col-span-4 sm:col-span-2 flex flex-col justify-end">
                <label className="text-xs text-muted-foreground">Suggested</label>
                <InterpretationBadge value={row.interpretation} />
              </div>
              <div className="col-span-3 sm:col-span-2">
                <label className="text-xs text-muted-foreground">Interpretation</label>
                <Select
                  value={row.interpretation ?? ""}
                  onChange={(e) =>
                    updateRow(index, {
                      interpretation: (e.target.value || null) as LaboratoryResultInput["interpretation"],
                      manualOverride: true,
                    })
                  }
                >
                  <option value="">-</option>
                  <option value="Normal">Normal</option>
                  <option value="Low">Low</option>
                  <option value="High">High</option>
                  <option value="Abnormal">Abnormal</option>
                </Select>
              </div>
              <div className="col-span-9 sm:col-span-8">
                <label className="text-xs text-muted-foreground">Remarks</label>
                <Input value={row.remarks ?? ""} onChange={(e) => updateRow(index, { remarks: e.target.value })} />
              </div>
              <div className="col-span-12 flex justify-end sm:col-span-1 sm:items-end">
                <Button type="button" variant="ghost" size="sm" onClick={() => removeRow(index)} disabled={rows.length === 1}>
                  Remove
                </Button>
              </div>
            </div>
          ))}
          <Button type="button" variant="outline" size="sm" onClick={addRow}>
            + Add parameter
          </Button>

          <div className="space-y-2 border-t border-border pt-4">
            <p className="text-sm font-medium">Result Image</p>
            <LaboratoryAttachmentList attachments={attachmentsQuery.data ?? []} />
            <div>
              <label className="text-xs text-muted-foreground">Attach the actual laboratory result image</label>
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="mt-1 block text-sm"
                disabled={uploadAttachment.isPending}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) uploadAttachment.mutate({ file, attachmentType: "Image" });
                  e.target.value = "";
                }}
              />
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={mutation.isPending}>
            {mutation.isPending ? "Saving..." : "Save Results"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
