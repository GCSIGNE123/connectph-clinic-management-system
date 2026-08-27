"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState } from "@/components/layout/EmptyState";
import { SkeletonList } from "@/components/layout/LoadingSkeletons";
import { apiClient } from "@/lib/api-client";
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

  const isLoading = ordersQuery.isLoading || proceduresQuery.isLoading || referralsQuery.isLoading;
  if (isLoading) return <SkeletonList rows={4} />;

  const submitOrder = () => {
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
                  <Select value={orderForm.category} onChange={(e) => setOrderForm((f) => ({ ...f, category: e.target.value as OrderCategory }))}>
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
              <div>
                <label className="text-xs font-medium text-muted-foreground">Item / test name</label>
                <Input value={orderForm.itemName} onChange={(e) => setOrderForm((f) => ({ ...f, itemName: e.target.value }))} placeholder="e.g. CBC, Chest X-Ray" />
              </div>
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
              <Button type="button" onClick={submitOrder} disabled={createOrder.isPending || !orderForm.itemName.trim()}>
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
