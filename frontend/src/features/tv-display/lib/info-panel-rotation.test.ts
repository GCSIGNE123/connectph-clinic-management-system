import { describe, expect, it } from "vitest";
import { getRotationIndex } from "./info-panel-rotation";
import type { TvInfoContentItem } from "@/features/tv-display/types";

function item(overrides: Partial<TvInfoContentItem> & { id: string; durationSeconds: number }): TvInfoContentItem {
  return {
    title: "Title",
    body: "Body",
    contentType: "Announcement",
    displayOrder: 0,
    isActive: true,
    imageUrl: null,
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("getRotationIndex", () => {
  it("returns -1 for an empty info panel", () => {
    expect(getRotationIndex([], 5000)).toBe(-1);
  });

  it("returns the single item's index for the whole rotation when there's only one active item", () => {
    const items = [item({ id: "a", durationSeconds: 10 })];
    expect(getRotationIndex(items, 0)).toBe(0);
    expect(getRotationIndex(items, 9999)).toBe(0);
    expect(getRotationIndex(items, 50_000)).toBe(0);
  });

  it("advances to the next item once the current item's duration elapses", () => {
    const items = [item({ id: "a", durationSeconds: 10 }), item({ id: "b", durationSeconds: 5 })];
    expect(getRotationIndex(items, 0)).toBe(0);
    expect(getRotationIndex(items, 9_999)).toBe(0);
    expect(getRotationIndex(items, 10_000)).toBe(1);
    expect(getRotationIndex(items, 14_999)).toBe(1);
  });

  it("wraps back to the first item after a full cycle", () => {
    const items = [item({ id: "a", durationSeconds: 10 }), item({ id: "b", durationSeconds: 5 })];
    // total cycle = 15s
    expect(getRotationIndex(items, 15_000)).toBe(0);
    expect(getRotationIndex(items, 25_000)).toBe(1);
    expect(getRotationIndex(items, 30_000)).toBe(0);
  });

  it("respects each item's own duration_seconds, not a fixed interval", () => {
    const items = [
      item({ id: "a", durationSeconds: 3 }),
      item({ id: "b", durationSeconds: 20 }),
      item({ id: "c", durationSeconds: 3 }),
    ];
    expect(getRotationIndex(items, 2_999)).toBe(0);
    expect(getRotationIndex(items, 3_000)).toBe(1);
    expect(getRotationIndex(items, 22_999)).toBe(1);
    expect(getRotationIndex(items, 23_000)).toBe(2);
  });
});
