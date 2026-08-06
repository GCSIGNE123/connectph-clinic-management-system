"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { useAddInvoiceItem } from "@/features/billing/hooks/use-invoice-mutations";
import type { InvoiceItemType } from "@/features/billing/types";

const ITEM_TYPES: InvoiceItemType[] = [
  "ConsultationFee", "FollowUpFee", "MedicalCertificate", "Laboratory", "XRay", "Procedure", "Vaccination", "Custom",
];

export function AddItemDialog({ open, onOpenChange, invoiceId }: { open: boolean; onOpenChange: (open: boolean) => void; invoiceId: string }) {
  const [description, setDescription] = useState("");
  const [itemType, setItemType] = useState<InvoiceItemType>("Custom");
  const [quantity, setQuantity] = useState("1");
  const [unitPrice, setUnitPrice] = useState("0");
  const addItem = useAddInvoiceItem(invoiceId);

  async function handleSubmit() {
    if (!description.trim()) return;
    await addItem.mutateAsync({
      description: description.trim(), itemType, quantity: Number(quantity) || 1, unitPrice: Number(unitPrice) || 0,
    });
    onOpenChange(false);
    setDescription("");
    setQuantity("1");
    setUnitPrice("0");
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add invoice item</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <Label>Description</Label>
            <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="e.g. Laboratory - CBC" />
          </div>
          <div>
            <Label>Item type</Label>
            <Select value={itemType} onChange={(e) => setItemType(e.target.value as InvoiceItemType)}>
              {ITEM_TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Quantity</Label>
              <Input type="number" min="1" step="1" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
            </div>
            <div>
              <Label>Unit price</Label>
              <Input type="number" min="0" step="0.01" value={unitPrice} onChange={(e) => setUnitPrice(e.target.value)} />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="button" onClick={handleSubmit} disabled={addItem.isPending}>
            {addItem.isPending ? "Adding..." : "Add item"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
