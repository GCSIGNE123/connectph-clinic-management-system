"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { validateSplitPayments } from "@/features/billing/calculations";
import { useRecordPayment } from "@/features/billing/hooks/use-payments";
import type { PaymentMethod } from "@/features/billing/types";
import { useShiftRequiredError } from "@/features/shifts/hooks/use-shift-required-error";
import { ShiftRequiredDialog } from "@/features/shifts/components/ShiftRequiredDialog";

const METHODS: PaymentMethod[] = ["Cash", "GCash", "BankTransfer", "CreditCard", "DebitCard"];

interface Row {
  id: string;
  paymentMethod: PaymentMethod;
  amount: string;
  referenceNumber: string;
}

function newRow(amount = ""): Row {
  return { id: crypto.randomUUID(), paymentMethod: "Cash", amount, referenceNumber: "" };
}

export function PaymentDialog({
  open,
  onOpenChange,
  invoiceId,
  balanceDue,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  invoiceId: string;
  balanceDue: number;
}) {
  const [rows, setRows] = useState<Row[]>([newRow(balanceDue.toFixed(2))]);
  const shiftError = useShiftRequiredError();
  const recordPayment = useRecordPayment(invoiceId, shiftError.handleError);

  const parsedRows = rows.map((r) => ({ ...r, amount: Number(r.amount) || 0 }));
  const validation = validateSplitPayments(parsedRows, balanceDue);

  function updateRow(id: string, patch: Partial<Row>) {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  }

  function addRow() {
    setRows((prev) => [...prev, newRow()]);
  }

  function removeRow(id: string) {
    setRows((prev) => (prev.length > 1 ? prev.filter((r) => r.id !== id) : prev));
  }

  async function handleSubmit() {
    if (!validation.valid) return;
    await recordPayment.mutateAsync(
      parsedRows.map((r) => ({
        paymentMethod: r.paymentMethod,
        amount: r.amount,
        referenceNumber: r.paymentMethod === "Cash" ? undefined : r.referenceNumber || undefined,
      }))
    );
    onOpenChange(false);
    setRows([newRow()]);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Record payment</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Balance due: <span className="font-semibold text-foreground">₱{balanceDue.toFixed(2)}</span>
          </p>

          {rows.map((row, idx) => (
            <div key={row.id} className="grid grid-cols-[1fr_1fr_1fr_auto] gap-2 items-end">
              <div>
                <Label>Method</Label>
                <Select value={row.paymentMethod} onChange={(e) => updateRow(row.id, { paymentMethod: e.target.value as PaymentMethod })}>
                  {METHODS.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label>Amount</Label>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={row.amount}
                  onChange={(e) => updateRow(row.id, { amount: e.target.value })}
                />
              </div>
              <div>
                <Label>Reference #</Label>
                <Input
                  value={row.referenceNumber}
                  disabled={row.paymentMethod === "Cash"}
                  onChange={(e) => updateRow(row.id, { referenceNumber: e.target.value })}
                  placeholder={row.paymentMethod === "Cash" ? "N/A" : "Ref. number"}
                />
              </div>
              <Button type="button" variant="ghost" size="sm" disabled={rows.length === 1} onClick={() => removeRow(row.id)}>
                &times;
              </Button>
              {idx === rows.length - 1 ? null : null}
            </div>
          ))}

          <Button type="button" variant="outline" size="sm" onClick={addRow}>
            + Add split payment
          </Button>

          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Total entered</span>
            <span className="font-medium">₱{validation.total.toFixed(2)}</span>
          </div>
          {!validation.valid && validation.message ? (
            <p className="text-sm text-destructive">{validation.message}</p>
          ) : null}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" onClick={handleSubmit} disabled={!validation.valid || recordPayment.isPending}>
            {recordPayment.isPending ? "Recording..." : "Record payment"}
          </Button>
        </DialogFooter>
      </DialogContent>
      <ShiftRequiredDialog open={shiftError.open} onOpenChange={shiftError.setOpen} />
    </Dialog>
  );
}
