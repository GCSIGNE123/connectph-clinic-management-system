import type { LaboratoryOrder, LaboratoryResult } from "@/features/laboratory/types";

/** Phase 4G: one printable row per template parameter, carrying every
 * matching `LaboratoryResult` (usually exactly one - MORE than one only
 * for a `requiresSite` parameter like KOH Mount, where each site's result
 * shares the same `parameterName` but must stay visually distinct, never
 * collapsed/overwritten - see `upsert_results`' no-uniqueness-constraint
 * storage this relies on). Never test-name-specific: driven entirely by
 * `order.template.parameters` (already `display_order`-sorted by the
 * backend relationship) and matched to `order.results` purely by
 * `parameterName` (case-insensitive), the same convention
 * `_apply_resolved_range_to_result` uses server-side. */
export interface LaboratoryReportRow {
  parameterName: string;
  section: string | null;
  results: LaboratoryResult[];
}

export function buildReportRows(order: LaboratoryOrder): LaboratoryReportRow[] {
  const resultsByName = new Map<string, LaboratoryResult[]>();
  for (const result of order.results) {
    const key = result.parameterName.trim().toLowerCase();
    const existing = resultsByName.get(key);
    if (existing) {
      existing.push(result);
    } else {
      resultsByName.set(key, [result]);
    }
  }

  if (order.template) {
    return order.template.parameters
      .map((parameter) => ({
        parameterName: parameter.parameterName,
        section: parameter.section ?? null,
        results: resultsByName.get(parameter.parameterName.trim().toLowerCase()) ?? [],
      }))
      .filter((row) => row.results.length > 0);
  }

  // Untemplated order (test_type matched no active template): no template
  // means no defined order/section to respect - list results exactly as
  // stored, one row each, no section grouping invented.
  return order.results.map((result) => ({
    parameterName: result.parameterName,
    section: null,
    results: [result],
  }));
}

/** Contiguous grouping by `section` - identical convention to
 * `ResultEntryDialog`'s `groupBySection`: a section header is only shown
 * once per contiguous run, and a template with no sections at all (CBC,
 * Blood Typing) produces a single unheaded group. */
export function groupReportRowsBySection(
  rows: LaboratoryReportRow[]
): { section: string | null; rows: LaboratoryReportRow[] }[] {
  const groups: { section: string | null; rows: LaboratoryReportRow[] }[] = [];
  for (const row of rows) {
    const last = groups[groups.length - 1];
    if (last && last.section === row.section) {
      last.rows.push(row);
    } else {
      groups.push({ section: row.section, rows: [row] });
    }
  }
  return groups;
}

/** Type-aware value rendering, driven entirely by `resultType` - never a
 * parameter/test-name check. Titer/Microscopy render from `textValue`
 * exactly like Text (Phase 4E: neither has a dedicated storage shape).
 * Categorical reads the Phase 3 `{"value": ...}` convention. Returns null
 * (never "-") when a result exists but genuinely has no value to show -
 * the caller decides how to represent that, e.g. Blank. */
export function reportResultValue(result: LaboratoryResult): string | null {
  switch (result.resultType) {
    case "Numeric":
      return result.numericValue === null ? null : String(result.numericValue);
    case "Categorical":
      return (result.structuredValue?.value as string | undefined) ?? null;
    case "Text":
    case "Titer":
    case "Microscopy":
    default:
      return result.textValue ?? null;
  }
}
