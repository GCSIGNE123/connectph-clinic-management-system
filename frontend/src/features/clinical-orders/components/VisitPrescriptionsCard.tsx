"use client";

import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/layout/EmptyState";
import { usePrescriptionsForVisit } from "@/features/clinical-orders/hooks/use-clinical-orders";
import { PrescriptionDetailDialog } from "@/features/clinical-orders/components/PrescriptionDetailDialog";
import type { Prescription } from "@/features/clinical-orders/types";

/** Read-only Prescriptions summary for the Visit Details page. Feature 5
 * Part B: rows are clickable, same chevron + hover affordance as
 * `VisitOrdersCard`. */
export function VisitPrescriptionsCard({ visitId }: { visitId: string }) {
  const { data: prescriptions, isLoading } = usePrescriptionsForVisit(visitId);
  const [selected, setSelected] = useState<Prescription | null>(null);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Prescriptions</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : prescriptions && prescriptions.length > 0 ? (
          <ul className="space-y-2 text-sm">
            {prescriptions.map((rx) => (
              <li
                key={rx.id}
                role="button"
                tabIndex={0}
                onClick={() => setSelected(rx)}
                onKeyDown={(e) => e.key === "Enter" && setSelected(rx)}
                className="cursor-pointer rounded-md border-b border-border/50 py-1 pr-1 last:border-0 hover:bg-accent/50"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-xs text-muted-foreground">{rx.prescriptionNumber}</span>
                  <span className="flex items-center gap-2">
                    <Badge variant={rx.status === "Finalized" ? "success" : "secondary"}>{rx.status}</Badge>
                    <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  </span>
                </div>
                <p className="text-muted-foreground">{rx.items.map((i) => i.medicine).join(", ")}</p>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No prescriptions yet" description="Prescriptions written during this visit's consultation will appear here." />
        )}
      </CardContent>
      <PrescriptionDetailDialog prescription={selected} open={selected !== null} onOpenChange={(open) => !open && setSelected(null)} />
    </Card>
  );
}
