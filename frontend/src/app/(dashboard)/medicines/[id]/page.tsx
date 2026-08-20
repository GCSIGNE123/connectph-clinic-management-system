"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { apiClient } from "@/lib/api-client";
import { createCrudApi } from "@/features/clinic-config/api/crud-factory";
import { MasterDataFormDialog } from "@/features/clinic-config/components/MasterDataFormDialog";
import { createCrudHooks } from "@/features/clinic-config/hooks/use-crud";
import type { Medicine, MedicineBatch, MedicineStockMovement, MedicineStockMovementType } from "@/features/clinic-config/types";
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

// "Dispensed" is deliberately excluded here - it exists on the backend/model
// for future compatibility only (prescription-to-dispensing integration, a
// later phase); Phase 2 never exposes it as a normal user action.
const MOVEMENT_TYPE_OPTIONS: { value: Exclude<MedicineStockMovementType, "Dispensed">; label: string }[] = [
  { value: "Received", label: "Received (add stock)" },
  { value: "Adjustment", label: "Adjustment (+/-)" },
  { value: "Expired", label: "Expired (remove stock)" },
  { value: "Recalled", label: "Recalled (remove stock)" },
];

const REASON_REQUIRED_TYPES = new Set(["Adjustment", "Expired", "Recalled"]);

/**
 * Medicine detail page: Medicines list -> Batches action -> here. Shows the
 * medicine's stocked batches/lots (quantity, expiry, status) with Add/Edit
 * actions (Phase 1), plus each batch's Stock Movement ledger with an Add
 * Movement action (Phase 2). Quantity is no longer editable via the Edit
 * Batch form - every post-creation quantity change goes through a ledgered
 * movement instead (see `MedicineBatchUpdate`'s Phase 2 docstring).
 */
export default function MedicineDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { data: currentUser } = useCurrentUser();
  const canManage = Boolean(currentUser && MANAGE_ROLES.has(currentUser.role));
  const { toast } = useToast();
  const queryClient = useQueryClient();

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
  const [selectedBatch, setSelectedBatch] = useState<MedicineBatch | null>(null);
  const [movementDialogOpen, setMovementDialogOpen] = useState(false);

  const medicine = medicineQuery.data;
  const batches = batchesQuery.data?.items ?? [];

  const movementsKey = ["medicines", params.id, "batches", selectedBatch?.id, "movements"];
  const movementsApi = selectedBatch
    ? createCrudApi<MedicineStockMovement>(`/medicines/${params.id}/batches/${selectedBatch.id}/movements`)
    : null;
  const movementsQuery = useQuery({
    queryKey: movementsKey,
    queryFn: () => movementsApi!.list({ limit: 100 }),
    enabled: Boolean(selectedBatch),
  });
  const createMovement = useMutation({
    mutationFn: (payload: { movement_type: string; quantity_delta: number; reason?: string }) =>
      apiClient.post(`/medicines/${params.id}/batches/${selectedBatch!.id}/movements`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: movementsKey });
      queryClient.invalidateQueries({ queryKey: [`medicine-batches-${params.id}`] });
    },
  });

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
                  <TableHead className="text-right">Actions</TableHead>
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
                      <TableCell className="text-right">
                        <Button type="button" variant="ghost" size="sm" onClick={() => setSelectedBatch(batch)}>
                          Movements
                        </Button>
                        {canManage ? (
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
                        ) : null}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {selectedBatch ? (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle>Stock Movements - {selectedBatch.batch_number}</CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">
                Current quantity {selectedBatch.quantity_remaining} · Expiry {selectedBatch.expiry_date} · Status{" "}
                {selectedBatch.status}
              </p>
            </div>
            {canManage ? (
              <Button type="button" size="sm" onClick={() => setMovementDialogOpen(true)}>
                <Plus className="h-4 w-4" aria-hidden="true" />
                Add Stock Movement
              </Button>
            ) : null}
          </CardHeader>
          <CardContent>
            <div className="rounded-lg border border-border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date/Time</TableHead>
                    <TableHead>Movement</TableHead>
                    <TableHead>Quantity Change</TableHead>
                    <TableHead>Resulting Quantity</TableHead>
                    <TableHead>Reason</TableHead>
                    <TableHead>Performed By</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {movementsQuery.isLoading ? (
                    Array.from({ length: 2 }).map((_, i) => (
                      <TableRow key={i}>
                        <TableCell colSpan={6}>
                          <Skeleton className="h-6 w-full" />
                        </TableCell>
                      </TableRow>
                    ))
                  ) : movementsQuery.isError ? (
                    <TableRow>
                      <TableCell colSpan={6} className="text-center text-sm text-destructive">
                        Failed to load stock movements.
                      </TableCell>
                    </TableRow>
                  ) : (movementsQuery.data?.items.length ?? 0) === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6} className="text-center text-sm text-muted-foreground">
                        No stock movements recorded yet.
                      </TableCell>
                    </TableRow>
                  ) : (
                    movementsQuery.data!.items.map((movement) => (
                      <TableRow key={movement.id}>
                        <TableCell>{new Date(movement.created_at).toLocaleString()}</TableCell>
                        <TableCell>{movement.movement_type}</TableCell>
                        <TableCell className={movement.quantity_delta < 0 ? "text-destructive" : "text-emerald-700"}>
                          {movement.quantity_delta > 0 ? `+${movement.quantity_delta}` : movement.quantity_delta}
                        </TableCell>
                        <TableCell>{movement.resulting_quantity}</TableCell>
                        <TableCell>{movement.reason ?? "-"}</TableCell>
                        <TableCell>{movement.performed_by_name ?? "-"}</TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <MasterDataFormDialog<MedicineBatch>
        open={formOpen}
        onOpenChange={setFormOpen}
        record={editing}
        fields={[
          { name: "batch_number", label: "Batch #", type: "text", required: true },
          { name: "quantity_received", label: "Quantity received", type: "number", required: true, createOnly: true },
          { name: "quantity_remaining", label: "Quantity remaining", type: "number", required: true, createOnly: true },
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

      <AddMovementDialog
        open={movementDialogOpen}
        onOpenChange={setMovementDialogOpen}
        onSubmit={async (payload) => {
          try {
            await createMovement.mutateAsync(payload);
            toast({ title: "Stock movement recorded", variant: "success" });
            setMovementDialogOpen(false);
          } catch (err) {
            toast({ title: "Something went wrong", description: (err as Error).message, variant: "error" });
          }
        }}
      />
    </div>
  );
}

interface AddMovementDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (payload: { movement_type: string; quantity_delta: number; reason?: string }) => Promise<void>;
}

/**
 * Dedicated (not `MasterDataFormDialog`-driven) form: the amount field's
 * label/sign and the reason field's required-ness both change per movement
 * type, which a flat `FieldConfig[]` can't express - see the Phase 2 spec's
 * "The UI should adapt to movement type."
 */
function AddMovementDialog({ open, onOpenChange, onSubmit }: AddMovementDialogProps) {
  const [movementType, setMovementType] = useState<string>("Received");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const isRemoval = movementType === "Expired" || movementType === "Recalled";
  const amountLabel =
    movementType === "Received" ? "Quantity to add" : movementType === "Adjustment" ? "Adjustment amount (+/-)" : "Quantity to remove";
  const reasonRequired = REASON_REQUIRED_TYPES.has(movementType);

  function reset() {
    setMovementType("Received");
    setAmount("");
    setReason("");
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Add Stock Movement</DialogTitle>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            const parsedAmount = Number(amount);
            if (!amount || Number.isNaN(parsedAmount) || parsedAmount === 0) return;
            const quantityDelta =
              movementType === "Adjustment" ? parsedAmount : isRemoval ? -Math.abs(parsedAmount) : Math.abs(parsedAmount);
            setSubmitting(true);
            try {
              await onSubmit({
                movement_type: movementType,
                quantity_delta: quantityDelta,
                reason: reason.trim() || undefined,
              });
              reset();
            } finally {
              setSubmitting(false);
            }
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="movement_type">Movement type</Label>
            <Select id="movement_type" value={movementType} onChange={(e) => setMovementType(e.target.value)}>
              {MOVEMENT_TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="amount">{amountLabel}</Label>
            <Input
              id="amount"
              type="number"
              min={movementType === "Adjustment" ? undefined : 1}
              required
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder={movementType === "Adjustment" ? "e.g. -5 or 10" : "e.g. 50"}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="reason">
              Reason
              {reasonRequired ? " *" : ""}
            </Label>
            <Textarea
              id="reason"
              value={reason}
              required={reasonRequired}
              onChange={(e) => setReason(e.target.value)}
              placeholder={reasonRequired ? "Required for this movement type" : "Optional, e.g. PO number"}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" isLoading={submitting}>
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
