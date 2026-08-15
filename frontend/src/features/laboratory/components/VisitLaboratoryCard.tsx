"use client";

import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/layout/EmptyState";
import { useLaboratoryForVisit } from "@/features/laboratory/hooks/use-laboratory";
import { LaboratoryStatusBadge } from "@/features/laboratory/components/LaboratoryStatusBadge";
import { LaboratoryOrderDetailDialog } from "@/features/laboratory/components/LaboratoryOrderDetailDialog";
import type { LaboratoryOrder } from "@/features/laboratory/types";

/** Visit-level Laboratory tab/card (Phase 10) - distinct from
 * `VisitOrdersCard` (which shows the generic Phase 9 Order rows for every
 * category): this shows the fuller lab-specific detail (status lifecycle,
 * entered results, attachment count) that only exists once a
 * Laboratory-category order has its `laboratory_orders` workflow record
 * attached. Feature 5 Part B: rows are clickable, same chevron + hover
 * affordance as `VisitOrdersCard`/`VisitPrescriptionsCard`. */
export function VisitLaboratoryCard({ visitId }: { visitId: string }) {
  const { data: labOrders, isLoading } = useLaboratoryForVisit(visitId);
  const [selected, setSelected] = useState<LaboratoryOrder | null>(null);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Laboratory</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : labOrders && labOrders.length > 0 ? (
          <ul className="space-y-3 text-sm">
            {labOrders.map((lo) => (
              <li
                key={lo.id}
                role="button"
                tabIndex={0}
                onClick={() => setSelected(lo)}
                onKeyDown={(e) => e.key === "Enter" && setSelected(lo)}
                className="cursor-pointer rounded-md border-b border-border/50 pb-2 pr-1 last:border-0 hover:bg-accent/50"
              >
                <div className="flex items-center justify-between gap-2">
                  <span>
                    <span className="font-mono text-xs text-muted-foreground">{lo.orderNumber}</span> {lo.testType}
                  </span>
                  <span className="flex items-center gap-2">
                    <LaboratoryStatusBadge status={lo.status} />
                    <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  </span>
                </div>
                {lo.results.length > 0 && (
                  <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                    {lo.results.map((r) => (
                      <li key={r.id}>
                        {r.parameterName}: {r.resultType === "Numeric" ? r.numericValue : r.textValue}
                        {r.units ? ` ${r.units}` : ""}
                        {r.normalRange ? ` (Normal: ${r.normalRange})` : ""}
                        {r.interpretation ? ` — ${r.interpretation}` : ""}
                      </li>
                    ))}
                  </ul>
                )}
                {lo.attachments.length > 0 && (
                  <p className="mt-1 text-xs text-muted-foreground">{lo.attachments.length} attachment(s)</p>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No laboratory orders yet" description="Laboratory orders created during this visit's consultation will appear here." />
        )}
      </CardContent>
      <LaboratoryOrderDetailDialog order={selected} open={selected !== null} onOpenChange={(open) => !open && setSelected(null)} />
    </Card>
  );
}
