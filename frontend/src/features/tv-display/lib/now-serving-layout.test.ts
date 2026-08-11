import { describe, expect, it } from "vitest";
import { getNowServingLayout } from "./now-serving-layout";

const BASE = "text-6xl md:text-7xl lg:[font-size:clamp(3rem,6vw,7rem)]";

describe("getNowServingLayout", () => {
  it("centers a single ticket as one large card using the admin's configured font size", () => {
    const layout = getNowServingLayout(1, BASE);
    expect(layout.gridClassName).toContain("justify-center");
    expect(layout.numberSizeClassName).toBe(BASE);
  });

  it("uses a roomy grid and the admin's configured font size for 2-4 tickets", () => {
    const layout = getNowServingLayout(4, BASE);
    expect(layout.gridClassName).toContain("grid");
    expect(layout.numberSizeClassName).toBe(BASE);
  });

  it("uses a moderate (non-admin) font size for 5-8 tickets so two rows fit without cropping", () => {
    const layout = getNowServingLayout(8, BASE);
    expect(layout.gridClassName).toContain("grid");
    expect(layout.numberSizeClassName).not.toBe(BASE);
  });

  it("switches to a denser grid and a compact (non-admin) font size at 9+ tickets", () => {
    const layout = getNowServingLayout(9, BASE);
    expect(layout.gridClassName).toContain("2xl:grid-cols-6");
    expect(layout.numberSizeClassName).not.toBe(BASE);
  });

  it("stays in the dense tier for very high ticket counts (e.g. 14)", () => {
    const layout = getNowServingLayout(14, BASE);
    expect(layout.gridClassName).toContain("2xl:grid-cols-6");
    expect(layout.cardClassName).toContain("p-[0.35cqw]");
  });

  it("shrinks the secondary (initials/detail) text and line spacing progressively across tiers, not just the queue number", () => {
    const low = getNowServingLayout(4, BASE);
    const moderate = getNowServingLayout(8, BASE);
    const compact = getNowServingLayout(14, BASE);
    // 1-4 tickets uses the largest, fixed secondary sizes.
    expect(low.initialsSizeClassName).toBe("text-[clamp(1rem,4.5cqw,2rem)]");
    expect(low.lineSpacingClassName).toBe("mt-2");
    // 5-8 and 9+ each get their own, smaller secondary sizes and tighter
    // line spacing - previously these lines were the same size at every
    // tier, which contributed to the grid genuinely overflowing its
    // available height at realistic multi-department ticket counts.
    expect(moderate.initialsSizeClassName).not.toBe(low.initialsSizeClassName);
    expect(moderate.detailSizeClassName).not.toBe(low.detailSizeClassName);
    expect(compact.initialsSizeClassName).not.toBe(moderate.initialsSizeClassName);
    expect(compact.detailSizeClassName).not.toBe(moderate.detailSizeClassName);
    expect(compact.lineSpacingClassName).toBe("mt-0.5");
  });
});
