import { describe, expect, test } from "vitest";
import { groupNowServing, groupWaiting } from "./grouping";
import type { TvDisplayNowServing, TvDisplayWaitingEntry } from "@/features/tv-display/types";

function nowServing(overrides: Partial<TvDisplayNowServing>): TvDisplayNowServing {
  return {
    queueId: "q1",
    queueNumber: "A001",
    patientInitials: "JD",
    doctorName: null,
    departmentId: null,
    departmentName: null,
    roomName: null,
    status: "Called",
    calledAt: "2026-08-09T00:00:00Z",
    ...overrides,
  };
}

function waiting(overrides: Partial<TvDisplayWaitingEntry>): TvDisplayWaitingEntry {
  return {
    queueId: "q2",
    queueNumber: "A002",
    patientInitials: "MS",
    doctorName: null,
    departmentId: null,
    departmentName: null,
    priority: "Normal",
    ...overrides,
  };
}

describe("groupNowServing", () => {
  test("a single-doctor clinic produces exactly one group", () => {
    const groups = groupNowServing([
      nowServing({ queueId: "1", queueNumber: "A001", doctorName: "Mendoza" }),
      nowServing({ queueId: "2", queueNumber: "A002", doctorName: "Mendoza" }),
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0].label).toBe("Dr. Mendoza");
    expect(groups[0].entries).toHaveLength(2);
  });

  test("groups by doctor when multiple doctors are active simultaneously", () => {
    const groups = groupNowServing([
      nowServing({ queueId: "1", queueNumber: "A001", doctorName: "Mendoza" }),
      nowServing({ queueId: "2", queueNumber: "B001", doctorName: "Reyes" }),
    ]);
    expect(groups.map((g) => g.label).sort()).toEqual(["Dr. Mendoza", "Dr. Reyes"]);
  });

  test("falls back to department name for a department-only ticket (e.g. Laboratory)", () => {
    const groups = groupNowServing([
      nowServing({ queueId: "1", queueNumber: "L001", doctorName: null, departmentName: "Laboratory" }),
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0].label).toBe("Laboratory");
  });

  test("mixed doctors and department-only tickets produce separate groups", () => {
    const groups = groupNowServing([
      nowServing({ queueId: "1", queueNumber: "A001", doctorName: "Mendoza" }),
      nowServing({ queueId: "2", queueNumber: "B001", doctorName: "Reyes" }),
      nowServing({ queueId: "3", queueNumber: "L001", doctorName: null, departmentName: "Laboratory" }),
      nowServing({ queueId: "4", queueNumber: "R001", doctorName: null, departmentName: "Radiology" }),
    ]);
    expect(groups).toHaveLength(4);
  });

  test("falls back to General when neither doctor nor department is present", () => {
    const groups = groupNowServing([nowServing({ queueId: "1" })]);
    expect(groups[0].label).toBe("General");
  });

  test("empty input produces no groups", () => {
    expect(groupNowServing([])).toEqual([]);
  });
});

describe("groupWaiting", () => {
  test("groups next-waiting entries under the same destination key as now-serving", () => {
    const groups = groupWaiting([
      waiting({ queueId: "1", queueNumber: "A003", doctorName: "Mendoza" }),
      waiting({ queueId: "2", queueNumber: "A004", doctorName: "Mendoza" }),
      waiting({ queueId: "3", queueNumber: "L002", departmentName: "Laboratory" }),
    ]);
    expect(groups).toHaveLength(2);
    const mendoza = groups.find((g) => g.label === "Dr. Mendoza");
    expect(mendoza?.entries.map((e) => e.queueNumber)).toEqual(["A003", "A004"]);
  });
});
