"use client";

import { useMemo, useState } from "react";
import { Plus, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertDialog } from "@/components/ui/alert-dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import type { ColumnConfig, FieldConfig } from "@/features/clinic-config/components/FieldConfig";
import { MasterDataFormDialog } from "@/features/clinic-config/components/MasterDataFormDialog";
import { createCrudHooks } from "@/features/clinic-config/hooks/use-crud";

interface MasterDataPageProps<T extends { id: string; status?: string }> {
  title: string;
  description: string;
  resourceKey: string;
  resourcePath: string;
  columns: ColumnConfig<T>[];
  fields: FieldConfig[];
  canManage: boolean;
  searchPlaceholder?: string;
  rowLabel: (row: T) => string;
}

/**
 * Generic card-based list + CRUD page shared by the simpler Phase 4
 * master-data modules (departments, consultation rooms, services,
 * holidays, ...). See `features/clinic-config/types.ts` for the design
 * rationale behind this shared, config-driven approach.
 */
export function MasterDataPage<T extends { id: string; status?: string }>({
  title,
  description,
  resourceKey,
  resourcePath,
  columns,
  fields,
  canManage,
  searchPlaceholder = "Search...",
  rowLabel,
}: MasterDataPageProps<T>) {
  const { useList, useMutations } = useMemo(() => createCrudHooks<T>(resourceKey, resourcePath), [resourceKey, resourcePath]);
  const [search, setSearch] = useState("");
  const { data, isLoading } = useList({ q: search || undefined, limit: 50 });
  const { create, update, remove } = useMutations();
  const { toast } = useToast();

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<T | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<T | null>(null);

  const items = data?.items ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-foreground">{title}</h1>
          <p className="text-sm text-muted-foreground">{description}</p>
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

      <div className="relative w-full sm:max-w-xs">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
        <Input
          type="search"
          placeholder={searchPlaceholder}
          className="pl-8"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="rounded-lg border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              {columns.map((col) => (
                <TableHead key={col.header}>{col.header}</TableHead>
              ))}
              {canManage ? <TableHead className="text-right">Actions</TableHead> : null}
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 3 }).map((_, i) => (
                <TableRow key={i}>
                  <TableCell colSpan={columns.length + 1}>
                    <Skeleton className="h-6 w-full" />
                  </TableCell>
                </TableRow>
              ))
            ) : items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columns.length + 1} className="text-center text-sm text-muted-foreground">
                  No records found.
                </TableCell>
              </TableRow>
            ) : (
              items.map((row) => (
                <TableRow key={row.id}>
                  {columns.map((col) => (
                    <TableCell key={col.header}>{col.render(row)}</TableCell>
                  ))}
                  {canManage ? (
                    <TableCell className="text-right">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setEditing(row);
                          setFormOpen(true);
                        }}
                      >
                        Edit
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="text-destructive"
                        onClick={() => setDeleteTarget(row)}
                      >
                        Delete
                      </Button>
                    </TableCell>
                  ) : null}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <MasterDataFormDialog<T>
        open={formOpen}
        onOpenChange={setFormOpen}
        record={editing}
        fields={fields}
        onSubmit={async (values) => {
          try {
            if (editing) {
              await update.mutateAsync({ id: editing.id, payload: values as Partial<T> });
              toast({ title: "Saved", variant: "success" });
            } else {
              await create.mutateAsync(values as Partial<T>);
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
        title={`Delete ${deleteTarget ? rowLabel(deleteTarget) : ""}?`}
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
