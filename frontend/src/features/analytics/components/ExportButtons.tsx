"use client";

import { useState } from "react";
import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { analyticsApi } from "@/features/analytics/api/analytics-api";
import type { ReportFilters, ReportKey } from "@/features/analytics/types";

export interface ExportButtonsProps {
  report: ReportKey;
  filters: ReportFilters;
  onError?: (message: string) => void;
}

/** CSV works as a real download; Excel piggybacks on the same
 * CSV-compatible endpoint (see backend `export_report` docstring/decision);
 * PDF is an explicit, disabled "Coming soon" per the spec's "do not
 * implement PDF styling yet" exclusion - the backend also 501s it. */
export function ExportButtons({ report, filters, onError }: ExportButtonsProps) {
  const [busy, setBusy] = useState<"csv" | "excel" | null>(null);

  const handleExport = async (format: "csv" | "excel") => {
    setBusy(format);
    try {
      await analyticsApi.exportReport(report, format, filters);
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Export failed");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <Button type="button" variant="outline" size="sm" disabled={busy !== null} onClick={() => handleExport("csv")}>
        <Download className="mr-1.5 h-3.5 w-3.5" />
        {busy === "csv" ? "Exporting..." : "Export CSV"}
      </Button>
      <Button type="button" variant="outline" size="sm" disabled={busy !== null} onClick={() => handleExport("excel")}>
        <Download className="mr-1.5 h-3.5 w-3.5" />
        {busy === "excel" ? "Exporting..." : "Export Excel"}
      </Button>
      <Button type="button" variant="outline" size="sm" disabled title="PDF export is not implemented yet">
        Export PDF (Coming soon)
      </Button>
    </div>
  );
}
