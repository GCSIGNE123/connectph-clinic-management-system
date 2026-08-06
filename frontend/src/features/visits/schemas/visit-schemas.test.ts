import { describe, expect, it } from "vitest";
import { visitFilterSchema, editVisitSchema, visitStatusUpdateSchema } from "./visit-schemas";
import { VisitPriority, VisitStatus, VisitType } from "@/features/visits/types";

describe("visitFilterSchema", () => {
  it("accepts an empty filter set (no filters applied)", () => {
    const result = visitFilterSchema.safeParse({});
    expect(result.success).toBe(true);
  });

  it("accepts a valid combination of filters", () => {
    const result = visitFilterSchema.safeParse({
      search: "Juan",
      status: VisitStatus.Waiting,
      visitType: VisitType.WalkIn,
      doctorId: "11111111-1111-1111-1111-111111111111",
      departmentId: "22222222-2222-2222-2222-222222222222",
      dateFrom: "2026-07-01",
      dateTo: "2026-07-26",
    });
    expect(result.success).toBe(true);
  });

  it("rejects an invalid status value", () => {
    const result = visitFilterSchema.safeParse({ status: "InProgress" });
    expect(result.success).toBe(false);
  });

  it("rejects an invalid visit type value", () => {
    const result = visitFilterSchema.safeParse({ visitType: "DriveThru" });
    expect(result.success).toBe(false);
  });
});

describe("editVisitSchema", () => {
  it("accepts a partial update payload", () => {
    const result = editVisitSchema.safeParse({ priority: VisitPriority.Emergency });
    expect(result.success).toBe(true);
  });

  it("rejects remarks over the max length", () => {
    const result = editVisitSchema.safeParse({ remarks: "x".repeat(1001) });
    expect(result.success).toBe(false);
  });
});

describe("visitStatusUpdateSchema", () => {
  it("accepts a valid status transition payload", () => {
    const result = visitStatusUpdateSchema.safeParse({ status: VisitStatus.Called, note: "Calling patient" });
    expect(result.success).toBe(true);
  });

  it("rejects an invalid status value", () => {
    const result = visitStatusUpdateSchema.safeParse({ status: "Unknown" });
    expect(result.success).toBe(false);
  });

  it("rejects a note over the max length", () => {
    const result = visitStatusUpdateSchema.safeParse({ status: VisitStatus.Called, note: "x".repeat(501) });
    expect(result.success).toBe(false);
  });
});
