import { describe, expect, it } from "vitest";
import { splitPrimaryNowServing } from "./now-serving-primary";
import type { TvDisplayNowServing } from "@/features/tv-display/types";

function entry(overrides: Partial<TvDisplayNowServing>): TvDisplayNowServing {
  return {
    queueId: "id",
    queueNumber: "A001",
    patientInitials: "AA",
    doctorName: null,
    departmentId: null,
    departmentName: null,
    roomName: null,
    status: "Called",
    calledAt: null,
    visitClassification: "Regular",
    ...overrides,
  };
}

describe("splitPrimaryNowServing", () => {
  it("keeps a single ticket per destination entirely as primary", () => {
    const { primary, overflow } = splitPrimaryNowServing([
      entry({ queueId: "1", doctorName: "Aurora Canora" }),
      entry({ queueId: "2", departmentName: "Laboratory" }),
    ]);
    expect(primary).toHaveLength(2);
    expect(overflow).toHaveLength(0);
  });

  it("demotes all but the most recently called ticket for the same doctor", () => {
    const { primary, overflow } = splitPrimaryNowServing([
      entry({ queueId: "1", queueNumber: "A005", doctorName: "Aurora Canora", calledAt: "2026-08-11T00:00:00Z" }),
      entry({ queueId: "2", queueNumber: "A006", doctorName: "Aurora Canora", calledAt: "2026-08-11T00:05:00Z" }),
      entry({ queueId: "3", queueNumber: "A007", doctorName: "Aurora Canora", calledAt: "2026-08-11T00:02:00Z" }),
    ]);
    expect(primary).toHaveLength(1);
    expect(primary[0].queueNumber).toBe("A006"); // latest calledAt
    expect(overflow.map((e) => e.queueNumber).sort()).toEqual(["A005", "A007"]);
  });

  it("treats each destination independently", () => {
    const { primary, overflow } = splitPrimaryNowServing([
      entry({ queueId: "1", queueNumber: "A005", doctorName: "Aurora Canora", calledAt: "2026-08-11T00:00:00Z" }),
      entry({ queueId: "2", queueNumber: "A006", doctorName: "Aurora Canora", calledAt: "2026-08-11T00:05:00Z" }),
      entry({ queueId: "3", queueNumber: "L001", departmentName: "Laboratory", calledAt: "2026-08-11T00:01:00Z" }),
    ]);
    expect(primary.map((e) => e.queueNumber).sort()).toEqual(["A006", "L001"]);
    expect(overflow.map((e) => e.queueNumber)).toEqual(["A005"]);
  });

  it("returns empty arrays for empty input", () => {
    expect(splitPrimaryNowServing([])).toEqual({ primary: [], overflow: [] });
  });

  it("falls back gracefully when calledAt is null for every ticket in a group", () => {
    const { primary, overflow } = splitPrimaryNowServing([
      entry({ queueId: "1", queueNumber: "A005", doctorName: "Aurora Canora", calledAt: null }),
      entry({ queueId: "2", queueNumber: "A006", doctorName: "Aurora Canora", calledAt: null }),
    ]);
    expect(primary).toHaveLength(1);
    expect(overflow).toHaveLength(1);
  });
});
