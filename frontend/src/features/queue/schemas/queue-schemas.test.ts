import { describe, expect, it } from "vitest";
import { newQueueSchema } from "./queue-schemas";
import { QueuePriority, VisitClassification } from "@/features/queue/types";

function validPayload(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    patientId: "11111111-1111-1111-1111-111111111111",
    branchId: "22222222-2222-2222-2222-222222222222",
    departmentId: "33333333-3333-3333-3333-333333333333",
    serviceId: "44444444-4444-4444-4444-444444444444",
    priority: QueuePriority.Normal,
    visitClassification: VisitClassification.Regular,
    ...overrides,
  };
}

describe("newQueueSchema", () => {
  it("accepts a valid minimal payload", () => {
    const result = newQueueSchema.safeParse(validPayload());
    expect(result.success).toBe(true);
  });

  it("rejects a missing patient", () => {
    const result = newQueueSchema.safeParse(validPayload({ patientId: "" }));
    expect(result.success).toBe(false);
  });

  it("rejects a missing branch", () => {
    const result = newQueueSchema.safeParse(validPayload({ branchId: "" }));
    expect(result.success).toBe(false);
  });

  it("rejects a missing department", () => {
    const result = newQueueSchema.safeParse(validPayload({ departmentId: "" }));
    expect(result.success).toBe(false);
  });

  it("rejects a missing service", () => {
    const result = newQueueSchema.safeParse(validPayload({ serviceId: "" }));
    expect(result.success).toBe(false);
  });

  it("allows an empty doctorId (any available doctor)", () => {
    const result = newQueueSchema.safeParse(validPayload({ doctorId: "" }));
    expect(result.success).toBe(true);
  });

  it("rejects an invalid priority value", () => {
    const result = newQueueSchema.safeParse(validPayload({ priority: "Urgent" }));
    expect(result.success).toBe(false);
  });
});
