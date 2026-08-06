"use client";

import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useEnterResults } from "@/features/laboratory/hooks/use-laboratory";
import type { LaboratoryOrder, LaboratoryResultInput } from "@/features/laboratory/types";

interface ResultEntryDialogProps {
  order: LaboratoryOrder | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function emptyRow(): LaboratoryResultInput {
  return { parameterName: "", resultType: "Numeric", numericValue: null, textValue: null, normalRange: "", units: "", interpretation: null, remarks: "" };
}

/** Pre-populates one row per matched template parameter (if the order was
 * created against a configured template) or per already-entered result
 * (editing an existing submission); otherwise starts with a single blank
 * row the lab tech can fill in freely, per spec's "editable/addable if not
 * [using a template]". */
function initialRows(order: LaboratoryOrder | null): LaboratoryResultInput[] {
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
    }));
  }
  return [emptyRow()];
}

export function ResultEntryDialog({ order, open, onOpenChange }: ResultEntryDialogProps) {
  const [rows, setRows] = useState<LaboratoryResultInput[]>(() => initialRows(order));
  const mutation = useEnterResults();

  useEffect(() => {
    if (open) setRows(initialRows(order));
  }, [open, order]);

  if (!order) return null;

  function updateRow(index: number, patch: Partial<LaboratoryResultInput>) {
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, ...patch } : r)));
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
      .map((r) => ({
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
              <div className="col-span-3 sm:col-span-2">
                <label className="text-xs text-muted-foreground">Interpretation</label>
                <Select
                  value={row.interpretation ?? ""}
                  onChange={(e) => updateRow(index, { interpretation: (e.target.value || null) as LaboratoryResultInput["interpretation"] })}
                >
                  <option value="">-</option>
                  <option value="Normal">Normal</option>
                  <option value="Low">Low</option>
                  <option value="High">High</option>
                  <option value="Abnormal">Abnormal</option>
                </Select>
              </div>
              <div className="col-span-9 sm:col-span-9">
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
