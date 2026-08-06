"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { migrationApi } from "@/features/migration/api/migration-api";

export const migrationKeys = {
  all: ["migration"] as const,
  batches: () => [...migrationKeys.all, "batches"] as const,
  batch: (id: string) => [...migrationKeys.all, "batch", id] as const,
  status: (id: string) => [...migrationKeys.all, "status", id] as const,
};

const TERMINAL_STATUSES = new Set(["Completed", "Failed", "PartiallyCompleted", "Cancelled"]);

/** Polls `GET /migration/batches/{id}/status` every 2s while the batch is
 * Importing, and stops automatically once it reaches a terminal status. */
export function useMigrationStatus(batchId: string | null) {
  const [pollingEnabled, setPollingEnabled] = useState(true);

  const query = useQuery({
    queryKey: batchId ? migrationKeys.status(batchId) : ["migration-status-disabled"],
    queryFn: () => migrationApi.getStatus(batchId as string),
    enabled: Boolean(batchId) && pollingEnabled,
    refetchInterval: 2000,
  });

  useEffect(() => {
    if (query.data && TERMINAL_STATUSES.has(query.data.batch.status)) {
      setPollingEnabled(false);
    }
  }, [query.data]);

  useEffect(() => {
    setPollingEnabled(true);
  }, [batchId]);

  return query;
}

export function useMigrationBatches() {
  return useQuery({ queryKey: migrationKeys.batches(), queryFn: migrationApi.listBatches });
}

export function useInvalidateMigration() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: migrationKeys.all });
}
