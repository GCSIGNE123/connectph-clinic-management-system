/**
 * Task #2: small STATIC starter vocabulary for the SOAP suggestion fields,
 * following the Task #8 pattern (`features/clinical-orders/lib/prescription-vocabulary.ts`).
 *
 * Generic documentation phrases only - NOT a clinical recommendation, NOT a
 * controlled vocabulary or ICD catalog, no patient data, and no canned SOAP
 * narratives. Selecting one is exactly as significant as typing it by hand;
 * the doctor can always edit it or write something completely different.
 * The clinic's own learned suggestions (`GET /consultations/soap-suggestions`)
 * always come first, ahead of these.
 *
 * ICD-10 code/description have no static list on purpose (no invented ICD
 * catalog) - they are learned from the clinic's own diagnoses only.
 */

export type SoapSuggestField =
  | "chief_complaint"
  | "physical_examination"
  | "clinical_findings"
  | "clinical_impression"
  | "differential_diagnosis"
  | "treatment_plan"
  | "patient_instructions"
  | "followup_recommendation";

export type DiagnosisSuggestField = "icd10_code" | "icd10_description";

export type SuggestionFieldKey = SoapSuggestField | DiagnosisSuggestField;

export const STATIC_SOAP_SUGGESTIONS: Record<SuggestionFieldKey, string[]> = {
  chief_complaint: [
    "Fever",
    "Cough",
    "Colds",
    "Headache",
    "Sore throat",
    "Abdominal pain",
    "Diarrhea",
    "Vomiting",
    "Dizziness",
    "Body malaise",
    "Chest pain",
    "Difficulty of breathing",
    "Skin rash",
    "Back pain",
    "Painful urination",
  ],
  physical_examination: [
    "Awake, alert, no acute distress",
    "Lungs clear on both sides",
    "Abdomen soft, non-tender",
    "Heart regular rate and rhythm",
    "Throat congested",
    "Nasal congestion",
    "No pallor, no jaundice",
  ],
  clinical_findings: ["No abnormal findings", "Within normal limits", "Tenderness noted", "Erythema noted", "Swelling noted"],
  clinical_impression: [
    "Acute upper respiratory tract infection",
    "Acute pharyngitis",
    "Acute gastroenteritis",
    "Urinary tract infection",
    "Hypertension",
    "Diabetes mellitus",
    "Viral illness",
  ],
  differential_diagnosis: ["Viral infection", "Bacterial infection", "Allergic reaction", "Rule out dengue"],
  treatment_plan: [
    "Rest and hydration",
    "Symptomatic treatment",
    "Medications as prescribed",
    "Laboratory tests requested",
    "Monitor symptoms",
  ],
  patient_instructions: [
    "Take medications as prescribed",
    "Increase oral fluid intake",
    "Get adequate rest",
    "Return if symptoms worsen",
  ],
  followup_recommendation: [
    "Follow up in 1 week",
    "Follow up in 2 weeks",
    "Follow up in 1 month",
    "Follow up after laboratory results",
    "Return if symptoms persist or worsen",
  ],
  icd10_code: [],
  icd10_description: [],
};

/** Learned (clinic) suggestions first, then the static starters, de-duplicated case-insensitively. */
export function mergeSuggestions(learned: string[], starter: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const s of [...learned, ...starter]) {
    const key = s.trim().toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(s);
  }
  return out;
}
