"use client";

import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  useEnterResults,
  useLaboratoryAttachments,
  useLaboratoryOrder,
  useUploadLaboratoryAttachment,
} from "@/features/laboratory/hooks/use-laboratory";
import { interpretResult } from "@/features/laboratory/types";
import type { LaboratoryOrder, LaboratoryResult, LaboratoryResultInput, LaboratoryTemplateParameter } from "@/features/laboratory/types";
import { InterpretationBadge } from "@/features/laboratory/components/InterpretationBadge";
import { LaboratoryAttachmentList } from "@/features/laboratory/components/LaboratoryAttachmentList";

interface ResultEntryDialogProps {
  order: LaboratoryOrder | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Row state extends the submit payload with local-only fields: once the
 * lab tech explicitly picks an interpretation from the dropdown, live
 * recomputation (while typing the value) must stop overwriting it - the
 * manual choice always wins, per spec. `options`/`section`/`requiresSite`
 * are also local-only (all sourced from the template - never hard-coded
 * here); `requiresSite` is stripped before submit, but `site` itself IS a
 * real submitted field (see LaboratoryResultInput.site). */
type RowState = LaboratoryResultInput & {
  manualOverride: boolean;
  options: string[] | null;
  section: string | null;
  requiresSite: boolean;
};

function emptyRow(): RowState {
  return {
    parameterName: "", resultType: "Numeric", numericValue: null, textValue: null,
    normalRange: "", units: "", interpretation: null, remarks: "",
    rangeLow: null, rangeHigh: null, expectedNormalText: null, structuredValue: null, site: null,
    manualOverride: false, options: null, section: null, requiresSite: false,
  };
}

/** A `LaboratoryResult` doesn't carry its own `options`/`section` (only the
 * template parameter does) - looked up by parameter name from the order's
 * linked template so an already-entered result's row still shows its full
 * choice list and section, not just the value it currently holds. */
function templateParameterFor(order: LaboratoryOrder | null, parameterName: string) {
  return order?.template?.parameters.find(
    (p) => p.parameterName.trim().toLowerCase() === parameterName.trim().toLowerCase(),
  );
}

function rowFromResult(r: LaboratoryResult, p?: LaboratoryTemplateParameter): RowState {
  return {
    parameterName: r.parameterName,
    resultType: r.resultType,
    numericValue: r.numericValue,
    textValue: r.textValue,
    normalRange: r.normalRange ?? p?.normalRange ?? "",
    units: r.units ?? p?.unit ?? "",
    interpretation: r.interpretation,
    remarks: r.remarks ?? "",
    rangeLow: r.rangeLow,
    rangeHigh: r.rangeHigh,
    expectedNormalText: null,
    structuredValue: r.structuredValue,
    site: r.site,
    manualOverride: r.interpretation !== null,
    options: p?.options ?? null,
    section: p?.section ?? null,
    requiresSite: p?.requiresSite ?? false,
  };
}

/** Phase 4H fix: reopening a PARTIALLY-completed templated order used to
 * show only the already-entered results and silently drop every
 * not-yet-entered template parameter - since `upsert_results` is a full
 * replace-all, resuming from that truncated form and saving again would
 * have discarded nothing already-saved (those rows were still present),
 * but the technician had no way to see/continue the remaining parameters
 * without manually re-adding them via free-text "Add row" (losing the
 * prefilled unit/range/options/section entirely, and risking a
 * mismatched name). Now: for a templated order, EVERY template parameter
 * gets a row (in template `display_order`) - populated from its matching
 * result(s) if any exist, blank otherwise. A `requiresSite` parameter with
 * multiple site-specific results (e.g. KOH Mount) gets one row per
 * result, matching `buildReportRows`' same site-aware convention. Any
 * result with no matching template parameter (untemplated ad-hoc rows
 * from a prior session) is still appended, never dropped. Untemplated
 * orders keep the original results-only/blank-row behavior, unchanged. */
function initialRows(order: LaboratoryOrder | null): RowState[] {
  if (!order) return [emptyRow()];

  if (order.template && order.template.parameters.length > 0) {
    const resultsByName = new Map<string, LaboratoryResult[]>();
    for (const r of order.results) {
      const key = r.parameterName.trim().toLowerCase();
      const existing = resultsByName.get(key);
      if (existing) existing.push(r);
      else resultsByName.set(key, [r]);
    }

    const rows: RowState[] = [];
    for (const p of order.template.parameters) {
      const key = p.parameterName.trim().toLowerCase();
      const matches = resultsByName.get(key);
      if (matches && matches.length > 0) {
        for (const r of matches) rows.push(rowFromResult(r, p));
        resultsByName.delete(key);
      } else {
        rows.push({
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
          structuredValue: null,
          site: null,
          manualOverride: false,
          options: p.options ?? null,
          section: p.section ?? null,
          requiresSite: p.requiresSite ?? false,
        });
      }
    }
    // Leftover results that matched no template parameter - still shown,
    // never silently dropped.
    for (const leftover of resultsByName.values()) {
      for (const r of leftover) rows.push(rowFromResult(r, templateParameterFor(order, r.parameterName)));
    }
    return rows;
  }

  if (order.results.length > 0) {
    return order.results.map((r) => rowFromResult(r, templateParameterFor(order, r.parameterName)));
  }

  return [emptyRow()];
}

/** Groups rows by `section`, preserving row order within and across groups
 * (consecutive same-section rows merge into one group; a run of `null`-
 * section rows - the CBC/Blood Typing case, no sections configured at all -
 * becomes a single unheaded group so those templates render exactly as
 * before, with no heading). Never re-sorts - the backend's own
 * `display_order`/result order is the only ordering authority. */
function groupBySection(rows: RowState[]): { section: string | null; rows: { row: RowState; index: number }[] }[] {
  const groups: { section: string | null; rows: { row: RowState; index: number }[] }[] = [];
  rows.forEach((row, index) => {
    const key = row.section ?? null;
    const last = groups[groups.length - 1];
    if (last && last.section === key) {
      last.rows.push({ row, index });
    } else {
      groups.push({ section: key, rows: [{ row, index }] });
    }
  });
  return groups;
}

/** A Categorical row can only produce a valid result if the administrator
 * has actually configured `options` for that parameter - see Phase 4B's
 * "options-less categorical parameters" rule: never fabricate choices, and
 * never let the technician submit a value for a parameter that has none
 * configured. */
function isSubmittableCategorical(row: RowState): boolean {
  return row.resultType !== "Categorical" || Boolean(row.options && row.options.length > 0);
}

export function ResultEntryDialog({ order, open, onOpenChange }: ResultEntryDialogProps) {
  // Phase 2B: the worklist row passed in as `order` may be stale/pre-
  // resolution (e.g. fetched before a reference range was configured for
  // this parameter, or before any patient-specific range was applicable) -
  // re-fetching on open gets the backend-resolved range/interpretation
  // basis for THIS order's own patient (see `LaboratoryService.get()`'s
  // `_overlay_resolved_ranges`). The backend remains the single source of
  // truth for the range; this only changes which fetch of that same order
  // shape the prefill reads from. Falls back to the passed-in `order`
  // while the query is in flight so the dialog isn't blank on first open.
  const orderQuery = useLaboratoryOrder(open ? order?.id : null);
  const resolvedOrder = orderQuery.data ?? order;

  const [rows, setRows] = useState<RowState[]>(() => initialRows(resolvedOrder));
  const mutation = useEnterResults();
  const attachmentsQuery = useLaboratoryAttachments(order?.id);
  const uploadAttachment = useUploadLaboratoryAttachment(order?.id);

  useEffect(() => {
    if (open) setRows(initialRows(resolvedOrder));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- resolvedOrder is derived from order/orderQuery.data, both already tracked
  }, [open, order, orderQuery.data]);

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
      // A parameter with no name, or an options-less Categorical parameter
      // (nothing configured to select from - see isSubmittableCategorical),
      // is silently excluded rather than submitted invalid - the technician
      // can still save every OTHER valid row (existing partial-submission
      // behavior, unchanged).
      .filter((r) => r.parameterName.trim().length > 0 && isSubmittableCategorical(r))
      .map(({ manualOverride: _manualOverride, options: _options, section: _section, requiresSite: _requiresSite, ...r }) => ({
        ...r,
        numericValue: r.resultType === "Numeric" ? (r.numericValue === null || Number.isNaN(r.numericValue) ? null : r.numericValue) : null,
        // Phase 4C note: this `=== "Text"` check (not "anything that isn't
        // Numeric/Categorical") means a `Titer`-typed row's textValue would
        // be silently discarded here today - one of two concrete gaps
        // (along with the Type selector below having no "Titer" option)
        // that make `LaboratoryResultType.TITER` not yet safely usable
        // end-to-end. Not fixed in Phase 4C - VDRL uses Categorical
        // instead (see backend `DEFAULT_LABORATORY_TEMPLATES`'s Phase 4C
        // note) rather than partially wiring up a broken Titer workflow.
        // Phase 4E: Titer/Microscopy are free-text-valued (like Text) -
        // storage-wise they're indistinguishable from Text results (both
        // use text_value; see LaboratoryResult's docstring on why Titer
        // was never given dedicated storage, and why Microscopy's
        // structured_value convention was never actually implemented
        // anywhere, so free text is the smallest correct representation).
        textValue: ["Text", "Titer", "Microscopy"].includes(r.resultType) ? r.textValue || null : null,
        structuredValue: r.resultType === "Categorical" ? r.structuredValue || null : null,
      }));
    if (cleaned.length === 0) return;
    try {
      // Phase 4I: echoes back the `updatedAt` this form was actually built
      // from - if someone else saved in between, the backend rejects this
      // (409) instead of silently discarding their save.
      await mutation.mutateAsync({ id: order!.id, results: cleaned, expectedUpdatedAt: resolvedOrder?.updatedAt ?? null });
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
          {/* Phase 4B: rows are grouped by `parameter.section` (generic -
              any template, not just Urinalysis, whose parameters carry a
              section renders this way). A template with no sections at all
              (CBC, Blood Typing) produces a single unheaded group, so their
              layout is unchanged from before this phase. */}
          {groupBySection(rows).map((group, groupIndex) => (
            <div key={groupIndex} className="space-y-2">
              {group.section && (
                <h3 className="pt-2 text-sm font-semibold text-foreground first:pt-0">{group.section}</h3>
              )}
              {group.rows.map(({ row, index }) => {
                const categoricalConfigured = Boolean(row.options && row.options.length > 0);
                return (
                  <div key={index} className="grid grid-cols-12 gap-2 rounded-md border border-border p-3">
                    <div className="col-span-12 sm:col-span-3">
                      <label className="text-xs text-muted-foreground">Parameter</label>
                      <Input value={row.parameterName} onChange={(e) => updateRow(index, { parameterName: e.target.value })} placeholder="e.g. Hemoglobin" />
                    </div>
                    <div className="col-span-6 sm:col-span-2">
                      <label className="text-xs text-muted-foreground">Type</label>
                      <Select
                        value={row.resultType}
                        onChange={(e) => updateRow(index, { resultType: e.target.value as LaboratoryResultInput["resultType"] })}
                        disabled={row.resultType === "Categorical" || row.resultType === "Titer" || row.resultType === "Microscopy"}
                      >
                        <option value="Numeric">Numeric</option>
                        <option value="Text">Text</option>
                        {row.resultType === "Categorical" && <option value="Categorical">Categorical</option>}
                        {/* Phase 4E: like Categorical, Titer/Microscopy only ever
                            appear here because the template parameter already
                            configured that type - never freely selectable for an
                            ad-hoc row, same as Categorical's existing pattern. */}
                        {row.resultType === "Titer" && <option value="Titer">Titer</option>}
                        {row.resultType === "Microscopy" && <option value="Microscopy">Microscopy</option>}
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
                    ) : row.resultType === "Categorical" ? (
                      // Phase 3/4B: options come entirely from the template
                      // parameter (`row.options`) - never hard-coded here,
                      // so this same branch is reusable for any future
                      // Categorical test. An administrator who hasn't
                      // configured options yet gets a disabled control, not
                      // a fabricated choice list or a silent Text fallback.
                      <div className="col-span-6 sm:col-span-2">
                        <label className="text-xs text-muted-foreground">Value</label>
                        {categoricalConfigured ? (
                          <Select
                            value={(row.structuredValue?.value as string | undefined) ?? ""}
                            onChange={(e) => updateRow(index, { structuredValue: e.target.value ? { value: e.target.value } : null })}
                          >
                            <option value="">Select...</option>
                            {(row.options ?? []).map((option) => (
                              <option key={option} value={option}>
                                {option}
                              </option>
                            ))}
                          </Select>
                        ) : (
                          <Select value="" disabled aria-label={`${row.parameterName || "Parameter"} - no options configured`}>
                            <option value="">No options configured</option>
                          </Select>
                        )}
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
                      <label className="text-xs text-muted-foreground">
                        {row.resultType === "Categorical" ? "Reference/Normal" : "Normal Range"}
                      </label>
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
                    {row.requiresSite && (
                      // Phase 4D: a generic site input, shown purely
                      // because `parameter.requiresSite` says so (e.g. KOH
                      // Mount) - never a test-specific branch. No site
                      // vocabulary is pre-filled; the technician enters the
                      // actual specimen site as free text.
                      <div className="col-span-6 sm:col-span-3">
                        <label className="text-xs text-muted-foreground">Site</label>
                        <Input
                          value={row.site ?? ""}
                          onChange={(e) => updateRow(index, { site: e.target.value || null })}
                          placeholder="e.g. Skin, Vaginal, Nail"
                        />
                      </div>
                    )}
                    <div className={row.requiresSite ? "col-span-12 sm:col-span-5" : "col-span-9 sm:col-span-8"}>
                      <label className="text-xs text-muted-foreground">Remarks</label>
                      <Input value={row.remarks ?? ""} onChange={(e) => updateRow(index, { remarks: e.target.value })} />
                    </div>
                    <div className="col-span-12 flex justify-end sm:col-span-1 sm:items-end">
                      <Button type="button" variant="ghost" size="sm" onClick={() => removeRow(index)} disabled={rows.length === 1}>
                        Remove
                      </Button>
                    </div>
                  </div>
                );
              })}
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
