"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { usePrintPreferences } from "@/features/print-settings/use-print-settings";
import { PAPER_SIZES, PAPER_SIZE_CSS, PAPER_SIZE_LABELS, PAPER_SIZE_PREVIEW_PX, type PaperSize } from "@/features/print-settings/types";

/**
 * Phase 20 (item 10): generic print-friendly view for Prescription /
 * Laboratory Request / Referral documents - follows the exact same
 * hide-everything-but-#printable + `window.print()` pattern already used
 * by `features/billing/components/ReceiptDialog.tsx` (Phase 10's receipt
 * print) and `features/queue/components/QueueSlipDialog.tsx` (Queue Slip).
 * No PDF-generation library is introduced - `window.print()` with
 * print-specific CSS is the established, scoped-appropriate pattern in
 * this codebase.
 *
 * Client Acceptance Revisions - Round 2 (HIGH item 4: Printer Settings)
 * extended this component, rather than building a new print pipeline, with:
 *   - a paper size selector (defaults to the stored preference from
 *     `/printer-settings`, overridable per document) applied via a real
 *     `@page { size: ... }` print-CSS rule;
 *   - a "preview" affordance - the content area is rendered at an
 *     on-screen size that approximates the chosen paper before the user
 *     ever invokes `window.print()`, so paper-size changes are visible
 *     immediately without opening the OS print dialog;
 *   - a "preferred printer" reminder line sourced from the same stored
 *     preference - shown next to the Print button. As documented in
 *     `features/print-settings/use-print-settings.ts`, a web page cannot
 *     actually choose the OS print dialog's printer (a real browser
 *     security restriction), so this is a labeled reminder, not a
 *     selection mechanism.
 */
export function PrintableDocumentDialog({
  open,
  onOpenChange,
  title,
  printableId,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  printableId: string;
  children: React.ReactNode;
}) {
  const { preferences, setPaperSize } = usePrintPreferences();
  // Per-document override: starts at the stored default but doesn't write
  // back to it unless the user visits Printer Settings - a one-off "print
  // this one on Letter instead" shouldn't silently change the default.
  const [paperSizeOverride, setPaperSizeOverride] = useState<PaperSize | null>(null);
  const paperSize = paperSizeOverride ?? preferences.paperSize;
  const previewDims = PAPER_SIZE_PREVIEW_PX[paperSize];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>

        <div className="flex flex-wrap items-end gap-3 border-b border-border pb-3">
          <div className="space-y-1">
            <Label htmlFor={`${printableId}-paper-size`} className="text-xs">
              Paper size (preview)
            </Label>
            <Select
              id={`${printableId}-paper-size`}
              className="h-8 w-48 text-xs"
              value={paperSize}
              onChange={(e) => setPaperSizeOverride(e.target.value as PaperSize)}
            >
              {PAPER_SIZES.map((size) => (
                <option key={size} value={size}>
                  {PAPER_SIZE_LABELS[size]}
                </option>
              ))}
            </Select>
          </div>
          <button
            type="button"
            className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
            onClick={() => setPaperSize(paperSize)}
          >
            Set as default
          </button>
        </div>

        {/* Print preview: on-screen box sized to approximate the selected
            paper, so a paper-size change is visible before printing. */}
        <div className="flex justify-center overflow-auto rounded-md bg-muted/40 p-4">
          <div
            id={printableId}
            className="space-y-3 overflow-auto border border-border bg-background p-4 text-sm shadow-sm"
            style={{ width: previewDims.width, minHeight: previewDims.minHeight }}
          >
            {children}
          </div>
        </div>

        {preferences.defaultPrinterName ? (
          <p className="text-xs text-muted-foreground">
            Preferred printer: <span className="font-medium">{preferences.defaultPrinterName}</span> - select
            it in the dialog that opens (browsers can&apos;t choose it for you).
          </p>
        ) : null}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          <Button type="button" onClick={() => window.print()}>
            Print
          </Button>
        </DialogFooter>
      </DialogContent>

      <style jsx global>{`
        @media print {
          @page {
            size: ${PAPER_SIZE_CSS[paperSize]};
            margin: 12mm;
          }
          body * {
            visibility: hidden;
          }
          #${printableId},
          #${printableId} * {
            visibility: visible;
          }
          #${printableId} {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: auto;
            min-height: 0;
            border: none;
            box-shadow: none;
          }
        }
      `}</style>
    </Dialog>
  );
}
