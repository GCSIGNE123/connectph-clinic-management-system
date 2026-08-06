"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { usePrintPreferences } from "@/features/print-settings/use-print-settings";
import { PAPER_SIZES, PAPER_SIZE_LABELS, type PaperSize } from "@/features/print-settings/types";

/**
 * Client Acceptance Revisions - Round 2, HIGH item 4: Printer Settings.
 *
 * Deliberately client-only, `localStorage`-backed preferences (no backend
 * model, no migration) - see `features/print-settings/use-print-settings.ts`
 * for the full rationale. Applies immediately to every print-friendly
 * dialog in the app (Prescription / Laboratory Request / Referral via
 * `PrintableDocumentDialog`) without needing a page reload, since those
 * dialogs read the same hook.
 */
export default function PrinterSettingsPage() {
  const { preferences, setPaperSize, setDefaultPrinterName } = usePrintPreferences();

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Printer Settings</h1>
        <p className="text-sm text-muted-foreground">
          These preferences are stored on this browser/device only and apply the next time you print a
          Prescription, Laboratory Request, or Referral.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Paper size</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Label htmlFor="paper-size">Default paper size</Label>
          <Select
            id="paper-size"
            value={preferences.paperSize}
            onChange={(e) => setPaperSize(e.target.value as PaperSize)}
            className="max-w-xs"
          >
            {PAPER_SIZES.map((size) => (
              <option key={size} value={size}>
                {PAPER_SIZE_LABELS[size]}
              </option>
            ))}
          </Select>
          <p className="text-xs text-muted-foreground">
            Applied via print CSS (<code>@page</code>) so the browser&apos;s print/PDF output is sized
            correctly. You can still override this per document from the print preview.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Default printer</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Label htmlFor="default-printer">Preferred printer (label only)</Label>
          <Input
            id="default-printer"
            value={preferences.defaultPrinterName}
            onChange={(e) => setDefaultPrinterName(e.target.value)}
            placeholder="e.g. Front Desk - HP LaserJet M126"
            className="max-w-xs"
          />
          <p className="text-xs text-muted-foreground">
            <strong>Important limitation:</strong> web browsers do not allow a page to programmatically
            choose which physical printer the OS print dialog sends a job to - this is a deliberate browser
            security restriction, not a gap in this app. This field is only a reminder shown next to the
            Print button (e.g. &quot;Preferred printer: Front Desk - HP LaserJet M126&quot;) so staff know
            which printer to select in the native dialog that appears - it does not select a printer for
            you.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
