import { describe, expect, it } from "vitest";
import { cn, getInitials, formatDate, assertNever } from "./utils";

describe("cn", () => {
  it("merges class names and resolves tailwind conflicts", () => {
    expect(cn("px-2", "px-4")).toBe("px-4");
  });

  it("handles conditional class values", () => {
    expect(cn("base", false && "hidden", "visible")).toBe("base visible");
  });
});

describe("getInitials", () => {
  it("returns initials from a full name", () => {
    expect(getInitials("Jane Doe")).toBe("JD");
  });

  it("returns first two letters for a single word name", () => {
    expect(getInitials("Cher")).toBe("CH");
  });

  it("returns empty string for empty input", () => {
    expect(getInitials("   ")).toBe("");
  });
});

describe("formatDate", () => {
  it("formats an ISO date string", () => {
    const result = formatDate("2026-07-23T00:00:00.000Z");
    expect(result).toContain("2026");
  });
});

describe("assertNever", () => {
  it("throws when called", () => {
    // @ts-expect-error intentionally passing a value for the exhaustiveness check
    expect(() => assertNever("unexpected")).toThrow();
  });
});
