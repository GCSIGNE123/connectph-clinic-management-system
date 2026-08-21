"use client";

import type { ComponentType } from "react";
import { Bell } from "lucide-react";
import { cn } from "@/lib/utils";

export interface NotificationBellProps {
  /** Unread count to display as a badge - see `TopNav.tsx` for how this is
   * wired to the real `/messages/unread-count` endpoint. */
  count?: number;
  /** Phase 3: lets a second bell instance (inventory expiry alerts) use a
   * distinct icon from the default Messages bell, so the two are visually
   * distinguishable at a glance. Defaults to the original bell icon. */
  icon?: ComponentType<{ className?: string; "aria-hidden"?: boolean | "true" | "false" }>;
}

/**
 * Bell icon + unread-count badge. Purely presentational - the caller
 * decides what wraps it (a `<Link>` in `TopNav.tsx`) and where the count
 * comes from.
 */
export function NotificationBell({ count = 0, icon: Icon = Bell }: NotificationBellProps) {
  const hasUnread = count > 0;

  return (
    <span className="relative inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground">
      <Icon className="h-4 w-4" aria-hidden="true" />
      {hasUnread ? (
        <span
          className={cn(
            "absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold text-destructive-foreground"
          )}
        >
          {count > 9 ? "9+" : count}
        </span>
      ) : null}
    </span>
  );
}
