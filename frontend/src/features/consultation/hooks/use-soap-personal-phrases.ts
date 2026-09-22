"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { consultationApi } from "@/features/consultation/api/consultation-api";
import type { SuggestionFieldKey } from "@/features/consultation/lib/soap-vocabulary";

export type PersonalSuggestions = { favorites: string[]; recent: string[] };

const personalKey = (field: SuggestionFieldKey) => ["consultation", "soap-personal", field] as const;

/**
 * The signed-in Doctor's own My Phrases + Recently used for one field. `enabled` is
 * flipped on the first time the field is focused, so opening the consultation page does
 * not fire one request per field. A failed/empty response is fine - the caller falls back
 * to the plain clinic + starter list.
 */
export function usePersonalSuggestions(field: SuggestionFieldKey, enabled: boolean) {
  return useQuery({
    queryKey: personalKey(field),
    queryFn: () => consultationApi.getPersonalSuggestions(field),
    enabled,
    staleTime: 15 * 1000,
    retry: false,
    refetchOnWindowFocus: false,
  });
}

/** Save (favorite=true) or remove (favorite=false) one phrase in the Doctor's My Phrases. */
export function useToggleFavoritePhrase(field: SuggestionFieldKey) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ text, favorite }: { text: string; favorite: boolean }) => {
      if (favorite) return consultationApi.addFavoritePhrase(field, text);
      await consultationApi.removeFavoritePhrase(field, text);
      return text;
    },
    onSuccess: (savedText, { favorite, text }) => {
      // Update the cached list right away so the row moves between sections without waiting for a refetch.
      queryClient.setQueryData<PersonalSuggestions>(personalKey(field), (old) => {
        if (!old) return old;
        const key = (savedText || text).trim().toLowerCase();
        const favorites = old.favorites.filter((f) => f.trim().toLowerCase() !== key);
        return favorite
          ? { favorites: [savedText, ...favorites], recent: old.recent.filter((r) => r.trim().toLowerCase() !== key) }
          : { favorites, recent: old.recent };
      });
      void queryClient.invalidateQueries({ queryKey: personalKey(field) });
    },
  });
}
