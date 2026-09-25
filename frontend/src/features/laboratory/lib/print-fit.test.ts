import { afterEach, describe, expect, it, vi } from "vitest";
import {
  PAGE_MARGIN_MM,
  computeFitZoom,
  currentPaperSize,
  fitReportToOnePage,
  printableAreaPx,
  resetReportFit,
} from "./print-fit";

describe("printableAreaPx", () => {
  it("is the sheet minus the 12mm @page margins on every side", () => {
    expect(PAGE_MARGIN_MM).toBe(12);
    const letter = printableAreaPx("Letter")!;
    expect(letter.width).toBeCloseTo(((215.9 - 24) * 96) / 25.4, 1); // ~725px
    expect(letter.height).toBeCloseTo(((279.4 - 24) * 96) / 25.4, 1); // ~965px
    const a4 = printableAreaPx("A4")!;
    expect(a4.height).toBeCloseTo(((297 - 24) * 96) / 25.4, 1); // ~1032px
    expect(a4.height).toBeGreaterThan(letter.height);
    expect(printableAreaPx("HalfLetter")!.height).toBeLessThan(letter.height);
  });

  it("has no page to fit for a continuous thermal roll", () => {
    expect(printableAreaPx("Thermal80mm")).toBeNull();
  });
});

describe("computeFitZoom", () => {
  it("leaves a report that already fits at 100%", () => {
    expect(computeFitZoom(700, 965)).toBe(1);
    expect(computeFitZoom(0, 965)).toBe(1);
  });

  it("scales a too-tall report down so it lands inside one page (with a little slack)", () => {
    const zoom = computeFitZoom(1200, 965);
    expect(zoom).toBeLessThan(1);
    expect(1200 * zoom).toBeLessThanOrEqual(965);
    expect(1200 * zoom).toBeGreaterThan(965 * 0.9); // no needless over-shrinking
  });

  it("never shrinks below a readable floor, and ignores bad input", () => {
    expect(computeFitZoom(100000, 965)).toBe(0.5);
    expect(computeFitZoom(NaN, 965)).toBe(1);
    expect(computeFitZoom(1200, 0)).toBe(1);
    expect(computeFitZoom(1200, Infinity)).toBe(1);
  });
});

function buildPrintRoot(naturalHeight: number) {
  document.body.innerHTML = `<div id="laboratory-report-print-root"><div id="laboratory-report-body"></div></div>`;
  const root = document.getElementById("laboratory-report-print-root") as HTMLElement;
  const body = root.querySelector("#laboratory-report-body") as HTMLElement;
  // jsdom has no layout: report the natural height, and capture the style the
  // root had at the moment of measurement (it must be laid out off-screen at the printable width).
  const seen: { style?: string } = {};
  body.getBoundingClientRect = () => {
    seen.style = root.getAttribute("style") ?? "";
    return { height: naturalHeight } as DOMRect;
  };
  const store = new Map<string, string>();
  body.style.setProperty = (k: string, v: string) => void store.set(k, v);
  body.style.removeProperty = (k: string) => (store.delete(k), "");
  body.style.getPropertyValue = (k: string) => store.get(k) ?? "";
  return { root, body, seen };
}

describe("fitReportToOnePage", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("scales a report that is taller than one page and measures it at the real printable width", () => {
    const { root, body, seen } = buildPrintRoot(1300);
    const zoom = fitReportToOnePage(root, "Letter");
    expect(zoom).toBeLessThan(1);
    expect(Number(body.style.getPropertyValue("zoom"))).toBeCloseTo(zoom, 5);
    expect(seen.style).toMatch(/position:\s*absolute/);
    expect(seen.style).toMatch(/visibility:\s*hidden/);
    expect(seen.style).toMatch(/width: 72\d\.\d+px/); // Letter printable width, ~725px
    // the temporary measuring style is removed again
    expect(root.getAttribute("style")).toBeNull();
  });

  it("leaves a report that already fits completely untouched", () => {
    const { root, body } = buildPrintRoot(800);
    expect(fitReportToOnePage(root, "Letter")).toBe(1);
    expect(body.style.getPropertyValue("zoom")).toBe("");
  });

  it("uses the selected paper: the same report fits A4 but is scaled on Letter", () => {
    const { root: letterRoot } = buildPrintRoot(990);
    expect(fitReportToOnePage(letterRoot, "Letter")).toBeLessThan(1);
    const { root: a4Root } = buildPrintRoot(990);
    expect(fitReportToOnePage(a4Root, "A4")).toBe(1);
  });

  it("does nothing for a thermal roll or when the report body is missing", () => {
    const { root } = buildPrintRoot(5000);
    expect(fitReportToOnePage(root, "Thermal80mm")).toBe(1);
    document.body.innerHTML = `<div id="laboratory-report-print-root"></div>`;
    expect(fitReportToOnePage(document.getElementById("laboratory-report-print-root")!, "Letter")).toBe(1);
  });

  it("re-measures from an unscaled state, so calling it twice does not compound the zoom", () => {
    const { root, body } = buildPrintRoot(1300);
    const first = fitReportToOnePage(root, "Letter");
    const second = fitReportToOnePage(root, "Letter");
    expect(second).toBeCloseTo(first, 5);
    expect(Number(body.style.getPropertyValue("zoom"))).toBeCloseTo(first, 5);
  });

  it("preserves a pre-existing inline style on the root", () => {
    const { root } = buildPrintRoot(1300);
    root.setAttribute("style", "color: red;");
    fitReportToOnePage(root, "Letter");
    expect(root.getAttribute("style")).toBe("color: red;");
  });

  it("resetReportFit removes the scaling after printing", () => {
    const { root, body } = buildPrintRoot(1300);
    fitReportToOnePage(root, "Letter");
    expect(body.style.getPropertyValue("zoom")).not.toBe("");
    resetReportFit(root);
    expect(body.style.getPropertyValue("zoom")).toBe("");
  });
});

describe("currentPaperSize", () => {
  afterEach(() => {
    document.body.innerHTML = "";
    vi.restoreAllMocks();
  });

  it("reads the paper size the print dialog has selected, defaulting to Letter", () => {
    document.body.innerHTML = `<div id="x" data-paper-size="A4"></div>`;
    expect(currentPaperSize("x")).toBe("A4");
    document.body.innerHTML = `<div id="x" data-paper-size="bogus"></div>`;
    expect(currentPaperSize("x")).toBe("Letter");
    document.body.innerHTML = "";
    expect(currentPaperSize("x")).toBe("Letter");
  });
});
