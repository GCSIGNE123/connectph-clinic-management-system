"use client";

import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { billingApi } from "@/features/billing/api/billing-api";
import type { ReceiptPayload } from "@/features/billing/types";

/** Print-friendly receipt preview - follows the same
 * hide-everything-but-#printable / `window.print()` pattern already used by
 * `features/queue/components/QueueSlipDialog.tsx` for the Queue Slip. */
export function ReceiptDialog({
  open,
  onOpenChange,
  invoiceId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  invoiceId: string;
}) {
  const [receipt, setReceipt] = useState<ReceiptPayload | null>(null);
  const [printed, setPrinted] = useState(false);

  useEffect(() => {
    if (!open) {
      setReceipt(null);
      setPrinted(false);
      return;
    }
    billingApi.getReceipt(invoiceId).then(setReceipt).catch(() => setReceipt(null));
  }, [open, invoiceId]);

  async function handlePrint() {
    if (!printed) {
      try {
        const printedReceipt = await billingApi.printReceipt(invoiceId);
        setReceipt(printedReceipt);
        setPrinted(true);
      } catch {
        // fall through to still let the user print the preview
      }
    }
    window.print();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Receipt</DialogTitle>
        </DialogHeader>

        <div id="billing-receipt-printable" className="space-y-3 rounded-md border border-border p-4 text-sm">
          {receipt ? (
            <>
              <div className="text-center">
                <p className="font-semibold">{receipt.clinicName}</p>
                {receipt.branchName ? <p className="text-xs text-muted-foreground">{receipt.branchName}</p> : null}
              </div>
              <div className="border-t border-dashed pt-2 space-y-1">
                <Row label="Receipt #" value={receipt.receiptNumber} />
                <Row label="Invoice #" value={receipt.invoiceNumber} />
                <Row label="Visit #" value={receipt.visitNumber ?? "-"} />
                <Row label="Patient" value={receipt.patientName ?? "-"} />
                <Row label="Cashier" value={receipt.cashierName ?? "-"} />
                <Row label="Date" value={new Date(receipt.printedAt).toLocaleString()} />
              </div>
              <div className="border-t border-dashed pt-2 space-y-1">
                {receipt.items.map((item, idx) => (
                  <div key={idx} className="flex justify-between">
                    <span>
                      {item.description} x{item.quantity}
                    </span>
                    <span>₱{item.lineTotal.toFixed(2)}</span>
                  </div>
                ))}
              </div>
              {receipt.discounts.length > 0 ? (
                <div className="border-t border-dashed pt-2 space-y-1">
                  {receipt.discounts.map((d) => (
                    <div key={d.id} className="flex justify-between text-muted-foreground">
                      <span>{d.discountType} discount</span>
                      <span>-₱{d.amount.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              ) : null}
              <div className="border-t border-dashed pt-2 space-y-1">
                <Row label="Subtotal" value={`₱${receipt.subtotal.toFixed(2)}`} />
                <Row label="Discount" value={`-₱${receipt.discountTotal.toFixed(2)}`} />
                <Row label="Grand total" value={`₱${receipt.grandTotal.toFixed(2)}`} strong />
                <Row label="Amount paid" value={`₱${receipt.amountPaid.toFixed(2)}`} />
                <Row label="Balance due" value={`₱${receipt.balanceDue.toFixed(2)}`} />
              </div>
              {receipt.payments.length > 0 ? (
                <div className="border-t border-dashed pt-2 space-y-1">
                  {receipt.payments
                    .filter((p) => p.status === "Completed")
                    .map((p) => (
                      <div key={p.id} className="flex justify-between text-muted-foreground">
                        <span>
                          {p.paymentMethod}
                          {p.referenceNumber ? ` (${p.referenceNumber})` : ""}
                        </span>
                        <span>₱{p.amount.toFixed(2)}</span>
                      </div>
                    ))}
                </div>
              ) : null}
            </>
          ) : (
            <p className="text-center text-muted-foreground">Loading receipt...</p>
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          <Button type="button" onClick={handlePrint} disabled={!receipt}>
            Print
          </Button>
        </DialogFooter>
      </DialogContent>

      <style jsx global>{`
        @media print {
          body * {
            visibility: hidden;
          }
          #billing-receipt-printable,
          #billing-receipt-printable * {
            visibility: visible;
          }
          #billing-receipt-printable {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            border: none;
          }
        }
      `}</style>
    </Dialog>
  );
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className={`flex justify-between ${strong ? "font-semibold" : ""}`}>
      <span>{label}</span>
      <span>{value}</span>
    </div>
  );
}
