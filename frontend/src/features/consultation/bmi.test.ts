import { describe, expect, it } from "vitest";
import { computeBmi } from "./bmi";

describe("computeBmi", () => {
  it("computes BMI from height/weight matching the backend formula", () => {
    expect(computeBmi(170, 70)).toBeCloseTo(24.22, 2);
    expect(computeBmi(160, 64)).toBeCloseTo(25.0, 2);
  });

  it("returns null when height or weight is missing or invalid", () => {
    expect(computeBmi(null, 70)).toBeNull();
    expect(computeBmi(170, null)).toBeNull();
    expect(computeBmi(0, 70)).toBeNull();
    expect(computeBmi(undefined, undefined)).toBeNull();
  });
});
