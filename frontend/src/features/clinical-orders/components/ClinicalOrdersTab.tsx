"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { SearchableSelect } from "@/components/ui/searchable-select";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState } from "@/components/layout/EmptyState";
import { SkeletonList } from "@/components/layout/LoadingSkeletons";
import { apiClient } from "@/lib/api-client";
import { useLaboratoryTemplates } from "@/features/laboratory/hooks/use-laboratory";
import {
  useCreateOrder, useCreateProcedure, useCreateReferral,
  useOrdersForConsultation, useProceduresForConsultation, useReferralsForConsultation,
  useUpdateOrderStatus,
} from "@/features/clinical-orders/hooks/use-clinical-orders";
import type { Order, OrderCategory, OrderItemInput, OrderPriority, OrderStatus, Procedure, Referral } from "@/features/clinical-orders/types";
import { PrintableDocumentDialog } from "@/features/clinical-orders/components/PrintableDocumentDialog";
import { DoctorSignatureBlock } from "@/features/clinical-orders/components/DoctorSignatureBlock";
import type { ClinicSettings } from "@/features/clinic-config/types";
import { formatDateTime } from "@/lib/utils";

const ORDER_CATEGORIES: OrderCategory[] = ["Laboratory", "Radiology", "Vaccination", "Custom"];
const ORDER_STATUSES: OrderStatus[] = ["Requested", "Collected", "Processing", "Completed", "Cancelled"];

// Print title/section label per category - Laboratory's wording is
// preserved byte-for-byte (pre-existing behavior); other categories get
// their own category-appropriate wording instead of a generic label.
const ORDER_PRINT_TITLE: Partial<Record<OrderCategory, string>> = {
  Laboratory: "Laboratory Request",
  Radiology: "Radiology Request",
  Vaccination: "Vaccination Request",
  Custom: "Order Request",
};
const ORDER_PRINT_ITEMS_LABEL: Partial<Record<OrderCategory, string>> = {
  Laboratory: "Requested tests",
  Radiology: "Requested exams",
  Vaccination: "Requested vaccines",
  Custom: "Requested items",
};

const STATUS_VARIANT: Record<OrderStatus, "default" | "secondary" | "success" | "destructive"> = {
  Requested: "secondary", Collected: "default", Processing: "default", Completed: "success", Cancelled: "destructive",
};

export function ClinicalOrdersTab({
  consultationId,
  visitId,
  canEdit,
  patientName,
  doctorName,
  doctorPrcLicense,
  doctorPtrNumber,
  visitNumber,
  hideLaboratoryOption,
}: {
  consultationId: string;
  visitId: string;
  canEdit: boolean;
  patientName?: string | null;
  doctorName?: string | null;
  doctorPrcLicense?: string | null;
  doctorPtrNumber?: string | null;
  visitNumber?: string | null;
  // Doctor Workspace Configuration: the "Lab Requests" consultation section
  // maps to hiding just the Laboratory category here (Radiology/
  // Vaccination/Custom still use this same generic Orders tab) - never a
  // whole separate tab, since those other categories aren't gated by that
  // toggle.
  hideLaboratoryOption?: boolean;
}) {
  const availableCategories = hideLaboratoryOption ? ORDER_CATEGORIES.filter((c) => c !== "Laboratory") : ORDER_CATEGORIES;
  const [printOrder, setPrintOrder] = useState<Order | null>(null);
  const [printProcedure, setPrintProcedure] = useState<Procedure | null>(null);
  const [printReferral, setPrintReferral] = useState<Referral | null>(null);
  // Doctor E-Signature (Referral previously had no signature block at all)
  // - same clinic-license-number lookup PrescriptionTab already does.
  const clinicQuery = useQuery({
    queryKey: ["clinic-settings"],
    queryFn: () => apiClient.get<ClinicSettings>("/clinic-settings"),
  });
  const clinic = clinicQuery.data;
  const ordersQuery = useOrdersForConsultation(consultationId);
  const proceduresQuery = useProceduresForConsultation(consultationId);
  const referralsQuery = useReferralsForConsultation(consultationId);
  const createOrder = useCreateOrder(consultationId, visitId);
  const updateOrderStatus = useUpdateOrderStatus(consultationId, visitId);
  const createProcedure = useCreateProcedure(consultationId, visitId);
  const createReferral = useCreateReferral(consultationId, visitId);

  const [orderForm, setOrderForm] = useState<{ category: OrderCategory; priority: OrderPriority; scheduledDate: string; notes: string; itemName: string; examType: string; bodyPart: string; indication: string }>(
    { category: availableCategories[0], priority: "Routine", scheduledDate: "", notes: "", itemName: "", examType: "", bodyPart: "", indication: "" }
  );
  const [procedureForm, setProcedureForm] = useState({ name: "", date: "", notes: "" });
  const [referralForm, setReferralForm] = useState({ referredTo: "", reason: "", notes: "" });

  // Task #3: Laboratory items are picked from the clinic's own configured
  // Laboratory Templates (not typed free-text, not the Services catalog -
  // see the module note below for why), one at a time via the
  // search-select, collected into this list, and submitted together as ONE
  // Order with N OrderItems. Radiology/Vaccination/Custom are untouched -
  // still the single free-text field they always were. The picker itself
  // is deliberately kept uncontrolled (`value=""` always) - it's a
  // "search, pick, add to the list below" control, not a bound single
  // value, so it clears itself after every pick, ready for the next one.
  const [selectedLabItems, setSelectedLabItems] = useState<string[]>([]);
  // Laboratory Templates, not the Services catalog: `LaboratoryService.
  // create_from_order` (Task #1) resolves each OrderItem's billing/worklist
  // template by exact-matching its `item_name` against LaboratoryTemplate.
  // test_name (`_resolve_template_id`) - it never looks at ClinicService at
  // all. Sourcing this picker's options from `test_name` directly
  // guarantees every selection is a tier-1 exact match (real template,
  // real price, real worklist entry); sourcing from the Services catalog
  // instead would risk exactly the name-drift silent-mismatch failure
  // `_resolve_template_id`'s own docstring describes as the production bug
  // it was built to avoid (a Service named differently from its Template
  // never auto-links, and `_sync_billing` then silently skips billing for
  // that item since `template_id` stays null).
  const templatesQuery = useLaboratoryTemplates(true);
  const labTemplateOptions = (templatesQuery.data ?? [])
    .filter((t) => !selectedLabItems.includes(t.testName))
    .map((t) => ({ value: t.testName, label: t.testName }));

  const isLoading = ordersQuery.isLoading || proceduresQuery.isLoading || referralsQuery.isLoading;
  if (isLoading) return <SkeletonList rows={4} />;

  const addLabItem = (testName: string) => {
    setSelectedLabItems((names) => (names.includes(testName) ? names : [...names, testName]));
  };
  const removeLabItem = (testName: string) => setSelectedLabItems((names) => names.filter((n) => n !== testName));

  const submitOrder = () => {
    if (orderForm.category === "Laboratory") {
      if (selectedLabItems.length === 0) return;
      createOrder.mutate(
        {
          orderCategory: "Laboratory", priority: orderForm.priority,
          scheduledDate: orderForm.scheduledDate || null, clinicalNotes: orderForm.notes || null,
          items: selectedLabItems.map((itemName): OrderItemInput => ({ itemName })),
        },
        { onSuccess: () => { setSelectedLabItems([]); setOrderForm((f) => ({ ...f, notes: "" })); } }
      );
      return;
    }
    if (!orderForm.itemName.trim()) return;
    const item: OrderItemInput = { itemName: orderForm.itemName };
    if (orderForm.category === "Radiology") {
      item.examType = orderForm.examType || null;
      item.bodyPart = orderForm.bodyPart || null;
      item.clinicalIndication = orderForm.indication || null;
    }
    createOrder.mutate(
      {
        orderCategory: orderForm.category, priority: orderForm.priority,
        scheduledDate: orderForm.scheduledDate || null, clinicalNotes: orderForm.notes || null,
        items: [item],
      },
      { onSuccess: () => setOrderForm((f) => ({ ...f, itemName: "", examType: "", bodyPart: "", indication: "", notes: "" })) }
    );
  };

  const createDisabled =
    createOrder.isPending || (orderForm.category === "Laboratory" ? selectedLabItems.length === 0 : !orderForm.itemName.trim());

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader><CardTitle>Orders</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          {ordersQuery.data && ordersQuery.data.length > 0 ? (
            <ul className="space-y-2">
              {ordersQuery.data.map((order) => (
                <li key={order.id} className="rounded-md border border-border p-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs text-muted-foreground">{order.orderNumber}</span>
                    <Badge variant="secondary">{order.orderCategory}</Badge>
                    <Badge variant={order.priority === "STAT" ? "destructive" : "secondary"}>{order.priority}</Badge>
                    <Badge variant={STATUS_VARIANT[order.status]}>{order.status}</Badge>
                    {/* Print is available for every Order category created
                        through this tab (Laboratory/Radiology/Vaccination/
                        Custom - see `ORDER_CATEGORIES` below; `Procedure`/
                        `Referral` are OrderCategory enum values that are
                        never actually used to create an `orders` row, since
                        those flows write to their own separate tables and
                        already have their own print dialogs). */}
                    <Button type="button" variant="outline" size="sm" className="ml-auto h-7 text-xs" onClick={() => setPrintOrder(order)}>
                      Print
                    </Button>
                    {canEdit ? (
                      <Select
                        className="h-7 w-36 text-xs"
                        value={order.status}
                        onChange={(e) => updateOrderStatus.mutate({ orderId: order.id, status: e.target.value as OrderStatus })}
                      >
                        {ORDER_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                      </Select>
                    ) : null}
                  </div>
                  <ul className="mt-2 space-y-1 text-muted-foreground">
                    {order.items.map((item) => (
                      <li key={item.id}>
                        {item.itemName}
                        {item.examType ? ` — ${item.examType}${item.bodyPart ? ` (${item.bodyPart})` : ""}` : ""}
                      </li>
                    ))}
                  </ul>
                  {order.clinicalNotes ? <p className="mt-1 text-xs text-muted-foreground">{order.clinicalNotes}</p> : null}
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No orders yet" description="Create a Laboratory, Radiology, Vaccination, or Custom order below." />
          )}

          {canEdit ? (
            <div className="space-y-3 border-t border-border pt-4">
              <div className="grid gap-3 sm:grid-cols-3">
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Category</label>
                  <Select
                    value={orderForm.category}
                    onChange={(e) => {
                      const category = e.target.value as OrderCategory;
                      setOrderForm((f) => ({ ...f, category }));
                      // Switching away from Laboratory drops any in-progress
                      // multi-select so a stale pending selection can't leak
                      // into a different category's single-item submit.
                      if (category !== "Laboratory") setSelectedLabItems([]);
                    }}
                  >
                    {availableCategories.map((c) => <option key={c} value={c}>{c}</option>)}
                  </Select>
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Priority</label>
                  <Select value={orderForm.priority} onChange={(e) => setOrderForm((f) => ({ ...f, priority: e.target.value as OrderPriority }))}>
                    <option value="Routine">Routine</option>
                    <option value="STAT">STAT</option>
                  </Select>
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Scheduled date (optional)</label>
                  <Input type="date" value={orderForm.scheduledDate} onChange={(e) => setOrderForm((f) => ({ ...f, scheduledDate: e.target.value }))} />
                </div>
              </div>
              {orderForm.category === "Laboratory" ? (
                <div className="space-y-2">
                  <label className="text-xs font-medium text-muted-foreground">Laboratory requests</label>
                  <SearchableSelect
                    options={labTemplateOptions}
                    value=""
                    onChange={addLabItem}
                    placeholder={templatesQuery.isLoading ? "Loading test catalog…" : "Search laboratory test…"}
                    emptyLabel={templatesQuery.data?.length ? "No matching tests." : "No laboratory tests configured for this clinic yet."}
                    disabled={templatesQuery.isLoading}
                  />
                  {selectedLabItems.length > 0 ? (
                    <ul className="space-y-1">
                      {selectedLabItems.map((name) => (
                        <li key={name} className="flex items-center justify-between rounded-md border border-border bg-muted/40 px-3 py-1.5 text-sm">
                          <span>{name}</span>
                          <Button type="button" variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={() => removeLabItem(name)}>
                            Remove
                          </Button>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs text-muted-foreground">Select one or more tests - all selected tests submit together as one Order.</p>
                  )}
                </div>
              ) : (
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Item / test name</label>
                  <Input value={orderForm.itemName} onChange={(e) => setOrderForm((f) => ({ ...f, itemName: e.target.value }))} placeholder="e.g. Chest X-Ray" />
                </div>
              )}
              {orderForm.category === "Radiology" ? (
                <div className="grid gap-3 sm:grid-cols-3">
                  <div>
                    <label className="text-xs font-medium text-muted-foreground">Exam type</label>
                    <Input value={orderForm.examType} onChange={(e) => setOrderForm((f) => ({ ...f, examType: e.target.value }))} />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground">Body part</label>
                    <Input value={orderForm.bodyPart} onChange={(e) => setOrderForm((f) => ({ ...f, bodyPart: e.target.value }))} />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground">Clinical indication</label>
                    <Input value={orderForm.indication} onChange={(e) => setOrderForm((f) => ({ ...f, indication: e.target.value }))} />
                  </div>
                </div>
              ) : null}
              <div>
                <label className="text-xs font-medium text-muted-foreground">Clinical notes (optional)</label>
                <Textarea rows={2} value={orderForm.notes} onChange={(e) => setOrderForm((f) => ({ ...f, notes: e.target.value }))} />
              </div>
              <Button type="button" onClick={submitOrder} disabled={createDisabled}>
                Create Order
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Procedures</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          {proceduresQuery.data && proceduresQuery.data.length > 0 ? (
            <ul className="space-y-2 text-sm">
              {proceduresQuery.data.map((p) => (
                <li key={p.id} className="rounded-md border border-border p-3">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{p.procedureName}</span>
                    <Badge variant={STATUS_VARIANT[p.status]}>{p.status}</Badge>
                    <Button type="button" variant="outline" size="sm" className="ml-auto h-7 text-xs" onClick={() => setPrintProcedure(p)}>
                      Print
                    </Button>
                  </div>
                  {p.notes ? <p className="mt-1 text-muted-foreground">{p.notes}</p> : null}
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No procedures recorded" description="Record a procedure performed during this consultation." />
          )}
          {canEdit ? (
            <div className="flex flex-wrap items-end gap-3 border-t border-border pt-4">
              <div>
                <label className="text-xs font-medium text-muted-foreground">Procedure</label>
                <Input value={procedureForm.name} onChange={(e) => setProcedureForm((f) => ({ ...f, name: e.target.value }))} placeholder="e.g. Wound Dressing" />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground">Date (optional)</label>
                <Input type="date" value={procedureForm.date} onChange={(e) => setProcedureForm((f) => ({ ...f, date: e.target.value }))} />
              </div>
              <div className="flex-1 min-w-[200px]">
                <label className="text-xs font-medium text-muted-foreground">Notes</label>
                <Input value={procedureForm.notes} onChange={(e) => setProcedureForm((f) => ({ ...f, notes: e.target.value }))} />
              </div>
              <Button
                type="button"
                disabled={createProcedure.isPending || !procedureForm.name.trim()}
                onClick={() =>
                  createProcedure.mutate(
                    { procedureName: procedureForm.name, procedureDate: procedureForm.date || null, notes: procedureForm.notes || null },
                    { onSuccess: () => setProcedureForm({ name: "", date: "", notes: "" }) }
                  )
                }
              >
                Add Procedure
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Referrals</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          {referralsQuery.data && referralsQuery.data.length > 0 ? (
            <ul className="space-y-2 text-sm">
              {referralsQuery.data.map((r) => (
                <li key={r.id} className="rounded-md border border-border p-3">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{r.referredTo}</span>
                    <Badge variant={STATUS_VARIANT[r.status]}>{r.status}</Badge>
                    <Button type="button" variant="outline" size="sm" className="ml-auto h-7 text-xs" onClick={() => setPrintReferral(r)}>
                      Print
                    </Button>
                  </div>
                  {r.reason ? <p className="mt-1 text-muted-foreground">{r.reason}</p> : null}
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No referrals recorded" description="Refer the patient to a specialist or facility." />
          )}
          {canEdit ? (
            <div className="flex flex-wrap items-end gap-3 border-t border-border pt-4">
              <div>
                <label className="text-xs font-medium text-muted-foreground">Referred to</label>
                <Input value={referralForm.referredTo} onChange={(e) => setReferralForm((f) => ({ ...f, referredTo: e.target.value }))} placeholder="e.g. Dr. Cardio Specialist" />
              </div>
              <div className="flex-1 min-w-[200px]">
                <label className="text-xs font-medium text-muted-foreground">Reason</label>
                <Input value={referralForm.reason} onChange={(e) => setReferralForm((f) => ({ ...f, reason: e.target.value }))} />
              </div>
              <Button
                type="button"
                disabled={createReferral.isPending || !referralForm.referredTo.trim()}
                onClick={() =>
                  createReferral.mutate(
                    { referredTo: referralForm.referredTo, reason: referralForm.reason || null, notes: referralForm.notes || null },
                    { onSuccess: () => setReferralForm({ referredTo: "", reason: "", notes: "" }) }
                  )
                }
              >
                Add Referral
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <PrintableDocumentDialog
        open={printOrder !== null}
        onOpenChange={(open) => !open && setPrintOrder(null)}
        title={printOrder ? ORDER_PRINT_TITLE[printOrder.orderCategory] ?? "Order Request" : "Order Request"}
        printableId="lab-request-printable"
      >
        {printOrder ? (
          <>
            <div className="text-center">
              <p className="font-semibold">{ORDER_PRINT_TITLE[printOrder.orderCategory] ?? "Order Request"}</p>
              <p className="text-xs text-muted-foreground">{printOrder.orderNumber}</p>
            </div>
            <div className="border-t border-dashed pt-2 space-y-1">
              <PrintRow label="Visit #" value={visitNumber ?? "-"} />
              <PrintRow label="Patient" value={patientName ?? "-"} />
              <PrintRow label="Ordering doctor" value={doctorName ?? "-"} />
              <PrintRow label="Priority" value={printOrder.priority} />
              <PrintRow label="Date" value={formatDateTime(printOrder.createdAt)} />
            </div>
            <div className="border-t border-dashed pt-2 space-y-1">
              <p className="font-medium">{ORDER_PRINT_ITEMS_LABEL[printOrder.orderCategory] ?? "Requested items"}</p>
              <ul className="list-disc pl-4">
                {printOrder.items.map((item) => (
                  <li key={item.id}>{item.itemName}</li>
                ))}
              </ul>
            </div>
            {printOrder.clinicalNotes ? (
              <div className="border-t border-dashed pt-2">
                <p className="font-medium">Clinical notes</p>
                <p>{printOrder.clinicalNotes}</p>
              </div>
            ) : null}
            {/* Orders/Procedures are mutable, ongoing clinical records (status
                cycles Requested -> Collected -> Processing -> Completed, no
                one-time "issue" step) - unlike Referral/Prescription/Medical
                Certificate, there is no document-level signature snapshot
                for them (see ClinicalOrdersTab's module notes). The doctor's
                CURRENT signature is used here, live, via the same
                `/doctors/{id}/signature/file` endpoint the E-Signature
                settings page itself uses - no new endpoint. */}
            <DoctorSignatureBlock
              doctorName={doctorName}
              doctorPrcLicense={doctorPrcLicense}
              doctorPtrNumber={doctorPtrNumber}
              clinicLicenseNumber={clinic?.license_number}
              signatureFileApiPath={printOrder.doctorId ? `/doctors/${printOrder.doctorId}/signature/file` : null}
              fallbackLabel="Ordering Physician"
              testId="order-signature-block"
            />
          </>
        ) : null}
      </PrintableDocumentDialog>

      <PrintableDocumentDialog
        open={printProcedure !== null}
        onOpenChange={(open) => !open && setPrintProcedure(null)}
        title="Procedure Record"
        printableId="procedure-printable"
      >
        {printProcedure ? (
          <>
            <div className="text-center">
              <p className="font-semibold">Procedure Record</p>
            </div>
            <div className="border-t border-dashed pt-2 space-y-1">
              <PrintRow label="Visit #" value={visitNumber ?? "-"} />
              <PrintRow label="Patient" value={patientName ?? "-"} />
              <PrintRow label="Performing doctor" value={doctorName ?? "-"} />
              <PrintRow label="Procedure" value={printProcedure.procedureName} />
              <PrintRow label="Date" value={printProcedure.procedureDate ? formatDateTime(printProcedure.procedureDate) : formatDateTime(printProcedure.createdAt)} />
            </div>
            {printProcedure.notes ? (
              <div className="border-t border-dashed pt-2">
                <p className="font-medium">Notes</p>
                <p>{printProcedure.notes}</p>
              </div>
            ) : null}
            <DoctorSignatureBlock
              doctorName={doctorName}
              doctorPrcLicense={doctorPrcLicense}
              doctorPtrNumber={doctorPtrNumber}
              clinicLicenseNumber={clinic?.license_number}
              signatureFileApiPath={printProcedure.doctorId ? `/doctors/${printProcedure.doctorId}/signature/file` : null}
              fallbackLabel="Performing Physician"
              testId="procedure-signature-block"
            />
          </>
        ) : null}
      </PrintableDocumentDialog>

      <PrintableDocumentDialog
        open={printReferral !== null}
        onOpenChange={(open) => !open && setPrintReferral(null)}
        title="Referral Letter"
        printableId="referral-printable"
      >
        {printReferral ? (
          <>
            <div className="text-center">
              <p className="font-semibold">Referral Letter</p>
            </div>
            <div className="border-t border-dashed pt-2 space-y-1">
              <PrintRow label="Visit #" value={visitNumber ?? "-"} />
              <PrintRow label="Patient" value={patientName ?? "-"} />
              <PrintRow label="Referring doctor" value={doctorName ?? "-"} />
              <PrintRow label="Referred to" value={printReferral.referredTo} />
              <PrintRow label="Date" value={formatDateTime(printReferral.createdAt)} />
            </div>
            {printReferral.reason ? (
              <div className="border-t border-dashed pt-2">
                <p className="font-medium">Reason</p>
                <p>{printReferral.reason}</p>
              </div>
            ) : null}
            {printReferral.notes ? (
              <div className="border-t border-dashed pt-2">
                <p className="font-medium">Notes</p>
                <p>{printReferral.notes}</p>
              </div>
            ) : null}
            <DoctorSignatureBlock
              doctorName={doctorName}
              doctorPrcLicense={doctorPrcLicense}
              doctorPtrNumber={doctorPtrNumber}
              clinicLicenseNumber={clinic?.license_number}
              signatureFileApiPath={printReferral.doctorSignatureSnapshotUrl ? `/referrals/${printReferral.id}/signature/file` : null}
              fallbackLabel="Referring Physician"
              testId="referral-signature-block"
            />
          </>
        ) : null}
      </PrintableDocumentDialog>
    </div>
  );
}

function PrintRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span>{value}</span>
    </div>
  );
}
