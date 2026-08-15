"use client";

import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/layout/EmptyState";
import { useOrdersForVisit } from "@/features/clinical-orders/hooks/use-clinical-orders";
import { OrderDetailDialog } from "@/features/clinical-orders/components/OrderDetailDialog";
import type { Order } from "@/features/clinical-orders/types";

/** Read-only Orders summary, matching the Phase 6-8 placeholder-card
 * pattern now made real (Phase 9). Editing happens on the Consultation
 * page's Orders tab, not here. Feature 5 Part B: rows are clickable
 * (chevron affordance + hover, not color alone) and open a read-only
 * detail dialog built entirely from data this card already fetched - no
 * new permission surface. */
export function VisitOrdersCard({ visitId }: { visitId: string }) {
  const { data: orders, isLoading } = useOrdersForVisit(visitId);
  const [selected, setSelected] = useState<Order | null>(null);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Orders</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : orders && orders.length > 0 ? (
          <ul className="space-y-2 text-sm">
            {orders.map((order) => (
              <li
                key={order.id}
                role="button"
                tabIndex={0}
                onClick={() => setSelected(order)}
                onKeyDown={(e) => e.key === "Enter" && setSelected(order)}
                className="flex cursor-pointer items-center justify-between gap-2 rounded-md border-b border-border/50 py-1 pr-1 last:border-0 hover:bg-accent/50"
              >
                <span>
                  <span className="font-mono text-xs text-muted-foreground">{order.orderNumber}</span>{" "}
                  <Badge variant="secondary">{order.orderCategory}</Badge>
                </span>
                <span className="flex items-center gap-2">
                  <Badge variant={order.status === "Completed" ? "success" : order.status === "Cancelled" ? "destructive" : "secondary"}>
                    {order.status}
                  </Badge>
                  <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No orders yet" description="Orders created during this visit's consultation will appear here." />
        )}
      </CardContent>
      <OrderDetailDialog order={selected} open={selected !== null} onOpenChange={(open) => !open && setSelected(null)} />
    </Card>
  );
}
