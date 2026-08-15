"use client";

import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useCreateLaboratoryTemplate, useUpdateLaboratoryTemplate } from "@/features/laboratory/hooks/use-laboratory";
import type { LaboratoryTemplate, LaboratoryTemplateParameter } from "@/features/laboratory/types";

interface LaboratoryTemplateFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  template?: LaboratoryTemplate | null;
}

function emptyParameter(): LaboratoryTemplateParameter {
  return { parameterName: "", unit: "", normalRange: "", resultType: "Numeric", rangeLow: null, rangeHigh: null, expectedNormalText: "" };
}

/** Administrator-only CRUD for the configurable test catalog - the piece
 * that lets a new test (e.g. "HbA1c") be added with its own
 * parameters/ranges/units/price/turnaround/specimen-type entirely through
 * this UI, no code changes, per spec. Bespoke form (not the shared
 * `MasterDataPage`/`MasterDataFormDialog` pair) because of the nested,
 * variable-length parameter list - same judgment call already made for
 * Doctor/Consultation-Room forms elsewhere in the app. */
export function LaboratoryTemplateFormDialog({ open, onOpenChange, template }: LaboratoryTemplateFormDialogProps) {
  const isEdit = Boolean(template);
  const [testName, setTestName] = useState("");
  const [testCategory, setTestCategory] = useState("");
  const [specimenType, setSpecimenType] = useState("");
  const [defaultPrice, setDefaultPrice] = useState("0");
  const [turnaroundHours, setTurnaroundHours] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [parameters, setParameters] = useState<LaboratoryTemplateParameter[]>([emptyParameter()]);

  const createMutation = useCreateLaboratoryTemplate();
  const updateMutation = useUpdateLaboratoryTemplate();

  useEffect(() => {
    if (!open) return;
    if (template) {
      setTestName(template.testName);
      setTestCategory(template.testCategory ?? "");
      setSpecimenType(template.specimenType ?? "");
      setDefaultPrice(String(template.defaultPrice));
      setTurnaroundHours(template.turnaroundTimeHours ? String(template.turnaroundTimeHours) : "");
      setIsActive(template.isActive);
      setParameters(template.parameters.length > 0 ? template.parameters : [emptyParameter()]);
    } else {
      setTestName("");
      setTestCategory("");
      setSpecimenType("");
      setDefaultPrice("0");
      setTurnaroundHours("");
      setIsActive(true);
      setParameters([emptyParameter()]);
    }
  }, [open, template]);

  function updateParam(index: number, patch: Partial<LaboratoryTemplateParameter>) {
    setParameters((prev) => prev.map((p, i) => (i === index ? { ...p, ...patch } : p)));
  }

  function addParam() {
    setParameters((prev) => [...prev, emptyParameter()]);
  }

  function removeParam(index: number) {
    setParameters((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleSubmit() {
    const payload = {
      testName,
      testCategory: testCategory || null,
      specimenType: specimenType || null,
      defaultPrice: Number(defaultPrice) || 0,
      turnaroundTimeHours: turnaroundHours ? Number(turnaroundHours) : null,
      isActive,
      parameters: parameters
        .filter((p) => p.parameterName.trim().length > 0)
        .map((p) => ({ ...p, expectedNormalText: p.expectedNormalText?.trim() ? p.expectedNormalText.trim() : null })),
    };
    try {
      if (isEdit && template) {
        await updateMutation.mutateAsync({ id: template.id, payload });
      } else {
        await createMutation.mutateAsync(payload);
      }
      onOpenChange(false);
    } catch {
      // toast handled in the mutation's onError
    }
  }

  const isPending = createMutation.isPending || updateMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit Test Template" : "New Test Template"}</DialogTitle>
        </DialogHeader>

        <div className="max-h-[65vh] space-y-4 overflow-y-auto pr-1">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted-foreground">Test Name</label>
              <Input value={testName} onChange={(e) => setTestName(e.target.value)} placeholder="e.g. CBC" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Category</label>
              <Input value={testCategory} onChange={(e) => setTestCategory(e.target.value)} placeholder="e.g. Hematology" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Specimen Type</label>
              <Input value={specimenType} onChange={(e) => setSpecimenType(e.target.value)} placeholder="e.g. Whole Blood" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Default Price</label>
              <Input type="number" step="0.01" value={defaultPrice} onChange={(e) => setDefaultPrice(e.target.value)} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Turnaround (hours)</label>
              <Input type="number" value={turnaroundHours} onChange={(e) => setTurnaroundHours(e.target.value)} />
            </div>
            <div className="flex items-end gap-2">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
                Active
              </label>
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-sm font-medium">Result Parameters</p>
            {parameters.map((p, index) => (
              <div key={index} className="grid grid-cols-12 gap-2 rounded-md border border-border p-2">
                <div className="col-span-4">
                  <Input placeholder="Parameter" value={p.parameterName} onChange={(e) => updateParam(index, { parameterName: e.target.value })} />
                </div>
                <div className="col-span-2">
                  <Input placeholder="Unit" value={p.unit ?? ""} onChange={(e) => updateParam(index, { unit: e.target.value })} />
                </div>
                <div className="col-span-3">
                  <Input placeholder="Normal Range" value={p.normalRange ?? ""} onChange={(e) => updateParam(index, { normalRange: e.target.value })} />
                </div>
                <div className="col-span-2">
                  <Select value={p.resultType} onChange={(e) => updateParam(index, { resultType: e.target.value as "Numeric" | "Text" })}>
                    <option value="Numeric">Numeric</option>
                    <option value="Text">Text</option>
                  </Select>
                </div>
                <div className="col-span-1 flex items-center justify-end">
                  <Button type="button" variant="ghost" size="sm" onClick={() => removeParam(index)}>
                    &times;
                  </Button>
                </div>
                {p.resultType === "Numeric" ? (
                  <div className="col-span-12 grid grid-cols-2 gap-2 sm:col-span-8">
                    <div>
                      <label className="text-[11px] text-muted-foreground">Reference Low (optional)</label>
                      <Input
                        type="number" step="any" placeholder="Not yet configured"
                        value={p.rangeLow ?? ""}
                        onChange={(e) => updateParam(index, { rangeLow: e.target.value === "" ? null : Number(e.target.value) })}
                      />
                    </div>
                    <div>
                      <label className="text-[11px] text-muted-foreground">Reference High (optional)</label>
                      <Input
                        type="number" step="any" placeholder="Not yet configured"
                        value={p.rangeHigh ?? ""}
                        onChange={(e) => updateParam(index, { rangeHigh: e.target.value === "" ? null : Number(e.target.value) })}
                      />
                    </div>
                  </div>
                ) : (
                  <div className="col-span-12 sm:col-span-8">
                    <label className="text-[11px] text-muted-foreground">Expected Normal Value (optional)</label>
                    <Input
                      placeholder="e.g. Negative - not yet configured if blank"
                      value={p.expectedNormalText ?? ""}
                      onChange={(e) => updateParam(index, { expectedNormalText: e.target.value })}
                    />
                  </div>
                )}
              </div>
            ))}
            <Button type="button" variant="outline" size="sm" onClick={addParam}>
              + Add parameter
            </Button>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={isPending || !testName.trim()}>
            {isPending ? "Saving..." : isEdit ? "Save Changes" : "Create Template"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
