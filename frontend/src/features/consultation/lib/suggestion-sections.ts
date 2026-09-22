import type { SuggestionSection } from "@/features/clinical-orders/components/SuggestionInput";

/**
 * Task #2 enhancement: build the Doctor's grouped suggestion list. Order (highest priority
 * first) is My phrases -> Recently used -> Clinic suggestions -> Starters. A phrase appears
 * once, in the highest section that has it (case-insensitive), and each section is kept
 * short so the list stays quick to scan. Nothing is ever taken from another SOAP field: the
 * caller passes only this field's lists.
 */
export const SECTION_LIMITS = { mine: 5, recent: 5, clinic: 5, starters: 4 } as const;

export function buildSuggestionSections(lists: {
  mine: string[];
  recent: string[];
  clinic: string[];
  starters: string[];
}): SuggestionSection[] {
  const seen = new Set<string>();
  const take = (items: string[]) => {
    const out: string[] = [];
    for (const s of items) {
      const key = s.trim().toLowerCase();
      if (!key || seen.has(key)) continue;
      seen.add(key);
      out.push(s);
    }
    return out;
  };
  const sections: SuggestionSection[] = [
    { id: "mine", label: "My phrases", items: take(lists.mine), limit: SECTION_LIMITS.mine },
    { id: "recent", label: "Recently used", items: take(lists.recent), limit: SECTION_LIMITS.recent },
    { id: "clinic", label: "Clinic suggestions", items: take(lists.clinic), limit: SECTION_LIMITS.clinic },
    { id: "starters", label: "Starters", items: take(lists.starters), limit: SECTION_LIMITS.starters },
  ];
  return sections.filter((s) => s.items.length > 0);
}
