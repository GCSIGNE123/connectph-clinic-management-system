"use client";

import { useRouter } from "next/navigation";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

export interface ShiftRequiredDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Item 7 (Shift Enforcement) - the shared "you need an open shift" prompt,
 * used by the Queue page, the appointment check-in action, and the Payment
 * dialog (see `use-shift-required-error.ts`). Deliberately a single small
 * component so the copy/behaviour ("Start Shift" -> `/shifts`) stays
 * consistent across all three call sites instead of three near-duplicate
 * inline blocks.
 */
export function ShiftRequiredDialog({ open, onOpenChange }: ShiftRequiredDialogProps) {
  const router = useRouter();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Shift required</DialogTitle>
          <DialogDescription>Please start your shift before serving patients.</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" onClick={() => router.push("/shifts")}>
            Start Shift
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
