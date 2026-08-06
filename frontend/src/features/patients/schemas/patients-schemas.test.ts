import { describe, expect, it } from "vitest";
import { createPatientSchema } from "./patients-schemas";
import { PatientCivilStatus, PatientGender } from "@/features/patients/types";

function validPayload(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    firstName: "Juan",
    lastName: "Dela Cruz",
    birthDate: "1990-01-01",
    gender: PatientGender.Male,
    civilStatus: PatientCivilStatus.Single,
    nationality: "Filipino",
    mobileNumber: "+639171234567",
    ...overrides,
  };
}

describe("createPatientSchema", () => {
  it("accepts a valid minimal payload", () => {
    const result = createPatientSchema.safeParse(validPayload());
    expect(result.success).toBe(true);
  });

  it("rejects a missing first name", () => {
    const result = createPatientSchema.safeParse(validPayload({ firstName: "" }));
    expect(result.success).toBe(false);
  });

  it("rejects an invalid mobile number", () => {
    const result = createPatientSchema.safeParse(validPayload({ mobileNumber: "abc" }));
    expect(result.success).toBe(false);
  });

  it("rejects a future birth date", () => {
    const future = new Date();
    future.setFullYear(future.getFullYear() + 1);
    const result = createPatientSchema.safeParse(
      validPayload({ birthDate: future.toISOString().slice(0, 10) })
    );
    expect(result.success).toBe(false);
  });

  it("rejects a missing gender", () => {
    const result = createPatientSchema.safeParse(validPayload({ gender: "Alien" }));
    expect(result.success).toBe(false);
  });
});
