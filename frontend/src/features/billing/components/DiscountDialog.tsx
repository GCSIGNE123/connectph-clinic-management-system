"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { useApplyDiscount } from "@/features/billing/hooks/use-invoice-mutations";
import type { DiscountCalculationType, DiscountType } from "@/features/billing/types";

const DISCOUNT_TYPES: DiscountType[] = ["SeniorCitizen", "PWD", "Employee", "Custom"];

export function DiscountDialog({
  open,
  onOpenChange,
  invoiceId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  invoiceId: string;
}) {
  const [discountType, setDiscountType] = useState<DiscountType>("SeniorCitizen");
  const [calculationType, setCalculationType] = useState<DiscountCalculationType>("Percentage");
  const [value, setValue] = useState("20");
  const [reason, setReason] = useState("");
  const applyDiscount = useApplyDiscount(invoiceId);

  async function handleSubmit() {
    const numeric = Number(value);
    if (!(numeric > 0)) return;
    await applyDiscount.mutateAsync({ discountType, calculationType, value: numeric, reason: reason || undefined });
    onOpenChange(false);
    setReason("");
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Apply discount</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <Label>Discount type</Label>
            <Select value={discountType} onChange={(e) => setDiscountType(e.target.value as DiscountType)}>
              {DISCOUNT_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Calculation</Label>
              <Select value={calculationType} onChange={(e) => setCalculationType(e.target.value as DiscountCalculationType)}>
                <option value="Percentage">Percentage (%)</option>
                <option value="FixedAmount">Fixed amount (₱)</option>
              </Select>
            </div>
            <div>
              <Label>Value</Label>
              <Input type="number" min="0" step="0.01" value={value} onChange={(e) => setValue(e.target.value)} />
            </div>
          </div>
          <div>
            <Label>Reason (optional)</Label>
            <Textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Senior citizen ID verified" />
          </div>
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" onClick={handleSubmit} disabled={applyDiscount.isPending}>
            {applyDiscount.isPending ? "Applying..." : "Apply discount"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
