"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { createCrudApi } from "@/features/clinic-config/api/crud-factory";
import { MasterDataFormDialog } from "@/features/clinic-config/components/MasterDataFormDialog";
import { createCrudHooks } from "@/features/clinic-config/hooks/use-crud";
import type { Medicine, MedicineBatch } from "@/features/clinic-config/types";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { Role } from "@/types";

const medicinesApi = createCrudApi<Medicine>("/medicines");
const MANAGE_ROLES = new Set<Role>([Role.Owner, Role.Administrator, Role.Receptionist]);

const STATUS_BADGE_CLASS: Record<string, string> = {
  Active: "bg-emerald-100 text-emerald-800",
  Depleted: "bg-slate-100 text-slate-700",
  Expired: "bg-red-100 text-red-800",
  Recalled: "bg-amber-100 text-amber-800",
};

/**
 * Medicine detail page: Medicines list -> Batches action -> here. Shows the
 * medicine's stocked batches/lots (quantity, expiry, status) with Add/Edit
 * actions. Phase 1 scope only: no stock movement history, no dispensing
 * controls (see the Doctor E-Signature detail page for the same "generic
 * modal can't handle a one-to-many child list" precedent this follows).
 */
export default function MedicineDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { data: currentUser } = useCurrentUser();
  const canManage = Boolean(currentUser && MANAGE_ROLES.has(currentUser.role));
  const { toast } = useToast();

  const { useList: useBatchList, useMutations: useBatchMutations } = createCrudHooks<MedicineBatch>(
    `medicine-batches-${params.id}`,
    `/medicines/${params.id}/batches`
  );
  const medicineQuery = useQuery({
    queryKey: ["medicines", "detail", params.id],
    queryFn: () => medicinesApi.get(params.id),
  });
  const batchesQuery = useBatchList({ limit: 100 });
  const { create, update } = useBatchMutations();

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<MedicineBatch | null>(null);

  const medicine = medicineQuery.data;
  const batches = batchesQuery.data?.items ?? [];

  if (medicineQuery.isLoading || !medicine) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button type="button" variant="ghost" size="sm" onClick={() => router.push("/medicines")}>
          <ArrowLeft className="mr-1.5 h-4 w-4" aria-hidden="true" />
          Back to Medicines
        </Button>
      </div>

      <div>
        <h1 className="text-2xl font-semibold">
          {medicine.generic_name}
          {medicine.brand_name ? ` (${medicine.brand_name})` : ""}
        </h1>
        <p className="text-sm text-muted-foreground">
          {[medicine.strength, medicine.dosage_form, medicine.unit].filter(Boolean).join(" · ") || "No additional details"}
        </p>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle>Batches</CardTitle>
          {canManage ? (
            <Button
              type="button"
              size="sm"
              onClick={() => {
                setEditing(null);
                setFormOpen(true);
              }}
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add Batch
            </Button>
          ) : null}
        </CardHeader>
        <CardContent>
          <div className="rounded-lg border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Batch #</TableHead>
                  <TableHead>Quantity</TableHead>
                  <TableHead>Received</TableHead>
                  <TableHead>Expiry</TableHead>
                  <TableHead>Supplier</TableHead>
                  <TableHead>Cost/Unit</TableHead>
                  <TableHead>Status</TableHead>
                  {canManage ? <TableHead className="text-right">Actions</TableHead> : null}
                </TableRow>
              </TableHeader>
              <TableBody>
                {batchesQuery.isLoading ? (
                  Array.from({ length: 3 }).map((_, i) => (
                    <TableRow key={i}>
                      <TableCell colSpan={8}>
                        <Skeleton className="h-6 w-full" />
                      </TableCell>
                    </TableRow>
                  ))
                ) : batches.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} className="text-center text-sm text-muted-foreground">
                      No batches recorded yet.
                    </TableCell>
                  </TableRow>
                ) : (
                  batches.map((batch) => (
                    <TableRow key={batch.id}>
                      <TableCell>{batch.batch_number}</TableCell>
                      <TableCell>
                        {batch.quantity_remaining} / {batch.quantity_received}
                      </TableCell>
                      <TableCell>{batch.received_date ?? "-"}</TableCell>
                      <TableCell>{batch.expiry_date}</TableCell>
                      <TableCell>{batch.supplier ?? "-"}</TableCell>
                      <TableCell>{batch.cost_per_unit ?? "-"}</TableCell>
                      <TableCell>
                        <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_BADGE_CLASS[batch.status] ?? ""}`}>
                          {batch.status}
                        </span>
                      </TableCell>
                      {canManage ? (
                        <TableCell className="text-right">
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setEditing(batch);
                              setFormOpen(true);
                            }}
                          >
                            Edit
                          </Button>
                        </TableCell>
                      ) : null}
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <MasterDataFormDialog<MedicineBatch>
        open={formOpen}
        onOpenChange={setFormOpen}
        record={editing}
        fields={[
          { name: "batch_number", label: "Batch #", type: "text", required: true },
          { name: "quantity_received", label: "Quantity received", type: "number", required: true },
          { name: "quantity_remaining", label: "Quantity remaining", type: "number", required: true },
          { name: "expiry_date", label: "Expiry date", type: "date", required: true },
          { name: "received_date", label: "Received date", type: "date" },
          { name: "supplier", label: "Supplier", type: "text" },
          { name: "cost_per_unit", label: "Cost per unit", type: "number" },
        ]}
        onSubmit={async (values) => {
          try {
            if (editing) {
              await update.mutateAsync({ id: editing.id, payload: values as Partial<MedicineBatch> });
              toast({ title: "Batch saved", variant: "success" });
            } else {
              await create.mutateAsync(values as Partial<MedicineBatch>);
              toast({ title: "Batch added", variant: "success" });
            }
            setFormOpen(false);
          } catch (err) {
            toast({ title: "Something went wrong", description: (err as Error).message, variant: "error" });
          }
        }}
      />
    </div>
  );
}
