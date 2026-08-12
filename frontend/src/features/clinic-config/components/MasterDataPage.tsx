"use client";

import { useMemo, useRef, useState } from "react";
import { Plus, Search, Download, Upload, ArrowUp, ArrowDown, ArrowUpDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertDialog } from "@/components/ui/alert-dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import type { ColumnConfig, FieldConfig } from "@/features/clinic-config/components/FieldConfig";
import { MasterDataFormDialog } from "@/features/clinic-config/components/MasterDataFormDialog";
import { createCrudHooks } from "@/features/clinic-config/hooks/use-crud";
import { toCsv, parseCsv, downloadCsv } from "@/lib/csv";

/** Optional CSV import/export config for a `MasterDataPage` resource - only
 * a handful of resources need this (Services was the first request), so
 * it's opt-in per page rather than built into every master-data page. */
export interface MasterDataCsvConfig<T> {
  /** Download filename, e.g. "services.csv". */
  filename: string;
  /** CSV header row, in column order - also the keys `fromRow` receives. */
  headers: string[];
  /** Maps one record to a CSV row, in the same order as `headers`. */
  toRow: (item: T) => (string | number | null | undefined)[];
  /** Parses one CSV row (header-keyed) into a create/update payload. Throw
   * a descriptive `Error` to reject a malformed row - surfaced per-row in
   * the import summary rather than aborting the whole file. */
  fromRow: (row: Record<string, string>) => Partial<T>;
  /** Field used to detect "this row already exists" during import (e.g.
   * `service_code`) - a match updates that record, no match creates a new
   * one. Must be a field also present on `T` and derivable from `fromRow`'s
   * output. */
  matchKey: keyof T;
}

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
  csv?: MasterDataCsvConfig<T>;
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
  csv,
}: MasterDataPageProps<T>) {
  const { useList, useMutations } = useMemo(() => createCrudHooks<T>(resourceKey, resourcePath), [resourceKey, resourcePath]);
  const [search, setSearch] = useState("");
  const { data, isLoading } = useList({ q: search || undefined, limit: 50 });
  const { create, update, remove } = useMutations();
  const { toast } = useToast();

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<T | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<T | null>(null);
  const [importing, setImporting] = useState(false);
  const importFileRef = useRef<HTMLInputElement>(null);

  const items = data?.items ?? [];

  const [sort, setSort] = useState<{ columnIndex: number; direction: "asc" | "desc" } | null>(null);

  function toggleSort(columnIndex: number) {
    setSort((prev) => {
      if (!prev || prev.columnIndex !== columnIndex) return { columnIndex, direction: "asc" };
      if (prev.direction === "asc") return { columnIndex, direction: "desc" };
      return null; // third click clears sorting, back to the server's own order
    });
  }

  const sortedItems = useMemo(() => {
    if (!sort) return items;
    const col = columns[sort.columnIndex];
    if (!col?.sortable) return items;
    const getValue = col.sortValue ?? col.render;
    const withKeys = items.map((row) => ({ row, value: getValue(row) }));
    withKeys.sort((a, b) => {
      const av = a.value;
      const bv = b.value;
      if (av === null || av === undefined) return bv === null || bv === undefined ? 0 : 1;
      if (bv === null || bv === undefined) return -1;
      // Numeric compare when both values parse as numbers (covers prices
      // like "400.00" that would sort wrong lexicographically as strings -
      // "1200.00" < "300.00" by string order but not by value), otherwise
      // fall back to locale-aware string compare.
      const an = typeof av === "number" ? av : Number(av);
      const bn = typeof bv === "number" ? bv : Number(bv);
      const bothNumeric = !Number.isNaN(an) && !Number.isNaN(bn) && String(av).trim() !== "" && String(bv).trim() !== "";
      const cmp = bothNumeric ? an - bn : String(av).localeCompare(String(bv), undefined, { numeric: true, sensitivity: "base" });
      return sort.direction === "asc" ? cmp : -cmp;
    });
    return withKeys.map((k) => k.row);
  }, [items, sort, columns]);

  function handleExportCsv() {
    if (!csv) return;
    const csvText = toCsv(csv.headers, items.map(csv.toRow));
    downloadCsv(csv.filename, csvText);
  }

  async function handleImportCsvFile(file: File) {
    if (!csv) return;
    setImporting(true);
    try {
      const text = await file.text();
      const rows = parseCsv(text);
      let created = 0;
      let updated = 0;
      const errors: string[] = [];

      for (const [index, row] of rows.entries()) {
        try {
          const payload = csv.fromRow(row);
          const matchValue = payload[csv.matchKey];
          const existing = items.find((item) => item[csv.matchKey] === matchValue);
          if (existing) {
            await update.mutateAsync({ id: existing.id, payload });
            updated += 1;
          } else {
            await create.mutateAsync(payload);
            created += 1;
          }
        } catch (err) {
          errors.push(`Row ${index + 2}: ${(err as Error).message}`);
        }
      }

      if (errors.length === 0) {
        toast({ title: `Import complete`, description: `${created} created, ${updated} updated.`, variant: "success" });
      } else {
        toast({
          title: `Import finished with ${errors.length} error(s)`,
          description: `${created} created, ${updated} updated. ${errors.slice(0, 3).join(" ")}`,
          variant: "error",
        });
      }
    } catch (err) {
      toast({ title: "Import failed", description: (err as Error).message, variant: "error" });
    } finally {
      setImporting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-foreground">{title}</h1>
          <p className="text-sm text-muted-foreground">{description}</p>
        </div>
        {canManage ? (
          <div className="flex flex-wrap items-center gap-2">
            {csv ? (
              <>
                <Button type="button" variant="outline" onClick={handleExportCsv}>
                  <Download className="h-4 w-4" aria-hidden="true" />
                  Export CSV
                </Button>
                <input
                  ref={importFileRef}
                  type="file"
                  accept=".csv,text/csv"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    e.target.value = "";
                    if (file) void handleImportCsvFile(file);
                  }}
                />
                <Button
                  type="button"
                  variant="outline"
                  isLoading={importing}
                  onClick={() => importFileRef.current?.click()}
                >
                  <Upload className="h-4 w-4" aria-hidden="true" />
                  Import CSV
                </Button>
              </>
            ) : null}
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
          </div>
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
              {columns.map((col, index) =>
                col.sortable ? (
                  <TableHead key={col.header}>
                    <button
                      type="button"
                      onClick={() => toggleSort(index)}
                      className="inline-flex items-center gap-1 hover:text-foreground"
                    >
                      {col.header}
                      {sort?.columnIndex === index ? (
                        sort.direction === "asc" ? (
                          <ArrowUp className="h-3.5 w-3.5" aria-hidden="true" />
                        ) : (
                          <ArrowDown className="h-3.5 w-3.5" aria-hidden="true" />
                        )
                      ) : (
                        <ArrowUpDown className="h-3.5 w-3.5 opacity-40" aria-hidden="true" />
                      )}
                    </button>
                  </TableHead>
                ) : (
                  <TableHead key={col.header}>{col.header}</TableHead>
                )
              )}
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
            ) : sortedItems.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columns.length + 1} className="text-center text-sm text-muted-foreground">
                  No records found.
                </TableCell>
              </TableRow>
            ) : (
              sortedItems.map((row) => (
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
