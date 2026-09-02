import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { PrintableDocumentDialog } from "./PrintableDocumentDialog";

// Client request: a caller can opt a printed document into a default
// "Save as PDF" filename by passing `printFilename` - the browser derives
// its suggested filename from `document.title` at print time (there is no
// dedicated filename API), so this component temporarily swaps
// `document.title`, prints, then restores it via the `afterprint` event.
// Every existing caller that omits the prop must keep behaving exactly as
// before (plain `window.print()`, `document.title` never touched).
describe("PrintableDocumentDialog print filename (printFilename prop)", () => {
  const originalTitle = document.title;

  afterEach(() => {
    document.title = originalTitle;
    vi.restoreAllMocks();
  });

  it("omitting printFilename leaves document.title completely untouched (existing Receipt/Queue Slip/Prescription/Referral/Lab Request behavior)", () => {
    document.title = "Some Existing Page Title";
    vi.spyOn(window, "print").mockImplementation(() => {});

    render(
      <PrintableDocumentDialog open onOpenChange={() => {}} title="Prescription" printableId="rx-printable">
        <p>content</p>
      </PrintableDocumentDialog>
    );
    screen.getByRole("button", { name: /^print$/i }).click();

    expect(window.print).toHaveBeenCalledTimes(1);
    expect(document.title).toBe("Some Existing Page Title");
  });

  it("providing printFilename sets document.title to it (stripped of any .pdf extension) before calling window.print()", () => {
    document.title = "Some Existing Page Title";
    let titleDuringPrint: string | null = null;
    vi.spyOn(window, "print").mockImplementation(() => {
      titleDuringPrint = document.title;
    });

    render(
      <PrintableDocumentDialog
        open
        onOpenChange={() => {}}
        title="Laboratory Report"
        printableId="laboratory-report-printable"
        printFilename="Paul_Test-0007.pdf"
      >
        <p>content</p>
      </PrintableDocumentDialog>
    );
    screen.getByRole("button", { name: /^print$/i }).click();

    expect(window.print).toHaveBeenCalledTimes(1);
    // The .pdf extension is stripped before assigning to document.title -
    // the browser appends its own, so passing it through unchanged would
    // suggest "Paul_Test-0007.pdf.pdf".
    expect(titleDuringPrint).toBe("Paul_Test-0007");
  });

  it("restores the original document.title after the print job ends (afterprint), regardless of print/save/cancel", () => {
    document.title = "Some Existing Page Title";
    vi.spyOn(window, "print").mockImplementation(() => {});

    render(
      <PrintableDocumentDialog
        open
        onOpenChange={() => {}}
        title="Laboratory Report"
        printableId="laboratory-report-printable"
        printFilename="Paul_Test-0007.pdf"
      >
        <p>content</p>
      </PrintableDocumentDialog>
    );
    screen.getByRole("button", { name: /^print$/i }).click();
    expect(document.title).toBe("Paul_Test-0007");

    window.dispatchEvent(new Event("afterprint"));
    expect(document.title).toBe("Some Existing Page Title");
  });

  it("printFilename passed as already-extensionless still works (no double-strip issue)", () => {
    vi.spyOn(window, "print").mockImplementation(() => {});
    render(
      <PrintableDocumentDialog
        open
        onOpenChange={() => {}}
        title="Laboratory Report"
        printableId="laboratory-report-printable"
        printFilename="Richard_Test-0002"
      >
        <p>content</p>
      </PrintableDocumentDialog>
    );
    screen.getByRole("button", { name: /^print$/i }).click();
    expect(document.title).toBe("Richard_Test-0002");
  });
});
