/**
 * Client Acceptance Revisions - Round 2, HIGH item 4: Printer Settings.
 *
 * There is deliberately NO backend model / migration for this feature. A web
 * page cannot programmatically choose which physical printer the OS print
 * dialog sends a job to - that's a real browser security boundary (see the
 * module doc on `use-print-settings.ts`), so "default printer" here is
 * stored, per-browser, as a *preference the user is reminded of*, not a
 * mechanism that actually selects a printer. Paper size, on the other hand,
 * genuinely can be applied via print CSS `@page` rules, so that part is a
 * real functional setting.
 */

export const PAPER_SIZES = ["A4", "Letter", "HalfLetter", "Thermal80mm"] as const;
export type PaperSize = (typeof PAPER_SIZES)[number];

export const PAPER_SIZE_LABELS: Record<PaperSize, string> = {
  A4: "A4 (210 x 297 mm)",
  Letter: "Letter (8.5 x 11 in)",
  // Client Acceptance Revisions - Round 3 (item 8): standard prescription
  // pad size (half of US Letter, 8.5 x 5.5in) - the common real-world size
  // for a physical Rx pad. Added here rather than a one-off value baked
  // into the Prescription print view, so it's a normal, reusable paper
  // size choice like the others.
  HalfLetter: "Half Letter / Prescription pad (5.5 x 8.5 in)",
  Thermal80mm: "Thermal receipt (80mm roll)",
};

/** `@page { size: ... }` value for each paper size. Thermal receipt rolls
 * have no fixed length, so only the width is constrained - `auto` lets the
 * printer/browser paginate to content height. */
export const PAPER_SIZE_CSS: Record<PaperSize, string> = {
  A4: "A4",
  // Explicit "portrait" (Letter is already portrait by default without it)
  // per the Laboratory Report redesign spec, which requires the literal
  // `@page { size: Letter portrait; }` rule to appear in the print CSS.
  Letter: "Letter portrait",
  HalfLetter: "5.5in 8.5in",
  Thermal80mm: "80mm auto",
};

/** Approximate on-screen preview dimensions (px, at a fixed 96dpi-ish scale)
 * used purely to render a "this is roughly what will print" preview box -
 * not an exact physical simulation. */
export const PAPER_SIZE_PREVIEW_PX: Record<PaperSize, { width: number; minHeight: number }> = {
  A4: { width: 380, minHeight: 537 },
  Letter: { width: 380, minHeight: 492 },
  HalfLetter: { width: 320, minHeight: 494 },
  Thermal80mm: { width: 220, minHeight: 320 },
};

export interface PrintPreferences {
  paperSize: PaperSize;
  /** Free-text label of the printer the user intends to use. This is a
   * *reminder/preference only* - see the module doc above. */
  defaultPrinterName: string;
}

export const DEFAULT_PRINT_PREFERENCES: PrintPreferences = {
  paperSize: "A4",
  defaultPrinterName: "",
};
