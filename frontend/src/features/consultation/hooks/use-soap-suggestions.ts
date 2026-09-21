"use client";

import { useQuery } from "@tanstack/react-query";
import { consultationApi } from "@/features/consultation/api/consultation-api";
import type { SuggestionFieldKey } from "@/features/consultation/lib/soap-vocabulary";

/** The clinic's own learned suggestions for one SOAP/diagnosis field. A failed or
 * empty response is fine - the caller falls back to the static starters. */
export function useSoapSuggestions(field: SuggestionFieldKey, enabled: boolean) {
  return useQuery({
    queryKey: ["consultation", "soap-suggestions", field],
    queryFn: () => consultationApi.getSoapSuggestions(field),
    enabled,
    staleTime: 5 * 60 * 1000,
    retry: false,
    refetchOnWindowFocus: false,
  });
}
