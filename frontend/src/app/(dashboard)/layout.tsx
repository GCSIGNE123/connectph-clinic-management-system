import type { ReactNode } from "react";
import { DashboardShell } from "@/components/layout/DashboardShell";

/**
 * Protected layout for all /dashboard/* routes. The actual redirect-if-
 * unauthenticated check happens in src/middleware.ts (cookie presence
 * check); this layout focuses on rendering the authenticated app shell.
 */
export default function DashboardLayout({ children }: { children: ReactNode }) {
  return <DashboardShell>{children}</DashboardShell>;
}
