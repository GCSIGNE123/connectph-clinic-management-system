/** Client request: the Laboratory Report's browser Print -> Save as PDF
 * flow should suggest a default filename of
 * "<Patient_Name>-<last 4 digits of Order #>.pdf" (e.g. "Paul Test" /
 * "ORD-20260901-000007" -> "Paul_Test-0007.pdf") instead of whatever the
 * page's own `document.title` happens to be.
 *
 * This module is pure, side-effect-free filename-building logic only - see
 * `PrintableDocumentDialog`'s `printFilename` prop for how it's actually
 * wired into the `window.print()` flow (browsers derive their "Save as
 * PDF" suggested filename from `document.title`, not from any dedicated
 * filename API - there is no other JS-accessible lever for this without
 * replacing the native browser print pipeline with a PDF-generation
 * library, which this deliberately does not do).
 *
 * Deliberately never reads Visit #/Queue # (per the client's explicit
 * "do not use Visit # or Queue # for the filename" instruction) and never
 * mutates the Order # displayed on the report itself - both are read
 * as-is from the same already-fetched `LaboratoryOrder` the report body
 * renders, purely to build a filename string. */

const INVALID_FILENAME_CHARS = /[<>:"/\\|?*\x00-\x1F]/g;

/** Strips characters that are unsafe on Windows and other common
 * filesystems (`< > : " / \ | ? *` plus control characters), then
 * collapses any run of whitespace - a single space or several in a row -
 * into exactly one underscore, matching the client's "replace spaces with
 * underscores" request without producing "Paul___Test" for a
 * multiple-space name. Leading/trailing underscores left over from a name
 * that started/ended with now-stripped characters are trimmed too, so the
 * filename never starts or ends with a stray "_". */
function sanitizeFilenameSegment(input: string): string {
  return input
    .replace(INVALID_FILENAME_CHARS, "")
    .trim()
    .replace(/\s+/g, "_")
    .replace(/^_+|_+$/g, "");
}

/** Order numbers in this app always follow the `ORD-YYYYMMDD-NNNNNN`
 * format (see `OrderNumberGenerator`) - extracting only the digit
 * characters and taking the last 4 of them is equivalent to "the last 4
 * digits of the sequence number" for that format, and degrades gracefully
 * (rather than throwing) for anything else. Leading zeroes are preserved
 * because this stays a string the whole way through - never parsed as a
 * number. Returns "" (not a fabricated "0000") when the order number is
 * null/empty or contains no digits at all - matching this codebase's
 * "never invent a placeholder" convention (see `report.ts`'s own
 * docstrings) - the caller then omits the suffix entirely. */
function last4OrderDigits(orderNumber: string | null | undefined): string {
  const digitsOnly = (orderNumber ?? "").replace(/\D/g, "");
  return digitsOnly.slice(-4);
}

/** Builds the default "Save as PDF" filename for a Laboratory Report:
 * "<Patient_Name>-<last 4 order digits>.pdf", or just "<Patient_Name>.pdf"
 * when no order number/digits are available (never a fabricated "-0000").
 * Falls back to "Laboratory_Report" (never a blank filename) when the
 * patient name itself is missing/empty - a real, permitted case per
 * `LaboratoryOrder.patientName: string | null`. */
export function buildLaboratoryReportFilename(
  patientName: string | null | undefined,
  orderNumber: string | null | undefined
): string {
  const sanitizedName = patientName ? sanitizeFilenameSegment(patientName) : "";
  const namePart = sanitizedName || "Laboratory_Report";
  const last4 = last4OrderDigits(orderNumber);
  return last4 ? `${namePart}-${last4}.pdf` : `${namePart}.pdf`;
}
