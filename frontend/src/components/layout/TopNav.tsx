"use client";

import { useRouter } from "next/navigation";
import { Menu, Search, Stethoscope } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { NotificationBell } from "@/components/layout/NotificationBell";
import { UserMenu } from "@/components/layout/UserMenu";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { useUnreadByConversation, useUnreadMessageCount } from "@/features/messages/hooks/use-messages";

export interface TopNavProps {
  onMenuClick?: () => void;
  clinicName?: string;
}

/**
 * Top navigation bar: clinic branding, a search placeholder (no real
 * search wired up yet), and account/notification/theme controls.
 */
export function TopNav({ onMenuClick, clinicName = "CONNECT.PH Clinic Platform" }: TopNavProps) {
  // Client Acceptance Revisions - Round 2 (MEDIUM item 4): the Receptionist
  // <-> Doctor messaging feature already had a working `GET
  // /messages/unread-count` endpoint and a polling hook
  // (`useUnreadMessageCount`, 30s interval) - only the visible badge was
  // missing. Wires the existing (until now unused-in-the-nav)
  // `NotificationBell` placeholder to that real count and links it to the
  // Messages page, rather than adding a new toast/sound system.
  const { data: unreadCount } = useUnreadMessageCount();
  // Item 6: clicking the bell must jump straight into the actual unread
  // conversation(s) instead of a plain link to `/messages` that dumps the
  // user on the "Select a staff member" picker. `useUnreadByConversation`
  // (new `/messages/unread-by-conversation` endpoint) gives us the actual
  // conversation partner(s) with unread messages.
  const { data: unreadConversations } = useUnreadByConversation();
  const router = useRouter();

  const handleOpenConversation = (otherUserId: string) => {
    router.push(`/messages?with=${otherUserId}`);
  };

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-border bg-background/95 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/75">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="lg:hidden"
        aria-label="Toggle sidebar"
        onClick={onMenuClick}
      >
        <Menu className="h-5 w-5" aria-hidden="true" />
      </Button>

      <div className="flex items-center gap-2 font-semibold text-foreground">
        <span className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <Stethoscope className="h-4 w-4" aria-hidden="true" />
        </span>
        <span className="hidden truncate sm:inline">{clinicName}</span>
      </div>

      <div className="ml-2 hidden flex-1 max-w-md items-center gap-2 md:flex">
        <div className="relative w-full">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            type="search"
            placeholder="Search (coming soon)"
            className="pl-8"
            disabled
            aria-label="Search"
          />
        </div>
      </div>

      <div className="ml-auto flex items-center gap-1">
        <DropdownMenu>
          <DropdownMenuTrigger>
            <button
              type="button"
              aria-label={unreadCount ? `${unreadCount} unread messages` : "Messages"}
            >
              <NotificationBell count={unreadCount ?? 0} />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-72">
            <DropdownMenuLabel>Messages</DropdownMenuLabel>
            {unreadConversations && unreadConversations.length > 0 ? (
              unreadConversations.map((c) => (
                <DropdownMenuItem key={c.otherUserId} onClick={() => handleOpenConversation(c.otherUserId)}>
                  <span className="flex w-full items-center justify-between gap-2">
                    <span className="truncate">{c.otherUserName ?? "Staff member"}</span>
                    <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold text-destructive-foreground">
                      {c.unreadCount > 9 ? "9+" : c.unreadCount}
                    </span>
                  </span>
                </DropdownMenuItem>
              ))
            ) : (
              <DropdownMenuItem onClick={() => router.push("/messages")}>No unread messages</DropdownMenuItem>
            )}
            <DropdownMenuItem onClick={() => router.push("/messages")}>View all messages</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <ThemeToggle />
        <UserMenu />
      </div>
    </header>
  );
}
