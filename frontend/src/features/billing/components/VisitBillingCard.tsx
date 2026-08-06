"use client";

import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/layout/EmptyState";
import { InvoiceStatusBadge } from "@/features/billing/components/InvoiceStatusBadge";
import { useInvoiceForVisit } from "@/features/billing/hooks/use-invoice";

/** Real "Billing" tab/card for the Visit Details page (Phase 9), replacing
 * the Phase 6-8 "coming soon" placeholder. */
export function VisitBillingCard({ visitId }: { visitId: string }) {
  const router = useRouter();
  const { data: invoice, isLoading } = useInvoiceForVisit(visitId);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Billing</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-20 w-full" />
        ) : !invoice ? (
          <EmptyState title="No invoice yet" description="An invoice is created automatically once the consultation is completed." />
        ) : (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-medium">{invoice.invoiceNumber}</span>
              <InvoiceStatusBadge status={invoice.status} />
            </div>
            <div className="flex justify-between text-sm text-muted-foreground">
              <span>Grand total</span>
              <span className="text-foreground">₱{invoice.grandTotal.toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-sm text-muted-foreground">
              <span>Balance due</span>
              <span className="text-foreground">₱{invoice.balanceDue.toFixed(2)}</span>
            </div>
            <Button type="button" size="sm" variant="outline" className="w-full" onClick={() => router.push(`/billing/${invoice.id}`)}>
              View invoice &amp; receipt
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
