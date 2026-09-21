import { describe, expect, it } from "vitest";
import { STATIC_SOAP_SUGGESTIONS, mergeSuggestions, type SuggestionFieldKey } from "./soap-vocabulary";

describe("soap-vocabulary (Task #2)", () => {
  it("covers exactly the approved suggestion fields", () => {
    expect(Object.keys(STATIC_SOAP_SUGGESTIONS).sort()).toEqual(
      [
        "chief_complaint", "physical_examination", "clinical_findings", "clinical_impression", "differential_diagnosis",
        "treatment_plan", "patient_instructions", "followup_recommendation", "icd10_code", "icd10_description",
      ].sort()
    );
  });

  it("has starter phrases for every SOAP field and NO bundled ICD-10 catalog", () => {
    for (const [field, list] of Object.entries(STATIC_SOAP_SUGGESTIONS) as [SuggestionFieldKey, string[]][]) {
      if (field.startsWith("icd10")) expect(list).toEqual([]);
      else expect(list.length).toBeGreaterThan(0);
    }
  });

  it("keeps the starter phrases short, unique and free of identifiers / long narratives", () => {
    for (const list of Object.values(STATIC_SOAP_SUGGESTIONS)) {
      expect(new Set(list.map((s) => s.toLowerCase())).size).toBe(list.length);
      for (const s of list) {
        expect(s.length).toBeLessThanOrEqual(60);
        expect(s).not.toMatch(/@|https?:|www\.|\d{7,}/);
        expect(s).not.toMatch(/\n/);
      }
    }
  });

  it("mergeSuggestions puts learned values first and drops case-insensitive duplicates", () => {
    const merged = mergeSuggestions(["Headache", "Hip pain"], ["fever", "HEADACHE", "Cough"]);
    expect(merged).toEqual(["Headache", "Hip pain", "fever", "Cough"]);
  });

  it("mergeSuggestions ignores blanks and works with no learned values", () => {
    expect(mergeSuggestions([], ["A", " ", "a", "B"])).toEqual(["A", "B"]);
    expect(mergeSuggestions([], [])).toEqual([]);
  });
});
