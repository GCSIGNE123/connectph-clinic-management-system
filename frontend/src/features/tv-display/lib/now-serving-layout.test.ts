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
    expect(layout.cardClassName).toContain("p-[0.6cqw]");
  });
});
