import { describe, expect, it } from "vitest";
import { COMMON_MEDICINES, validatePrescriptionItems, type PrescriptionItemInput } from "./types";

function item(overrides: Partial<PrescriptionItemInput> = {}): PrescriptionItemInput {
  return { medicine: "Amoxicillin", dosage: "500mg", frequency: "TID", duration: "7 days", substitutionAllowed: true, ...overrides };
}

describe("validatePrescriptionItems", () => {
  it("returns no warnings for a clean, complete list of items", () => {
    const warnings = validatePrescriptionItems([item(), item({ medicine: "Paracetamol" })]);
    expect(warnings).toEqual([]);
  });

  it("flags a missing dosage", () => {
    const warnings = validatePrescriptionItems([item({ dosage: undefined })]);
    expect(warnings.some((w) => w.includes("Missing dosage"))).toBe(true);
  });

  it("flags a missing duration", () => {
    const warnings = validatePrescriptionItems([item({ duration: undefined })]);
    expect(warnings.some((w) => w.includes("Missing duration"))).toBe(true);
  });

  it("flags duplicate medicines case-insensitively", () => {
    const warnings = validatePrescriptionItems([item({ medicine: "Amoxicillin" }), item({ medicine: "amoxicillin" })]);
    expect(warnings.some((w) => w.includes("Duplicate medicine"))).toBe(true);
  });

  it("never blocks - always returns an array, even with many issues at once", () => {
    const warnings = validatePrescriptionItems([
      item({ medicine: "X", dosage: undefined, duration: undefined }),
      item({ medicine: "X", dosage: undefined, duration: undefined }),
    ]);
    expect(warnings.length).toBeGreaterThan(0);
    expect(Array.isArray(warnings)).toBe(true);
  });

  it("ignores empty item lists", () => {
    expect(validatePrescriptionItems([])).toEqual([]);
  });
});

describe("COMMON_MEDICINES autocomplete filtering", () => {
  function filter(query: string) {
    return COMMON_MEDICINES.filter((m) => m.toLowerCase().includes(query.trim().toLowerCase()));
  }

  it("matches a case-insensitive substring", () => {
    expect(filter("amox")).toContain("Amoxicillin");
    expect(filter("AMOX")).toContain("Amoxicillin");
  });

  it("returns no matches for an unrelated query, allowing free text entry", () => {
    expect(filter("zzzznotarealmedicine")).toEqual([]);
  });

  it("the list is non-empty and contains common Philippine-clinic medicines", () => {
    expect(COMMON_MEDICINES.length).toBeGreaterThan(15);
    expect(COMMON_MEDICINES).toContain("Paracetamol");
  });
});
