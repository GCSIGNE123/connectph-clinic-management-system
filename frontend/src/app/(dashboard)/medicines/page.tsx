"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Clock, Plus, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { AlertDialog } from "@/components/ui/alert-dialog";
import { useToast } from "@/components/ui/toast";
import { apiClient } from "@/lib/api-client";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { MasterDataFormDialog } from "@/features/clinic-config/components/MasterDataFormDialog";
import { createCrudHooks } from "@/features/clinic-config/hooks/use-crud";
import type { Medicine, MedicineStats, MedicineStockStatus } from "@/features/clinic-config/types";
import { Role } from "@/types";

const MANAGE_ROLES = new Set<Role>([Role.Owner, Role.Administrator, Role.Receptionist]);

const FILTERS: { value: MedicineStockStatus | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "in_stock", label: "In Stock" },
  { value: "low_stock", label: "Low Stock" },
  { value: "near_expiry", label: "Near Expiry" },
  { value: "expired", label: "Expired" },
  { value: "out_of_stock", label: "Out of Stock" },
];

const STATUS_BADGE_CLASS: Record<string, string> = {
  in_stock: "bg-emerald-100 text-emerald-800",
  low_stock: "bg-amber-100 text-amber-800",
  near_expiry: "bg-amber-100 text-amber-800",
  expired: "bg-red-100 text-red-800",
  out_of_stock: "bg-slate-100 text-slate-700",
};

const STATUS_LABEL: Record<string, string> = {
  in_stock: "In Stock",
  low_stock: "Low Stock",
  near_expiry: "Near Expiry",
  expired: "Expired",
  out_of_stock: "Out of Stock",
};

const { useList, useMutations } = createCrudHooks<Medicine>("medicines", "/medicines");

function StatCard({
  label, value, isLoading, icon: Icon, active, onClick,
}: { label: string; value?: number; isLoading?: boolean; icon: typeof AlertTriangle; active?: boolean; onClick?: () => void }) {
  return (
    <button type="button" onClick={onClick} className="text-left">
      <Card className={active ? "border-primary" : undefined}>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
          <Icon className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        </CardHeader>
        <CardContent>
          {isLoading ? <Skeleton className="h-8 w-16" /> : <div className="text-2xl font-semibold text-foreground">{value ?? 0}</div>}
        </CardContent>
      </Card>
    </button>
  );
}

/**
 * Medicine Inventory Phase 3: catalog list + stock-status filter chips +
 * expiry/stock summary stat cards. Batch/lot tracking + movement ledger
 * still live on the dedicated `/medicines/{id}` detail page. Not built on
 * the shared `MasterDataPage` (used by 8+ other master-data pages) since
 * that component has no hook for extra list query params beyond
 * search/limit - a custom page keeps this feature's filtering isolated
 * rather than growing a shared component's surface for one consumer.
 */
export default function MedicinesPage() {
  const { data: currentUser } = useCurrentUser();
  const canManage = Boolean(currentUser && MANAGE_ROLES.has(currentUser.role));
  const { toast } = useToast();
  const searchParams = useSearchParams();
  const filterFromUrl = searchParams.get("filter") as MedicineStockStatus | null;

  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<MedicineStockStatus | "all">(filterFromUrl ?? "all");
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Medicine | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Medicine | null>(null);

  const { data, isLoading } = useList({ q: search || undefined, stock_status: filter === "all" ? undefined : filter, limit: 50 });
  const { create, update, remove } = useMutations();
  const items = useMemo(() => data?.items ?? [], [data]);

  const statsQuery = useQuery({
    queryKey: ["medicines", "stats"],
    queryFn: () => apiClient.get<MedicineStats>("/medicines/stats"),
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Medicines</h1>
          <p className="text-sm text-muted-foreground">
            Medicine catalog. Open a medicine to manage its stocked batches, quantities, and expiry dates.
          </p>
        </div>
        {canManage ? (
          <Button
            type="button"
            onClick={() => {
              setEditing(null);
              setFormOpen(true);
            }}
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            Add
          </Button>
        ) : null}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Expiring Soon"
          value={statsQuery.data?.expiring_soon}
          isLoading={statsQuery.isLoading}
          icon={Clock}
          active={filter === "near_expiry"}
          onClick={() => setFilter("near_expiry")}
        />
        <StatCard
          label="Expired"
          value={statsQuery.data?.expired}
          isLoading={statsQuery.isLoading}
          icon={AlertTriangle}
          active={filter === "expired"}
          onClick={() => setFilter("expired")}
        />
        <StatCard
          label="Low Stock"
          value={statsQuery.data?.low_stock}
          isLoading={statsQuery.isLoading}
          icon={AlertTriangle}
          active={filter === "low_stock"}
          onClick={() => setFilter("low_stock")}
        />
        <StatCard
          label="Out of Stock"
          value={statsQuery.data?.out_of_stock}
          isLoading={statsQuery.isLoading}
          icon={AlertTriangle}
          active={filter === "out_of_stock"}
          onClick={() => setFilter("out_of_stock")}
        />
      </div>

      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Stock status filters">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            aria-label={`Filter: ${f.label}`}
            onClick={() => setFilter(f.value)}
            className={`rounded-full border px-3 py-1 text-xs font-medium ${
              filter === f.value ? "border-primary bg-primary text-primary-foreground" : "border-border text-muted-foreground hover:bg-accent"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="relative w-full sm:max-w-xs">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
        <Input type="search" placeholder="Search medicines" className="pl-8" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>

      <div className="rounded-lg border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Generic Name</TableHead>
              <TableHead>Brand Name</TableHead>
              <TableHead>Strength</TableHead>
              <TableHead>Dosage Form</TableHead>
              <TableHead>Unit</TableHead>
              <TableHead>Reorder Level</TableHead>
              <TableHead>Stock Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 3 }).map((_, i) => (
                <TableRow key={i}>
                  <TableCell colSpan={8}>
                    <Skeleton className="h-6 w-full" />
                  </TableCell>
                </TableRow>
              ))
            ) : items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="text-center text-sm text-muted-foreground">
                  No records found.
                </TableCell>
              </TableRow>
            ) : (
              items.map((m) => (
                <TableRow key={m.id}>
                  <TableCell>{m.generic_name}</TableCell>
                  <TableCell>{m.brand_name ?? "-"}</TableCell>
                  <TableCell>{m.strength ?? "-"}</TableCell>
                  <TableCell>{m.dosage_form ?? "-"}</TableCell>
                  <TableCell>{m.unit ?? "-"}</TableCell>
                  <TableCell>{m.reorder_level ?? "-"}</TableCell>
                  <TableCell>
                    {m.stock_status ? (
                      <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_BADGE_CLASS[m.stock_status] ?? ""}`}>
                        {STATUS_LABEL[m.stock_status]}
                      </span>
                    ) : (
                      "-"
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button type="button" variant="ghost" size="sm" asChild>
                      <Link href={`/medicines/${m.id}`}>Batches</Link>
                    </Button>
                    {canManage ? (
                      <>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setEditing(m);
                            setFormOpen(true);
                          }}
                        >
                          Edit
                        </Button>
                        <Button type="button" variant="ghost" size="sm" className="text-destructive" onClick={() => setDeleteTarget(m)}>
                          Delete
                        </Button>
                      </>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <MasterDataFormDialog<Medicine>
        open={formOpen}
        onOpenChange={setFormOpen}
        record={editing}
        fields={[
          { name: "generic_name", label: "Generic name", type: "text", required: true },
          { name: "brand_name", label: "Brand name", type: "text" },
          { name: "strength", label: "Strength", type: "text", placeholder: "e.g. 500mg" },
          { name: "dosage_form", label: "Dosage form", type: "text", placeholder: "e.g. Tablet" },
          { name: "unit", label: "Unit", type: "text", placeholder: "e.g. tablet" },
          { name: "reorder_level", label: "Reorder level", type: "number" },
          { name: "is_active", label: "Active", type: "checkbox" },
        ]}
        onSubmit={async (values) => {
          try {
            if (editing) {
              await update.mutateAsync({ id: editing.id, payload: values as Partial<Medicine> });
              toast({ title: "Saved", variant: "success" });
            } else {
              await create.mutateAsync(values as Partial<Medicine>);
              toast({ title: "Created", variant: "success" });
            }
            setFormOpen(false);
          } catch (err) {
            toast({ title: "Something went wrong", description: (err as Error).message, variant: "error" });
          }
        }}
      />

      <AlertDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title={`Delete ${deleteTarget?.generic_name ?? ""}?`}
        description="This record will be soft-deleted and can be restored later by an administrator."
        confirmLabel="Delete"
        isConfirming={remove.isPending}
        onConfirm={async () => {
          if (!deleteTarget) return;
          try {
            await remove.mutateAsync(deleteTarget.id);
            toast({ title: "Deleted", variant: "success" });
          } catch (err) {
            toast({ title: "Delete failed", description: (err as Error).message, variant: "error" });
          } finally {
            setDeleteTarget(null);
          }
        }}
      />
    </div>
  );
}
