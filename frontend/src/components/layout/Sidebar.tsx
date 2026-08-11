"use client";

import type { ComponentType } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  Building2,
  CalendarClock,
  CalendarDays,
  ChevronLeft,
  ClipboardList,
  LayoutDashboard,
  ListTree,
  Palette,
  Settings,
  Stethoscope,
  Ticket,
  UserCog,
  Users,
  UsersRound,
  FileClock,
  ClipboardCheck,
  Receipt,
  FlaskConical,
  Monitor,
  UploadCloud,
  MessageSquare,
  Printer,
  Volume2,
  Wallet,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { NavItem } from "@/types";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";

/** Phase 12: Owner Dashboard & Reports is Owner/Administrator only - the
 * backend 403s every other role on every `/analytics/*` endpoint, and this
 * nav item is hidden entirely for other roles so a Doctor/Cashier/etc.
 * session never even sees a link to a page it can't use. */
const ANALYTICS_ROLES = new Set(["Owner", "Administrator"]);

/**
 * Primary navigation. Pharmacy is intentionally omitted here (rather than
 * linked to a stub page) because that module is out of scope so far - the
 * only in-scope preview of that work is the "coming soon" tab on the
 * patient profile page. Billing (Phase 12), Laboratory (Phase 10), and
 * Appointments (Phase 11) now have real pages and are linked below.
 */
const NAV_ITEMS: (NavItem & { icon: ComponentType<{ className?: string }> })[] = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Patients", href: "/patients", icon: Users },
  { label: "Appointments", href: "/appointments", icon: CalendarDays },
  { label: "Queue", href: "/queue", icon: UsersRound },
  { label: "Visits", href: "/visits", icon: FileClock },
  { label: "Doctor Workspace", href: "/doctor-workspace", icon: ClipboardCheck },
  { label: "Laboratory", href: "/laboratory", icon: FlaskConical },
  { label: "Billing", href: "/billing", icon: Receipt },
  // Phase 21: Receptionist Shift Management - not role-gated in this list
  // (same pattern as most nav items here); the backend still only lets a
  // Receptionist start/view/close their OWN shift, Owner/Administrator can
  // do the same for anyone's.
  { label: "Shift", href: "/shifts", icon: Wallet },
  // Phase 20 (item 14): minimal Receptionist<->Doctor internal messaging -
  // deliberately not role-gated (any staff member may message any other),
  // same as most of this nav list pre-BUG-017.
  { label: "Messages", href: "/messages", icon: MessageSquare },
  { label: "Users", href: "/users", icon: UserCog },
];

/** Phase 4: Clinic Configuration & Master Data. */
const CONFIG_NAV_ITEMS: (NavItem & { icon: ComponentType<{ className?: string }> })[] = [
  { label: "Clinic Settings", href: "/clinic-settings", icon: Settings },
  { label: "Branches", href: "/branches", icon: Building2 },
  { label: "Departments", href: "/departments", icon: ListTree },
  { label: "Doctors", href: "/doctors", icon: Stethoscope },
  { label: "Doctor Schedules", href: "/doctor-schedules", icon: CalendarClock },
  { label: "Consultation Rooms", href: "/consultation-rooms", icon: ClipboardList },
  { label: "Services", href: "/services", icon: Palette },
  { label: "Queue Settings", href: "/queue-settings", icon: Ticket },
  { label: "Operating Hours", href: "/operating-hours", icon: CalendarClock },
  { label: "Holidays", href: "/holidays", icon: CalendarDays },
  { label: "Laboratory Templates", href: "/laboratory-templates", icon: FlaskConical },
  // Client Acceptance Revisions - Round 2 (HIGH item 4): per-browser
  // preference (paper size + a "preferred printer" reminder label), stored
  // in localStorage - not role-gated, since it's a local device preference
  // any staff member printing documents from that device would want to set.
  { label: "Printer Settings", href: "/printer-settings", icon: Printer },
  // Item 8: same "local device preference, localStorage-backed, not
  // role-gated" pattern as Printer Settings above - voice/rate/volume/
  // enable-disable for the Call/Recall TTS announcements.
  { label: "Queue Announcer", href: "/queue-announcer-settings", icon: Volume2 },
];

export interface SidebarProps {
  collapsed: boolean;
  onToggleCollapsed: () => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}

/**
 * Responsive, collapsible sidebar. On desktop it can collapse to an icon
 * rail; on mobile it slides in as an overlay controlled by `mobileOpen`.
 */
export function Sidebar({ collapsed, onToggleCollapsed, mobileOpen, onCloseMobile }: SidebarProps) {
  const pathname = usePathname();
  const { data: currentUser } = useCurrentUser();
  const canSeeAnalytics = Boolean(currentUser && ANALYTICS_ROLES.has(currentUser.role ?? ""));
  const navItems = canSeeAnalytics
    ? [...NAV_ITEMS, { label: "Owner Dashboard", href: "/analytics", icon: BarChart3 }]
    : NAV_ITEMS;
  // Phase 13: TV Displays administration is Owner/Administrator only,
  // same gate/rationale as the Owner Dashboard above - the backend 403s
  // every /tv-displays* mutation and read for other roles.
  const canSeeTvDisplays = Boolean(currentUser && ANALYTICS_ROLES.has(currentUser.role ?? ""));
  const configNavItems = canSeeTvDisplays
    ? [
        ...CONFIG_NAV_ITEMS,
        { label: "TV Displays", href: "/tv-displays", icon: Monitor },
        { label: "TV Info Panel", href: "/tv-info-content", icon: Monitor },
      ]
    : CONFIG_NAV_ITEMS;
  // Phase 14: Legacy Migration Wizard is Owner/Administrator only, the
  // same strictest gate as Analytics/TV Displays - bulk-importing real
  // clinical data is not something any operational role can trigger.
  const canSeeMigration = Boolean(currentUser && ANALYTICS_ROLES.has(currentUser.role ?? ""));
  const finalConfigNavItems = canSeeMigration
    ? [...configNavItems, { label: "Legacy Migration", href: "/migration", icon: UploadCloud }]
    : configNavItems;

  return (
    <>
      {mobileOpen ? (
        <div
          className="fixed inset-0 z-40 bg-black/40 lg:hidden"
          onClick={onCloseMobile}
          aria-hidden="true"
        />
      ) : null}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex flex-col border-r border-border bg-card transition-all duration-200 ease-in-out",
          "lg:sticky lg:top-0 lg:z-0 lg:h-screen lg:translate-x-0",
          collapsed ? "lg:w-16" : "lg:w-64",
          mobileOpen ? "w-64 translate-x-0" : "w-64 -translate-x-full lg:translate-x-0"
        )}
      >
        <nav className="flex-1 space-y-1 overflow-y-auto p-3">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onCloseMobile}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                  collapsed && "lg:justify-center lg:px-2"
                )}
                title={collapsed ? item.label : undefined}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span className={cn(collapsed && "lg:hidden")}>{item.label}</span>
              </Link>
            );
          })}

          <div className={cn("mt-4 border-t border-border pt-3", collapsed && "lg:mt-2")}>
            <p className={cn("px-3 pb-1 text-xs font-semibold uppercase text-muted-foreground", collapsed && "lg:hidden")}>
              Clinic Configuration
            </p>
            {finalConfigNavItems.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={onCloseMobile}
                  className={cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                    collapsed && "lg:justify-center lg:px-2"
                  )}
                  title={collapsed ? item.label : undefined}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  <span className={cn(collapsed && "lg:hidden")}>{item.label}</span>
                </Link>
              );
            })}
          </div>
        </nav>

        <div className="border-t border-border p-3">
          <button
            type="button"
            onClick={onToggleCollapsed}
            className="hidden w-full items-center justify-center gap-2 rounded-md p-2 text-xs font-medium text-muted-foreground hover:bg-accent lg:flex"
          >
            <ChevronLeft className={cn("h-4 w-4 transition-transform", collapsed && "rotate-180")} />
            <span className={cn(collapsed && "hidden")}>Collapse</span>
          </button>
        </div>
      </aside>
    </>
  );
}
