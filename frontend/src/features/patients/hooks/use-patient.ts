"use client";

import { useQuery } from "@tanstack/react-query";
import { patientsApi } from "@/features/patients/api/patients-api";
import { patientsKeys } from "@/features/patients/hooks/use-patients";

/** Fetches a single patient's full profile. */
export function usePatient(id: string | undefined) {
  return useQuery({
    queryKey: patientsKeys.detail(id ?? ""),
    queryFn: () => patientsApi.get(id as string),
    enabled: Boolean(id),
  });
}

/** Fetches the QR check-in payload for a single patient. */
export function usePatientQr(id: string | undefined, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: patientsKeys.qr(id ?? ""),
    queryFn: () => patientsApi.getQr(id as string),
    enabled: Boolean(id) && (options?.enabled ?? true),
  });
}
