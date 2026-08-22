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

/** Same interpretation → color mapping as `VARIANT_BY_INTERPRETATION`,
 * expressed as plain text color classes for `InterpretationText` below -
 * one shared semantic source, two renderings (pill vs. compact text). */
const TEXT_CLASS_BY_INTERPRETATION: Record<LaboratoryInterpretation, string> = {
  Low: "text-destructive",
  High: "text-destructive",
  Abnormal: "text-destructive",
  Normal: "text-green-700 dark:text-green-500",
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

/** Compact plain-text rendering of the exact same interpretation semantics
 * as `InterpretationBadge` (same labels, same icon-not-color-alone rule) -
 * for the printed Laboratory Report, where a full dashboard-style pill per
 * row wastes paper. Renders nothing (blank cell) when there's no
 * interpretation, matching the printed report's "leave it blank rather
 * than fabricate" requirement - unlike `InterpretationBadge`, which shows
 * an explicit "Not configured" label for on-screen use. */
export function InterpretationText({ value }: { value: LaboratoryInterpretation | null | undefined }) {
  if (!value) return null;
  return <span className={TEXT_CLASS_BY_INTERPRETATION[value]}>{LABEL_BY_INTERPRETATION[value]}</span>;
}
