"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { patientsApi } from "@/features/patients/api/patients-api";
import type { PatientListParams } from "@/features/patients/types";

export const patientsKeys = {
  all: ["patients"] as const,
  list: (params: PatientListParams) => ["patients", "list", params] as const,
  detail: (id: string) => ["patients", "detail", id] as const,
  qr: (id: string) => ["patients", "qr", id] as const,
};

/** Debounces a rapidly-changing value (e.g. search input) by `delayMs`. */
export function useDebouncedValue<T>(value: T, delayMs = 350): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}

/** Paginated, searchable, filterable, sortable patient list. */
export function usePatients(params: PatientListParams) {
  return useQuery({
    queryKey: patientsKeys.list(params),
    queryFn: () => patientsApi.list(params),
    placeholderData: (previousData) => previousData,
  });
}
