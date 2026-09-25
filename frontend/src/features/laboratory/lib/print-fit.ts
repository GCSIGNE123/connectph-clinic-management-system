/**
 * One-page laboratory report printing.
 *
 * Every laboratory report (any template, any number of parameters, with or
 * without the hand-signed countersigning Med Tech block) must print on ONE
 * page. The report body is laid out normally and its natural height is
 * measured at the printable width of the selected paper; if it is taller than
 * one printable page it is scaled down (CSS `zoom`, which - unlike
 * `transform` - shrinks the layout box itself, so the browser sees a shorter
 * document and never creates a second page). A report that already fits is
 * left at 100%. Nothing is ever clipped or hidden.
 *
 * Page geometry must stay in sync with `PrintableDocumentDialog`'s
 * `@page { size: <paper>; margin: 12mm; }` rule.
 */

export type FitPaperSize = "A4" | "Letter" | "HalfLetter" | "Thermal80mm";

/** Same 12mm margin `PrintableDocumentDialog` puts in its `@page` rule. */
export const PAGE_MARGIN_MM = 12;
const PX_PER_MM = 96 / 25.4;

/** Sheet size in mm (portrait). Thermal rolls have no fixed page height. */
const PAPER_MM: Record<Exclude<FitPaperSize, "Thermal80mm">, { width: number; height: number }> = {
  A4: { width: 210, height: 297 },
  Letter: { width: 215.9, height: 279.4 },
  HalfLetter: { width: 139.7, height: 215.9 },
};

/** Printable (inside the margins) page area in CSS px, or null for a
 * continuous roll (Thermal80mm), where there is no page to fit into. */
export function printableAreaPx(paper: FitPaperSize): { width: number; height: number } | null {
  if (paper === "Thermal80mm") return null;
  const sheet = PAPER_MM[paper];
  if (!sheet) return null;
  return {
    width: (sheet.width - 2 * PAGE_MARGIN_MM) * PX_PER_MM,
    height: (sheet.height - 2 * PAGE_MARGIN_MM) * PX_PER_MM,
  };
}

/** A little slack so sub-pixel rounding / font metrics can never spill a
 * last line onto a second page. */
const FIT_SAFETY = 0.96;
/** Below this the text would be unreadably small - never scale further. */
const MIN_ZOOM = 0.5;

/** Zoom factor (<= 1) that makes `naturalHeight` fit in `availableHeight`. */
export function computeFitZoom(naturalHeight: number, availableHeight: number): number {
  if (!Number.isFinite(naturalHeight) || !Number.isFinite(availableHeight)) return 1;
  if (naturalHeight <= 0 || availableHeight <= 0) return 1;
  const target = availableHeight * FIT_SAFETY;
  if (naturalHeight <= target) return 1;
  return Math.max(MIN_ZOOM, target / naturalHeight);
}

const BODY_SELECTOR = "#laboratory-report-body";

/** Scales the report inside `root` (the portaled print root) so it fits one
 * printable page of `paper`. Returns the zoom applied (1 = untouched). Safe to
 * call repeatedly - it always re-measures from an unscaled state. */
export function fitReportToOnePage(root: HTMLElement, paper: FitPaperSize): number {
  const body = root.querySelector<HTMLElement>(BODY_SELECTOR);
  const area = printableAreaPx(paper);
  if (!body || !area) return 1;

  body.style.removeProperty("zoom");

  // The print root is `display: none` on screen: lay it out off-screen at the
  // real printable width so the measurement reflects what will print.
  const previousStyle = root.getAttribute("style");
  root.style.cssText +=
    `;display:flex;flex-direction:column;position:absolute;left:-100000px;top:0;` +
    `width:${area.width}px;min-height:0;visibility:hidden;`;
  const naturalHeight = body.getBoundingClientRect().height;
  if (previousStyle === null) root.removeAttribute("style");
  else root.setAttribute("style", previousStyle);

  const zoom = computeFitZoom(naturalHeight, area.height);
  if (zoom < 1) body.style.setProperty("zoom", String(zoom));
  return zoom;
}

/** Undoes `fitReportToOnePage` (called after printing). */
export function resetReportFit(root: HTMLElement): void {
  root.querySelector<HTMLElement>(BODY_SELECTOR)?.style.removeProperty("zoom");
}

/** Reads the paper size the shared print dialog currently has selected. */
export function currentPaperSize(printableId: string): FitPaperSize {
  const value = document.getElementById(printableId)?.getAttribute("data-paper-size");
  return value === "A4" || value === "Letter" || value === "HalfLetter" || value === "Thermal80mm" ? value : "Letter";
}
