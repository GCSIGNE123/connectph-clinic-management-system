"use client";

import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { useCurrentShift, useStartShift, useCloseShift, useShift } from "@/features/shifts/hooks/use-shifts";
import type { Shift } from "@/features/shifts/types";

function peso(value: string | null | undefined): string {
  const n = Number(value ?? 0);
  return `₱${n.toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-border py-2 text-sm last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium text-foreground">{value}</span>
    </div>
  );
}

function StartShiftForm() {
  const [openingCash, setOpeningCash] = useState("");
  const startShift = useStartShift();

  return (
    <Card>
      <CardContent className="space-y-4 p-4">
        <div>
          <h2 className="text-base font-semibold text-foreground">Start your shift</h2>
          <p className="text-sm text-muted-foreground">
            Count your starting cash drawer and enter it below before you begin taking payments.
          </p>
        </div>
        <div className="max-w-xs space-y-1">
          <Label htmlFor="opening-cash">Opening cash</Label>
          <Input
            id="opening-cash"
            type="number"
            min="0"
            step="0.01"
            value={openingCash}
            onChange={(e) => setOpeningCash(e.target.value)}
            placeholder="0.00"
          />
        </div>
        {startShift.isError ? (
          <p className="text-sm text-destructive">
            {(startShift.error as Error)?.message ?? "Could not start shift."}
          </p>
        ) : null}
        <Button
          type="button"
          disabled={!openingCash || Number(openingCash) < 0 || startShift.isPending}
          onClick={() => startShift.mutate({ openingCash: Number(openingCash) })}
        >
          Start Shift
        </Button>
      </CardContent>
    </Card>
  );
}

function LiveSummary({ shift }: { shift: Shift }) {
  const { summary } = shift;
  return (
    <Card>
      <CardContent className="space-y-1 p-4">
        <h2 className="mb-2 text-base font-semibold text-foreground">Live Summary</h2>
        <SummaryRow label="Cash payments" value={peso(summary.cashCollections)} />
        <SummaryRow label="GCash / e-wallet payments" value={peso(summary.gcashCollections)} />
        <SummaryRow label="Card payments" value={peso(summary.cardCollections)} />
        <SummaryRow label="Other payments" value={peso(summary.otherCollections)} />
        <SummaryRow label="Total collections" value={peso(summary.totalCollections)} />
        <SummaryRow label="Discounts given" value={peso(summary.discountsGiven)} />
        <SummaryRow label="Refunds" value={peso(summary.totalRefunds)} />
      </CardContent>
    </Card>
  );
}

function CloseShiftForm({ shift, onClosed }: { shift: Shift; onClosed: (shiftId: string) => void }) {
  const [actualCash, setActualCash] = useState("");
  const [notes, setNotes] = useState("");
  const closeShift = useCloseShift();

  return (
    <Card>
      <CardContent className="space-y-4 p-4">
        <div>
          <h2 className="text-base font-semibold text-foreground">End of shift</h2>
          <p className="text-sm text-muted-foreground">Count the cash drawer and enter the actual amount.</p>
        </div>
        <div className="max-w-xs space-y-1">
          <Label htmlFor="actual-cash">Actual cash count</Label>
          <Input
            id="actual-cash"
            type="number"
            min="0"
            step="0.01"
            value={actualCash}
            onChange={(e) => setActualCash(e.target.value)}
            placeholder="0.00"
          />
        </div>
        <div className="max-w-md space-y-1">
          <Label htmlFor="notes">Notes (optional)</Label>
          <Textarea id="notes" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </div>
        {closeShift.isError ? (
          <p className="text-sm text-destructive">{(closeShift.error as Error)?.message ?? "Could not close shift."}</p>
        ) : null}
        <Button
          type="button"
          variant="destructive"
          disabled={!actualCash || Number(actualCash) < 0 || closeShift.isPending}
          onClick={() =>
            closeShift.mutate(
              { shiftId: shift.id, actualCashCount: Number(actualCash), notes: notes || undefined },
              { onSuccess: () => onClosed(shift.id) }
            )
          }
        >
          Close Shift
        </Button>
      </CardContent>
    </Card>
  );
}

function ShiftReport({ shift }: { shift: Shift }) {
  const difference = Number(shift.cashDifference ?? 0);
  const isOver = difference > 0;
  const isShort = difference < 0;
  return (
    <Card>
      <CardContent className="space-y-1 p-4">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-base font-semibold text-foreground">Shift Summary Report</h2>
          <Badge variant={shift.status === "Open" ? "default" : "secondary"}>{shift.status}</Badge>
        </div>
        <SummaryRow label="Opening cash" value={peso(shift.openingCash)} />
        <SummaryRow label="Cash sales" value={peso(shift.summary.cashCollections)} />
        <SummaryRow
          label="Non-cash payments"
          value={peso(
            (
              Number(shift.summary.gcashCollections) +
              Number(shift.summary.cardCollections) +
              Number(shift.summary.otherCollections)
            ).toString()
          )}
        />
        <SummaryRow label="Discounts" value={peso(shift.summary.discountsGiven)} />
        <SummaryRow label="Expected cash" value={peso(shift.expectedCash)} />
        <SummaryRow label="Actual cash" value={peso(shift.actualCashCount)} />
        <div className="flex items-center justify-between py-2 text-sm">
          <span className="text-muted-foreground">Variance</span>
          <span
            className={
              isOver
                ? "font-semibold text-emerald-600"
                : isShort
                  ? "font-semibold text-destructive"
                  : "font-medium text-foreground"
            }
          >
            {peso(Math.abs(difference).toString())} {isOver ? "(Over)" : isShort ? "(Short)" : "(Exact)"}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Phase 21: Receptionist Shift Management. Beginning-of-shift: opening cash
 * form. During-shift: live-computed summary polled every 15s. End-of-shift:
 * actual cash count input, then the closed shift's report (still viewable
 * here right after closing, since `GET /shifts/current` no longer returns it
 * but the mutation result / a `GET /shifts/{id}` does).
 */
export default function ShiftsPage() {
  const { data: currentShift, isLoading } = useCurrentShift();
  // Tracked explicitly (not just the mutation's transient `data`/`isSuccess`
  // state) so the just-closed report survives re-renders/refetches that
  // happen as `shifts/current` gets invalidated right after close.
  const [justClosedShiftId, setJustClosedShiftId] = useState<string | null>(null);
  const { data: justClosedShift } = useShift(justClosedShiftId ?? undefined);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Shift</h1>
        <p className="text-sm text-muted-foreground">Track your cash drawer for daily cash accountability.</p>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : currentShift ? (
        <>
          <LiveSummary shift={currentShift} />
          <CloseShiftForm shift={currentShift} onClosed={(id) => setJustClosedShiftId(id)} />
        </>
      ) : justClosedShift ? (
        <ShiftReport shift={justClosedShift} />
      ) : (
        <StartShiftForm />
      )}
    </div>
  );
}
