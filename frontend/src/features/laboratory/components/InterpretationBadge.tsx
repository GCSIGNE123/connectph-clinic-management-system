import { Badge } from "@/components/ui/badge";
import type { LaboratoryInterpretation } from "@/features/laboratory/types";

const VARIANT_BY_INTERPRETATION: Record<LaboratoryInterpretation, "default" | "secondary" | "destructive" | "success" | "outline"> = {
  Low: "destructive",
  High: "destructive",
  Abnormal: "destructive",
  Normal: "success",
};

export const LABEL_BY_INTERPRETATION: Record<LaboratoryInterpretation, string> = {
  Low: "↓ Low",
  High: "↑ High",
  Abnormal: "Abnormal",
  Normal: "✓ Normal",
};

/** Icon + text, never color alone, per spec - keeps the signal legible for
 * colorblind users and in print/grayscale contexts. Renders nothing when
 * there's no interpretation to show (missing/invalid range or value). */
export function InterpretationBadge({ value }: { value: LaboratoryInterpretation | null | undefined }) {
  if (!value) {
    return <span className="text-xs text-muted-foreground">Not configured</span>;
  }
  return <Badge variant={VARIANT_BY_INTERPRETATION[value]}>{LABEL_BY_INTERPRETATION[value]}</Badge>;
}

/** Printed-report FLAG column (clinic's existing paper-report convention):
 * a bare, red "L"/"H" for a numeric result outside its persisted range, or
 * nothing at all - never the full word, an icon, or a checkmark. Reuses
 * the exact same persisted `interpretation` this file's other components
 * read (never recalculated) - this is purely a different rendering of the
 * same stored semantics, not a new range/clinical calculation.
 *
 * `Normal` and the non-directional `Abnormal` (from a qualitative Text
 * result that doesn't match its configured expected-normal value) both
 * render blank: the FLAG column's only allowed characters are H, L, or
 * blank, and `Abnormal` has no "above/below" direction to map to either
 * one - printing blank rather than guessing a direction was confirmed as
 * the intended behavior over silently mislabeling it. */
const FLAG_BY_INTERPRETATION: Partial<Record<LaboratoryInterpretation, "L" | "H">> = {
  Low: "L",
  High: "H",
};

export function FlagText({ value }: { value: LaboratoryInterpretation | null | undefined }) {
  const flag = value ? FLAG_BY_INTERPRETATION[value] : undefined;
  if (!flag) return null;
  return <span className="font-semibold text-destructive">{flag}</span>;
}
