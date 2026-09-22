"use client";

import { useMemo } from "react";
import { SuggestionInput } from "@/features/clinical-orders/components/SuggestionInput";
import { PersonalSoapSuggestionInput } from "@/features/consultation/components/PersonalSoapSuggestionInput";
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
function ClassicSoapSuggestionInput({
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

/**
 * Task #2 enhancement: `personal` (Doctor consultation page only) switches the field to the
 * Doctor's My Phrases / Recently used view (`PersonalSoapSuggestionInput`). Without it - and
 * always for Receptionist/Nurse intake and read-only viewers - the classic clinic + starter
 * list above is used unchanged.
 */
export function SoapSuggestionInput(props: {
  field: SuggestionFieldKey;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  multiline?: boolean;
  rows?: number;
  personal?: boolean;
  "aria-label"?: string;
}) {
  const { personal, ...rest } = props;
  if (personal && !rest.disabled) {
    return (
      <PersonalSoapSuggestionInput
        field={rest.field}
        value={rest.value}
        onChange={rest.onChange}
        multiline={rest.multiline}
        rows={rest.rows}
        aria-label={rest["aria-label"]}
      />
    );
  }
  return <ClassicSoapSuggestionInput {...rest} />;
}
