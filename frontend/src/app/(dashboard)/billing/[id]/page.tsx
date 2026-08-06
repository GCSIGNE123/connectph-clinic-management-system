"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertDialog } from "@/components/ui/alert-dialog";
import { useInvoice } from "@/features/billing/hooks/use-invoice";
import { useRemoveInvoiceItem, useRemoveDiscount } from "@/features/billing/hooks/use-invoice-mutations";
import { useVoidPayment } from "@/features/billing/hooks/use-payments";
import { InvoiceStatusBadge } from "@/features/billing/components/InvoiceStatusBadge";
import { AddItemDialog } from "@/features/billing/components/AddItemDialog";
import { DiscountDialog } from "@/features/billing/components/DiscountDialog";
import { PaymentDialog } from "@/features/billing/components/PaymentDialog";
import { ReceiptDialog } from "@/features/billing/components/ReceiptDialog";

const EDITABLE_STATUSES = new Set(["Draft", "PendingPayment"]);

export default function InvoiceDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { data: invoice, isLoading } = useInvoice(params.id);
  const removeItem = useRemoveInvoiceItem(params.id);
  const removeDiscount = useRemoveDiscount(params.id);
  const voidPayment = useVoidPayment();

  const [addItemOpen, setAddItemOpen] = useState(false);
  const [discountOpen, setDiscountOpen] = useState(false);
  const [paymentOpen, setPaymentOpen] = useState(false);
  const [receiptOpen, setReceiptOpen] = useState(false);
  const [voidTarget, setVoidTarget] = useState<string | null>(null);

  if (isLoading || !invoice) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const editable = EDITABLE_STATUSES.has(invoice.status);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button type="button" variant="ghost" size="icon" onClick={() => router.push("/billing")}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{invoice.invoiceNumber}</h1>
          <p className="text-sm text-muted-foreground">
            {invoice.patientName} &middot; Visit {invoice.visitNumber} &middot; {invoice.doctorName ?? "No doctor"}
          </p>
        </div>
        <InvoiceStatusBadge status={invoice.status} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>Line items</CardTitle>
              {editable ? (
                <Button type="button" size="sm" onClick={() => setAddItemOpen(true)}>
                  + Add item
                </Button>
              ) : null}
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Description</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead className="text-right">Qty</TableHead>
                    <TableHead className="text-right">Unit Price</TableHead>
                    <TableHead className="text-right">Total</TableHead>
                    {editable ? <TableHead /> : null}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {invoice.items.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>{item.description}</TableCell>
                      <TableCell>{item.itemType}</TableCell>
                      <TableCell className="text-right">{item.quantity}</TableCell>
                      <TableCell className="text-right">₱{item.unitPrice.toFixed(2)}</TableCell>
                      <TableCell className="text-right">₱{item.lineTotal.toFixed(2)}</TableCell>
                      {editable ? (
                        <TableCell className="text-right">
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={() => removeItem.mutate(item.id)}
                            disabled={removeItem.isPending}
                          >
                            Remove
                          </Button>
                        </TableCell>
                      ) : null}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {invoice.discounts.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>Discounts</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {invoice.discounts.map((d) => (
                  <div key={d.id} className="flex items-center justify-between text-sm">
                    <span>
                      {d.discountType} ({d.calculationType === "Percentage" ? `${d.value}%` : `₱${d.value.toFixed(2)}`})
                      {d.reason ? ` — ${d.reason}` : ""}
                    </span>
                    <div className="flex items-center gap-3">
                      <span className="font-medium">-₱{d.amount.toFixed(2)}</span>
                      {editable ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => removeDiscount.mutate(d.id)}
                          disabled={removeDiscount.isPending}
                        >
                          Remove
                        </Button>
                      ) : null}
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}

          <Card>
            <CardHeader>
              <CardTitle>Payments</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {invoice.payments.length === 0 ? (
                <p className="p-4 text-sm text-muted-foreground">No payments recorded yet.</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Method</TableHead>
                      <TableHead>Reference</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Paid at</TableHead>
                      <TableHead className="text-right">Amount</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {invoice.payments.map((p) => (
                      <TableRow key={p.id}>
                        <TableCell>{p.paymentMethod}</TableCell>
                        <TableCell>{p.referenceNumber ?? "-"}</TableCell>
                        <TableCell>{p.status}</TableCell>
                        <TableCell>{new Date(p.paidAt).toLocaleString()}</TableCell>
                        <TableCell className="text-right">₱{p.amount.toFixed(2)}</TableCell>
                        <TableCell className="text-right">
                          {p.status === "Completed" ? (
                            <Button type="button" variant="ghost" size="sm" onClick={() => setVoidTarget(p.id)}>
                              Void
                            </Button>
                          ) : null}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Totals</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <TotalRow label="Subtotal" value={invoice.subtotal} />
              <TotalRow label="Discount" value={-invoice.discountTotal} />
              <TotalRow label="Grand total" value={invoice.grandTotal} strong />
              <TotalRow label="Amount paid" value={invoice.amountPaid} />
              <TotalRow label="Balance due" value={invoice.balanceDue} strong />
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-2 p-4">
              {editable ? (
                <Button type="button" variant="outline" className="w-full" onClick={() => setDiscountOpen(true)}>
                  Apply discount
                </Button>
              ) : null}
              {invoice.balanceDue > 0 && invoice.status !== "Cancelled" && invoice.status !== "Draft" ? (
                <Button type="button" className="w-full" onClick={() => setPaymentOpen(true)}>
                  Record payment
                </Button>
              ) : null}
              <Button type="button" variant="outline" className="w-full" onClick={() => setReceiptOpen(true)}>
                View / print receipt
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>

      <AddItemDialog open={addItemOpen} onOpenChange={setAddItemOpen} invoiceId={invoice.id} />
      <DiscountDialog open={discountOpen} onOpenChange={setDiscountOpen} invoiceId={invoice.id} />
      <PaymentDialog open={paymentOpen} onOpenChange={setPaymentOpen} invoiceId={invoice.id} balanceDue={invoice.balanceDue} />
      <ReceiptDialog open={receiptOpen} onOpenChange={setReceiptOpen} invoiceId={invoice.id} />
      <AlertDialog
        open={Boolean(voidTarget)}
        onOpenChange={(open) => !open && setVoidTarget(null)}
        title="Void this payment?"
        description="This will reduce the invoice's amount paid and may move its status backward. This cannot be undone."
        confirmLabel="Void payment"
        confirmVariant="destructive"
        isConfirming={voidPayment.isPending}
        onConfirm={() => {
          if (voidTarget) voidPayment.mutate(voidTarget, { onSuccess: () => setVoidTarget(null) });
        }}
      />
    </div>
  );
}

function TotalRow({ label, value, strong }: { label: string; value: number; strong?: boolean }) {
  return (
    <div className={`flex items-center justify-between ${strong ? "font-semibold text-foreground" : "text-muted-foreground"}`}>
      <span>{label}</span>
      <span>₱{value.toFixed(2)}</span>
    </div>
  );
}
