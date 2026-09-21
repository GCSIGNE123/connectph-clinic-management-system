"use client";

import { useMemo } from "react";
import { SuggestionInput } from "@/features/clinical-orders/components/SuggestionInput";
import { useSoapSuggestions } from "@/features/consultation/hooks/use-soap-suggestions";
import {
  STATIC_SOAP_SUGGESTIONS,
  mergeSuggestions,
  type SuggestionFieldKey,
} from "@/features/consultation/lib/soap-vocabulary";

/**
 * Task #2: a SOAP / diagnosis field with suggestions - the clinic's learned
 * values first, then a small static starter list. Free text is always
 * allowed (see `SuggestionInput`). Read-only viewers get a plain disabled
 * field and no suggestion request is made.
 */
export function SoapSuggestionInput({
  field,
  value,
  onChange,
  disabled,
  multiline = true,
  rows,
  "aria-label": ariaLabel,
}: {
  field: SuggestionFieldKey;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  multiline?: boolean;
  rows?: number;
  "aria-label"?: string;
}) {
  const { data: learned } = useSoapSuggestions(field, !disabled);
  const suggestions = useMemo(
    () => mergeSuggestions(learned ?? [], STATIC_SOAP_SUGGESTIONS[field]),
    [learned, field]
  );
  return (
    <SuggestionInput
      value={value}
      onChange={onChange}
      suggestions={suggestions}
      multiline={multiline}
      rows={rows}
      disabled={disabled}
      aria-label={ariaLabel}
      className={multiline ? "mt-1" : undefined}
    />
  );
}
