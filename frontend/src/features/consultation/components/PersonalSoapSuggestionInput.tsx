"use client";

import { useEffect, useMemo, useState } from "react";
import { SuggestionInput } from "@/features/clinical-orders/components/SuggestionInput";
import { useSoapSuggestions } from "@/features/consultation/hooks/use-soap-suggestions";
import { usePersonalSuggestions, useToggleFavoritePhrase } from "@/features/consultation/hooks/use-soap-personal-phrases";
import { buildSuggestionSections } from "@/features/consultation/lib/suggestion-sections";
import {
  STATIC_SOAP_SUGGESTIONS,
  mergeSuggestions,
  type SuggestionFieldKey,
} from "@/features/consultation/lib/soap-vocabulary";
import { ApiError } from "@/lib/api-client";

/**
 * Task #2 enhancement: the Doctor's version of a SOAP / diagnosis suggestion field.
 *
 * Adds the Doctor's own MY PHRASES and RECENTLY USED ahead of the clinic-learned
 * suggestions and the static starters, plus a small Save-to-My-Phrases action for the
 * line/segment being typed. Used ONLY on the Doctor consultation page (never for
 * Receptionist/Nurse intake). The personal list is requested the first time the field is
 * focused; until it has loaded - or if the request fails - this behaves exactly like the
 * classic clinic + starter list, and free text is always allowed.
 */
export function PersonalSoapSuggestionInput({
  field,
  value,
  onChange,
  multiline = true,
  rows,
  "aria-label": ariaLabel,
}: {
  field: SuggestionFieldKey;
  value: string;
  onChange: (value: string) => void;
  multiline?: boolean;
  rows?: number;
  "aria-label"?: string;
}) {
  const [wantsPersonal, setWantsPersonal] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const { data: learned } = useSoapSuggestions(field, true);
  const personalQuery = usePersonalSuggestions(field, wantsPersonal);
  const toggle = useToggleFavoritePhrase(field);
  const personalData = personalQuery.data;

  // A stale "could not save" message should not linger while the Doctor keeps typing.
  useEffect(() => setNotice(null), [value]);

  const flat = useMemo(() => mergeSuggestions(learned ?? [], STATIC_SOAP_SUGGESTIONS[field]), [learned, field]);
  const sections = useMemo(
    () =>
      personalData
        ? buildSuggestionSections({
            mine: personalData.favorites,
            recent: personalData.recent,
            clinic: learned ?? [],
            starters: STATIC_SOAP_SUGGESTIONS[field],
          })
        : undefined,
    [personalData, learned, field]
  );
  const savedKeys = useMemo(
    () => new Set((personalData?.favorites ?? []).map((f) => f.trim().toLowerCase())),
    [personalData]
  );

  function run(text: string, favorite: boolean) {
    setNotice(null);
    toggle.mutate(
      { text, favorite },
      {
        onError: (err) =>
          setNotice(err instanceof ApiError && err.message ? err.message : "Could not update My Phrases. Please try again."),
      }
    );
  }

  return (
    <SuggestionInput
      value={value}
      onChange={onChange}
      suggestions={flat}
      sections={sections}
      personal={personalData ? { savedKeys, onSave: (t) => run(t, true), onRemove: (t) => run(t, false), notice } : undefined}
      onFocus={() => {
        setNotice(null);
        if (wantsPersonal) void personalQuery.refetch();
        else setWantsPersonal(true);
      }}
      multiline={multiline}
      rows={rows}
      aria-label={ariaLabel}
      className={multiline ? "mt-1" : undefined}
    />
  );
}
