"use client";

import { useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useVaccinationsWorklist, useCancelVaccination } from "@/features/vaccinations/hooks/use-vaccinations";
import { AdministerVaccinationDialog } from "@/features/vaccinations/components/AdministerVaccinationDialog";
import type { VaccinationAdministration, VaccinationStatus } from "@/features/vaccinations/types";

const STATUS_VARIANT: Record<VaccinationStatus, "default" | "success" | "secondary" | "destructive"> = {
  Requested: "default",
  Administered: "success",
  Cancelled: "destructive",
};

export default function VaccinationsPage() {
  const { data: vaccinations, isLoading } = useVaccinationsWorklist();
  const cancelVaccination = useCancelVaccination();
  const [q, setQ] = useState("");
  const [administering, setAdministering] = useState<VaccinationAdministration | null>(null);

  const filtered = useMemo(() => {
    if (!vaccinations) return [];
    const query = q.trim().toLowerCase();
    if (!query) return vaccinations;
    return vaccinations.filter((v) => v.vaccineName.toLowerCase().includes(query));
  }, [vaccinations, q]);

  const pendingCount = vaccinations?.filter((v) => v.status === "Requested").length ?? null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Vaccinations</h1>
        <p className="text-sm text-muted-foreground">
          Doctor-ordered vaccinations awaiting administration. Any Nurse, Receptionist, or the ordering Doctor may administer.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label="Pending" value={isLoading ? null : pendingCount} />
        <StatCard label="Administered" value={isLoading ? null : vaccinations?.filter((v) => v.status === "Administered").length} />
        <StatCard label="Cancelled" value={isLoading ? null : vaccinations?.filter((v) => v.status === "Cancelled").length} />
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle>Worklist</CardTitle>
          <Input placeholder="Search vaccine name..." value={q} onChange={(e) => setQ(e.target.value)} className="sm:w-80" />
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="space-y-2 p-4">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : filtered.length === 0 ? (
            <p className="p-6 text-sm text-muted-foreground">No vaccination orders.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="p-3 font-medium">Vaccine</th>
                  <th className="p-3 font-medium">Status</th>
                  <th className="p-3 font-medium">Dose / Site / Route</th>
                  <th className="p-3 font-medium">Lot #</th>
                  <th className="p-3 font-medium">Administered At</th>
                  <th className="p-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((v) => (
                  <tr key={v.id} className="border-b last:border-0">
                    <td className="p-3">{v.vaccineName}</td>
                    <td className="p-3">
                      <Badge variant={STATUS_VARIANT[v.status]}>{v.status}</Badge>
                    </td>
                    <td className="p-3 text-muted-foreground">
                      {[v.dose, v.site, v.route].filter(Boolean).join(" / ") || "-"}
                    </td>
                    <td className="p-3 text-muted-foreground">{v.lotNumber ?? "-"}</td>
                    <td className="p-3 text-muted-foreground">
                      {v.administeredAt ? new Date(v.administeredAt).toLocaleString() : "-"}
                    </td>
                    <td className="p-3">
                      {v.status === "Requested" ? (
                        <div className="flex gap-2">
                          <Button size="sm" onClick={() => setAdministering(v)}>
                            Administer
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={cancelVaccination.isPending}
                            onClick={() => cancelVaccination.mutate(v.id)}
                          >
                            Cancel
                          </Button>
                        </div>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <AdministerVaccinationDialog
        open={administering !== null}
        onOpenChange={(open) => !open && setAdministering(null)}
        vaccination={administering}
      />
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs text-muted-foreground">{label}</p>
        {value === null || value === undefined ? (
          <Skeleton className="mt-1 h-7 w-16" />
        ) : (
          <p className="mt-1 text-2xl font-semibold tracking-tight">{value}</p>
        )}
      </CardContent>
    </Card>
  );
}
