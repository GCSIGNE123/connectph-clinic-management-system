import { Badge } from "@/components/ui/badge";
import type { LaboratoryInterpretation, LaboratoryResultType } from "@/features/laboratory/types";

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
 * a bare, colored single character for a result outside/against its
 * persisted normal, or nothing at all - never the full word, an icon, or
 * a checkmark. Reuses the exact same persisted `interpretation` this
 * file's other components read (never recalculated) - this is purely a
 * different rendering of the same stored semantics, not a new range/
 * clinical calculation.
 *
 * `Normal` always renders blank, for every result type. `Abnormal` (the
 * non-directional interpretation - no "above/below" a numeric range to
 * report) is direction-less by nature, so it can't reuse L/H; it splits
 * by `resultType` instead:
 *   - Categorical (e.g. HBsAg Positive/Negative, and every other
 *     Positive/Negative qualitative test) -> "A", per product decision:
 *     a Positive categorical result is clinically significant enough to
 *     warrant its own flag character, distinct from H/L, which stay
 *     reserved for numeric direction only.
 *   - Text (free-text qualitative results not backed by a fixed option
 *     list) -> still blank, unchanged from the original "confirmed"
 *     Round 4 behavior - no compelling reason surfaced to revisit that
 *     established convention for this result kind. */
const FLAG_BY_INTERPRETATION: Partial<Record<LaboratoryInterpretation, "L" | "H" | "A">> = {
  Low: "L",
  High: "H",
  Abnormal: "A",
};

/** Round 7 (flag colors): L (below range) reads as an urgent/low-value
 * signal - red/`text-destructive`, the same token already used everywhere
 * else in this app for "needs attention". H (above range) is deliberately
 * NOT red - a single "everything abnormal is red" color would make L and H
 * visually indistinguishable at a glance, so H uses the existing blue
 * `text-primary` token (info/high-value semantic) instead. Only the flag
 * character itself carries color - see `LaboratoryReportView.tsx`'s Flag
 * `<td>`, which wraps nothing else in this span. A (categorical abnormal)
 * reuses the same urgent `text-destructive` token as L - a Positive
 * qualitative result is a "needs attention" signal, not an informational
 * one like H. */
const FLAG_COLOR_CLASS: Record<"L" | "H" | "A", string> = {
  L: "text-destructive",
  H: "text-primary",
  A: "text-destructive",
};

export function FlagText({
  value,
  resultType,
}: {
  value: LaboratoryInterpretation | null | undefined;
  /** Only Categorical's `Abnormal` maps to "A" - Text's `Abnormal` stays
   * blank, preserving the original Round 4 convention for that result
   * kind untouched. Numeric never produces `Abnormal` in the first place
   * (see `interpret_result`), so this only ever disambiguates those two. */
  resultType: LaboratoryResultType;
}) {
  const effectiveValue = value === "Abnormal" && resultType !== "Categorical" ? undefined : value;
  const flag = effectiveValue ? FLAG_BY_INTERPRETATION[effectiveValue] : undefined;
  if (!flag) return null;
  return <span className={`font-semibold ${FLAG_COLOR_CLASS[flag]}`}>{flag}</span>;
}
