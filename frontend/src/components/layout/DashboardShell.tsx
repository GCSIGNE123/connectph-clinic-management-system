"use client";

import * as React from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { TopNav } from "@/components/layout/TopNav";
import { cn } from "@/lib/utils";

export interface DashboardShellProps {
  children: React.ReactNode;
  clinicName?: string;
}

/**
 * Combines the sidebar and top navigation into the authenticated dashboard
 * layout shell. Manages sidebar collapse (desktop) and open/close (mobile)
 * state.
 */
export function DashboardShell({ children, clinicName }: DashboardShellProps) {
  const [collapsed, setCollapsed] = React.useState(false);
  const [mobileOpen, setMobileOpen] = React.useState(false);

  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar
        collapsed={collapsed}
        onToggleCollapsed={() => setCollapsed((prev) => !prev)}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />

      <div className={cn("flex min-h-screen w-full flex-1 flex-col")}>
        <TopNav onMenuClick={() => setMobileOpen(true)} clinicName={clinicName} />
        <main className="flex-1 p-4 sm:p-6">{children}</main>
      </div>
    </div>
  );
}
