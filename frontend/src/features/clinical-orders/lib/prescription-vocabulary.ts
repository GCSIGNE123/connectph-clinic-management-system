/**
 * Task #8: data-entry convenience suggestions for prescription fields that
 * have no authoritative catalog in this application (unlike Medicine/
 * Strength/Form, which come from the real `Medicine` inventory catalog -
 * see `PrescriptionTab.tsx`). These are plain UI vocabulary examples for
 * the searchable/free-text suggestion inputs, centralized here once rather
 * than duplicated across components.
 *
 * NOT a clinical recommendation, NOT a controlled vocabulary, and NOT tied
 * to any particular medicine or patient - selecting one is exactly as
 * significant as typing it by hand. The doctor can always type a value
 * that isn't in this list (see `SuggestionInput`); nothing here restricts
 * what a prescription item can say.
 *
 * Deliberately a static frontend list rather than a new clinic-configurable
 * backend table for this pass - the smallest change that satisfies "avoid
 * doctors retyping common values" without a new admin module. If the
 * clinic later wants to edit these without a code change, they belong in
 * the existing per-clinic `system_settings` key/value store (already used
 * for other clinic-level configuration) behind a small settings screen -
 * a natural, separately-scoped follow-up, not part of this change.
 */

export const FREQUENCY_SUGGESTIONS: string[] = [
  "Once daily",
  "Twice daily",
  "Three times daily",
  "Four times daily",
  "Every 4 hours",
  "Every 6 hours",
  "Every 8 hours",
  "Every 12 hours",
  "As needed",
  "At bedtime",
  "Before meals",
  "After meals",
];

export const ROUTE_SUGGESTIONS: string[] = [
  "Oral",
  "Topical",
  "Intravenous",
  "Intramuscular",
  "Subcutaneous",
  "Sublingual",
  "Rectal",
  "Ophthalmic",
  "Otic",
  "Nasal",
  "Inhalation",
];

export const DOSAGE_SUGGESTIONS: string[] = [
  "1 tablet",
  "2 tablets",
  "1/2 tablet",
  "1 capsule",
  "2 capsules",
  "5 mL",
  "10 mL",
  "15 mL",
  "1 drop",
  "2 drops",
  "1 puff",
  "1 sachet",
];

export const DURATION_SUGGESTIONS: string[] = [
  "3 days",
  "5 days",
  "7 days",
  "10 days",
  "14 days",
  "1 month",
  "Until finished",
  "Ongoing/maintenance",
];
