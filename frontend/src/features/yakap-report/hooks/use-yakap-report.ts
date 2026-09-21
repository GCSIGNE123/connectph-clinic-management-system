"use client";

import { useQuery } from "@tanstack/react-query";
import { yakapReportApi } from "@/features/yakap-report/api/yakap-report-api";
import type { YakapReportParams } from "@/features/yakap-report/types";

export const yakapReportKeys = {
  report: (params: YakapReportParams) => ["billing", "yakap-report", params] as const,
};

/** Server-side YAKAP billing report (summary + one page of invoice rows). A custom
 * period is only queried once both dates are chosen. */
export function useYakapReport(params: YakapReportParams) {
  const customReady = params.period !== "custom" || Boolean(params.start && params.end);
  return useQuery({
    queryKey: yakapReportKeys.report(params),
    queryFn: () => yakapReportApi.get(params),
    enabled: customReady,
    placeholderData: (prev) => prev,
  });
}
